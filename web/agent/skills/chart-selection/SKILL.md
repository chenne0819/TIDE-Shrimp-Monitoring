---
name: chart-selection
description: Choose TIDE chart templates for trends, comparisons, distributions, relationships and data inspection. Use when building a multi-chart analysis board from shrimp measurements.
---

# Chart selection

Each chart should answer one clear question. Measurement overviews, analysis overviews, growth summaries, trends, comparisons, and distributions require charts by default; the user need not name a chart type. 「今天的量測結果怎麼樣？」 should create a central overview and suitable charts, even on the first turn. Answer only in chat for scalar follow-ups, result explanations, clarification, or explicit text-only requests. Use at most eight charts. The backend provides KPIs automatically, so do not duplicate them with chart requests.

Use statistics requests for correlation coefficients, t-tests, and ANOVA. The frontend displays statistical cards directly, so `charts=[]` is valid. Add relevant charts such as scatter or box plots only when the user also requests a visual comparison; do not force statistical results into unrelated charts.

| type | Suitable use | Data requirements |
| --- | --- | --- |
| line | Daily length, width, weight, or individual-count trends | `group_by=day`; do not put length/width and weight on a shared unit axis |
| area | Recorded-video or individual counts over time | Daily series; never fill missing data with invented measurements |
| bar | Comparisons between periods, ponds, sexes, or water-color classes | `group_by=period/pond/sex/water` |
| stacked_bar | Category composition by pond or day | Groups and series must be meaningfully additive; never stack mean lengths |
| histogram | Length, width, or weight distributions | Dimension metric; use the same bins for both periods |
| scatter | Length–width, length–weight, or width–weight relationships | Both `metric` and `secondary_metric` are dimension metrics; backend supplies paired points; disclose sampling |
| boxplot | Dimension variability by pond or period | Dimension metric; use backend quantiles, never infer them from means or histograms |
| heatmap | Daily sample counts or mean dimensions by pond | Must use `group_by=day`; the backend adds ponds as the other axis. `group_by=pond` produces period-by-pond totals, not a daily heatmap |
| donut | Sex proportions or proportions of videos by water color | `group_by=sex/water`; use counts and retain Unknown separately |
| table | Exact values, sample counts, and measurement summaries | Can accompany any chart; include units and dates |

Common combinations:

- Today's results: one histogram each for length, width, and weight; optionally add a water-color donut or pond table. Do not combine incompatible dimension units on one axis.
- This month versus last month: one line chart each for length, width, and weight, plus a length box plot or histogram. KPIs show current-versus-previous differences.
- Pond comparisons: bar + boxplot + heatmap.
- Distributions: histogram + boxplot; add scatter when asked about a relationship.

Use plain Traditional Chinese titles such as 「每日估計長度」 and 「各池寬度分布」 rather than slogans. Do not select maps, funnels, gauges, or network charts without supporting data. Never generate HTML, JavaScript, SVG source, external image URLs, or SQL. The frontend renders fixed templates only.

When the user says 「各池」, use `group_by=pond` for bar, boxplot, and table charts. A sex-composition stacked bar by pond also uses `pond`; the backend adds male/female series automatically. Do not replace pond grouping with `sex`. Daily-by-pond heatmaps are the exception described above: use `day`. Before returning the plan, check each chart's dates, ponds, and grouping against the request; do not omit grouping because several charts were requested.

Validation limits: `stacked_bar` and `donut` accept only `shrimp_count` or `video_count` as their metric. Sex proportions use `shrimp_count`; video water-color proportions use `video_count`. `histogram`, `boxplot`, and `scatter` accept only dimension metrics. Only `scatter` requires a non-null `secondary_metric`, which must differ from `metric`; all other charts require `secondary_metric=null`. Do not calculate sex proportions from video counts because one video may contain multiple sexes. Do not use a donut with overlapping periods.
