# FastAPI and the video worker

Run these commands from **`web/backend/`**, using `web/.venv`. Inference uses the separate analyzer environment under `tracking/`.

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
..\.venv\Scripts\python.exe -m app.worker
# Process one job for integration testing
..\.venv\Scripts\python.exe -m app.worker --once
..\.venv\Scripts\python.exe -m pytest tests -q
```

On macOS/Linux use `../.venv/bin/python`. Interactive API docs are at `http://127.0.0.1:8000/docs`. Startup creates initial/missing tables; future changes to existing columns require migrations.

## Configuration

The application loads `web/.env` regardless of working directory. `DATABASE_URL` is required, using `postgresql+psycopg://...`; missing configuration fails explicitly. URL-encode reserved characters such as `@` in its password.

Relative settings resolve from **`web/`**: `STORAGE_ROOT=storage`, `ANALYZER_ROOT=../tracking`. An empty `ANALYZER_PYTHON` selects `tracking/.venv/Scripts/python.exe` or `tracking/.venv/bin/python`.

`CORS_ORIGINS` is a comma-separated list of complete frontend origins. `TRUSTED_HOSTS` contains API hostnames without scheme/port, defaulting to `localhost,127.0.0.1`. `MAX_UPLOAD_BYTES` defaults to 2 GiB and is enforced during parsing, with an additional bounded form-data allowance for the total body. Defaults: `ANALYZER_TIMEOUT_SECONDS=86400`, `WORKER_LEASE_SECONDS=180` (minimum 30), `WORKER_POLL_SECONDS=3`. API and worker must share access to storage and the analyzer environment.

## Upload and results

Every POST, including retry, needs `X-Tide-CSRF`. Obtain `csrf_token` from `GET /api/session`; the frontend does this automatically. Do not cache the token across API restarts. CLI requests without Origin still require it; supplied Origins must be allowed. This is local CSRF protection, not user authentication.

Example from a directory containing your own `sample.mp4`:

```powershell
$TideSession = Invoke-RestMethod http://127.0.0.1:8000/api/session
curl.exe -H "X-Tide-CSRF: $($TideSession.csrf_token)" -F "file=@sample.mp4" -F "pond=A-01" -F "recorded_at=2026-09-20" -F "mode=general" -F "water_policy=report" http://127.0.0.1:8000/api/jobs
```

No private sample footage/still is distributed. Python clients can GET the session, then pass `headers={"X-Tide-CSRF": token}` on POST. In Swagger, call session first and paste the token into Authorize.

Modes are `general`, `head_tail`, `predict`. Omit `max_frames` for the full video; `max_frames=8` is a test limit. `recorded_at` accepts a Taipei date or timezone-qualified ISO datetime. `water_policy=report` records classification and continues; `stop` produces `stopped` when the first frame is turbid.

The API returns 202 with a job ID; the worker claims it separately. Read `GET /api/jobs/{id}` or `GET /api/overview?start_date=2026-09-20&end_date=2026-09-20&pond=A-01`. Date bounds include the full Taipei day. Empty averages are `null`, never fabricated values.

Dashboard measurements use each video's per-ID aggregate, preventing IDs seen in more frames from receiving extra weight. IDs do not link individuals across recordings. Prediction mode retains the analyzer's paired IDs. Width is an OBB proxy; inherited camera/regression calibration still requires validation. AI inferential methods additionally offer/require video means as documented in [statistical methods](../docs/statistical-methods.md).

The worker transcodes source/result videos to H.264/yuv420p MP4 and creates JPEG thumbnails. Playback URLs appear only when ready. Video endpoints support one HTTP Range and HEAD. Allowlisted CSV/JSON exports are downloadable; execution logs are not public. Transcoding removes audio.

## Inbox delivery

Default inbox: `web/storage/inbox`. An explicit relative `--inbox storage/inbox` also resolves from `web/`.

1. Finish writing `storage/inbox/example.mp4`.
2. Optionally add `example.json`.
3. Only after writing is complete, create empty `example.mp4.ready`.

```json
{"pond":"A-01","recorded_at":"2026-09-20","mode":"general","water_policy":"report","max_frames":8}
```

Remove `max_frames` for full-video analysis. The source remains in place and the marker becomes `example.mp4.ingested`. A unique ingestion key uses source path, size and modification time to prevent re-queuing after restart. Files without `.ready` are not accepted; do not modify the video after adding the marker. Errors produce `.error.txt`; after correction a subsequent scan retries intake.

## State and recovery

PostgreSQL `FOR UPDATE SKIP LOCKED` lets workers claim different jobs. The claim transaction commits before starting inference. Leases and worker heartbeats update approximately every five seconds. Progress describes transcoding/inference/import stages, not exact per-frame completion.

After a worker exits and its lease expires, another worker marks the stale job failed; it does **not** rerun inference automatically. `POST /api/jobs/{id}/retry` re-queues failed/stopped jobs. Each attempt has a separate output directory; an old process that lost its lease cannot publish results. Retry retains `water_policy`, so `stop` may stop again. Logs stay under `web/storage/jobs/{id}/attempt-*/`.

This local/internal version has no accounts, record permissions or upload quotas. Before public deployment add authentication, HTTPS, reverse-proxy limits, storage management and backups. Extensions and size are validated first; worker decoding rejects invalid video content with a failed state rather than fabricated success.
