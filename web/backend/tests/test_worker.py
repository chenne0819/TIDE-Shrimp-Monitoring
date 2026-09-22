from datetime import timedelta
import json
from uuid import uuid4

import pytest

from app.database import Job, utcnow
from app.results import read_results
from app.worker import LostLease, QueueWorker, ingest_inbox


def queued(worker, settings):
    job_id = str(uuid4())
    directory = settings.storage_root / "jobs" / job_id
    directory.mkdir(parents=True)
    source = directory / "original.mp4"
    source.write_bytes(b"source")
    with worker.sessions() as db:
        db.add(Job(id=job_id, filename="source.mp4", pond="A-01", recorded_at=utcnow(), source_path=source.relative_to(settings.storage_root).as_posix()))
        db.commit()
    return job_id


def test_claim_commits_and_recovery_is_conservative(settings):
    one, two = QueueWorker(settings), QueueWorker(settings)
    try:
        first, second = queued(one, settings), queued(one, settings)
        assert one.claim() == first
        assert two.claim() == second
        assert one.claim() is None
        with one.sessions() as db:
            job = db.get(Job, first)
            assert job.status == "processing" and job.attempts == 1
            job.lease_until = utcnow() - timedelta(seconds=1)
            db.commit()
        assert two.claim() is None
        with one.sessions() as db:
            assert db.get(Job, first).status == "failed"
            assert db.get(Job, second).status == "processing"
        with pytest.raises(LostLease):
            one.heartbeat(first, force=True)
    finally:
        one.close()
        two.close()


def test_worker_failure_is_persisted(settings, monkeypatch):
    worker = QueueWorker(settings)
    job_id = queued(worker, settings)
    assert worker.claim() == job_id
    monkeypatch.setattr(worker, "transcode", lambda *args: (_ for _ in ()).throw(RuntimeError("bad video")))
    worker.process(job_id)
    with worker.sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == "failed" and job.error
        assert job.worker_id is None and job.lease_until is None
    worker.close()


@pytest.mark.parametrize("predict", [False, True])
def test_import_actual_export_schemas_and_nulls(tmp_path, predict):
    (tmp_path / "monitoring.json").write_text(json.dumps({"status": "completed", "water_model": "C:/private/model.pth"}))
    (tmp_path / "water_quality.csv").write_text("water_label,water_confidence\nturbid,0.95\n")
    if predict:
        name = "per_shrimp_summary.csv"
        header = "Shrimp_ID,Final_Label,Total_Seen,mean_length_mm,mean_width_mm,mean_weight_g\n"
    else:
        name = "per_shrimp.csv"
        header = "track_id,final_label,observations,mean_length_mm,mean_width_mm,mean_weight_g\n"
    (tmp_path / name).write_text(header + "1,male,100,70,12,3\n2,Female,1,90,nan,5\n3,Unknown,0,0,0,0\n")
    result = read_results(tmp_path)
    assert len(result["tracks"]) == 2
    assert result["avg_length_mm"] == 80 and result["avg_weight_g"] == 4
    assert result["avg_width_mm"] == 12
    assert result["tracks"][0]["label"] == "Male"
    assert "water_model" not in result["metadata"]
    assert result["water_label"] == "turbid"


def test_stopped_water_does_not_require_track_csv(tmp_path):
    (tmp_path / "monitoring.json").write_text('{"status":"skipped_turbid"}')
    result = read_results(tmp_path)
    assert result["status"] == "stopped" and result["tracks"] == []


def test_general_mode_short_sex_labels(tmp_path):
    (tmp_path / "monitoring.json").write_text('{"status":"completed"}')
    (tmp_path / "per_shrimp.csv").write_text("track_id,final_label,observations\n1,M,40\n2,F,40\n3,obs,8\n")
    assert [track["label"] for track in read_results(tmp_path)["tracks"]] == ["Male", "Female", "Unknown"]


def test_inbox_ready_and_duplicate_after_restart(settings, tmp_path):
    worker = QueueWorker(settings)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "test.mp4").write_bytes(b"video")
    assert ingest_inbox(settings, worker.sessions, inbox) == 0
    (inbox / "test.json").write_text('{"pond":"B-02","recorded_at":"2026-09-20","max_frames":8}')
    (inbox / "test.mp4.ready").touch()
    assert ingest_inbox(settings, worker.sessions, inbox) == 1
    assert (inbox / "test.mp4.ingested").exists() and (inbox / "test.mp4").exists()
    (inbox / "test.mp4.ready").touch()
    assert ingest_inbox(settings, worker.sessions, inbox) == 0
    with worker.sessions() as db:
        jobs = db.query(Job).all()
        assert len(jobs) == 1 and jobs[0].pond == "B-02" and jobs[0].max_frames == 8
    worker.close()


def test_inbox_bad_metadata_does_not_queue(settings, tmp_path):
    worker = QueueWorker(settings)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "bad.mp4").write_bytes(b"video")
    (inbox / "bad.mp4.ready").touch()
    (inbox / "bad.json").write_text('{"max_frames":-1}')
    assert ingest_inbox(settings, worker.sessions, inbox) == 0
    assert (inbox / "bad.mp4.error.txt").exists()
    with worker.sessions() as db:
        assert db.query(Job).count() == 0
    worker.close()
