# General tracking

`general_track.run_track` tracks head/tail OBB detections with ByteTrack, corrects crop direction, and classifies female/male. Execution settings live in [config.toml](config.toml); every parameter has a Chinese explanation.

## Run

From `tracking/`, using the repository-root Python 3.14 environment:

```powershell
..\.venv\Scripts\python.exe -m general_track.run_track
..\.venv\Scripts\python.exe -m general_track.run_track --config general_track/config.toml
..\.venv\Scripts\python.exe -m general_track.run_track --help
```

From the repository root with its existing virtual environment:

```powershell
$env:PYTHONPATH = "tracking"
.\.venv\Scripts\python.exe -m general_track.run_track --config tracking/general_track/config.toml
```

The only command options are `--config` and `--help`. Previous options such as `--video`, `--cnn-threshold`, `--monitoring`, `--max-frames` and preview flags have been removed. Edit the corresponding TOML fields instead. The PowerShell wrapper accepts only `-Config` and requires Python 3.14 in the repository-root `.venv`.

Relative video, model, custom tracker and output paths resolve against the TOML file's directory. The default config is located relative to `run_track.py`, independently of the working directory. If copying a config elsewhere, update its relative paths or use absolute paths. Internal tracker names `bytetrack.yaml` and `botsort.yaml` are resolved by Ultralytics.

## Settings and behavior

- `video` is a video path or integer camera index. Supply your own input after cloning.
- `obb_model` defaults to the head/tail OBB checkpoint; `classifier_model` defaults to ResNet50. Compatible ResNet18/34/50, ResNet50-FPN and YOLO classification checkpoints remain supported. No HBB detector is used.
- `cnn_threshold` is optional, within 0 to 1. Male probability at or above the threshold yields male, otherwise female. Omit it to retain the classifier decision. This runs before the existing per-track majority vote; ties remain male. Explicit thresholds are exported in detections.csv.
- `max_frames` is an optional positive integer. Omit it for the full video. Enable the commented `max_frames = 30` example for a short test.
- Head/tail associations orient the head left before extracting the existing classifier region. Ambiguous direction continues to skip that crop.
- Main-frame labels use compact `1 M` / `1 F` (`?` without an ID), with white text on a dark gray background. Preview labels also show the smoothed male probability, for example `1 F | Pm 0.013`. OBB outlines use cyan-blue for male and green for female. Each run resets display IDs and the detector's existing tracker session.
- Preview labels use an exponential moving average of raw `male_probability` per track with a one-second time constant: `alpha = 1 - exp(-elapsed_seconds / 1.0)`. Constant-input smoothing is independent of FPS. The first observation is shown immediately; the threshold is the configured `cnn_threshold`, or 0.5 when omitted. A smoothed classification must oppose the displayed label continuously for one second before switching. Missing observations interrupt confirmation; a processing gap above one second neither updates the score nor counts as confirmation. Labels survive short misses and reset after more than three seconds without a valid observation. Each new ID starts independently; detections without an ID display `?` and do not accumulate evidence. The main preview shows the stable ID, sex label and smoothed male probability; the debug panel also shows `Pm` (smoothed male probability) and a separate `CNN` row for the raw prediction. The smoothed score is not calibrated confidence. CSV and final per-track majority voting remain unchanged. Preview voting has been removed. This stabilizes display and does not establish improved accuracy.
- `smooth_video = true` applies the same EMA and switch confirmation to saved video labels, colors and optional debug panels, including headless runs. It uses `frame_index / fps` on the encoded video's timeline (30 FPS fallback if input FPS is unavailable), so processing speed does not change the result. Live preview keeps its own wall-clock smoothing state. Both states reset each run. Raw CSV values, final majority voting, measurements and saved classifier-crop labels are unchanged. Standalone configs default to `false` when omitted; web jobs always enable it. `preview_only` still writes no output.
- `water_quality` enables the first-frame water check. `biometrics` independently enables length, OBB width proxy and weight estimation. Both true enables complete monitoring. Disabled features do not load their missing assets; explicitly enabled missing/incompatible models fail clearly.
- `water_policy = "stop"` stops a turbid source before shrimp inference; `"report"` records water appearance and continues.
- Calibration and `weight_mode` retain the existing measurement formulas; see the [monitoring guide](../docs/monitoring-integration.md).
- `preview` displays and saves. `preview_only` displays without writing video, CSV, crops or monitoring results. Preview needs GUI OpenCV and a display.
- `debug` includes the classifier panel in saved video and initially in preview. D toggles only the preview panel; Q/Esc exits preview. `save_crops` saves exact classifier inputs unless preview_only is true.

Malformed TOML, unknown fields, invalid types/ranges, missing required values and active model/input paths fail before model inference. Importing the entry or using help does not load Torch or model weights.

## Modules

| Module | Responsibility |
| --- | --- |
| `run_track.py` | Read/validate TOML, create model objects and start the run |
| `modules/head_tail_pipeline.py` | Coordinate per-frame processing, display IDs and per-track summaries |
| `modules/obb_track.py` | OBB/ByteTrack invocation, class validation and ordinary detection rows |
| `modules/sex_classifier.py` | Model loading, classifier preprocessing and probabilities |
| `modules/head_tail_common.py` | Association, rectification, head-left orientation and classifier region |
| `modules/visualization.py` | Overlays, debug panels and preview |
| `modules/preview_smoothing.py` | Time-aware probability smoothing and switch confirmation for preview/video overlays |
| `modules/output.py` | Run directory, annotated video, classifier crops and CSV output |

The old `modules/config.py` is removed. Feature modules do not read the TOML or import global model settings. `HeadTailShrimpAnalyzer` now accepts constructed OBB/classifier objects, not model filenames or implicit global model defaults. `modules.analyzer.ShrimpSexRatioAnalyzer` remains an alias. For Python use, call `load_settings(path)`, `create_analyzer(settings)` from `run_track.py`, then `.run()` with the execution fields. The existing `.run()` result dictionary is retained.

## Outputs and external callers

Runs save `result.mp4`, `detections.csv`, `per_shrimp.csv` and optional `classifier_crops/` under `output_root/<video>/<timestamp>/`. When the same path already exists, a numeric suffix prevents overwriting an earlier run. Monitoring appends its original fields, summaries and files.

The web worker reads this template, resolves model and custom tracker paths relative to it, and writes a separate TOML for each job. It passes `--config`, supplies the uploaded video, output directory, frame limit and water policy, enables both monitoring models and `smooth_video`, and disables preview/debug/crop output. The shared template is not modified. The web result reader imports the exported schema. Previously completed videos are unchanged; submit a new analysis to generate a smoothed result.

The [EMA tuning snapshot](../docs/ema-threshold-results.md) reports a candidate
preview threshold of 0.14, not an applied default. Preview smoothing currently
shares `cnn_threshold`; there is no separate EMA-threshold TOML setting.

Use the existing root environment for tests:

```powershell
$env:PYTHONPATH = "tracking"
.\.venv\Scripts\python.exe -m pytest tracking/tests -q
```
