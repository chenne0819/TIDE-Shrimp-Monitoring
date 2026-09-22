"""Durable queue worker: python -m app.worker [--once] [--inbox PATH]."""
import argparse
from datetime import timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

import imageio_ffmpeg
from sqlalchemy import select, update
from .config import Settings, app_path
from .database import Job, Track, Worker, init_database, make_engine, make_session_factory, utcnow
from .results import read_results
from .storage import VIDEO_EXTENSIONS, clean_filename, parse_recorded_at, safe_path

LOG = logging.getLogger("tide.worker")
MODULES = {"general": "general_track.run_track", "head_tail": "general_track.run_head_tail_track", "predict": "predict.run_predict"}


class LostLease(RuntimeError):
    pass


class QueueWorker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = make_engine(settings.database_url)
        self.sessions = make_session_factory(self.engine)
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"[:100]
        self.last_pulse = 0.0
        init_database(self.engine)
        settings.storage_root.mkdir(parents=True, exist_ok=True)

    def heartbeat(self, job_id: str | None = None, progress: int | None = None, force=False):
        if not force and time.monotonic() - self.last_pulse < 5:
            return
        now = utcnow()
        with self.sessions() as db:
            worker = db.get(Worker, self.worker_id)
            if worker is None:
                worker = Worker(id=self.worker_id, heartbeat_at=now)
                db.add(worker)
            worker.heartbeat_at, worker.status, worker.current_job_id = now, "busy" if job_id else "idle", job_id
            if job_id:
                values = {"lease_until": now + timedelta(seconds=self.settings.lease_seconds), "updated_at": now}
                if progress is not None:
                    values["progress"] = progress
                changed = db.execute(update(Job).where(Job.id == job_id, Job.status == "processing", Job.worker_id == self.worker_id).values(**values))
                if changed.rowcount != 1:
                    raise LostLease("Job ownership was lost; this process will not publish results.")
            db.commit()
        self.last_pulse = time.monotonic()

    def claim(self):
        self.heartbeat(force=True)
        now = utcnow()
        with self.sessions() as db:
            # A stale attempt is failed for explicit retry, never run twice automatically.
            stale = db.scalars(select(Job).where(Job.status == "processing", Job.lease_until < now).with_for_update(skip_locked=True)).all()
            for job in stale:
                job.status, job.error = "failed", "處理程序已中斷或失去心跳，請重新執行此分析。"
                job.worker_id, job.lease_until, job.updated_at = None, None, now
            job = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1).with_for_update(skip_locked=True))
            if job is None:
                db.commit()
                return None
            job.status, job.progress, job.worker_id = "processing", 3, self.worker_id
            job.attempts += 1
            job.lease_until, job.updated_at = now + timedelta(seconds=self.settings.lease_seconds), now
            job.error = None
            job_id = job.id
            db.commit()  # Release queue locks before model loading / subprocess execution.
            return job_id

    def command(self, command, job_id, log_path, *, cwd=None, timeout=None):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg"})
        started = time.monotonic()
        with log_path.open("wb") as log:
            child = subprocess.Popen([str(part) for part in command], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, shell=False)
            try:
                while child.poll() is None:
                    self.heartbeat(job_id)
                    if time.monotonic() - started > (timeout or self.settings.analyzer_timeout_seconds):
                        raise TimeoutError("影片處理超過設定的最長時間")
                    time.sleep(0.25)
                if child.returncode:
                    tail = log_path.read_bytes()[-6000:].decode("utf-8", errors="replace")
                    raise RuntimeError(f"Subprocess exited with code {child.returncode}. Log: {log_path.name}\n{tail}")
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()

    def transcode(self, source: Path, destination: Path, job_id: str, log_path: Path):
        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-y", "-i", source, "-map", "0:v:0",
                   "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", "-progress", "pipe:1", destination]
        self.command(command, job_id, log_path)
        frames = 0
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("frame=") and line[6:].strip().isdigit():
                frames = max(frames, int(line[6:].strip()))
        if not destination.is_file() or destination.stat().st_size == 0 or frames == 0:
            raise RuntimeError("影片沒有可解碼的影格")
        return frames

    def process(self, job_id):
        with self.sessions() as db:
            job = db.get(Job, job_id)
            source = safe_path(self.settings.storage_root, job.source_path)
            attempt = self.settings.storage_root / "jobs" / job_id / f"attempt-{job.attempts}-{uuid4().hex[:8]}"
            mode, max_frames, water_policy = job.mode, job.max_frames, job.water_policy
            source_browser_path = job.source_browser_path
        attempt.mkdir(parents=True)
        try:
            if not self.settings.analyzer_root.is_dir() or not self.settings.analyzer_python.is_file():
                raise RuntimeError("找不到分析專案或 Python；請設定 ANALYZER_ROOT / ANALYZER_PYTHON。")
            self.heartbeat(job_id, 8, force=True)
            if not source_browser_path or not safe_path(self.settings.storage_root, source_browser_path).is_file():
                source_browser = attempt / "source.mp4"
                self.transcode(source, source_browser, job_id, attempt / "source-ffmpeg.log")
                thumbnail = attempt / "thumbnail.jpg"
                self.command([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-y", "-i", source_browser,
                              "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", thumbnail], job_id, attempt / "thumbnail.log")
                with self.sessions() as db:
                    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                    self.assert_owner(job)
                    job.source_browser_path = source_browser.relative_to(self.settings.storage_root).as_posix()
                    job.thumbnail_path = thumbnail.relative_to(self.settings.storage_root).as_posix()
                    db.commit()
            self.heartbeat(job_id, 20, force=True)
            output = attempt / "analysis"
            command = [self.settings.analyzer_python, "-m", MODULES[mode], "--video", source,
                       "--output-root", output, "--monitoring", "--water-policy", water_policy]
            if max_frames:
                command += ["--max-frames", str(max_frames)]
            self.command(command, job_id, attempt / "analyzer.log", cwd=self.settings.analyzer_root)
            self.heartbeat(job_id, 85, force=True)
            result = read_results(output)
            result_video = None
            if result["video"] and result["status"] != "stopped":
                result_video = attempt / "result.mp4"
                frames = self.transcode(result["video"], result_video, job_id, attempt / "result-ffmpeg.log")
                result["processed_frames"] = result["processed_frames"] or frames
            elif result["status"] != "stopped":
                raise RuntimeError("分析完成但沒有輸出影片")
            result["metadata"].update({"mode": mode, "max_frames": max_frames, "water_policy": water_policy,
                                       "progress_note": "進度表示處理階段，並非已分析影格百分比。"})
            public_metadata = attempt / "monitoring.json"
            public_metadata.write_text(json.dumps(result["metadata"], ensure_ascii=False, indent=2), encoding="utf-8")
            result["artifacts"]["monitoring"] = public_metadata
            with self.sessions() as db:
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                self.assert_owner(job)
                job.tracks = [Track(**track) for track in result["tracks"]]
                job.shrimp_count = len(result["tracks"])
                for key in ("status", "water_label", "water_confidence", "avg_length_mm", "avg_width_mm", "avg_weight_g", "processed_frames"):
                    setattr(job, key, result[key])
                job.result_path = result_video.relative_to(self.settings.storage_root).as_posix() if result_video else None
                job.details = result["metadata"]
                job.artifacts = {key: path.relative_to(self.settings.storage_root).as_posix() for key, path in result["artifacts"].items()}
                job.progress, job.updated_at, job.lease_until, job.worker_id = 100, utcnow(), None, None
                db.commit()
            LOG.info("Finished job %s (%s)", job_id, result["status"])
        except BaseException as exc:
            self.fail(job_id, exc)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            self.heartbeat(force=True)

    def assert_owner(self, job):
        if job is None or job.status != "processing" or job.worker_id != self.worker_id:
            raise LostLease("Job ownership was lost")

    def fail(self, job_id, error):
        LOG.exception("Job %s failed: %s", job_id, error)
        # Logs remain private on disk. API error is useful without leaking paths / raw model tracebacks.
        reason = "分析執行失敗，請確認影片、模型及分析環境；詳細資訊在此工作的 analyzer.log / ffmpeg.log。"
        if isinstance(error, TimeoutError):
            reason = str(error)
        elif isinstance(error, KeyboardInterrupt):
            reason = "處理程序已停止，請重新排程分析。"
        with self.sessions() as db:
            db.execute(update(Job).where(Job.id == job_id, Job.status == "processing", Job.worker_id == self.worker_id)
                       .values(status="failed", error=reason, updated_at=utcnow(), worker_id=None, lease_until=None))
            db.commit()

    def close(self):
        with self.sessions() as db:
            db.execute(update(Worker).where(Worker.id == self.worker_id).values(status="offline", heartbeat_at=utcnow(), current_job_id=None))
            db.commit()
        self.engine.dispose()


def ingest_inbox(settings: Settings, sessions, inbox: Path):
    """Only *.mp4.ready (etc.) markers opt completed uploads in; originals are retained."""
    inbox.mkdir(parents=True, exist_ok=True)
    ingested = 0
    for marker in sorted(inbox.glob("*.ready")):
        source = marker.with_suffix("")
        if source.suffix.lower() not in VIDEO_EXTENSIONS or not source.is_file():
            continue
        directory = None
        try:
            metadata_path = source.with_suffix(".json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
            pond = str(metadata.get("pond", "A-01")).strip()
            mode, policy = metadata.get("mode", "general"), metadata.get("water_policy", "report")
            max_frames = metadata.get("max_frames")
            if not pond or len(pond) > 80 or mode not in MODULES or policy not in {"stop", "report"}:
                raise ValueError("Invalid inbox metadata")
            if max_frames is not None and (not isinstance(max_frames, int) or isinstance(max_frames, bool) or max_frames < 1):
                raise ValueError("Invalid max_frames")
            stat = source.stat()
            if not 0 < stat.st_size <= settings.max_upload_bytes:
                raise ValueError("Inbox video is empty or too large")
            # Identical file at the same pathname and timestamp is ingested at most once, even after restart.
            key = hashlib.sha256(f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()
            with sessions() as db:
                if db.scalar(select(Job.id).where(Job.ingest_key == key)):
                    marker.replace(marker.with_suffix(".ingested"))
                    continue
                job_id = str(uuid4())
                directory = settings.storage_root / "jobs" / job_id
                directory.mkdir(parents=True)
                target = directory / f"original{source.suffix.lower()}"
                with source.open("rb") as reader, target.open("wb") as writer:
                    copied = 0
                    while chunk := reader.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > settings.max_upload_bytes:
                            raise ValueError("Inbox video grew beyond upload limit")
                        writer.write(chunk)
                if source.stat().st_size != stat.st_size or source.stat().st_mtime_ns != stat.st_mtime_ns:
                    raise ValueError("Inbox video changed after ready marker")
                job = Job(id=job_id, filename=clean_filename(source.name), pond=pond,
                          recorded_at=parse_recorded_at(metadata.get("recorded_at")), mode=mode, water_policy=policy,
                          max_frames=max_frames, source_path=target.relative_to(settings.storage_root).as_posix(), ingest_key=key)
                db.add(job)
                db.commit()
                directory = None  # Committed data must survive marker rename failures.
                marker.replace(marker.with_suffix(".ingested"))
                ingested += 1
        except Exception as exc:
            LOG.warning("Inbox entry %s was not ingested: %s", marker.name, exc)
            if directory:
                import shutil
                shutil.rmtree(directory, ignore_errors=True)
            marker.with_suffix(".error.txt").write_text(str(exc), encoding="utf-8")
    return ingested


def main():
    parser = argparse.ArgumentParser(description="蝦況 TIDE durable video worker")
    parser.add_argument("--once", action="store_true", help="Scan inbox and process at most one queued job, then exit")
    parser.add_argument("--inbox", help="Watch a directory using video.mp4.ready markers; relative to app root")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    worker = QueueWorker(settings)
    inbox = app_path(args.inbox) if args.inbox else settings.storage_root / "inbox"
    try:
        while True:
            ingest_inbox(settings, worker.sessions, inbox)
            job_id = worker.claim()
            if job_id:
                worker.process(job_id)
            if args.once:
                break
            if not job_id:
                time.sleep(settings.poll_seconds)
    except KeyboardInterrupt:
        LOG.info("Worker stopped")
    finally:
        worker.close()


if __name__ == "__main__":
    main()
