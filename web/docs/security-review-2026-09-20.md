# Code and security review — 2026-09-20

This is the historical review of the standalone `shrimp-observatory` application, now under `web/` in this monorepo. Scope: Next.js, FastAPI, worker/file handling, PostgreSQL configuration and launch scripts. The nine original findings were fixed the same day. Original locations/line numbers below describe the pre-fix version; current source and the fix table take precedence.

Private videos, databases, credentials and `.local` evidence are not part of publication. This report does not claim that translation/publication repeated scans or penetration testing. See [validation](validation.md) for later work.

## AI feature review

- Models produce bounded JSON plans. Pydantic/data tools allowlist metrics, dates, templates and counts; arbitrary SQL, Python, HTML, URLs and file paths are not executable inputs.
- Official OpenAI SDK: no tools, no automatic retry, `store=false`. The pinned Codex adapter ignores personal settings/rules, strips environment secrets and disables shell/web/MCP/apps/plugins/browser/image. Its restricted catalog removes patch capability; prompts are not the execution-permission boundary.
- Host/Origin/CSRF protection remains, with 16 KiB JSON limits, 20 questions per conversation and idempotency IDs. The backend computes numeric results.
- Fixed premature concurrency release, repeated-cancel cleanup and Windows blocked-stdin deadline handling. Isolated real threads/process trees and nonreading-stdin processes exercised these paths.
- React escaping, renderer allowlists and CSV formula protection remain. Each HTTP request has a 30-second deadline; retries retain their request ID.
- One trusted-local API process remains the deployment boundary. No multi-user accounts/record authorization exist. Model prose is not checked numerically sentence by sentence; users can inspect source data and charts.

The dependency-scan numbers below belong to the earlier pre-SDK review, not a fresh scan after adding AI dependencies.

## Fixes and acceptance evidence

| Finding | Implemented fix | Evidence |
| --- | --- | --- |
| SEC-01: late upload limits | Pre-body Content-Length/stream totals; per-file, header, five-field and duplicate checks during parsing; cleanup of temporary/uncommitted data | [Request tests](../backend/tests/test_request_security.py): chunked, overflow, extra files, disconnect, cancellation, truncation, disk-spooled files |
| SEC-02: cross-site job creation | Host allowlist, Origin checks, session endpoint and CSRF header; frontend/Swagger/CLI support | Rejected before body read: 403; bad Host: 400; trusted frontend still receives errors |
| BUG-01: stale lists | Poll every 15 seconds idle/4 seconds active; focus refresh, pond sync and retry after errors | [Recording tests](../frontend/tests/recordings-filters.test.cjs) |
| BUG-02: misleading cancellation | Separate preparation, transfer and commitment; `upload.onload` ends transfer; unknown outcomes require list inspection before retry | [Lifecycle tests](../frontend/tests/api-lifecycle.test.cjs), including token-fetch cancellation and late responses |
| BUG-03: failed startup overwrites .env | Verify port/cluster/connectivity/database, then atomic update; preserve original on failure | [13 script scenarios](../scripts/tests/test-local-db.ps1), PowerShell 7.6.5 and 5.1 |
| BUG-04: silent database fallback | Require DATABASE_URL; remove known default credentials | Missing-configuration fail-fast test |
| BUG-05: boundary 500s | Date/timezone overflow → 422; bounded Range parsing → 416 | [API tests](../backend/tests/test_api.py), plus live date rejection |
| P3: stale invalid date draft | Recreate date field when clearing, even if parent value was already empty | Hook tests and browser invalid-date reset |
| P3: missing password encoding guidance | Document URL encoding; helper encodes special characters | [README](../README.md), successful script scenario |

Cross-review also fixed partial storage files after cancellation during copying, and legitimate native media/download requests rejected by cross-site checks. The read-only exception is limited to known UUID video/thumbnail/allowlisted-artifact GET/HEAD routes. Session, JSON API, mutations and explicit untrusted Origins remain protected. UTF-8 BOMs were added to two PowerShell launchers for 5.1 parsing.

Historical final acceptance:

- **63 backend and 15 frontend tests passed**, with lint, TypeScript and production build.
- **13 isolated database-helper scenarios** and both script parsers passed on PowerShell 7.6.5/5.1, without operating real PostgreSQL.
- A private clip through the new API, isolated SQLite/storage and existing analyzer produced six IDs: length 90.350 mm, width 19.183 mm, weight 4.267 g, water turbid. These were uncalibrated estimates. Range, thumbnails, CSV/JSON and date boundaries passed.
- Browser token/form validation, invalid-date clearing, existing playback (`readyState=4`, width 990px, no media error) and CSV download succeeded.
- API/database/worker were healthy after restart; the five existing PostgreSQL jobs/30 per-video IDs remained. Invalid-pond POST created no record.

Evidence was stored under `.local/review-fixes/integration-result.json` and `live-check.json` in the original application. Earlier `.local/review/` scripts reproduce **pre-fix** behavior and may intentionally fail after fixes; use maintained tests for regression checks.

## Original security findings — fixed, retained for provenance

### SEC-01 / P1: multipart body already received before the size check

Historical location: [main.py](../backend/app/main.py), lines 98 and 119–123.

FastAPI's `UploadFile = File(...)` parsed multipart before the handler. Its size check limited copying from the already-received temporary file to storage, not network receipt/spooling. Unused extra file fields were also parsed.

Isolated reproduction: with a 128-byte limit, a 16,384-byte upload returned 413 only after all bytes were parsed. A one-byte `file` plus a 16,384-byte `ignored` file returned 202 after both were parsed. The installed parser allowed 1,000 files; its 1 MiB threshold meant disk spooling, not a file-size limit.

Impact: excess memory/temp-disk consumption, including accidental large uploads. Only small payloads were used; no disk-exhaustion test occurred.

Required remedy: bound ASGI receipt before parsing, including missing Content-Length/chunked bodies; allow one file and bounded fields; retain a second per-file bound and clean temporary files on failure. The installed Starlette offered `RequestBodyLimitMiddleware` as a candidate at the time; the implemented protection is described above.

### SEC-02 / P1: untrusted Origin could create jobs

Historical location: [main.py](../backend/app/main.py), lines 61–62, 97–100 and 157–158.

CORS controlled response reading, but did not validate Origin/authentication/CSRF before upload/retry. A request with `Origin: http://evil.example` and `Sec-Fetch-Site: cross-site` returned 202 and created a queued job; retry of a known failed job also returned 202. Lack of ACAO did not undo the write. Arbitrary Host reads succeeded without an allowlist.

Impact: an untrusted page whose request reached the local API could consume storage/inference resources without knowing an existing job ID.

This demonstrated server behavior, **not bypass of every browser's local-network protections**. Browser Local Network Access, mixed-content or DNS checks may block requests first; they are not server authorization. References: [MDN simple CORS requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#simple_requests), [local network access](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Local_network_access).

Required remedy: reject untrusted/null Origins before body parsing, validate a token for intended clients and restrict Host. A same-origin proxy would still require deliberate login/CSRF design. Trusted frontend/CLI compatibility must remain.

## Original functionality/reliability findings — fixed

### BUG-01 / P2: idle recording lists did not refresh

Historical [recordings.tsx](../frontend/src/components/recordings.tsx), lines 38–43. Polling continued only while that page already contained queued/processing jobs. Empty/completed lists missed inbox/other-window arrivals and work on other pages; pond options loaded only on mount. An isolated Node test observed no next timer. Remedy: slower idle polling, focus refresh and pond synchronization, tested from an initially empty list.

### BUG-02 / P2: “cancel upload” did not cancel committed analysis

Historical [upload.tsx](../frontend/src/components/upload.tsx), lines 247–263; [api.ts](../frontend/src/lib/api.ts), lines 73–76. After 100% transfer and server commitment but before response arrival, UI still offered cancellation. `xhr.abort()` was reported as cancellation although no backend job stop occurred. An isolated XHR reproduction showed potential duplicate resubmission/measurement counts. Remedy: distinguish transfer/commitment, stop offering transfer cancellation after upload completion, and require list inspection for unknown outcomes. Client idempotency or true worker cancellation were separate proposed extensions, not features claimed by this fix.

### BUG-03 / P2: failed database startup overwrote valid configuration

Historical [local-db.ps1](../scripts/local-db.ps1), lines 41–47. The helper wrote `.env` before startup/connectivity/database checks. Fake `pg_ctl`/`psql` in a temporary folder reproduced a valid 55432 URL changing to 55499 despite failure; real PostgreSQL was untouched. Remedy: validate first, then atomic replacement, covering running-old-port, connection and createdb failures.

### BUG-04 / P2: missing DATABASE_URL silently selected another database

Historical [config.py](../backend/app/config.py), line 36. Known fallback credentials `tide:tide` on 5432 differed from the helper's 55432; a coincidentally matching database could receive initialization/writes. Static inspection/URL parsing established this; no other database was contacted. Remedy: fail explicitly without DATABASE_URL; tests supply their own URL.

### BUG-05 / P2: syntactically valid boundary input caused 500

Historical [storage.py](../backend/app/storage.py), lines 44 and 71–73. `end_date=9999-12-31` overflowed when computing the following day. Excessive Range digits exceeded Python's integer-string conversion limit. Isolated API tests produced 500; no privilege escalation or whole-service outage was demonstrated. Remedy: supported date bounds/overflow handling, bounded Range digits and 422/416 responses.

### Lower-priority findings

- **P3 invalid date draft:** [date-field.tsx](../frontend/src/components/date-field.tsx), historical lines 73–81, and [filters.tsx](../frontend/src/components/filters.tsx), line 50. With an already-empty parent date, entering `2026-02-30` then clearing filters left the internal draft. Isolated hooks reproduced it; explicit reset key/token resolved it.
- **P3 password guidance:** historical [README](../README.md), line 55, omitted URL encoding of reserved password characters such as `@`. Documentation and helper handling were added.

## Pre-fix baseline and limits

| Check | Historical result |
| --- | --- |
| Backend pytest | 24 passed; two test-framework deprecations |
| Frontend typecheck/lint | Passed, including additional source/config diagnostics |
| `npm audit --json` | Zero known vulnerabilities; dependency metadata total 446 |
| `pip-audit -r backend/requirements-lock.txt --no-deps --disable-pip` | 34 pinned versions, zero known vulnerabilities, zero skipped |
| SQL/path/export tests | Injection-shaped pond name did not bypass filtering; traversal kind → 422; disallowed artifact → 404 |
| XSS | Reviewed names escaped by React; malicious HTML did not execute; no `dangerouslySetInnerHTML` found |
| Private data | Ignore rules covered .env/.local/storage/weights; inspected credential-file ACL lacked broad Everyone/Users/Authenticated Users read grants |
| Demo fallback | No automatic replacement of failed real API results with synthetic data |
| Worker isolation | HLS disguised as MP4 did not decode; a local timeout test did not observe continued child writes; neither hypothesis was reported as a vulnerability |

Scans reflect vulnerability databases at that time, not proof of safety. Bundled FFmpeg was 7.1; npm/pip scans were not a full native-decoder audit. No load/disk-exhaustion testing, public penetration test, exhaustive browser-policy review, model-accuracy or biomass calibration validation was performed.

Ignored local evidence names: `backend_api_audit.py`, `backend-api-audit-results.json`, `frontend-audit.cjs`, `frontend-audit.results.json`, `frontend-audit.notes.md`, `worker_audit.py`, `worker-audit-results.json`, `pip-audit.json`. Frontend evidence included SHA-256 values and simulation boundaries. Reproductions used isolated SQLite/temp files and did not submit jobs to the running worker.

All nine findings above were fixed. Public-deployment authentication, data authorization and quotas remain unimplemented requirements, not completed protections.
