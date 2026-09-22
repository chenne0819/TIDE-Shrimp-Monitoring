# AI workspace review and cleanup

Historical review dated **2026-09-20**, covering chat, execution records, collapse/resize, overview routing and code usage in the original standalone application. This publication translates the record; it does not rerun or reassert those historical checks. The earlier security review is [separate](security-review-2026-09-20.md).

## Actual model connection

At review time the local API reported `enabled=true`, `provider=codex`, `model=gpt-5.6-terra`. Real HTTP/model queries, database computation and persisted results used the owner's logged-in Codex quota. The OpenAI Responses adapter existed but was not exercised with a real API key in this round. See [configuration](ai-analysis.md).

The model interpreted questions, selected bounded plans and narrated computed results. These were not canned answers; arbitrary model-generated SQL/code was not permitted.

## Findings and fixes

| Finding | Fix |
| --- | --- |
| Explicit text-only requests could still update the center | Application presentation override retains necessary internal aggregates; negated phrases such as “do not use only text” are not misclassified |
| Overview fallback could merge ponds across periods | Preserve pond categories and period series; video-mean statistics do not acquire incompatible track-level distributions |
| Two observed ponds were described as four because four filters were selected | Compute overall/per-period `observed_ponds`; update persistent facts, follow-up prompts and project skills |
| Hidden mobile chat dimensions damaged scroll restoration | Measure only visible chat; retain reading position and remeasure multiline drafts after width changes |
| Viewport changes during a drag overwrote desktop preferences | End drag/release pointer capture before clamping width; identical width notifications do not reset dragging |
| Text-only completion assumed an existing board | Use wording that does not assume an earlier panel exists |

Observed pond counts use all matching completed videos, with at most 30 labels and an explicit truncation flag. Overall coverage is a period union; each period is separate. Old answers remain unchanged, and old facts missing coverage cannot infer it from filters.

## Cleanup evidence

- Removed two fully overridden landing CSS rules and styling for a removed title icon.
- Removed the unused `close_stdin` argument/branch in process stopping, retaining stream cleanup after I/O completion.
- Enabled TypeScript `noUnusedLocals` and `noUnusedParameters`.
- Corrected demo persistence/date documentation, stale test counts and historical-plan descriptions.
- The **historical** usage audit found all 36 frontend modules reachable from seven Next page/layout entries and all eight then-public assets referenced; no whole module, dependency or script could safely be deleted. Plans, tests and original generated assets remained useful. No owner video, model or conversation was removed.

Publication change: the two private demo media files are now excluded; the historical eight-asset audit is not a claim about the published inventory. See [assets](assets.md).

## Historical validation

- Backend: **288 passed**, with the existing Starlette/httpx and AnyIO deprecation warnings.
- Frontend: **148 passed**; ESLint and production build including TypeScript passed.
- Three real-model questions: today's overview produced three histograms; month-to-month width comparison stayed text-only; an explicit bar-chart request returned four pond categories and two period series, with missing prior-month values null. The first question exposed the pond-count narration error.
- Repeating the original today's-overview question after the fix correctly reported two ponds, two videos and 12 IDs, with three charts and three statistical results: mean length 90.4333 mm, width 19.2333 mm and weight 4.25 g.
- Browser checks: multiline drafts remeasured after 440→320px chat resizing; 390×844 mobile tab switches retained reading position without page-level horizontal overflow. Normal-operation console had no errors/warnings. Test drafts were cleared and width, viewport and original conversation restored.
- Frontend/API were rebuilt or restarted at that time. Ignored local evidence: `.local/assistant-review-smoke.json` and `.local/assistant-review-pond-fix.json`, relative to the former app root, now `web/` for analogous runs.

The private videos were workflow-validation inputs, not calibrated farm measurements. They and their database/evidence files are not published. This was neither exhaustive natural-language coverage nor a penetration test; model prose still needs comparison with chart/source values.
