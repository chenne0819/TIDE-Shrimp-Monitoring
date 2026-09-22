# Review fixes implementation plan — historical, 2026-09-20

**Goal:** Fix all nine findings while preserving local operation and existing records.

**Architecture:** Validate Host/Origin/CSRF before upload parsing; bound total body, multipart fields and file size. The frontend obtains tokens and fixes polling, transfer state and date-draft reset. The database helper updates configuration atomically only after successful readiness checks.

**Stack:** Next.js/React/TypeScript, FastAPI/Starlette/SQLAlchemy, PostgreSQL, PowerShell, pytest and Node tests.

**Historical completion:** all work completed; **63 backend tests, 15 frontend tests and 13 PowerShell scenarios on both tested versions** passed, with production build, isolated real inference and post-restart browser checks. See [the review report](../security-review-2026-09-20.md). Counts are not publication-time reruns. Paths below resolve from `web/`; the analyzer now lives at `../tracking`.

## 1. API protection and boundaries

Files: `backend/app/main.py`, `config.py`, `storage.py`, new request/multipart modules and backend tests.

1. Reproduce missing token, bad Origin/Host, extra files, streaming overflow and date/Range errors with isolated SQLite.
2. Add noncached `GET /api/session` returning token/upload limit; require `X-Tide-CSRF` for all POSTs. This is local cross-site protection, not login.
3. Validate before body consumption; bound body and parsed file size; close temporary files on every failure without creating a job.
4. Require DATABASE_URL, return 422 for invalid dates and 416 for invalid ranges.
5. From `web/`, run `.\.venv\Scripts\python.exe -m pytest backend/tests -q`.

## 2. Frontend lifecycle

Files: `frontend/src/lib/api.ts`, upload/recordings/date-field/filters components and regression tests.

1. Test external arrivals into idle lists, cancellation while a 100%-transferred request awaits commitment, cancellation during token loading and clearing same-value invalid date drafts.
2. Fetch a token before mutations; a cancelled token fetch must not later send POST.
3. Poll idle lists slowly, refresh on focus and update pond options.
4. Separate completed transfer from confirmed commitment; report unknown outcomes honestly rather than claiming analysis cancellation.
5. Explicitly reset date drafts.
6. Run tests, lint, typecheck and build.

## 3. Database launcher

Files: `scripts/local-db.ps1`, `scripts/tests/`.

1. Use temporary directories/fake PostgreSQL executables to verify start/connect/createdb failures preserve `.env`.
2. Validate ports and cluster state; atomically replace configuration through a same-directory temporary file only after success, retaining unrelated settings.
3. Test successful writes and URL encoding for special-character passwords, without operating a real database.

## 4. Documentation and integration

Files: environment example, READMEs, API/security/validation docs and `scripts/smoke-test.py`.

1. Document token acquisition, Host/Origin configuration, password encoding and missing-database behavior.
2. Run a private short clip through isolated database/storage, confirming dimensions, weight, water and media output.
3. Verify jobs are idle before restarting API/frontend; retain PostgreSQL and its five existing records.
4. Browser-check normal flows, date reset and rejected requests without unintended writes.
5. Record each fix and evidence while retaining limitations: no multi-user login or public-deployment protections.

The private videos and local evidence from this historical plan are excluded from publication.
