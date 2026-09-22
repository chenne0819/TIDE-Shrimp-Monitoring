# General tracking

This directory has two inference entry points. Both retain the newer project's head/tail OBB geometry and tracking. The shared [monitoring integration](../docs/monitoring-integration.md) adds opt-in first-frame water classification and estimated length, OBB width and weight.

From the monorepo root, run `cd tracking`, activate the tracking environment and supply the required private weights described in the [tracking README](../README.md). Commands below run from `tracking/`; `video/sample.mp4` is your own input, not an included file.

## OBB tracking, HBB male_line and sliding votes

```powershell
python -m general_track.run_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 30 --debug
```

The pipeline uses YOLO `track()` with ByteTrack to detect `shrimp`, `shrimp_head` and `shrimp_tail`. It rectifies the shrimp OBB crop with `minAreaRect`, `getPerspectiveTransform` and `warpPerspective`, aligns the head to the left, then runs HBB `male_line` detection on the full rectified crop. This mode does not use a CNN or an additional sex-region crop.

Default models:

- `model/yolo/best-obb-yolo11m-head_tail.pt`
- `model/yolo/best-hbb-yolo11n.pt`

The existing per-ID vote uses a configurable 300-frame sliding horizon. Complete windows follow the pipeline's observation rules; partial windows are not exported as complete windows. For a complete window, `male_rate = male_hits / window_frames`: below 1/3 is female (`F`), from 1/3 to below 2/3 is observation (`obs`), and at least 2/3 is male (`M`). A missing male-line detection retains a recent hit for the existing one-second grace period.

Common controls include `--window-frames`, `--tracker`, `--obb-conf`, `--obb-iou`, `--hbb-conf`, `--max-frames`, `--gt Male|Female` and `--number-of-shrimps`. Use `--help` for current defaults. Ground-truth labels/counts describe the evaluation input; they are not inferred pond population counts.

Output root: `general_track/exports/run_track/<video_name>/<timestamp>/`.

| File | Contents |
| --- | --- |
| `result.mp4` | Annotated video; `--debug` includes the crop/debug panel |
| `detections.csv` | Per-frame/per-ID male-line detection and voting records |
| `sliding_windows.csv` | Complete per-ID voting windows |
| `per_shrimp.csv` | Per-ID final state and vote summary |
| `video_info.csv` | Test-video metadata, including supplied ground truth/count |
| `window_vote_summary.csv` | Male/female/observation window totals and final prediction |

## Head/tail tracking and a sex classifier

```powershell
python -m general_track.run_head_tail_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 30 --debug
```

This mode rectifies and orients the shrimp crop, then extracts the existing classification region before classifying female/male. It retains per-track majority-vote behavior.

The default is **`model/cnn/best_resnet18-run3.pt`**, selected through `MODEL_SEX_CLASSIFIER_PATH`. Other compatible classifiers can be selected with `--classifier-model`; `--cnn-model` remains a compatibility alias. The upstream loader supports ResNet18/34/50, ResNet50-FPN and YOLO classification checkpoints with the expected format. For example:

```powershell
python -m general_track.run_head_tail_track --video video/sample.mp4 --classifier-model model/cnn/best_resnet34-run3.pt --monitoring --water-policy report
```

The optional `model/yolo/best-cls-yolo11m-run3.pt` was not available for local validation. Supply a valid classification checkpoint before selecting it; do not substitute an OBB or HBB detection checkpoint. Output root is `general_track/exports/head_tail_cls/`, containing `result.mp4`, `detections.csv` and `per_shrimp.csv` within each run.

## Preview, monitoring and model checks

- `--preview` displays and saves; `--preview-only` displays without writing output. A GUI-capable OpenCV build and display are required. Without preview, `--debug` still exports the debug panel.
- Preview scales proportionally to the display. The tracking/measurement coordinates remain those of the source frame.
- `--monitoring` enables both features; omit it for original behavior, or use `--water-quality`/`--biometrics` separately.
- Direct Python water policy defaults to `stop`; examples explicitly use `report`. A stopped turbid source does not produce fabricated measurements.
- Enabled saved-output runs add `monitoring.json`, water records and size/weight fields. Estimates retain the legacy calibration and require new-camera validation; width is an OBB proxy, not anatomical body width.
- The head/tail checkpoint must be an OBB model with `shrimp`, `shrimp_head` and `shrimp_tail`. A `task=classify` checkpoint with `female`/`male` names is not a substitute.

Defaults live in `modules/config.py` and resolve relative to `tracking/project_paths.py`. Explicit relative CLI overrides use the working directory. Active flow files are `modules/track_pipeline.py`, `modules/head_tail_pipeline.py`, and shared `modules/head_tail_common.py`. Upstream credit and historical validation are retained in the [tracking README](../README.md).
