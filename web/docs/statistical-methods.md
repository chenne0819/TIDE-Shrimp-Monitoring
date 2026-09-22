# Statistical methods in AI analysis

The model selects allowlisted methods and charts; fixed backend functions compute the results. It cannot run Python/SQL or supply test statistics. A query is limited to 2,000 completed videos, 50,000 tracked IDs and 10 pond groups. Exceeding a limit requires a narrower query, not truncated data represented as full statistics.

## Supported questions and results

| Method | Example question | Result |
| --- | --- | --- |
| Descriptive | “What are this month's minimum, maximum, median and SD of length?” | Valid count, min/max, mean, median, sample SD, Q1 and Q3; a numerical answer need not create a chart |
| Pearson | “Is length linearly related to weight this month? Include a scatter plot.” | Pearson r from all valid pairs; scatter display is capped at 500 points |
| Spearman | “Use Spearman for length and weight; there may be outliers.” | Spearman rho with average ranks for ties; monotonic association, not causality |
| Welch t | “Compare video-mean length between ponds A and B with Welch's t-test.” | Two-sided t, p, Welch degrees of freedom, first-minus-second mean difference and its 95% CI |
| Welch one-way ANOVA | “Compare video-mean weight across ponds A, B and C using ANOVA.” | Overall F and p without equal-variance assumption; no post-hoc pairwise tests |

Chart choice and statistical method are separate. Explanations or follow-ups supported by saved summaries can preserve the current board. New data, scope or methods require computation; `presentation` controls whether the result replaces the board. Ten chart templates remain available, with separate statistical cards rather than plotting p-values as measurement curves.

## Observations and missing values

- `track`: one aggregate per video and tracked ID. Matching IDs across videos count separately and may represent the same animal; they are not established independent experimental replicates.
- `video_mean`: average valid tracks within each video, then weight each video equally. t/ANOVA require this unit to reduce within-video pseudoreplication.
- Video means do not establish independence between videos, ponds or dates. Repeated filming may share animals and temporal dependence.
- Each measurement excludes missing, nonfinite and nonpositive values independently. Correlation uses complete pairs from the same ID. Both video-level means use the same paired subset, never independently filtered/misaligned arrays.
- SD uses n−1; with one observation it is `null`. Quartiles use linear interpolation. Empty data remain null, not zero.
- Period grouping filters each period separately. Pond grouping uses the union of requested periods, counting an overlapping video once.

Each analysis stores full per-period, per-dimension `descriptive_summary` values: `count/min/max/mean/median/std_dev/q1/q3`, from the same bounded query. Exact extrema must not be guessed from histogram edges, sampled scatter points or rounded averages.

## Applicability and interpretation

Pearson/Spearman require at least three valid pairs. Constant or numerically unstable input is not applicable. Track-level correlation reports a descriptive coefficient only, with no p-value. Video-mean Pearson may report a conditional two-sided p-value, assuming independent paired videos and the relevant distribution assumptions; the application does not verify them.

For Spearman, this version omits asymptotic p-values when there are at most 500 paired videos, following SciPy's caution about small-sample accuracy. It does not silently substitute a permutation test. [SciPy Spearman documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html)

Welch t requires exactly two groups; Welch ANOVA at least two. Every group requires at least two valid videos and nonzero variation. Overlapping periods, insufficient observations, constant groups or nonfinite calculations return `not_applicable` with a reason, not fake zeros or NaN. Welch relaxes equal variances, but independence and normality/large-sample approximation requirements remain. [SciPy t-test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html), [SciPy ANOVA](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.f_oneway.html)

The application does not automatically declare significance. There is no multiple-comparison correction, normality assessment, temporal-dependence model, mixed-effects model or repeated-measures model. ANOVA does not identify which pairs differ. A computed p-value of zero is treated as a numerical boundary and reported as null with an explanation, not zero probability.

Results retain warnings about unverified camera/regression calibration, OBB width, exploratory comparisons, and the inability to infer causality or individual growth.

## Implementation and validation

Paths are relative to `web/`:

- `backend/app/assistant/statistics_schemas.py`: strict allowlist of five methods, three dimensions and period/pond grouping.
- `backend/app/assistant/statistics.py`: complete pairs, video aggregation, descriptive summaries and fixed SciPy functions.
- `backend/app/assistant/analytics.py`: one bounded data load for charts, `statistics` and `descriptive_summary`.
- `backend/requirements.txt`: `scipy>=1.16,<2`; Welch `f_oneway(equal_var=False)` requires 1.16+.
- `backend/tests/test_assistant_statistics.py`: known values, independent dot-product/rank formulas, numerical t-density integration and a closed-form Welch ANOVA case; also missing values, ties, sample counts/units, constants, overlap, numerical limits, group bounds and schema rejection.

From `web/`:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/test_assistant_statistics.py tests/test_assistant_analytics.py -q
```

See [SciPy Pearson documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html) for formula/assumptions. Numerical tests use independent checks rather than calling the same SciPy function twice. Software checks do not establish model accuracy or camera calibration.
