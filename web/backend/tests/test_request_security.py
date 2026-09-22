import asyncio
from dataclasses import replace
import json
from tempfile import SpooledTemporaryFile

import anyio
import pytest
from fastapi.testclient import TestClient
import starlette.formparsers as multipart_module
from starlette.datastructures import UploadFile

from app.config import Settings
from app.database import Job
from app.main import create_app
from app.security import MULTIPART_OVERHEAD_BYTES
from app.uploads import UploadFields, UploadPayload


@pytest.fixture
def temp_files(monkeypatch):
    handles = []
    factory = multipart_module.SpooledTemporaryFile

    def tracked_file(*args, **kwargs):
        handle = factory(*args, **kwargs)
        handle.review_written_bytes = 0
        original_write = handle.write

        def write(data):
            handle.review_written_bytes += len(data)
            return original_write(data)

        handle.write = write
        handles.append(handle)
        return handle

    monkeypatch.setattr(multipart_module, "SpooledTemporaryFile", tracked_file)
    return handles


def multipart(parts, boundary="tide-test", complete=True):
    result = b""
    for name, filename, data in parts:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        result += f"--{boundary}\r\n{disposition}\r\n\r\n".encode() + data + b"\r\n"
    if complete:
        result += f"--{boundary}--\r\n".encode()
    return result


def raw_request(app, *, method="POST", path="/api/jobs", headers=(), messages=()):
    """Exercise the real ASGI receive stream, without TestClient joining chunks."""
    sent = []
    read_calls = 0
    pending = iter(messages)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
             "headers": [(b"host", b"testserver"), *[(name.lower().encode(), value.encode()) for name, value in headers]],
             "client": ("127.0.0.1", 12345), "server": ("testserver", 80)}

    async def receive():
        nonlocal read_calls
        read_calls += 1
        item = next(pending, {"type": "http.disconnect"})
        if isinstance(item, BaseException):
            raise item
        return item

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    return start["status"], read_calls, b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")


def request_headers(client, **extras):
    return [("content-type", "multipart/form-data; boundary=tide-test"),
            ("X-Tide-CSRF", client.headers["X-Tide-CSRF"]), *extras.items()]


def request_chunk(data, more=True):
    return {"type": "http.request", "body": data, "more_body": more}


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:9999"])
def test_untrusted_origins_cannot_read_session_or_mutate_before_body(client, temp_files, origin):
    for method, path in [("GET", "/api/session"), ("POST", "/api/jobs"),
                         ("POST", "/api/jobs/00000000-0000-0000-0000-000000000000/retry")]:
        status, reads, _ = raw_request(client.app, method=method, path=path,
                                      headers=[*request_headers(client), ("Origin", origin)],
                                      messages=[AssertionError("Unauthorized request read its body")])
        assert status == 403 and reads == 0
    assert temp_files == []
    assert client.get("/api/jobs").json()["total"] == 0


def test_cross_site_request_without_origin_is_rejected(client, temp_files):
    status, reads, _ = raw_request(client.app, method="GET", path="/api/session",
                                  headers=[("Sec-Fetch-Site", "cross-site")])
    assert (status, reads) == (403, 0)
    assert temp_files == []


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("resource,mode,destination", [
    ("video?kind=result", "no-cors", "video"),
    ("thumbnail", "no-cors", "image"),
    ("artifacts/tracks", "navigate", "document"),
])
def test_native_cross_site_media_and_download_without_origin(client, settings, method, resource, mode, destination):
    job_id = client.post("/api/jobs", files={"file": ("a.mp4", b"video")}).json()["id"]
    directory = settings.storage_root / "jobs" / job_id
    (directory / "result.mp4").write_bytes(b"0123456789")
    (directory / "thumbnail.jpg").write_bytes(b"jpeg-fixture")
    (directory / "tracks.csv").write_text("track_id\n1\n", encoding="utf-8")
    with client.app.state.sessions() as db:
        job = db.get(Job, job_id)
        job.result_path = f"jobs/{job_id}/result.mp4"
        job.thumbnail_path = f"jobs/{job_id}/thumbnail.jpg"
        job.artifacts = {"tracks": f"jobs/{job_id}/tracks.csv"}
        db.commit()
    # Browser-native <video>, <img>, and download navigation do not send the
    # CSRF header or necessarily Origin, unlike the authenticated POST client.
    client.headers.pop("X-Tide-CSRF")
    headers = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": mode, "Sec-Fetch-Dest": destination}
    url = f"/api/jobs/{job_id}/{resource}"
    if resource.startswith("video"):
        headers["Range"] = "bytes=2-5"
    response = client.request(method, url, headers=headers)
    assert response.status_code == (206 if resource.startswith("video") else 200)
    assert response.headers.get("content-length")
    if method == "HEAD":
        assert response.content == b""
    elif resource.startswith("video"):
        assert response.content == b"2345"
    else:
        assert response.content
    # The exception is limited to an absent Origin on known read-only files.
    blocked = client.request(method, url, headers={**headers, "Origin": "https://evil.example"})
    assert blocked.status_code == 403
    for path in ["/api/session", "/api/jobs", f"/api/jobs/{job_id}",
                 f"/api/jobs/{job_id}/artifacts/unknown"]:
        assert client.get(path, headers=headers).status_code == 403
    assert client.post(f"/api/jobs/{job_id}/retry", headers=headers).status_code == 403


@pytest.mark.parametrize("token", [None, "wrong", ""])
def test_missing_or_wrong_token_is_rejected_without_receiving_body(client, temp_files, token):
    headers = [("Content-Type", "multipart/form-data; boundary=tide-test")]
    if token is not None:
        headers.append(("X-Tide-CSRF", token))
    status, reads, _ = raw_request(client.app, headers=headers)
    assert (status, reads) == (403, 0)
    assert temp_files == []


def test_session_is_uncached_random_per_instance_and_supports_browser_and_cli(client, settings):
    session = client.get("/api/session", headers={"Origin": "http://localhost:3000"})
    assert session.status_code == 200
    assert session.headers["cache-control"] == "no-store"
    assert session.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert session.json()["max_upload_bytes"] == 128
    token = session.json()["csrf_token"]
    assert len(token) >= 32
    second = create_app(settings)
    with TestClient(second) as other:
        assert other.get("/api/session").json()["csrf_token"] != token
        assert other.post("/api/jobs", headers={"X-Tide-CSRF": token}, files={"file": ("a.mp4", b"x")}).status_code == 403
    # Allowed frontend origin and a CLI with no Origin both use the same documented flow.
    for origin in ["http://localhost:3000", "http://testserver", None]:
        headers = {"X-Tide-CSRF": client.get("/api/session").json()["csrf_token"]}
        if origin:
            headers["Origin"] = origin
        response = client.post("/api/jobs", headers=headers, files={"file": ("a.mp4", b"x")})
        assert response.status_code == 202


def test_untrusted_host_cannot_get_session_or_queue(client, temp_files):
    assert client.get("/api/session", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/jobs", headers={"Host": "evil.example"}, files={"file": ("a.mp4", b"x")}).status_code == 400
    assert temp_files == []


def test_preflight_and_openapi_expose_required_csrf_header(client):
    preflight = client.options("/api/jobs", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                                                    "Access-Control-Request-Headers": "X-Tide-CSRF"})
    assert preflight.status_code == 200
    assert "x-tide-csrf" in preflight.headers["access-control-allow-headers"].lower()
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-Tide-CSRF"
    operation = schema["paths"]["/api/jobs"]["post"]
    assert operation["security"] == [{"APIKeyHeader": []}]
    assert operation["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] == ["file"]


def test_trusted_frontend_can_read_early_security_and_size_errors(client, settings, temp_files):
    origin = "http://localhost:3000"
    unauthorized = client.post("/api/jobs", headers={"Origin": origin, "X-Tide-CSRF": "expired"},
                               files={"file": ("a.mp4", b"x")})
    assert unauthorized.status_code == 403
    assert unauthorized.headers["access-control-allow-origin"] == origin
    oversized = client.post("/api/jobs", content=b"", headers={"Origin": origin,
                            "Content-Length": str(settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES + 1)})
    assert oversized.status_code == 413
    assert oversized.headers["access-control-allow-origin"] == origin
    assert temp_files == []


def test_declared_total_oversize_is_rejected_before_receiving_or_allocating(client, settings, temp_files):
    status, reads, _ = raw_request(client.app, headers=request_headers(client, **{
        "Content-Length": str(settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES + 1)}))
    assert (status, reads) == (413, 0)
    assert temp_files == []
    assert client.get("/api/jobs").json()["total"] == 0


def test_chunked_total_limit_closes_partial_tempfile(client, settings, temp_files):
    prefix = b'--tide-test\r\nContent-Disposition: form-data; name="file"; filename="a.mp4"\r\n\r\n'
    status, reads, _ = raw_request(client.app, headers=request_headers(client, **{"Transfer-Encoding": "chunked"}),
                                  messages=[request_chunk(prefix + b"a" * 64),
                                            request_chunk(b"b" * (settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES), more=False)])
    assert status == 413 and reads == 2
    assert len(temp_files) == 1 and temp_files[0].closed
    assert temp_files[0].review_written_bytes == 64
    assert client.get("/api/jobs").json()["total"] == 0


def test_individual_file_limit_never_spools_bytes_above_limit(client, temp_files):
    prefix = b'--tide-test\r\nContent-Disposition: form-data; name="file"; filename="a.mp4"\r\n\r\n'
    status, reads, _ = raw_request(client.app, headers=request_headers(client),
                                  messages=[request_chunk(prefix + b"a" * 64), request_chunk(b"b" * 64),
                                            request_chunk(b"c\r\n--tide-test--\r\n", more=False)])
    assert status == 413 and reads == 3
    assert len(temp_files) == 1 and temp_files[0].closed
    assert temp_files[0].review_written_bytes == 128
    assert client.get("/api/jobs").json()["total"] == 0


@pytest.mark.parametrize("extra", [("ignored", "extra.bin", b"extra"), ("file", "second.mp4", b"extra"),
                                    ("unexpected", None, b"text"), ("pond", None, b"duplicate")])
def test_extra_duplicate_or_unknown_parts_rejected_and_closed(client, temp_files, extra):
    body = multipart([("pond", None, b"A-01"), ("file", "a.mp4", b"x"), extra])
    response = client.post("/api/jobs", content=body, headers={"Content-Type": "multipart/form-data; boundary=tide-test"})
    assert response.status_code == 400
    assert len(temp_files) == 1 and all(handle.closed for handle in temp_files)
    assert client.get("/api/jobs").json()["total"] == 0


@pytest.mark.parametrize("ending", ["truncated", "disconnect", "cancel"])
def test_interrupted_multipart_closes_unfinished_files(client, temp_files, ending):
    prefix = b'--tide-test\r\nContent-Disposition: form-data; name="file"; filename="a.mp4"\r\n\r\n'
    messages = [request_chunk(prefix + b"x", more=ending != "truncated")]
    if ending == "disconnect":
        messages.append({"type": "http.disconnect"})
    elif ending == "cancel":
        messages.append(asyncio.CancelledError())
    if ending == "cancel":
        with pytest.raises(asyncio.CancelledError):
            raw_request(client.app, headers=request_headers(client), messages=messages)
    else:
        status, _, _ = raw_request(client.app, headers=request_headers(client), messages=messages)
        assert status == 400
    assert len(temp_files) == 1 and temp_files[0].closed
    assert client.get("/api/jobs").json()["total"] == 0


def test_small_valid_chunked_upload_remains_supported_and_closes_file(client, temp_files):
    body = multipart([("pond", None, "測試池".encode()), ("file", "a.mp4", b"video")])
    chunks = [body[index:index + 17] for index in range(0, len(body), 17)]
    status, _, content = raw_request(client.app, headers=request_headers(client),
                                    messages=[request_chunk(chunk, index < len(chunks) - 1) for index, chunk in enumerate(chunks)])
    assert status == 202 and json.loads(content)["pond"] == "測試池"
    assert len(temp_files) == 1 and temp_files[0].closed


def test_cancellation_during_storage_copy_removes_partial_job_directory(client, settings):
    # A disk-backed spool makes UploadFile.close() await a worker thread. Under
    # an active CancelScope that await is cancelled too, so cleanup must not be
    # placed after it. Exercise the actual handler, cancelling its second read.
    endpoint = next(route.endpoint for route in client.app.routes
                    if getattr(route, "path", None) == "/api/jobs" and "POST" in route.methods)
    spool = SpooledTemporaryFile(max_size=1)
    spool.write(b"partial video data")
    spool.seek(0)
    assert spool._rolled
    upload = UploadFile(spool, filename="copy-cancel.mp4")
    original_read = upload.read
    observations = {"reads": 0, "partial_created": False}

    async def run():
        with anyio.CancelScope() as scope:
            async def interrupted_read(size):
                observations["reads"] += 1
                if observations["reads"] == 1:
                    return await original_read(size)
                observations["partial_created"] = bool(list((settings.storage_root / "jobs").rglob("original.mp4")))
                scope.cancel()
                await anyio.lowlevel.checkpoint()

            upload.read = interrupted_read
            try:
                await endpoint(None, UploadPayload(file=upload, fields=UploadFields()))
            finally:
                # Same synchronous input-spool ownership as receive_upload.
                spool.close()

    anyio.run(run)
    assert observations == {"reads": 2, "partial_created": True}
    assert spool.closed
    assert list((settings.storage_root / "jobs").iterdir()) == []
    assert client.get("/api/jobs").json()["total"] == 0


@pytest.mark.parametrize("content_type,body,status", [
    ("application/octet-stream", b"video", 415),
    ("multipart/form-data", b"broken", 400),
    ("multipart/form-data; boundary=tide-test", multipart([("file", "x" * 4097 + ".mp4", b"x")]), 413),
    ("multipart/form-data; boundary=tide-test", multipart([("pond", None, b"x" * 1025), ("file", "a.mp4", b"x")]), 400),
])
def test_bad_multipart_metadata_is_bounded(client, temp_files, content_type, body, status):
    response = client.post("/api/jobs", content=body, headers={"Content-Type": content_type})
    assert response.status_code == status
    assert all(handle.closed for handle in temp_files)
    assert client.get("/api/jobs").json()["total"] == 0


def test_database_url_is_required_and_host_wildcards_fail_fast(monkeypatch, settings):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings.from_env()
    for hosts in [("*",), ("*.localhost",), ()]:
        with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
            replace(settings, trusted_hosts=hosts)
