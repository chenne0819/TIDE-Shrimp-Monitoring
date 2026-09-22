from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.database import Job, Track
from app.storage import safe_path


def upload(client, **fields):
    return client.post("/api/jobs", files={"file": ("record.mp4", b"video payload", "video/mp4")}, data=fields)


def test_upload_queued_and_persistent(client, settings):
    response = upload(client, pond="B-02", recorded_at="2026-09-20", max_frames="8")
    assert response.status_code == 202
    result = response.json()
    assert result["status"] == "queued" and result["progress"] == 0
    assert result["source_video_url"] is None
    assert result["recorded_at"] == "2026-09-19T16:00:00+00:00"
    detail = client.get(f"/api/jobs/{result['id']}").json()
    assert detail["tracks"] == [] and detail["metadata"] == {}
    assert client.get("/api/jobs").json()["total"] == 1
    assert (settings.storage_root / "jobs" / result["id"] / "original.mp4").read_bytes() == b"video payload"


@pytest.mark.parametrize("fields", [{"pond": " "}, {"mode": "bad"}, {"water_policy": "bad"}, {"max_frames": "0"},
                                    {"recorded_at": "2026-09-20T12:00:00"}, {"recorded_at": "bad"}])
def test_upload_validation(client, fields):
    assert upload(client, **fields).status_code == 422
    assert client.get("/api/jobs").json()["total"] == 0


@pytest.mark.parametrize("filename,payload,status", [("bad.py", b"x", 415), ("empty.mp4", b"", 422), ("huge.mp4", b"x" * 129, 413)])
def test_upload_rejected_files_are_removed(client, settings, filename, payload, status):
    response = client.post("/api/jobs", files={"file": (filename, payload)})
    assert response.status_code == status
    assert list((settings.storage_root / "jobs").glob("*")) == []


def test_filename_never_selects_filesystem_path(client, settings):
    response = client.post("/api/jobs", files={"file": ("../../escape.mp4", b"x")})
    assert response.status_code == 202
    assert response.json()["filename"] == "escape.mp4"
    assert not (settings.storage_root.parent / "escape.mp4").exists()
    with pytest.raises(ValueError):
        safe_path(settings.storage_root, "../escape")


def test_overview_uses_equal_weight_per_track_not_frames_and_taipei_days(client):
    with client.app.state.sessions() as db:
        first = Job(id=str(uuid4()), filename="a.mp4", pond="A-01", recorded_at=datetime(2026, 9, 19, 16, tzinfo=timezone.utc),
                    source_path="a", status="completed", water_label="clear", shrimp_count=2)
        first.tracks = [Track(track_id="1", label="Male", observations=1000, length_mm=60, width_mm=10, weight_g=2),
                        Track(track_id="2", label="Female", observations=1, length_mm=100, width_mm=20, weight_g=6)]
        second = Job(id=str(uuid4()), filename="b.mp4", pond="A-01", recorded_at=datetime(2026, 9, 20, 15, 59, tzinfo=timezone.utc),
                     source_path="b", status="completed", water_label="turbid", shrimp_count=1)
        second.tracks = [Track(track_id="1", label="Unknown", observations=5, length_mm=80, weight_g=None)]
        outside = Job(id=str(uuid4()), filename="c.mp4", pond="B-01", recorded_at=datetime(2026, 9, 20, 16, tzinfo=timezone.utc), source_path="c")
        db.add_all([first, second, outside])
        db.commit()
    data = client.get("/api/overview?start_date=2026-09-20&end_date=2026-09-20&pond=A-01").json()
    assert data["summary"] == {"jobs_total": 2, "completed": 2, "processing": 0, "shrimp_count": 3,
                               "avg_length_mm": 80.0, "avg_width_mm": 15.0, "avg_weight_g": 4.0, "clear_count": 1, "turbid_count": 1}
    assert len(data["daily"]) == 1 and data["daily"][0]["date"] == "2026-09-20"
    assert data["daily"][0]["avg_width_mm"] == 15.0
    assert sum(item["count"] for item in data["distributions"]["length"]) == 3
    assert sum(item["count"] for item in data["distributions"]["weight"]) == 2
    assert sum(item["count"] for item in data["distributions"]["width"]) == 2
    assert data["sex"] == {"male": 1, "female": 1, "unknown": 1}
    assert client.get("/api/jobs?start_date=2026-09-20&end_date=2026-09-20").json()["total"] == 2
    assert client.get("/api/overview?start_date=2026-09-21&end_date=2026-09-20").status_code == 422


def test_empty_data_is_null_not_fake(client):
    overview = client.get("/api/overview").json()
    assert overview["summary"]["avg_weight_g"] is None
    assert overview["summary"]["avg_width_mm"] is None
    assert sum(item["count"] for item in overview["distributions"]["width"]) == 0
    assert overview["summary"]["shrimp_count"] == 0
    assert overview["daily"] == []
    assert client.get("/api/health").json() == {"status": "ok", "database": "connected", "worker": "offline"}


def test_width_distribution_boundaries_ignore_missing_and_unfinished_results(client):
    with client.app.state.sessions() as db:
        completed = Job(id=str(uuid4()), filename="width.mp4", pond="A-01",
                        recorded_at=datetime(2026, 9, 20, tzinfo=timezone.utc), source_path="width", status="completed")
        widths = [9.9, 10, 14.9, 15, 19.9, 20, 24.9, 25, None]
        completed.tracks = [Track(track_id=str(index), label="Unknown", observations=index + 1, width_mm=value)
                            for index, value in enumerate(widths)]
        unfinished = Job(id=str(uuid4()), filename="unfinished.mp4", pond="A-01",
                         recorded_at=datetime(2026, 9, 20, tzinfo=timezone.utc), source_path="unfinished", status="processing")
        unfinished.tracks = [Track(track_id="1", label="Unknown", observations=100, width_mm=999)]
        db.add_all([completed, unfinished])
        db.commit()
    data = client.get("/api/overview").json()
    assert data["summary"]["avg_width_mm"] == 17.45
    assert data["daily"][0]["avg_width_mm"] == 17.45
    assert data["distributions"]["width"] == [
        {"label": "<10", "count": 1}, {"label": "10–15", "count": 2},
        {"label": "15–20", "count": 2}, {"label": "20–25", "count": 2}, {"label": "≥25", "count": 1},
    ]


def test_retry_only_failed_and_clears_results(client):
    result = upload(client).json()
    route = f"/api/jobs/{result['id']}/retry"
    assert client.post(route).status_code == 409
    with client.app.state.sessions() as db:
        job = db.get(Job, result["id"])
        job.status, job.error, job.shrimp_count = "failed", "failure", 1
        job.tracks = [Track(track_id="1", label="Male", observations=1)]
        db.commit()
    retried = client.post(route)
    assert retried.status_code == 202 and retried.json()["status"] == "queued"
    assert retried.json()["error"] is None and retried.json()["shrimp_count"] == 0
    assert client.get(f"/api/jobs/{result['id']}").json()["tracks"] == []


def test_video_range_and_artifact_allowlist(client, settings):
    result = upload(client).json()
    job_id = result["id"]
    directory = settings.storage_root / "jobs" / job_id
    (directory / "browser.mp4").write_bytes(b"0123456789")
    (directory / "tracks.csv").write_text("track_id\n1\n")
    with client.app.state.sessions() as db:
        job = db.get(Job, job_id)
        job.result_path = f"jobs/{job_id}/browser.mp4"
        job.artifacts = {"tracks": f"jobs/{job_id}/tracks.csv"}
        db.commit()
    url = f"/api/jobs/{job_id}/video?kind=result"
    response = client.get(url, headers={"range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert client.get(url, headers={"range": "bytes=-3"}).content == b"789"
    assert client.get(url, headers={"range": "bytes=20-"}).status_code == 416
    assert client.get(url, headers={"range": "bytes=0-1,4-5"}).status_code == 416
    assert client.head(url).headers["content-length"] == "10"
    assert client.head(url).content == b""
    assert client.get(f"/api/jobs/{job_id}/artifacts/tracks").status_code == 200
    assert client.get(f"/api/jobs/{job_id}/artifacts/analyzer.log").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/video?kind=../../bad").status_code == 422
    for invalid_range in ["bytes=" + "9" * 5000 + "-", "bytes=-" + "9" * 5000, "bytes=1-0", "bytes=-0", "bytes=--1"]:
        invalid = client.get(url, headers={"range": invalid_range})
        assert invalid.status_code == 416
        assert invalid.headers["content-range"] == "bytes */10"


@pytest.mark.parametrize("query", ["end_date=9999-12-31", "start_date=0001-01-01"])
def test_date_boundaries_return_validation_errors(client, query):
    assert client.get(f"/api/jobs?{query}").status_code == 422
    assert client.get(f"/api/overview?{query}").status_code == 422


@pytest.mark.parametrize("timestamp", ["0001-01-01", "0001-01-01T00:00:00+08:00", "9999-12-31T23:59:59-08:00"])
def test_recorded_timestamp_overflow_is_422(client, timestamp):
    assert upload(client, recorded_at=timestamp).status_code == 422
    assert client.get("/api/jobs").json()["total"] == 0
