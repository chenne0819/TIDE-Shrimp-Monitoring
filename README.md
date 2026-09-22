# TIDE Shrimp Monitoring

An integrated shrimp video analysis and monitoring system: detection, tracking and sex classification, water appearance classification, size and weight estimates, and a web workspace for reviewing measurements and asking questions about the data.

## Repository layout

```text
TIDE-Shrimp-Monitoring/
├── tracking/   # Integrated Python inference and monitoring engine
└── web/        # Next.js frontend, FastAPI API/worker, PostgreSQL and AI assistant
```

These are two parts of the same system. `tracking/` can also run independently from Python. The web worker calls that engine through its existing command-line interface; inference is not performed inside an HTTP request.

| Component | Included features | Documentation |
| --- | --- | --- |
| Tracking engine | Newer YOLO OBB/HBB detection, tracking IDs, head/tail processing and sex classification; integrated first-frame water classification, calibrated length/width estimates and weight regression | [Tracking setup and models](tracking/README.md) |
| Monitoring outputs | Annotated video, per-ID summaries, CSV measurements, water classification and calibration metadata | [Integration guide](tracking/docs/monitoring-integration.md) |
| Web application | Video upload/inbox, background jobs, playback, date/pond filters, length/width/weight distributions and CSV export | [Web setup](web/README.md) |
| AI analysis | Natural-language questions, follow-up context, ten chart templates, descriptive statistics, Pearson/Spearman correlation, Welch t-test and Welch ANOVA | [AI analysis guide](web/docs/ai-analysis.md) |

The application interface and AI answers remain in Traditional Chinese. Maintained setup documentation and new integration comments are in English; archived upstream material retains its original language.

## Origins and development history

This repository is a fork of [NxBLANKxN/Shrimp-Male-Yolo-Tracking](https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking), based on upstream revision [`5662c81`](https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking/commit/5662c81ba1ad86b04cbc0bfe6206df1599dbc36a). Its detection, tracking and sex-classification implementation remains the foundation of `tracking/`.

Water classification and biometric conversion were adapted from [chenne0819/ShrimpVisionRT](https://github.com/chenne0819/ShrimpVisionRT), revision [`dd87698`](https://github.com/chenne0819/ShrimpVisionRT/commit/dd876980b83e42986b54c1ebeb52017c0728f113). Model provenance, hashes and reference geometry are documented in [the asset manifest](tracking/model/assets-manifest.json) and [biometric provenance](tracking/model/biometrics/provenance.json). The manifests are descriptions, not downloadable weights.

The upstream Git history is retained. Publication changes are separated into directory relocation, monitoring integration, the web application, and English documentation. Earlier local work is grouped into these commits; the history does not claim that each previous UI adjustment was committed separately. The [original upstream README](tracking/docs/README-original.md) is preserved verbatim for attribution and historical context.

## Getting started

Requirements: Git (and Git LFS for inherited upstream LFS assets), Python 3.12, Node.js 22 or later, PostgreSQL, and compatible inference weights. A GPU is optional and requires a compatible PyTorch/CUDA installation.

1. Clone this repository. Prepare the tracking environment and the required model files using [tracking/README.md](tracking/README.md). The optional Windows helper is `tracking/setup-monitoring.ps1`.
2. Configure the web environment following [web/README.md](web/README.md): create `web/.venv`, install the backend requirements, run `npm ci` in `web/frontend`, and copy `web/.env.example` to `web/.env`.
3. Choose your own PostgreSQL password and set `DATABASE_URL` and `POSTGRES_PASSWORD` consistently. `web/compose.yaml` can start a database bound to localhost. Do not deploy the example password.
4. Keep `ANALYZER_ROOT=../tracking` in `web/.env`. Paths resolve from `web/`, independently of the shell working directory. Leave `ANALYZER_PYTHON` empty to use the separate environment in `tracking/.venv`, or explicitly configure the inference Python executable.
5. Start the API, background worker and frontend in separate terminals. On Windows, run the following from `web/`:

```powershell
# Terminal 1: API
.\scripts\start-local.ps1 -Service api

# Terminal 2: background inference worker
.\scripts\start-local.ps1 -Service worker

# Terminal 3: Next.js
.\scripts\start-local.ps1 -Service web
```

Open [the web workspace](http://127.0.0.1:3000/dashboard), [the upload page](http://127.0.0.1:3000/upload), or [the API documentation](http://127.0.0.1:8000/docs). The [explicit demo](http://127.0.0.1:3000/dashboard?demo=1) uses synthetic measurements and does not include private recordings or extracted thumbnails. Real analysis requires the models and a running worker.

AI is disabled by default. The `codex` provider uses an existing local Codex login for trusted local testing; the `openai` provider uses the official OpenAI Responses SDK and a separate server-side API key. See [AI configuration](web/docs/ai-analysis.md). No account session or API key is supplied by this repository.

## Models and measurement limits

- Local model weights are excluded from the new integration commits. Obtain authorized copies separately and follow the documented `tracking/model/` layout. Inherited upstream LFS entries retain their original history; they do not provide the newly integrated private weights.
- Water results describe image appearance (`clear` / `turbid`) from the first frame. They are not pH, dissolved oxygen or a complete water-quality measurement.
- Width is an OBB short-edge proxy; length and weight are model estimates. The inherited reference is 800 × 450 at 2.5 pixels/mm. Recalibrate after changing the camera, distance, framing or geometry; resizing alone does not establish a physical scale.
- General tracking, head/tail tracking and single-frame analysis have prior local smoke-test evidence. The optional temporal multi-channel mode still needs a compatible nine-channel HBB checkpoint.
- Tracking IDs are local to a video. Comparisons across videos or dates do not establish the growth of the same individual shrimp.

## Privacy and publication

The ignore rules exclude local `.env` files, authentication caches, keys, databases, uploaded recordings, private demo footage, model weights, virtual environments and build output. Only configuration templates are included. Keep credentials on the server; never place them in `NEXT_PUBLIC_*` variables.

The current application is intended for a trusted local environment. Public multi-user deployment requires application authentication and appropriate deployment controls; see the [security review](web/docs/security-review-2026-09-20.md). Preserve upstream authorship and any applicable source/dependency notices when redistributing; this repository does not declare a new blanket license for upstream code or external model assets.

## Validation and contributions

See the [tracking validation record](tracking/docs/monitoring-validation.md), [web validation record](web/docs/validation.md) and [publication record](web/docs/publication-2026-09-22.md) for commands, scope and limitations. Some tracking tests require the separately supplied monitoring models. Unit tests and short-video smoke tests do not establish model accuracy.

For future changes, use focused English commit messages and keep functional changes separate from broad formatting or directory moves. Include the checks that were actually run. Never commit credentials or private recordings when adding a reproducible test case.
