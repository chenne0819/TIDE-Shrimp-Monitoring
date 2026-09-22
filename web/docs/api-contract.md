# TIDE API contract

The monorepo keeps the integrated analyzer in `tracking/` and this application in `web/`. The web worker invokes the analyzer without duplicating its inference code. Web calls FastAPI directly via NEXT_PUBLIC_API_URL (default http://localhost:8000). Paths below are prefixed /api. Dates use ISO 8601; daily grouping is Asia/Taipei. Optional start_date/end_date use YYYY-MM-DD inclusive. The application UI uses Traditional Chinese; this documentation is English.

## Job

`id: string (UUID), filename: string, pond: string, recorded_at: string, created_at: string, status: queued|processing|completed|stopped|failed, progress: number (0..100), mode: general|head_tail|predict, water_label: clear|turbid|null, water_confidence: number|null, shrimp_count: number, avg_length_mm: number|null, avg_width_mm: number|null, avg_weight_g: number|null, source_video_url: string|null, result_video_url: string|null, thumbnail_url: string|null, error: string|null, processed_frames: number`.

API media URLs are /api/... relative to the API origin, not web origin. Completed summaries count unique tracked individuals per recording, not a deduplicated pond population across videos. Measurements are estimates under original camera calibration, and width is OBB proxy.

## Endpoints

- GET /session → `{csrf_token: string, max_upload_bytes: number}`, `Cache-Control: no-store`. Fetch a fresh token before POST and send it as `X-Tide-CSRF`. The frontend does this automatically. Tokens rotate on API restart; intended local CLI clients may obtain a token without an Origin. Any supplied untrusted Origin is rejected, as are untrusted Host values. This is local CSRF protection, not multi-user authentication; keep the API on loopback.
- GET /health → `{status, database, worker}`. Health does not substitute sample results when unavailable.
- POST /jobs multipart: `file`, `pond` (default A-01), `recorded_at` (ISO datetime with timezone or date), `mode` (default general), `water_policy` (default report), optional `max_frames` positive integer. → Job (202). UI should label frame limit as an optional test limit; default is whole video.
- GET /jobs?start_date=&end_date=&pond=&status=&limit=20&offset=0 → `{items: Job[], total: number}`.
- GET /jobs/{id} → Job plus `tracks: [{track_id: string, label: Male|Female|Unknown, observations: number, length_mm: number|null, width_mm: number|null, weight_g: number|null}]`, `metadata: object`, `artifacts: [{kind:string,label:string,url:string}]`.
- POST /jobs/{id}/retry → Job (202); only failed/stopped jobs can be retried.
- GET /jobs/{id}/video?kind=source|result → browser-compatible MP4, supports Range.
- GET /jobs/{id}/thumbnail → JPEG.
- GET /jobs/{id}/artifacts/{kind} → known named exported CSV/JSON only.
- GET /overview?start_date=&end_date=&pond= → `{summary:{jobs_total,completed,processing,shrimp_count,avg_length_mm,avg_width_mm,avg_weight_g,clear_count,turbid_count}, daily:[{date,videos,shrimp_count,avg_length_mm,avg_width_mm,avg_weight_g,clear_count,turbid_count}], distributions:{length:[{label,count}],width:[{label,count}],weight:[{label,count}]}, sex:{male,female,unknown}, recent_jobs:Job[], available_ponds:string[]}`. Width is the estimated OBB short edge in mm. Histogram bins are `<10`, `10–15`, `15–20`, `20–25`, `≥25`, with lower bounds inclusive and upper bounds exclusive. Missing widths do not enter the average or histogram; only completed recordings contribute measurements.

All empty averages are null. No fabricated production data. The frontend offers an explicitly labeled opt-in synthetic demo dataset, separated from the real API, with uploads disabled. Published demos bundle no private video footage or stills. Initial real dashboard has proper loading/empty/error states. Use /dashboard?demo=1 for shareable demo preview and /dashboard for real data.

All POST routes require `X-Tide-CSRF`. Host/Origin/token validation occurs before reading the body. Upload accepts one file named `file` and only the documented unique text fields; duplicate/extra parts are rejected. File bytes are bounded during multipart parsing; a separate total-body bound includes a limited form overhead allowance and applies to chunked requests. Oversize requests return 413 without creating a job; malformed inputs are rejected and temporary files are closed. Unsupported date boundaries return 422; invalid byte ranges return 416. Transport cancellation does not guarantee a committed job has been canceled: clients should check the recording list if the submission outcome is unknown.

Browser video/image elements and download navigation may send `Sec-Fetch-Site: cross-site` without Origin when the frontend uses `127.0.0.1` and the API uses `localhost`. Only known read-only video/thumbnail/artifact GET/HEAD paths permit this browser shape. Session access, mutations, and other API paths retain the cross-site check; an explicitly untrusted Origin is always rejected. This exception does not grant authentication or access to arbitrary filesystem paths.

## Worker and storage

PostgreSQL durable queue; worker process claims queued job and executes existing Python CLI without shell. Local paths resolve from `web/`: `ANALYZER_ROOT=../tracking`; `ANALYZER_PYTHON` can override the interpreter, otherwise it selects `tracking/.venv` when present. `STORAGE_ROOT=./storage`. Keep uploads/output out of Git. Separate worker CLI supports --once for deterministic testing. Inbox accepts finished videos only after an explicit `.ready` marker, prevents duplicate ingestion, and supports same-stem JSON metadata. Capture worker heartbeat and recover stale jobs conservatively (don't reclaim a live long job). Export browser-ready H.264 MP4 and thumbnail using ffmpeg. API does not execute inference in the HTTP request.

Scope: local/internal trusted deployment. No login yet; bind local services to localhost and document authentication/reverse proxy required before public hosting.

## AI analysis

All routes below start with `/api/assistant`. Successful responses use `Cache-Control: no-store`; POST requires the same CSRF header as uploads. JSON requests are limited to 16 KiB before parsing, with no extra fields accepted.

| Method / path | Request / response |
| --- | --- |
| GET `/capabilities?demo=1` | Provider readiness, model, actual Taipei `today`, available ponds/date range, supported templates and `statistical_methods`. No model call. |
| GET `/conversations?demo=1&limit=30` | `{items: Conversation[]}`; real and demo lists are separate. Limit 1–100. |
| POST `/conversations` | `{demo: boolean}` → Conversation (201). |
| GET `/conversations/{uuid}` | Conversation plus ordered `messages`; up to 20 question/answer pairs. |
| POST `/conversations/{uuid}/messages` | `{message: string, request_id: UUID}` → assistant Message (202). Trimmed question 1–2000 characters. Same ID/question returns the existing run; same ID/different question returns 409. |
| POST `/messages/{uuid}/cancel` | Stops an active run and returns its current Message. Already finished runs are unchanged. |

Conversation: `{id,title,demo,created_at,updated_at}`. Message: `{id,role,content,status,response_kind,created_at,board,followups,error,activity}`. `response_kind` is `pending|answer|analysis`: pending means not yet classified, answer keeps the current canvas, analysis updates it. Only an active analysis response should replace the center with progress. Status can proceed through `planning → querying → answering → completed`; cached answers and clarification skip query/narration as appropriate. Terminal alternatives are `failed` and `cancelled`. Clients poll while active. Changing pages does not implicitly cancel server work. A narrative failure may retain a valid `board`; show it alongside the failure state.

`activity` is an ordered array of at most six persisted execution steps: `{id,kind,label,status,started_at,finished_at,detail,metadata}`. Kind is `context|plan|query|charts|answer|complete`; step status is `running|completed|failed|cancelled`. `finished_at` is nullable, timestamps are ISO 8601. Metadata contains application-owned context, validated query fields, or computed sample/chart counts. It never contains model reasoning, prompts, SQL, or credentials. A chart step means chart data was computed, not that a particular browser has rendered it. The completion summary reports actual jobs/tracks/chart counts; clarification explicitly reports that no measurement query ran. Legacy messages return `activity: []` without invented history. Activity is batched with conversation reads and survives restart in the additive `assistant_activity` table.

On initial entry clients load the catalog/history list without selecting a conversation. A new question first shows progress in chat. Only a confirmed `response_kind=analysis` replaces the center with processing; text answers and clarification retain the existing board. The right conversation panel fills the viewport height, with messages independently scrollable. Progress describes actual stages and elapsed time, not estimated percentages.

Board contains the validated periods/ponds/aggregation, KPIs, up to eight charts, period sample counts, limitations, and bounded source-video references. Chart templates and exact shared frontend types are defined in `frontend/src/lib/assistant-types.ts`; model-plan schema is in `backend/app/assistant/schemas.py`. The model cannot supply executable chart code or arbitrary SQL. All measurements are computed by the application from completed jobs. `observed_ponds: {count,labels,labels_truncated}` reports actual completed-video coverage for the query union and within each `period_summaries` entry; counts are complete, labels are capped at 30. `query.ponds` is selected scope, not observed coverage.

Plans also contain `presentation: answer|board` and up to six `statistics` requests. A statistics-only board may have zero charts. `board.statistics` contains method/status, metric(s), sample unit, group summaries, labeled values, warnings and a nullable reason; `board.descriptive_summary` retains full per-period summaries for follow-ups. Supported methods are descriptive, Pearson, Spearman, Welch t and Welch ANOVA, exposed in capabilities as `statistical_methods`. See [statistical methods](statistical-methods.md) for request fields and sample rules.

The additive `assistant_results` table persists validated plans, presentation and trusted computed facts separately from the displayed board. Text-only queries save facts but return `board: null`; this never means clearing the previous canvas. The public message endpoint exposes presentation through `response_kind`, not the internal facts object. Legacy boards remain viewable without migration or invented event history.

One active run per conversation (409 otherwise), configurable global concurrency (429 when full), disabled/unconfigured model (503). API restart marks interrupted runs failed. This implementation requires a single API process; use a shared task queue before adding replicas. Demo measurements are synthetic/in-memory, but demo conversations and boards are persisted separately and still use model quota. Configuration and project skills: [AI analysis](ai-analysis.md).
