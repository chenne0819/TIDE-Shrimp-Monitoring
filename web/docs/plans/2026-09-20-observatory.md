# Shrimp Observatory implementation plan — historical, 2026-09-20

**Goal:** Build a separate Next.js/FastAPI/PostgreSQL application for uploaded shrimp videos, reviewable outputs and daily measurements.

**Original architecture:** Next.js App Router serves a scroll-driven landing page and dashboard; FastAPI saves uploads and durable PostgreSQL jobs; a separate worker invokes the existing analyzer, imports CSV and prepares browser media. The original task did not modify inference. The published monorepo now places that integrated analyzer in `tracking/` and the application in `web/`, with `ANALYZER_ROOT=../tracking` relative to `web/`.

**Stack:** Next.js, TypeScript, React, Motion, Recharts, FastAPI, SQLAlchemy, PostgreSQL, Python subprocess and FFmpeg.

## Planned work and verification

1. Define [the API contract](../api-contract.md); separate backend/frontend.
2. Implement configuration, persistence, upload/list/detail/overview/media endpoints, worker/inbox and failure, aggregation, queue, traversal and file tests.
3. Create an aquatic landing page with original imagery and scroll transforms; connect real API dashboard, filters, upload/progress, charts, playback, CSV and visibly separate synthetic demos.
4. Provide portable environment examples, Compose, Python/npm setup and optional Windows launchers.
5. Test/build, start isolated PostgreSQL, upload an actual short video, run the worker, verify data/media ranges, review desktop/mobile and fix problems.
6. Document exact evidence and remaining deployment requirements, retaining a local preview. The original task did not publish the site.

Design direction: aquatic research/farm monitoring, cinematic observation illustrations, large Traditional Chinese text, deep teal/mist-white surfaces and a lime accent. Landing variance/motion/density: 7/6/3; dashboard: 4/3/6. Include reduced motion, rounded rectangles, contrast and truthful data/status labels.

## Original completion record

All six steps were completed in the then-separate `shrimp-observatory` folder. **23 backend tests passed**; frontend lint and production build passed. Actual PostgreSQL runs covered general, head/tail, prediction, inbox and browser upload. Desktop/mobile review, H.264 playback, CSV and portable settings were checked. A custom HTML calendar resolved embedded-browser native-picker compatibility; date selection and empty/single-day results were verified.

See [validation](../validation.md) for later stages and exact limitations. “Local preview available; no public deployment” described that historical delivery, not today's hosting status. Private test footage/database records are not included in publication.
