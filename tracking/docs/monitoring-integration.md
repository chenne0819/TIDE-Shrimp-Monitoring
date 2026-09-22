# Water, size and weight integration

This integration adds [ShrimpVisionRT](https://github.com/chenne0819/ShrimpVisionRT)'s first-frame water classifier and size/weight regressors to the newer [Shrimp-Male-Yolo-Tracking](https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking) workflows. Detection, head/tail alignment, sex classification, voting and IDs remain controlled by the newer project. Monitoring is opt-in and appends values to existing records and overlays.

## Setup and entry points

Follow the [tracking README](../README.md) to create the Python 3.12 environment and obtain private weights. From the monorepo root, run `cd tracking` and activate this directory's environment before these commands. `video/sample.mp4` is your own input, not a bundled sample.

```powershell
# General OBB tracking and single-frame HBB male_line detection.
python -m general_track.run_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 12

# Head/tail tracking and the default ResNet18 sex classifier.
python -m general_track.run_head_tail_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 8

# Single-frame OBB/HBB prediction with the default OBB and HBB-L models.
python -m predict.run_predict --video video/sample.mp4 --monitoring --water-policy report --max-frames 12
```

`multi_channel_track.run_multi_channel_track` also contains monitoring hooks, but requires a compatible three-frame, nine-channel HBB checkpoint at `model/best-hbb-3frame.pt` or an explicit `--hbb-model` path. That checkpoint was unavailable for recorded validation. Three-channel HBB weights cannot replace it. This entry point exposes neither `--max-frames` nor `--skip-frames`.

Head/tail classification defaults to `model/cnn/best_resnet18-run3.pt`. An optional YOLO classifier can be selected with `--classifier-model`; its checkpoint is not supplied. The [mode/model table](../README.md#private-model-assets-required-after-cloning) lists the maintained paths.

`--preview` displays and saves; `--preview-only` does not write any output. Preview requires a GUI-capable OpenCV environment and display. The Windows wrapper `run-monitoring.ps1` is an optional shortcut for the general Python entry point, enabling monitoring and `report`:

```powershell
.\run-monitoring.ps1 -Video video/sample.mp4 -MaxFrames 30 -Preview
.\run-monitoring.ps1 -Video video/sample.mp4 -WaterPolicy stop
```

`setup-monitoring.ps1` optionally creates the environment and handles the Albumentations/headless-OpenCV conflict. Recreate `.venv` after moving to another computer; do not copy an old environment.

## Shared options

| Option | Meaning and default |
| --- | --- |
| `--monitoring` | Enable water classification and biometrics together |
| `--water-quality` | Enable first-frame water classification only |
| `--biometrics` | Enable length, width proxy and weight estimation only |
| `--water-policy stop` | Python CLI default: stop a turbid source before shrimp inference |
| `--water-policy report` | Record water appearance and continue even when turbid |
| `--water-model PATH` | Default: `model/water/logistic_regression_model.pth` |
| `--biometrics-model-dir DIR` | Default: `model/biometrics`; all four fixed regression filenames are required |
| `--pixels-per-mm 2.5` | Pixels per mm in the calibration reference canvas |
| `--measurement-reference-size 800 450` | Reference width and height, without changing detector input |
| `--weight-mode length` | Default: estimate weight from calibrated length |
| `--weight-mode length-width` | Use calibrated length and OBB width proxy; validate this definition first |

Default assets resolve against `project_paths.py` in `tracking/`. Explicit relative asset, video and output arguments use the working directory; absolute overrides are supported. Logs may show resolved absolute paths, but source defaults contain no personal computer path.

## First-frame water classification

The original classifier is `Linear(784, 2)` with class order `turbid`, `clear`. Preprocessing converts to 28 × 28 grayscale, scales pixels to `[0, 1]`, normalizes with mean/std `0.5`, and flattens to 784 values. Compatibility includes the original ndarray behavior: OpenCV BGR bytes are interpreted as RGB before grayscale conversion. Changing that interpretation changes the supplied model's outputs.

Each source is checked once on its first available frame, before auto-total prescanning, frame skipping or shrimp inference. `stop` records `skipped_turbid`; `report` records the result and continues. The original video is not moved. This is visual clarity classification in one frame, not chemical water analysis or continuous monitoring.

## Geometry, regression and calibration

Measurement uses original-frame OBB coordinates from the newer detector. For source size `(W, H)` and reference size `(Rw, Rh)`:

```text
scale = min(Rw / W, Rh / H)
reference_length_px = OBB_long_edge_px * scale
reference_width_px  = OBB_short_edge_px * scale
length_mm = length_regressor(reference_length_px / pixels_per_mm)
width_mm  = width_regressor(reference_width_px / pixels_per_mm)
weight_g  = length_weight_regressor(length_mm)  # default
```

Both axes use one uniform scale, preserving edge measurements under rotation. Reference-canvas padding does not affect edge lengths. For another aspect ratio, this is a reference-canvas adaptation, not proof of identical legacy geometry or physical calibration. Detector input and tracking coordinates remain unchanged. The original one-decimal rounding and feature order are retained.

Defaults retain the old `800 × 450` and `2.5 px/mm`. The local smoke input was a `990 × 1398` portrait video. Running at that resolution does not establish correct millimeters: camera distance, field of view, lens, refraction and shrimp depth require validation. Derive `--measurement-reference-size` and `--pixels-per-mm` using a known object at the shrimp plane, then check regression outputs against measured shrimp. See the [calibration example](../README.md#calibration-and-replacement-models).

Width is the **new OBB short-edge proxy**, unlike the old segmentation-derived width. Exports use `width_source=obb_proxy`; overlays show `W~`. Default weight uses length alone rather than silently introducing an unvalidated width into the two-feature regressor. Explicit `length-width` uses `[length_mm, width_mm]` and does not fall back when width is unavailable.

Invalid/nonpositive results remain empty with a status instead of becoming zero-valued observations. A valid length may still yield length-only weight when width is unavailable. Measurements attach only to records retained by each original pipeline, including head/tail validity filtering; the integration does not add sex-voting samples.

## Model contracts and provenance

The user-provided newer bundle contained one head/tail OBB, four single-frame HBB variants (`n`, `s`, `m`, `l`), and three ResNet classifiers. Original water and regression weights were recovered unchanged from the local ShrimpVisionRT `shrimp_OBB/Model` directory. No random deployed weights were created.

| Filename | Feature input | Output |
| --- | --- | --- |
| `final_linear_model_length.pkl` | One reference-scaled length in mm | Calibrated length in mm |
| `final_linear_model_width.pkl` | One reference-scaled width in mm | Calibrated width in mm |
| `polynomial_regression_model_degree3.pkl` | Calibrated length in mm | Weight in g |
| `multi_feature_model.pkl` | `[length_mm, width_mm]` | Weight in g |

All four files load even in length-only mode. They must support `joblib.load`, `.predict()` and compatible `n_features_in_`. Their saved scikit-learn version was `1.6.1`. Water weights must expose `linear.weight` and `linear.bias` for the original `Linear(784, 2)` state dictionary. Different architectures require loader changes. Missing/incompatible files cause explicit errors. Only load serialized models from trusted sources.

The [asset manifest](../model/assets-manifest.json) records bundle names/hashes; [regression provenance](../model/biometrics/provenance.json) records source revision, hashes, estimator types, coefficients and calibration evidence. Weights are omitted from publication and must be obtained separately. Some inherited videos use Git LFS, but LFS pull does not retrieve the omitted model bundle.

## Integration files and outputs

| File | Responsibility |
| --- | --- |
| `shrimp_monitoring/water.py` | Original preprocessing, checkpoint validation and classification |
| `shrimp_monitoring/biometrics.py` | OBB geometry, scaling, regression and valid-value summaries |
| `shrimp_monitoring/runtime.py` | First-frame policy, overlays, output fields and metadata |
| `shrimp_monitoring/cli.py` | Shared opt-in options and defaults |
| `project_paths.py` | Portable default asset resolution |
| `general_track/modules/track_pipeline.py`, `head_tail_pipeline.py` | Hooks for both tracking entry points |
| `predict/modules/analyzer.py`, `multi_channel_track/modules/analyzer.py` | Hooks for prediction and temporal tracking |

Original detection records gain `length_px`, `width_px`, `length_mm`, `width_mm`, `weight_g`, `width_source`, `weight_method`, `measurement_status` and enabled water fields. Pixels are reference-scaled, not raw source pixels. Per-ID summaries gain `measurement_samples` and valid-value means; the sample count counts valid length observations, not shrimp.

Enabled monitoring writes `monitoring.json` with status, model locations, reference size, scale, weight mode and width provenance. Water-enabled runs also write `water_quality.csv` with label, confidence, policy and action. Predict/temporal monitoring files sit at the run root alongside the existing `data/`, `figures/` and `videos/` directories. A stopped source does not report an unwritten result video. Preview-only writes none of these files.

## Validation scope

The original water checkpoint produced `clear` at about `0.98684` for `2024-01-01-00_11_15.mp4`, and `turbid` at `0.92358` for `2024-01-08-06_53_42.mp4`. The new bottom-view smoke input produced `turbid` at `0.99995`; its tracking runs therefore used `report`. Confidence is not measured accuracy in that new setting.

The historical complete suite reached **86 passed** after portability changes. Coverage includes real-regressor parity, feature order, rounding, rotation/resolution, preprocessing, opt-in behavior, tracker/ID preservation, stop/report, first-frame handling, exports, preview-only and cleanup. Three entry points passed real-video short runs; the absent nine-channel model prevented equivalent temporal validation. These checks do not establish physical accuracy, full-video endurance or another operating system's compatibility.

After supplying the original water/regression assets, run `python -m pytest tests -q` from `tracking/`. Publication documentation preparation does not claim a fresh real-model run. See the [dated validation record](monitoring-validation.md) and the [original upstream README archive](README-original.md), which retains the original language and is not the maintained setup guide.
