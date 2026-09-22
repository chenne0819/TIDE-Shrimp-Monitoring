# AI analysis implementation plan — historical, 2026-09-20

This records the initial plan for the standalone application, now located under `web/`. Current behavior is documented in [AI analysis](../ai-analysis.md): confirmed new visual analyses show progress; text-only follow-ups retain the existing board.

Objective: add natural-language analysis, multi-chart results, follow-up questions and persistent chat using FastAPI, PostgreSQL, Next.js and Recharts.

1. Define bounded plans in `web/backend/app/assistant/schemas.py` and frontend result types in `web/frontend/src/lib/assistant-types.ts`. The model selects queries/templates; code computes numbers.
2. Implement Taipei dates, period/pond filters, completed-video/valid-ID aggregates, ten chart templates and KPIs in `analytics.py`. Test boundaries, null/nonfinite values, empty data, denominators and limits.
3. Store skills under `web/agent/skills/`; support official OpenAI SDK and local Codex login with server-managed configuration/errors/cancellation/deadlines.
4. Add chat tables and `/api/assistant`, retaining CSRF/Origin checks, idempotency, states, cancellation, history and bounded content. No arbitrary SQL/code/local paths.
5. Build `/assistant` with center results, right chat, sources, chart/table switches, CSV and examples; use mobile tabs. The initial plan retained old results during generation; later refinement replaced this with the conditional-progress behavior above.
6. Run backend data/security checks, frontend tests/lint/typecheck/build and desktop/mobile review; use the owner's authorized account for actual model tests.

References and configuration are consolidated in [AI analysis](../ai-analysis.md). Project skills are not installed globally. This historical plan is not evidence of a publication-time test run.
