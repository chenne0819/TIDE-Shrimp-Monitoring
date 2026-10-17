# Offline EMA threshold evaluation

The versioned [2026-10-17 tuning snapshot](ema-threshold-results.md) summarizes
the completed six-video experiment and its limitations. The candidate is not
an applied setting; the live preview currently shares the single-frame threshold.

`evaluate_ema.py` evaluates the six local `公蝦仰拍-1..3.mp4` and
`母蝦仰拍-1..3.mp4` recordings. The user identified five male shrimp in each
male recording and five female shrimp in each female recording. This supplies
video-level sex labels, not independently verified detection boxes or identities.
Do not interpret six recordings as thirty different shrimp.

Run from `tracking/` with the repository-root Python 3.14 environment:

```powershell
..\.venv\Scripts\python.exe -B evaluate_ema.py --output-root ..\test-results\ema-study
```

The collector uses the existing TOML/model assembly, detector, orientation,
classifier and preview smoother. It processes every decoded frame, with no GUI
window, no video encoder and no modifications to the config or model weights.
Raw class probabilities and monotonic processing timestamps are streamed to
per-video JSONL traces. Empty frames and untracked classifications are retained.
Offscreen composition simulates the existing debug preview load, but GUI and
logging overhead differ from interactive execution. Timing is specific to this
recorded run; subsequent executions may have different EMA behavior.

Only the replay threshold changes. EMA's time constant and switch confirmation
remain one second, with the existing three-second retention and gap behavior.
The single-frame `cnn_threshold` is unchanged. Search covers 0–1 in increments
of 0.01, then the neighborhoods of the three leading candidates at 0.001.

Repeat replay without loading neural models:

```powershell
..\.venv\Scripts\python.exe -B evaluate_ema.py --output-root ..\test-results\ema-study --replay-only
```

Completed traces can be reused by the normal command if the recorded environment,
config, source code and source video hashes match. Incomplete traces keep a
`.partial.jsonl` suffix and are not scored as complete videos.

Outputs:

- `environment.json`: Python/dependency versions, settings, GPU and model/code hashes.
- `<video>/trace.jsonl` and `metadata.json`: observations, both clocks, frame count,
  dimensions, source hash and collection duration.
- `threshold_metrics.csv`: all tested thresholds and video-balanced classification
  and switching metrics.
- `video_metrics.csv`: per-video results, IDs, coverage proxy and recovery timing.
- `summary.json` and `report.md`: baseline 0.03 versus the candidate.

Ranking uses video-balanced macro-F1 first, then fewer switches. It is a tuning
comparison, not an independent evaluation or proof of optimal visual stability.
Each video's valid tracked classifications receive equal within-video weight;
each of the three videos of a sex then contributes equally to that sex's rate.
Macro-F1 is computed from those video-balanced male/female rates. Long videos or
many fragmented tracks do not get extra inter-video weight.

Each tracked classification contributes `1 / source_fps` observation-seconds.
Missing detections/crops and untracked results are excluded from classification
accuracy and separately reported, not treated as correct. The coverage proxy
divides valid observations by `five expected shrimp × source frame count`;
duplicate/false tracks can make it misleading and it is not detector recall.
Track counts are not independent biological sample counts. First-correct delays
are reported per uninterrupted preview-state segment; never-correct segments
are counted separately so zero switching cannot conceal persistent errors.
Switch counts only compare labels within the same ID and retained preview state;
label changes when a new ID appears are not counted as same-ID switches.

Keep source-video/individual groups separate for independent validation. Whether
these videos were used for CNN training, or share shrimp across clips, is not
known. Sex-homogeneous labels do not identify false-positive boxes, and candidate
thresholds should be checked on unseen videos before application.
These clips also cannot validate male/female identity swaps in mixed-sex scenes.
