# EMA threshold tuning snapshot — 2026-10-17

This is a descriptive tuning result, not independent validation or evidence that
every tracked shrimp becomes more accurate. Raw videos, probability traces and
machine-specific reports remain local and are not included in this document.

## Data and method

- Six user-labeled clips: `公蝦仰拍-1..3.mp4` contain five males each;
  `母蝦仰拍-1..3.mp4` contain five females each. Clips may share individuals or
  overlap training data; neither independence nor train/test separation is known.
- All 26,699 frames were processed, without subsampling, with the existing OBB,
  ByteTrack, head/tail orientation and ResNet50 pipeline. `imgsz=640`, `conf=0.3`,
  `iou=0.3`, single-frame `cnn_threshold=0.03` and debug preview composition were
  retained. Water/biometrics were disabled during that recorded collection.
- The collector recorded full CNN probabilities and monotonic processing time.
  Every candidate replays the same observations/timestamps. EMA time constant
  and switch confirmation were each one second; retention was three seconds.
- 137 thresholds were evaluated: 0–1 by 0.01, then 0.001 steps near leading
  coarse candidates. Ranking used video-balanced macro-F1, then fewer switches.
- Python 3.14.3, torch 2.10.0+cu126, torchvision 0.25.0+cu126, Ultralytics
  8.4.176, scikit-learn 1.9.1 and NVIDIA RTX 3050 6GB Laptop GPU were recorded.

## Results

Only successful classifications with a tracking ID are scored. Each video has
equal weight within its sex; the two sexes are balanced when computing macro-F1.
These conditional rates do not measure detector recall or physical identity
tracking accuracy. A switch compares the same ID within retained preview state;
new-ID classifications are not counted as same-ID switches.

| Metric | EMA threshold 0.03 | EMA threshold 0.14 |
| --- | ---: | ---: |
| Video-balanced macro-F1 | 0.9791 | 0.9851 |
| Male mean conditional recall | 97.74% | 97.09% |
| Female mean conditional recall | 98.08% | 99.94% |
| Same-ID label switches | 75 | 6 |
| Preview-state segments never correct | 2 | 4 |

0.139 and 0.140 tied exactly on all per-video metrics in the recorded traces.
0.14 is the simpler candidate for a future trial. The six-switch result is also
the lowest among tested candidates within 0.005 macro-F1 of the maximum; this
tolerance is an engineering comparison, not statistical equivalence.

| Clip | 0.03 conditional accuracy | 0.14 conditional accuracy | Switches, 0.03 → 0.14 | Classified track IDs |
| --- | ---: | ---: | ---: | ---: |
| 公蝦仰拍-1 | 93.45% | 91.62% | 11 → 2 | 8 |
| 公蝦仰拍-2 | 99.87% | 99.73% | 2 → 2 | 5 |
| 公蝦仰拍-3 | 99.92% | 99.91% | 1 → 1 | 5 |
| 母蝦仰拍-1 | 97.05% | 99.83% | 27 → 1 | 17 |
| 母蝦仰拍-2 | 98.49% | 100.00% | 14 → 0 | 11 |
| 母蝦仰拍-3 | 98.70% | 99.99% | 20 → 0 | 19 |

## Interpretation and current behavior

Same-ID switches fell by 92%, but the first male clip became less accurate and
never-correct preview segments increased. Some clips produced more than five
classified IDs; fragmentation or false detections must be investigated separately.
Homogeneous-sex clips cannot validate male/female ID swaps in mixed-sex scenes.

**The candidate was not applied.** The current preview shares `cnn_threshold`
with raw single-frame classification, so its threshold remains 0.03. There is no
separate EMA-threshold TOML key yet. Do not replace the validated single-frame
0.03 merely to apply this report; introducing an independent preview threshold
is a separate code change.

Current sample settings enable biometrics, unlike the original tuning run.
Because EMA uses processing time, different GPU load, GUI overhead or enabled
monitoring can change its behavior. Recheck the candidate under the intended
runtime and on unseen, grouped videos before adopting it. Successful model
loading is distinct from classification quality and camera calibration.

For collection/replay commands, file formats, coverage handling and provenance,
see [offline evaluation](ema-evaluation.md). Cached collection directories reject
changed config/environment/code; use a new output directory for a new collection.
