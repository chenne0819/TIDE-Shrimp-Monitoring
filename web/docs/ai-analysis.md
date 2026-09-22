# AI analysis workspace

Open `/assistant` from the AI-analysis navigation item. Desktop shows results in the center and chat on the right; narrow screens switch between results and chat. Questions may request today's measurements, month-to-month length/width/weight comparisons, or a specific pond's width distribution, followed by further questions.

A response can produce up to eight charts and five KPIs (length, width, weight, tracked IDs, videos). Boards include dates, ponds, sample counts, aggregation, limitations and source videos, with table views and CSV export. PostgreSQL persists conversations and boards.

## Provider configuration

Edit `web/.env` and restart the API. See [.env.example](../.env.example); never expose keys in the frontend or Git.

| Setting | Meaning |
| --- | --- |
| `TIDE_AI_PROVIDER=disabled` | Shows configuration guidance; no imitation AI responses |
| `TIDE_AI_PROVIDER=codex` | Local testing with an existing ChatGPT/Codex login and that account's quota |
| `TIDE_AI_PROVIDER=openai` | Official OpenAI Python Responses SDK; requires `OPENAI_API_KEY` |
| `TIDE_AI_MODEL` | Model identifier; empty uses the configured provider default |
| `TIDE_AI_TIMEOUT_SECONDS=120` | Per-model-request deadline |
| `TIDE_AI_RUN_TIMEOUT_SECONDS=240` | Total question deadline |
| `TIDE_AI_MAX_CONCURRENT=2` | Global concurrent runs, bounded to 1–4 |

Codex defaults to `gpt-5.6-terra`, which must exist in the pinned runtime's bundled model catalog. Updating to a newer model requires a compatible runtime and repeated isolation checks. For the OpenAI API, choose a model available to your key that supports Responses and Structured Outputs; Codex model IDs cannot be assumed interchangeable with API IDs.

Install the backend dependencies using the lock file described in [the web README](../README.md). Codex requires `codex login` under the same user; `codex login status` checks it. The official runtime manages credentials. This application does not read/copy them or change global user configuration. A multi-user deployment needs application authentication and dedicated API credentials.

ChatGPT/Codex quota and OpenAI API billing are separate. The controlled Codex adapter uses pinned `openai-codex-cli-bin`, disabling personal configuration, shell, web, MCP, apps, plugins and other tools. OpenAI mode calls `AsyncOpenAI` directly; it cannot spend subscription quota.

## Project skills and execution

Skills live in [web/agent/skills](../agent/README.md), not global machine skills:

- [shrimp-analysis](../agent/skills/shrimp-analysis/SKILL.md): relative dates, ponds, measurement definitions, comparisons and missing data.
- [chart-selection](../agent/skills/chart-selection/SKILL.md): template use, metric constraints and combinations.

The project follows the `SKILL.md` front-matter/reference format. The server explicitly reads trusted files and supplies them to either provider; the model needs no shell access.

```text
Question + recent conversation + available data + project skills
  → classify answer / clarification / analysis
  → answer or clarification: retain board, return text
  → analysis: select validated dates, methods, charts and presentation
  → Pydantic validation and bounded SQLAlchemy computation
  → persist trusted computed facts before model narration
  → presentation=board updates center; answer retains it
  → persist conversation and result
```

The model receives no database credentials and cannot execute arbitrary SQL, Python, HTML or JavaScript. Renderers are fixed templates. Unsupported metrics, local paths and unbounded queries are not executed.

## Chat, progress and history

Initial entry shows a small empty-state icon, without auto-selecting history. The clock menu opens saved conversations. Desktop chat fills the viewport height; its messages scroll independently and the composer stays at the bottom. Drag the divider to resize (minimum 320px, maximum constrained by available space). With the divider focused, arrows adjust 16px, Shift+arrows 64px, and Home/End select the minimum/maximum. Width preference persists locally. Mobile uses results/chat tabs.

The sidebar button next to TIDE collapses chat, widening results; the results-header button restores it. Messages, draft, width and server work remain intact. Mobile collapse switches to results.

Submitting shows status in chat first. Only a confirmed new chart/statistics board replaces the center with a spinner, phase and elapsed time. Explanations, clarification and text-only numerical queries retain the current board, selected result and scroll. Exact saved summaries support extrema follow-ups; old conversations missing them require a statistics query without forced redraw. Histogram bin edges and sampled scatter points are not exact extrema.

Broad questions such as “How are today's measurements?” default to a visible overview, including on the first question. Single-day overviews can show length/width/weight distributions; multi-day questions use trends, and period comparisons use comparison charts. If a validated track-level descriptive plan omitted charts, the application adds appropriate templates while preserving dates, ponds and pond grouping. Video-mean statistics can remain statistics cards to avoid mixing observation units. Explicit text-only requests override board presentation; scalar/explanatory questions need not redraw.

Expandable execution records precede answers. Collapsed records show the latest two actual steps; active records show the current phase. Steps cover context, planning, querying/calculation, chart data and narration, followed by a completion summary. Fields come from validated plans and computed counts. These are application events, not hidden model reasoning; prompts, SQL, credentials and local paths are not exposed.

The additive `assistant_activity` table stores at most six steps per response. Startup creates missing tables without rewriting old video/chat columns. Legacy messages return empty activity arrays, not fabricated history. Cancellation, timeout and restart only mark actually started unfinished steps as stopped/failed. A completed board survives narration failure.

`assistant_results` separately stores the validated plan, trusted facts and presentation, including answer-only computations. Raw scatter tracks are excluded from model facts; bounded category/day aggregates are retained with truncation markers. Public `response_kind` tells the frontend whether an analysis has been confirmed; sending alone does not imply redraw.

## Chart templates

| Template | Use |
| --- | --- |
| Line / area | Daily measurement or count trends |
| Bar / stacked bar | Period, pond and additive category comparisons |
| Histogram | Length/width/weight distributions with shared period bins |
| Scatter | Paired measurements, with explicit bounded display sampling |
| Box plot | Actual five-number summary by pond/period |
| Heatmap | Daily-by-pond counts or measurement matrix |
| Donut | Sex/water category counts and composition |
| Table | Exact aggregates and sample counts |

These are ten templates. Calculations live in [analytics.py](../backend/app/assistant/analytics.py), plan types in [schemas.py](../backend/app/assistant/schemas.py). A new template requires schema, calculation, frontend allowlisted renderer, skill instructions and tests.

Descriptions, Pearson, Spearman, Welch t and Welch ANOVA are separate [statistical methods](statistical-methods.md). Cards show method, sample count/unit and inapplicability reasons. No post-hoc tests, multiple-comparison correction, control charts or forecasting are implemented. Measurement CSV fields include mm/g; missing values are not zero.

## Data and operational limits

- Real “today” uses Asia/Taipei and capture time. The AI demo contains 60 synthetic days and two ponds anchored to 2026-09-20. It creates no video jobs, but persists demo conversations/boards and uses model quota. Published demos contain no private footage or stills.
- This month means month-start through today; last month means the full previous calendar month. Unequal duration is disclosed. Comparisons are not identified individual growth.
- Chart/KPI averages weight valid IDs equally. Missing/nonpositive/nonfinite measurements are excluded, not filled with zero. Statistical requests may instead use video means.
- Selected ponds are query scope, not proof of observations. `period_summaries[].observed_ponds` reports actual completed-video pond coverage per period; the top-level field reports the union. Counts are complete; label lists are limited to 30 with a truncation flag.
- Width is an OBB short-edge proxy; length/weight are estimates. Image water classification is not pH or dissolved oxygen. Cross-camera comparability remains unverified without calibration.
- Limits: two periods, 366 days per period, eight charts, six statistical requests, ten statistical groups, 2,000 videos and 50,000 IDs. Exceeding data bounds requires narrowing scope rather than quietly truncating calculations.
- Questions are at most 2,000 characters; conversations at most 20 questions. Idempotency IDs prevent duplicate runs on retries. Cancellation reaches the server; restart marks active conversations interrupted.
- Numbers are computed by the backend, but model prose is not independently checked sentence by sentence. At most 80 rows per aggregate chart reach the model, while full boards/statistics are saved. Partial rows cannot justify whole-range trends, totals or model-calculated correlation.
- One API process owns tasks/cancellation. Move these to shared infrastructure before increasing API workers/replicas.

## Real-model smoke tests

From `web/`, this command consumes configured model quota and persists a demo conversation, but creates no video jobs:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/smoke-assistant.py --demo --question "Compare this month's length, width and weight with last month." --question "Keep those dates and show only width box plots by pond."
```

Omit `--demo` to query actual completed videos. The script has deadlines and cancellation handling.

## References

- [OpenAI Codex SDK](https://learn.chatgpt.com/docs/codex-sdk), [Codex authentication](https://learn.chatgpt.com/docs/auth)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Agent Skills format](https://developers.openai.com/api/docs/guides/tools-skills)
- [Codex status widget source](https://github.com/openai/codex/blob/main/codex-rs/tui/src/status_indicator_widget.rs), [execution events](https://learn.chatgpt.com/docs/app-server#turn-events): references for statuses, elapsed time and events; TIDE produces its own application events.
- [Metabase chart guide](https://www.metabase.com/learn/metabase-basics/querying-and-dashboards/visualization/chart-guide), [Superset charts/dashboards](https://superset.apache.org/docs/using-superset/creating-your-first-dashboard/)

These informed SDK, skill-format and visualization choices. This project's code implements its calculations, bounds and interface.
