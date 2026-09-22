# TIDE web application

TIDE is a shrimp-video analysis and data workspace. Next.js serves the landing page, uploads, daily trends, measurement distributions, video playback, and AI analysis. FastAPI accepts videos, PostgreSQL stores jobs, measurements and conversations, and a separate worker invokes the analyzer.

This monorepo keeps the application and analyzer separate:

```text
TIDE-Shrimp-Monitoring/
  tracking/             # Integrated Python analyzer; private weights and its own .venv
  web/                  # This application
    frontend/           # Next.js, TypeScript, Motion, Recharts
    backend/            # FastAPI, SQLAlchemy, worker
    agent/skills/       # Project-local analysis and chart-selection instructions
    storage/            # Local videos, outputs, inbox; excluded from Git
    scripts/            # Optional local startup tools
    docs/               # API, AI analysis, statistics and visual asset guides
    compose.yaml        # Dedicated PostgreSQL service
```

The web worker calls the analyzer under `tracking/` without duplicating its model or tracking implementation.

## Using the application

- Landing page: `http://localhost:3000`
- Real workspace: `http://localhost:3000/dashboard`
- Explicit synthetic-data preview: `http://localhost:3000/dashboard?demo=1`
- AI analysis: `http://localhost:3000/assistant`
- API documentation: `http://127.0.0.1:8000/docs`

The real workspace only displays API results. Connection failures produce an error, never substituted demo numbers. Dashboard/recording demos do not create measurement records, and uploading requires real mode. AI demos do not create video jobs, but their conversations and boards are persisted separately and still consume the configured model's quota. **Published demos contain synthetic statistics; private sample footage and stills are not bundled.** Landing images are generated illustrations, not measurements.

1. Upload a video with its pond, capture time and analysis mode.
2. The API saves the file and queues a durable job; a separate worker runs inference.
3. Review the annotated H.264 video, per-ID length/width/weight and sex labels, and CSV exports.
4. Filter by capture date in Asia/Taipei and pond. Switch the dashboard's trend/distribution metric.
5. Ask natural-language questions in AI analysis. The center initially shows an empty-state icon; a confirmed visual analysis shows progress and then its results. Explanations and text-only follow-ups retain the current board. The full-height chat supports draggable/keyboard resizing, history, example questions, expandable execution records and factual completion summaries.

Enable AI in `web/.env`. The `codex` provider can use an existing local ChatGPT/Codex login for testing; `openai` uses the official SDK and a separate API key. See [AI analysis](docs/ai-analysis.md) for configuration, skills and the ten chart templates. `/assistant?demo=1` uses 60 days of labeled synthetic measurements.

Supported statistics include minimum/maximum, mean, median, sample SD, quartiles, Pearson/Spearman correlation, Welch t and Welch one-way ANOVA. Each request supports up to eight charts and six statistical requests. Inferential comparisons use video means, not individual IDs from the same recording as independent replicates. See [statistical methods](docs/statistical-methods.md).

Estimated width is available in the overview KPI, width trend/distribution tabs and recording details. It is the regressed OBB short-edge proxy, not a direct anatomical width measurement.

Videos may also arrive through the API or inbox; see the [API contract](docs/api-contract.md) and [backend guide](backend/README.md).

## First-time setup

Requirements: Node.js 22+, Python 3.12, PostgreSQL installed locally or through Docker, and a working `tracking/` installation. Inference requires its model files and separate Python environment; the website does not download or train weights.

Run from **`web/`**:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
Copy-Item .env.example .env
cd frontend
npm.cmd ci
cd ..
```

On macOS/Linux, use `.venv/bin/python`, `npm ci` and `cp .env.example .env`. Historical validation was on Windows; install an appropriate analyzer environment on other platforms. Recreate virtual environments on each machine.

`backend/requirements.txt` defines compatible version ranges; `requirements-lock.txt` records the tested exact versions. The frontend uses `package-lock.json`.

### Database: choose one approach

**Docker Compose:** set `POSTGRES_PASSWORD` in `web/.env`, and use the same password in `DATABASE_URL`. The default exposed port is 55432.

`POSTGRES_PASSWORD` contains the raw password; URL-encode reserved characters in the password portion of `DATABASE_URL`. For example, the illustrative password `example@pass` becomes `example%40pass` in the URL but remains unchanged in `POSTGRES_PASSWORD`. Do not use that example password. Python's `urllib.parse.quote(password, safe="")` can encode locally; do not submit real passwords to online encoders. `DATABASE_URL` is required: the API/worker fail explicitly rather than connecting to a fallback database.

```powershell
docker compose up -d db
```

**Existing Windows PostgreSQL installation:** the optional helper creates a dedicated cluster under `web/.local/postgres`, generates credentials and updates `web/.env`; it does not modify an existing PostgreSQL database.

```powershell
.\scripts\local-db.ps1 -Action start
```

Use `-PgBin 'path to PostgreSQL bin'` if discovery fails; `-Action status` checks it and `-Action stop` stops this project's cluster. Do not run two databases on port 55432. Deleting `.local/postgres` or the Docker volume destroys the stored records.

The helper verifies startup, connectivity and database creation before atomically updating `.env`; failures preserve the old configuration. Stop this cluster before changing its port so an old running port cannot be mistaken for readiness on the new one.

### Analyzer location

Set **`ANALYZER_ROOT=../tracking`** in `web/.env`. All relative application settings resolve from `web/`, independent of the process working directory. Leaving `ANALYZER_PYTHON` empty selects `tracking/.venv` when present; an explicit interpreter path is also supported.

Backend and analyzer environments remain separate. The API does not need to import PyTorch; the worker invokes the analyzer's Python.

## Start three processes

From `web/`, open separate terminals:

```powershell
# API
.\scripts\start-local.ps1 api
# Analysis worker
.\scripts\start-local.ps1 worker
# Next.js
.\scripts\start-local.ps1 web
```

PowerShell scripts are optional launchers. The implementation is Python and Next.js; direct equivalents are:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Another terminal in web/backend/
..\.venv\Scripts\python.exe -m app.worker
# A third terminal in web/frontend/
npm.cmd run dev
```

For a production build, run `npm.cmd run build` then `npm.cmd start` in `web/frontend/`. An API without a worker leaves video jobs queued. PostgreSQL preserves records across restarts. Startup creates missing tables; this version does not provide a general migration framework for changes to existing columns.

`NEXT_PUBLIC_API_URL` in `web/frontend/.env.local` defaults to `http://localhost:8000`. Include the actual frontend origin in backend `CORS_ORIGINS`. Next.js embeds `NEXT_PUBLIC_*` values at build time, so rebuild after changing them.

### Local request protection and uploads

`TRUSTED_HOSTS` is a list of API hostnames without scheme/port (default `localhost,127.0.0.1`); `CORS_ORIGINS` contains full frontend origins including scheme/port.

The frontend obtains an in-memory CSRF token from `GET /api/session` and sends `X-Tide-CSRF` on mutations. The server validates Host, Origin and token before reading the body. Tokens rotate on API restart; CLI clients should obtain a fresh token before POST. See the [backend guide](backend/README.md). Do not put this token in `.env` or public frontend variables.

`MAX_UPLOAD_BYTES` defaults to 2 GiB. File size is limited during multipart parsing, with a separate total-body allowance for bounded form data. Extra/duplicate fields and multiple files are rejected. Parsing failures and oversized requests clean up temporary files and create no job. The worker verifies whether the video is decodable.

Recording lists refresh for jobs submitted through the inbox or other windows. After transfer completes, the upload page waits for server commitment and no longer offers transport cancellation. If the outcome is unknown after a disconnect, inspect the recording list before resubmitting. Aborting a browser transfer does not cancel an already-created analysis.

**CSRF tokens are not account authentication or record-level authorization.** Local CLI clients can obtain them. This version is for trusted local/internal use, with one API process. Public hosting requires authentication, data isolation, HTTPS, quotas, shared session/task handling where applicable, storage retention and backups. API and database startup defaults bind to localhost.

## Meaning of the results

- Modes: general tracking, head/tail tracking and sampled prediction. The nine-channel mode is not exposed because its weights were not supplied.
- Water classification describes only the first frame as clear/turbid. `report` records it and continues; `stop` stops on turbidity.
- Length and weight use inherited regression models; width estimates OBB width. New cameras are not calibrated automatically.
- Counts are per-video tracked IDs, not a pond-wide deduplicated population.
- Distributions use each video's per-ID aggregate, not every frame as a new individual.
- A test frame limit shortens processing; leave it empty to analyze the entire video. CPU time depends on video and model.

## Changing videos, cameras or regression models

**The default remains the old reference size `800 × 450`, `2.5 px/mm` and inherited regression models. New-camera accuracy has not been validated.** The implementation is in `tracking/shrimp_monitoring/biometrics.py`, with CLI defaults in `tracking/shrimp_monitoring/cli.py`. The web worker does not override these defaults and has no calibration form or scale environment variable.

```text
s = min(reference_width / original_width, reference_height / original_height)
reference_length_px = original_OBB_long_edge_px × s
reference_width_px  = original_OBB_short_edge_px × s
estimated_length_mm = length_regressor(reference_length_px / pixels_per_mm)
estimated_width_mm  = width_regressor(reference_width_px / pixels_per_mm)
estimated_weight_g  = weight_regressor(estimated_length_mm)  # default length mode
```

### 1. Measure the new capture scale

A different camera, lens, distance, crop or animal depth requires calibration. Place a known-length ruler/target in the animal's plane under the same capture conditions and measure its pixel span. Using the source resolution as the reference canvas makes `s=1` for that resolution. Otherwise, multiply the target's pixel span by the same `s` before computing `pixels_per_mm = reference_pixels / known_mm`. Resolution alone does not establish physical scale.

**Illustrative values only:** on a `990 × 1398` reference canvas, a 20 mm target spanning 100 px gives `pixels_per_mm=5.0`. These are not measured local calibration values. The old regressors still apply after scaling; validate against measured shrimp dimensions/weights and retrain if necessary. OBB short-edge width and the old segmentation width definition require separate validation.

### 2. Direct analyzer invocation

Run from **`tracking/`**, replacing the video and illustrative scale:

```powershell
.\.venv\Scripts\python.exe -m general_track.run_track --video video/new-video.mp4 --output-root general_track/exports/new-calibration --monitoring --water-policy report --measurement-reference-size 990 1398 --pixels-per-mm 5.0 --weight-mode length
```

`general_track.run_head_tail_track` and `predict.run_predict` accept the same calibration parameters. CLI overrides affect only that run, not future web jobs.

### 3. Web or inbox jobs

In [backend/app/worker.py](backend/app/worker.py), find `command = [...]` in `QueueWorker.process()` and add parameters before `if max_frames:`. This example is **not applied** by default:

```python
command += [
    "--measurement-reference-size", "990", "1398",
    "--pixels-per-mm", "5.0",
    "--weight-mode", "length",
]
```

Use measured values, wait for active work to finish, then restart the worker. Subsequent claims, including already-queued jobs, use the new settings; no frontend rebuild is required. These are shared worker settings, not per-camera/job calibration. Multiple capture configurations require an additional per-job calibration feature.

### 4. Replacement regression weights

Place new files under `tracking/model/biometrics-new/`, retaining these names and contracts. The loader checks all four files even in `length` mode.

| File | Input → output |
| --- | --- |
| `final_linear_model_length.pkl` | Converted length mm → calibrated length mm |
| `final_linear_model_width.pkl` | Converted OBB width mm → calibrated width mm |
| `polynomial_regression_model_degree3.pkl` | Calibrated length mm → weight g |
| `multi_feature_model.pkl` | [calibrated length mm, calibrated width mm] → weight g |

Files must load with `joblib.load`, expose `.predict()`, and have the expected `n_features_in_` (1 for the first three, 2 for the last). A different format requires loader changes, not an extension rename.

Use `--biometrics-model-dir model/biometrics-new` for direct runs, or append those two strings to the worker command. Analyzer-relative paths resolve from `tracking/`. Water-model replacement uses `--water-model model/water/replacement.pth` and requires a compatible classifier architecture.

Validate a short run and inspect monitoring JSON fields `reference_size`, `pixels_per_mm` and `weight_mode` in the recording's source/output details. Completed records are not recalculated automatically: upload a new job or submit a new inbox filename. Keep different calibrations separate; repeated analyses create additional records and counts.

## Capture dates

| Entry point | Date source |
| --- | --- |
| Web upload | Form defaults to the local time when opened; edit to the video's actual capture time. Submitted with timezone as ISO time |
| API | `recorded_at`; date-only means Taipei midnight, or supply timezone-qualified ISO time such as `2026-09-17T09:30:00+08:00` |
| Inbox | Same-stem JSON `recorded_at`, with the same format |
| API/inbox without `recorded_at` | Server receipt/job-creation time, not extracted capture time |
| Real dashboard default filter | Today in Taipei and the preceding six days; other records remain stored |
| Dashboard/recording `?demo=1` | Synthetic values dated `2026-09-14`–`2026-09-20`; no PostgreSQL measurement jobs or private bundled media |
| AI `/assistant?demo=1` | 60 synthetic days anchored to `2026-09-20`; model calls and separately saved conversations/boards |

The application does not infer capture time from embedded video metadata, filenames or file modification time. `recorded_at` drives daily statistics; `created_at` separately records server creation time. UI/filter dates use Asia/Taipei. Keep test databases separate from farm records and supply the correct capture time.

## Animation and checks

The landing page uses a layered, scroll-driven Canvas: the camera pans from surface to bed while a shrimp crosses right to left, blending three transparent poses. Scrolling backward reverses it; stopping freezes it. Copy fades early, with skip and reduced-motion support. This is generated-image animation, not footage or inference.

The four runtime WebP layers under `web/frontend/public/images/swim/` total 883,224 bytes. Static fallback and feature images are under `images/`. See the [scene implementation](docs/swimming-scene.md) and [asset provenance](docs/assets.md).

From `web/`:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests -q
cd ../frontend
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

The Windows database-helper tests run from `web/` with `pwsh -NoProfile -File scripts/tests/test-local-db.ps1`. They use temporary folders and fake PostgreSQL executables, not a real database.

With the API ready, no other worker and an empty queue, this optional smoke test creates a real analysis in a **test database**:

```powershell
.\.venv\Scripts\python.exe scripts/smoke-test.py --video path/to/your-sample.mp4 --max-frames 8
```

It uploads the supplied video and writes a validation-pond record. No sample video is bundled.

Do not commit `.env`, virtual environments, `.local`, `storage`, private videos/stills or model weights. Ignore rules exclude these; public deployment controls and backup/retention policies still need implementation.
