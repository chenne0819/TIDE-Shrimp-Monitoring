from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Annotated, Literal
from uuid import UUID, uuid4
import shutil
import secrets

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .config import Settings
from .database import Job, Track, Worker, init_database, make_engine, make_session_factory, utcnow
from .storage import ARTIFACT_NAMES, TAIPEI, VIDEO_EXTENSIONS, aware, clean_filename, day_bounds, parse_recorded_at, safe_path, video_response
from .security import LocalRequestProtection
from .uploads import UPLOAD_OPENAPI, UploadPayload, receive_upload
from .assistant.routes import router as assistant_router
from .assistant.service import AssistantService


def average(values):
    present = [value for value in values if value is not None]
    return round(mean(present), 3) if present else None


def serialize_job(job: Job):
    prefix = f"/api/jobs/{job.id}"
    return {
        "id": job.id, "filename": job.filename, "pond": job.pond,
        "recorded_at": aware(job.recorded_at).isoformat(), "created_at": aware(job.created_at).isoformat(),
        "status": job.status, "progress": job.progress, "mode": job.mode,
        "water_label": job.water_label, "water_confidence": job.water_confidence,
        "shrimp_count": job.shrimp_count, "avg_length_mm": job.avg_length_mm,
        "avg_width_mm": job.avg_width_mm, "avg_weight_g": job.avg_weight_g,
        "source_video_url": f"{prefix}/video?kind=source" if job.source_browser_path else None,
        "result_video_url": f"{prefix}/video?kind=result" if job.result_path else None,
        "thumbnail_url": f"{prefix}/thumbnail" if job.thumbnail_path else None,
        "error": job.error, "processed_frames": job.processed_frames,
    }


def track_json(track: Track):
    return {key: getattr(track, key) for key in ("track_id", "label", "observations", "length_mm", "width_mm", "weight_g")}


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    assistant = AssistantService(session_factory)

    @asynccontextmanager
    async def lifespan(app):
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        init_database(engine)
        assistant.recover_interrupted()
        try:
            yield
        finally:
            await assistant.close()
            engine.dispose()

    app = FastAPI(title="蝦況 TIDE API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = session_factory
    app.state.assistant = assistant
    csrf_token = secrets.token_urlsafe(32)
    app.add_middleware(LocalRequestProtection, allowed_origins=settings.cors_origins,
                       csrf_token=csrf_token, max_upload_bytes=settings.max_upload_bytes)
    # CORS decorates early security/size errors for the trusted frontend. It does
    # not bypass the inner pre-body protection for mutation requests.
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                       allow_methods=["GET", "HEAD", "POST"], allow_headers=["X-Tide-CSRF", "Content-Type", "Range"],
                       expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts), www_redirect=False)
    csrf_header = APIKeyHeader(name="X-Tide-CSRF", auto_error=False,
                              description="先 GET /api/session，將 csrf_token 貼入此欄。此 token 防止本機跨站請求，不代表使用者登入。")
    app.include_router(assistant_router, dependencies=[Security(csrf_header)])

    def session():
        with session_factory() as db:
            yield db

    Database = Annotated[Session, Depends(session)]

    def find_job(db, job_id):
        job = db.get(Job, str(job_id))
        if job is None:
            raise HTTPException(404, "找不到這筆影片分析")
        return job

    def filters(start_date, end_date, pond):
        start, end = day_bounds(start_date, end_date)
        conditions = []
        if start:
            conditions.append(Job.recorded_at >= start)
        if end:
            conditions.append(Job.recorded_at < end)
        if pond:
            conditions.append(Job.pond == pond)
        return conditions

    @app.get("/api/health")
    def health(db: Database):
        try:
            db.execute(text("SELECT 1"))
            latest = db.scalar(select(Worker).where(Worker.status != "offline").order_by(Worker.heartbeat_at.desc()).limit(1))
            worker = "online" if latest and aware(latest.heartbeat_at) > utcnow() - timedelta(seconds=settings.lease_seconds) else "offline"
            return {"status": "ok", "database": "connected", "worker": worker}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable", "database": "disconnected", "worker": "unknown"})

    @app.get("/api/session")
    def local_session():
        return JSONResponse({"csrf_token": csrf_token, "max_upload_bytes": settings.max_upload_bytes},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/jobs", status_code=202, dependencies=[Security(csrf_header)], openapi_extra=UPLOAD_OPENAPI)
    async def upload(db: Database, payload: Annotated[UploadPayload, Depends(receive_upload)]):
        file = payload.file
        pond, recorded_at, mode, water_policy, max_frames = (
            payload.fields.pond, payload.fields.recorded_at, payload.fields.mode,
            payload.fields.water_policy, payload.fields.max_frames,
        )
        pond = pond.strip()
        if not pond or len(pond) > 80 or any(ord(char) < 32 for char in pond):
            raise HTTPException(422, "池別需為 1 至 80 字元")
        if max_frames is not None and max_frames <= 0:
            raise HTTPException(422, "測試幀數必須大於零")
        timestamp = parse_recorded_at(recorded_at)
        filename = clean_filename(file.filename or "upload")
        suffix = Path(filename).suffix.lower()
        if suffix not in VIDEO_EXTENSIONS:
            raise HTTPException(415, "支援 MP4、MOV、AVI、MKV、WEBM 影片")
        job_id = str(uuid4())
        directory = settings.storage_root / "jobs" / job_id
        directory.mkdir(parents=True)
        path = directory / f"original{suffix}"
        committed = False
        try:
            size = 0
            with path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise HTTPException(413, "影片超過上傳大小限制")
                    target.write(chunk)
            if size == 0:
                raise HTTPException(422, "影片是空檔案")
            job = Job(id=job_id, filename=filename, pond=pond, recorded_at=timestamp,
                      mode=mode, water_policy=water_policy, max_frames=max_frames,
                      source_path=path.relative_to(settings.storage_root).as_posix())
            db.add(job)
            db.commit()
            committed = True
            return serialize_job(job)
        finally:
            # Cancellation must not interrupt removal of an uncommitted copy.
            # receive_upload owns the input spool and closes it synchronously.
            if not committed:
                shutil.rmtree(directory, ignore_errors=True)

    @app.get("/api/jobs")
    def list_jobs(db: Database, start_date: date | None = None, end_date: date | None = None,
                  pond: str | None = None, status: Literal["queued", "processing", "completed", "stopped", "failed"] | None = None,
                  limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        where = filters(start_date, end_date, pond)
        if status:
            where.append(Job.status == status)
        total = db.scalar(select(func.count()).select_from(Job).where(*where))
        jobs = db.scalars(select(Job).where(*where).order_by(Job.created_at.desc()).offset(offset).limit(limit)).all()
        return {"items": [serialize_job(job) for job in jobs], "total": total}

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: UUID, db: Database):
        job = find_job(db, job_id)
        return {**serialize_job(job), "tracks": [track_json(track) for track in job.tracks],
                "metadata": job.details,
                "artifacts": [{"kind": kind, "label": ARTIFACT_NAMES[kind], "url": f"/api/jobs/{job.id}/artifacts/{kind}"}
                              for kind in job.artifacts if kind in ARTIFACT_NAMES]}

    @app.post("/api/jobs/{job_id}/retry", status_code=202, dependencies=[Security(csrf_header)])
    def retry(job_id: UUID, db: Database):
        job = db.scalar(select(Job).where(Job.id == str(job_id)).with_for_update())
        if job is None:
            raise HTTPException(404, "找不到這筆影片分析")
        if job.status not in {"failed", "stopped"}:
            raise HTTPException(409, "只有失敗或停止的分析可以重新排程")
        job.status, job.progress, job.error = "queued", 0, None
        job.updated_at, job.worker_id, job.lease_until = utcnow(), None, None
        job.result_path = None
        job.water_label = job.water_confidence = None
        job.avg_length_mm = job.avg_width_mm = job.avg_weight_g = None
        job.shrimp_count = job.processed_frames = 0
        job.tracks.clear()
        job.artifacts, job.details = {}, {}
        db.commit()
        return serialize_job(job)

    @app.get("/api/jobs/{job_id}/video")
    @app.head("/api/jobs/{job_id}/video", include_in_schema=False)
    def video(job_id: UUID, request: Request, db: Database, kind: Literal["source", "result"] = "result"):
        job = find_job(db, job_id)
        relative = job.source_browser_path if kind == "source" else job.result_path
        if not relative:
            raise HTTPException(404, "影片尚未準備完成")
        return video_response(safe_path(settings.storage_root, relative), request.headers.get("range"), request.method == "HEAD")

    @app.get("/api/jobs/{job_id}/thumbnail")
    @app.head("/api/jobs/{job_id}/thumbnail", include_in_schema=False)
    def thumbnail(job_id: UUID, db: Database):
        job = find_job(db, job_id)
        if not job.thumbnail_path:
            raise HTTPException(404, "縮圖尚未準備完成")
        path = safe_path(settings.storage_root, job.thumbnail_path)
        if not path.is_file():
            raise HTTPException(404, "找不到縮圖")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/artifacts/{kind}")
    @app.head("/api/jobs/{job_id}/artifacts/{kind}", include_in_schema=False)
    def artifact(job_id: UUID, kind: str, db: Database):
        job = find_job(db, job_id)
        if kind not in ARTIFACT_NAMES or kind not in job.artifacts:
            raise HTTPException(404, "找不到此匯出檔案")
        path = safe_path(settings.storage_root, job.artifacts[kind])
        if not path.is_file() or path.suffix not in {".csv", ".json"}:
            raise HTTPException(404, "找不到此匯出檔案")
        return FileResponse(path, filename=f"{job.id}-{kind}{path.suffix}", media_type="application/json" if path.suffix == ".json" else "text/csv; charset=utf-8")

    @app.get("/api/overview")
    def overview(db: Database, start_date: date | None = None, end_date: date | None = None, pond: str | None = None):
        jobs = db.scalars(select(Job).where(*filters(start_date, end_date, pond)).order_by(Job.recorded_at.desc())).all()
        completed = [job for job in jobs if job.status == "completed"]
        tracks = [track for job in completed for track in job.tracks]
        grouped = {}
        for job in jobs:
            day = aware(job.recorded_at).astimezone(TAIPEI).date().isoformat()
            grouped.setdefault(day, []).append(job)
        daily = []
        for day, entries in sorted(grouped.items()):
            day_tracks = [track for job in entries if job.status == "completed" for track in job.tracks]
            daily.append({"date": day, "videos": len(entries), "shrimp_count": len(day_tracks),
                          "avg_length_mm": average(track.length_mm for track in day_tracks),
                          "avg_width_mm": average(track.width_mm for track in day_tracks),
                          "avg_weight_g": average(track.weight_g for track in day_tracks),
                          "clear_count": sum(job.water_label == "clear" for job in entries),
                          "turbid_count": sum(job.water_label == "turbid" for job in entries)})

        def histogram(field, boundaries, labels):
            result = [{"label": label, "count": 0} for label in labels]
            for track in tracks:
                value = getattr(track, field)
                if value is not None:
                    index = next((i for i, edge in enumerate(boundaries) if value < edge), len(boundaries))
                    result[index]["count"] += 1
            return result

        return {
            "summary": {"jobs_total": len(jobs), "completed": len(completed),
                        "processing": sum(job.status in {"queued", "processing"} for job in jobs),
                        "shrimp_count": len(tracks), "avg_length_mm": average(track.length_mm for track in tracks),
                        "avg_width_mm": average(track.width_mm for track in tracks),
                        "avg_weight_g": average(track.weight_g for track in tracks),
                        "clear_count": sum(job.water_label == "clear" for job in jobs),
                        "turbid_count": sum(job.water_label == "turbid" for job in jobs)},
            "daily": daily,
            "distributions": {"length": histogram("length_mm", [60, 80, 100, 120], ["<60", "60–80", "80–100", "100–120", "≥120"]),
                              "width": histogram("width_mm", [10, 15, 20, 25], ["<10", "10–15", "15–20", "20–25", "≥25"]),
                              "weight": histogram("weight_g", [2, 4, 6, 8], ["<2", "2–4", "4–6", "6–8", "≥8"])},
            "sex": {label.lower(): sum(track.label == label for track in tracks) for label in ["Male", "Female", "Unknown"]},
            "recent_jobs": [serialize_job(job) for job in sorted(jobs, key=lambda job: job.created_at, reverse=True)[:6]],
            "available_ponds": list(db.scalars(select(Job.pond).distinct().order_by(Job.pond)).all()),
        }

    return app


app = create_app()
