# Historical local validation record

**2026-09-20 — Windows, Python 3.12, Node.js 24.13, PostgreSQL 18.4.**

This preserves the original standalone application's validation history, including stage-specific counts and limitations. The application is now `web/`, the analyzer `tracking/`, and `ANALYZER_ROOT=../tracking` resolves from `web/`. Translation/publication does not imply rerunning these checks. Private footage, stills, databases and ignored `.local` evidence are not published. Demo statistics are synthetic.

## Upload-page split layout and typography

Removed the observation-tip card and its dedicated icon/function/CSS. Desktop places video drop on the left and capture metadata, settings, progress/errors and submission on the right, within one form. Both fieldsets respect demo/upload disabled state and retain cancellation/unknown-outcome protection.

Headings: 22px; labels: 16px; ordinary inputs: 17px; dates: 16px; supporting text: 14px. Mobile stacks video, information and submission; obsolete small-text overrides were removed.

The existing **nine upload lifecycle tests**, modified-component ESLint, formatting and production build including TypeScript passed. Browser checks covered 1440/1280px two-column and 390px single-column layouts, calendar placement, missing-video validation and both disabled demo columns. No page-level horizontal overflow or normal-operation console errors/warnings; no new video job was created.

## Translucent landing navigation

Navigation became a 50% dark-green overlay with 14px blur and a thin border; expanded mobile menu uses 82% dark green. Imagery begins at the page top, with hero copy reserving navigation height.

Production build including TypeScript passed. Browser checks at 1440×900 and 390×844 covered mobile menu toggling, Canvas loading and scroll motion without page-level overflow or console errors/warnings. This was CSS/documentation work; unrelated AI/backend suites were not rerun.

## AI workspace review and cleanup

**288 backend / 148 frontend tests passed**, plus ESLint, TypeScript and production build. Fixes covered text-only routing, cross-pond chart fallback, mobile scroll, resizing preferences, dead branches and obsolete CSS.

Actual Codex `gpt-5.6-terra` covered today's overview, month comparison in text and pond comparison charts. Selected-pond count was incorrectly narrated as observed count; after adding computed coverage, the same question correctly reported two ponds, two videos, 12 IDs and three distribution charts. No real OpenAI API-key call occurred in this round. See [review details](review-cleanup-2026-09-20.md). Earlier counts below describe their own stages.

## Collapsible chat sidebar

Collapse/restore controls retain mounted messages, drafts, result and width, transferring keyboard focus to visible controls. Restoring remeasures input height; hidden zero-height containers cannot overwrite reading position.

**144 frontend tests**, ESLint and production build including TypeScript passed. At 1440px, center width expanded 768→1216px and chat restored to 440px. A 320px chat header did not overflow. At 390px, collapse/restore and cross-size transitions worked without page overflow. Test drafts were unsent/cleared; no model call occurred; normal-operation console was clean.

## Detail typography and execution-record placement

Recording labels became 16px; measurements 24px desktop/22px mobile; units 15px; explanations 14–15px. Per-ID/source sections were adjusted too. Production CSS and 1280/390px layouts were inspected; mobile summary rows remained contained.

Execution records moved above answers, collapsed to the last two actual steps, with mouse/keyboard expansion and completion below the answer. Three historical answers were checked for DOM order and desktop/mobile Enter toggling, without duplicate summaries or overflow.

**143 frontend tests**, ESLint, TypeScript and production build passed, including order and active-step regressions. No model call or query logic changed; the frontend was rebuilt/restarted.

## First overview failed to create charts

The original question asking how today's measurements looked produced only text because routing overrequired explicit chart requests. The preceding ten real-model scenarios had not included this first-question overview.

Planner instructions, skills and presentation checks were changed: overview defaults to charts; fallback uses validated dates/ponds and preserves pond groups. A bare answer may be replanned once rather than guessing scope. Explicit text, explanations and scalars do not force center updates, and text-only completion no longer assumes an existing board.

- Full backend: **266 passed**. Independent review added **eight boundary cases**, then **69 relevant tests passed**, including **32 overview regressions**.
- Full frontend: **141 passed**, covering empty center → confirmed-analysis progress → first board → text follow-up retention, and statistics-only first results. Only the two existing dependency deprecations remained.
- Fresh real Codex conversation: the original question, without mentioning charts, produced three length/width/weight histograms, two videos and 12 IDs. Maximum-width and explicit-text follow-ups created neither a new panel nor a new measurement query. Evidence: `.local/assistant-overview-fix.json`.
- The original conversation was also retested through the production page: narration progress, three real SVG histograms, three descriptive results and five KPIs appeared. Maximum-width follow-up retained all charts without a center spinner. Earlier missing-chart history was not rewritten. Evidence: `.local/assistant-overview-ui-fix.json`.
- `scripts/evaluate-assistant.py` gained the first-overview case, bringing its scenario catalog to **11**. Only the targeted actual-model checks above ran in this stage, not all ten earlier cases again. Inputs remained workflow-validation estimates, not accuracy-calibrated farm data.

## Routing, resizable layout and statistics

- **242 backend / 139 frontend tests passed**, plus TypeScript, ESLint and production build. SciPy 1.18.1 and NumPy 2.5.3 were added to ranges/lock; `pip check` passed. Two existing Python test deprecations remained.
- Five methods: descriptive, Pearson, Spearman, Welch t and Welch ANOVA. **49 statistics tests** used known values, independent formulas and numerical integration, covering missing/pair/tie/unit/constant/overlap/numerical-limit/full-data cases. Existing ten-template calculations/renderers continued to pass.
- **17 routing regressions** covered trusted-cache answers, width focus, legacy recomputation, text queries, statistical cards, avoiding unnecessary charts, cancellation/timeouts/failures. Water/sex/trend aggregates missing from narrator input were restored. Structured-output schemas made every property required while retaining nullability, without mutating caller schemas.
- Actual logged-in Codex `gpt-5.6-terra`: **10/10 end-to-end scenarios** passed: width box plot → maximum → explanation → prior-month numbers without charts → histogram → descriptive statistics → Pearson/Spearman plus scatter → Welch t → ANOVA plus box plot → unsupported Cox analysis. Cached maximum used no model/new query; explanation only used the planner/answer route; changed-month text queried with `response_kind=answer`; new boards returned `analysis`. Cox correctly lacked survival/event data and invented no hazard ratio.
- Synthetic reference values: current-month maximum width **17 mm**; correlation used **787 complete pairs** while scatter displayed **500**. Welch t video samples were **40/62**. Two-pond ANOVA used **20 videos each**, distinguished from adjacent box plots' **388/403 IDs**. These were test data, not accuracy/experimental-design validation.
- At 1600×1000, chat top=0/height=1000; drag 440→626px, Home=320, ArrowLeft=336 and End=760 were observed, with width retained after refresh. At 1280×711, maximum chat width clamped to 688, leaving center ≥360. At 390×844, chat/examples/tabs worked without page-level overflow. Chart columns adapt to actual center width.
- During text follow-up, the old box plot stayed visible without a center spinner; new statistics showed real narration stage/elapsed time. Cards displayed units, valid samples, missing p-values and limitations; small p-values used scientific notation. React-escaped text supports basic bold/lists, not model HTML or arbitrary links.
- All five method cards were opened in production and rows/p-values/expandable limits inspected. Mobile statistics tables scrolled within their own container (890px content, 322px container), while the page stayed 390×844 with outer scroll 0. Normal console was clean; bold measurement text rendered correctly.

Rerun from `web/` with `python -X utf8 scripts/evaluate-assistant.py` against a running API; it consumes model quota and saves demo conversations. Historical output: `.local/assistant-routing-eval.json`. This is not exhaustive language/browser/method coverage. OpenAI API-key mode remained isolated-test-only. CSV limitations below remain relevant.

## Chat layout and persisted activity

- Full backend **175 passed**, frontend **118 passed**, covering activity persistence/failure/cancel/restart, ten-template renderer/CSV, initial empty state and polling races. Two dependency deprecations remained.
- TypeScript, ESLint and production build passed. The additive `assistant_activity` table initialized in existing local PostgreSQL without changing old conversations/boards; legacy activity stayed empty.
- A real model request through the production page showed the then-current immediate center spinner, elapsed time and planning→narration stages. Expanded records showed real context/plan/query/chart counts. Completion reported two videos, 12 IDs and four charts; reload retained six completed steps. Later routing changed initial-center behavior as described above.
- A subsequent browser question was cancelled during planning: completed context and cancelled plan remained, with no fabricated chart/completion steps. Spinner stopped, prior results were identified, and model temporary files were cleaned.
- Fixed new-conversation clearing of capabilities/errors during incomplete/failed initialization, and cancellation races from pending polls/late responses; deferred-transport tests covered both.
- Browser sizes: 1280×711, 1600×1000, 390×844. Chat filled space below the then-present navigation/demo marker; composer stayed visible, center/messages scrolled independently. A positioned table-caption container fixed page-height/scroll displacement. Outer scroll remained 0.
- Existing real-model demo conversations supplied all ten templates. Every chart/data switch was checked against actual SVG/HTML, series and columns; mobile tabs, activity expansion, example insertion and new empty conversations were exercised. No normal-operation console errors/warnings. This was manual browser QA, not every hover/browser or pixel snapshots.
- CSV temporary anchors and Blob URL cleanup passed normal/error tests, alongside all-template content/unit/formula-escaping checks. In this particular embedded-browser round, clicking produced neither a download event nor a file in default Downloads: **download-to-disk was not verified**. Browser limitation versus compatibility was unresolved; this does not erase the earlier successful download below.

Automated chart checks covered cross-period/null curves, area/bar groups, stacked totals, shared histogram bins, mm/g scatter pairs, five-number boxes, daily-by-pond heatmaps, video-category proportions and all table/CSV row-column mappings. Node tests checked Recharts props/data and custom SVG/HTML, not browser pixels. Evidence: `.local/assistant-refinement-smoke.json`.

## Initial AI workspace

- Full backend **160 passed**, covering ten charts, dates/missing values/denominators/bounds, order/idempotency/cancel/timeouts/CSRF/body size. Final chart-description/schema changes reran **67 relevant tests**, passing.
- Full frontend **57 passed**, covering conversation switches, deadlines, idempotency, cancellation, polling, nulls and CSV formulas. TypeScript, ESLint and production build passed.
- Actual model calls used local ChatGPT login, pinned Codex **0.155.1** and `gpt-5.6-terra`; no canned answer was counted as a model test. OpenAI Responses used isolated mocks, not an actual key.
- A synthetic cross-month request generated seven dimension-comparison charts; follow-up width boxes preserved **9/1–9/20 and 8/1–8/31**.
- Another request generated area, bar, stacked, heatmap, length/weight scatter, donut, box and table, jointly exercising all ten renderers.
- Follow-up daily-by-pond heatmap returned **20×2=40 cells**; pond/sex stacks returned A-01/B-02 bars. Grouping skills were strengthened.
- A browser question against real local records for **2026-09-20** returned two completed videos/12 IDs, mean length **90.4333 mm**, width **19.2333 mm**, weight **4.25 g**. Independent per-ID API averaging matched. These were initial workflow records, not calibrated farm measurements.
- Conversations/boards persisted and reloaded; synthetic measurements created no real video jobs.
- Production browser checked 1600px layout and 390×844 tabs/history/tables/CSV. CSV actually appeared on Windows with verified A-01/B-02 values despite no tool download event; it was moved to ignored `.local/assistant-smoke-chart.csv`. No page overflow or normal console errors/warnings.
- Real Windows process tests covered parent/child tree termination, large blocked-stdin timeout/cancellation and repeated cancellation, with no leftover model/I/O thread. SQL-thread cancellation retained concurrency capacity until cleanup.

Model prose could still misinterpret grouping; code computed chart values. No sentence-by-sentence numeric verification was claimed.

## After the initial security fixes

- **63 backend / 15 frontend regressions passed**, with lint/typecheck/build; no dependencies were added in that stage.
- Unauthorized requests were rejected before reading bodies. Oversize, extra/duplicate parts, chunking, disconnect and cancellation left no uncommitted job; disk-spooled cancellation was covered.
- **13 database-helper scenarios** and both script parsers passed on PowerShell **7.6.5/5.1**, using fake executables rather than real PostgreSQL.
- A private one-frame general-tracking clip through isolated SQLite/storage produced six IDs: **90.350 mm length / 19.183 mm width / 4.267 g weight**, turbid. Source/result MP4 Range, thumbnail and exports passed; accuracy remained unvalidated.
- Cross-review fixed partial copied-file cleanup and native media/thumbnail/download requests lacking Origin. Only known read-only artifact paths were exempted. Reloaded playback had readyState=4, width=990 and no media error; CSV succeeded.
- Invalid-date drafts cleared in-browser. Token-protected upload reached the expected pond-length validation error without creating a production job.
- API, worker and production frontend restarted healthy; existing PostgreSQL still held **five completed jobs / 30 per-video IDs**, mean width **19.190 mm**.
- See [security review](security-review-2026-09-20.md); ignored evidence: `.local/review-fixes/`.

## Initial backend and real-video workflow

- `python -m pytest tests -q`: **23 passed in 4.14 seconds**, covering upload size/name/cleanup, Taipei bounds, per-ID means, Range/HEAD, fail/retry, lease ownership, three CSV formats and inbox deduplication.
- Dedicated PostgreSQL and actual HTTP uploads invoked the existing analyzer, not fake models/APIs.
- General tracking: **8 frames / 6 IDs**, positive dimensions/weight, both videos returned 206 with MP4 headers, and thumbnails/exports were available.
- Inbox: video+JSON+`.ready`, head/tail mode **8 frames / 6 IDs**, marker became `.ingested`.
- Prediction: source limited to **3 frames**, default sampling every ten frames produced **one analyzed frame / 6 IDs**. Insufficient sex evidence remained Unknown.
- Three jobs had deliberately different test capture dates; daily statistics returned three days with six IDs each. Single-day filtering worked and illegal extensions were rejected.
- All three output modes supported Range. Input was a private **30-frame clip**; imagery was real, but dates/ponds were test labels.

Results remained in local PostgreSQL/storage; `.local/smoke-result.json` saved the first response. Those private inputs/results are not distributed. Equivalent analyzer paths now start at `tracking/`.

## Validation boundaries

This was short-clip workflow/data-integrity verification, not long-duration stress testing, accuracy validation or public-hosting assessment. PostgreSQL persistence and actual inference were exercised. Compose supplied portable configuration, but **no Docker container was started in that round**.

## Initial frontend/browser workflow

- Lint: zero errors/warnings; production build and TypeScript passed; preview used `next start`.
- Desktop and 390×844 checks covered landing, dashboard, detail/upload, scroll parallax, image crop, Chinese fonts and mobile menu, without page-level overflow.
- A browser-uploaded private clip to validation pond C-03, limited to eight frames, progressed to completed with **6 IDs / 8 frames**, saved in PostgreSQL.
- Detail playback: readyState=4, width=990, no media error; CSV click emitted a download event; source/annotated video switching worked.
- Pond filtering, trend metrics and reset were exercised. Synthetic demo labels were visible. API date errors remained errors, not substituted demo data.
- A custom HTML calendar replaced a native picker incompatible with the embedded browser. Desktop/mobile selection of **09/01–09/02** showed empty data; **09/19** showed one video/six IDs. `2026-02-30` failed form validation.
- After the calendar change, a one-frame upload saved validation pond D-04 at **2026-09-17 09:30 +08:00**, completed with six IDs and no error, bringing the historical local total to five completed test jobs.
- Demo submission was disabled with a real-workspace hint; normal-operation console was clean.

## Historical portability checks

Source/docs/launchers had no personal absolute paths. Relative model/storage settings resolved from the application root across working directories. Local Markdown links, PowerShell syntax and Compose configuration checks passed. Ignore rules covered private settings, weights, videos and database files. Publication changes the sibling names to `tracking/` and `web/`; the root publication record owns any new validation claims.

## Width overview addition

Width already existed in job/track records. Average, daily average and histogram were added to overview without schema changes or repeated inference.

- Backend suite became **24 passed**, covering equal-ID weighting, missing widths, excluding unfinished jobs, bin boundaries and null empty results.
- Five historical PostgreSQL jobs/30 IDs: mean estimated width **19.190 mm**; **16 IDs in 15–20 mm**, **14 in 20–25 mm**. On **09/19**, mean **19.233 mm**; no-data dates remained null.
- Frontend lint, TypeScript and production build passed. Both width selectors displayed **19.2 mm**, the daily curve and matching distribution. At 1440px five KPIs shared a row; 390px remained usable, with tables scrolling locally and measured page content width 375px. No page-level overflow or normal console errors/warnings.
