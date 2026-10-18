# Water, size and weight integration

This integration adds [ShrimpVisionRT](https://github.com/chenne0819/ShrimpVisionRT)'s first-frame water classifier and size/weight regressors to the newer [Shrimp-Male-Yolo-Tracking](https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking) workflows. Detection, head/tail alignment, sex classification, voting and IDs remain controlled by the newer project. Monitoring is opt-in and appends values to existing records and overlays.

## Setup and entry points

Follow the [tracking README](../README.md) for the environment and private assets. `general_track.run_track` now reads [config.toml](../general_track/config.toml); it accepts only --config and --help.

```powershell
cd tracking
..\.venv\Scripts\python.exe -m general_track.run_track --config general_track/config.toml
```

Set water_quality and biometrics independently in TOML. Both true enables both features; disabled features do not require their private weights. Set max_frames for a short test. Preview, crop saving, calibration and water policy are configured in the same file. All its parameters have explanatory comments. Relative paths use the TOML directory.

| TOML setting | Meaning |
| --- | --- |
| `water_quality` | First-frame clear/turbid classification |
| `biometrics` | Length, OBB width proxy and weight estimation |
| `water_policy` | stop before inference when turbid, or report and continue |
| `water_model` | Original Linear(784, 2) checkpoint |
| `biometrics_model_dir` | Directory containing all four fixed regressors |
| `pixels_per_mm` | Pixels per mm in the reference canvas |
| `measurement_reference_size` | Reference [width, height], without changing detector coordinates |
| `weight_mode` | length, or length-width after validating the width proxy |

The PowerShell wrapper accepts only -Config; it runs the same settings and does not override monitoring. The shared shrimp_monitoring APIs retain their original behavior. The web worker enables both monitoring features in a per-job TOML and passes `--config`; its result reader imports the same exported schema.

## First-frame water classification

The original classifier is `Linear(784, 2)` with class order `turbid`, `clear`. Preprocessing converts to 28 × 28 grayscale, scales pixels to `[0, 1]`, normalizes with mean/std `0.5`, and flattens to 784 values. Compatibility includes the original ndarray behavior: OpenCV BGR bytes are interpreted as RGB before grayscale conversion. Changing that interpretation changes the supplied model's outputs.

Each source is checked once on its first available frame, before shrimp inference. `stop` records `skipped_turbid`; `report` records the result and continues. The original video is not moved. This is visual clarity classification in one frame, not chemical water analysis or continuous monitoring.

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

Defaults retain the old `800 × 450` and `2.5 px/mm`. The local smoke input was a `990 × 1398` portrait video. Running at that resolution does not establish correct millimeters: camera distance, field of view, lens, refraction and shrimp depth require validation. Derive `measurement_reference_size` and `pixels_per_mm` using a known object at the shrimp plane, then check regression outputs against measured shrimp. See the [calibration example](../README.md#calibration-and-replacement-models).

Width is the **new OBB short-edge proxy**, unlike the old segmentation-derived width. Exports use `width_source=obb_proxy`; overlays show `W~`. Default weight uses length alone rather than silently introducing an unvalidated width into the two-feature regressor. Explicit `length-width` uses `[length_mm, width_mm]` and does not fall back when width is unavailable.

Invalid/nonpositive results remain empty with a status instead of becoming zero-valued observations. A valid length may still yield length-only weight when width is unavailable. Measurements attach to retained tracking records. The retained head/tail classifier pipeline keeps its crop direction correction, validity filtering and sex-voting behavior.

## Model contracts and provenance

The user-provided newer bundle contained one head/tail OBB, four single-frame HBB variants (`n`, `s`, `m`, `l`), and three ResNet classifiers. Original water and regression weights were recovered unchanged from the local ShrimpVisionRT `shrimp_OBB/Model` directory. No random deployed weights were created.

| Filename | Feature input | Output |
| --- | --- | --- |
| `final_linear_model_length.pkl` | One reference-scaled length in mm | Calibrated length in mm |
| `final_linear_model_width.pkl` | One reference-scaled width in mm | Calibrated width in mm |
| `polynomial_regression_model_degree3.pkl` | Calibrated length in mm | Weight in g |
| `multi_feature_model.pkl` | `[length_mm, width_mm]` | Weight in g |

All four files load even in length-only mode. They must support `joblib.load`, `.predict()` and compatible `n_features_in_`. Their saved scikit-learn version was `1.6.1`; the current runtime uses Python 3.14 and scikit-learn `1.9.1`. The four regressors and water checkpoint are included as ordinary Git files with recorded SHA-256 hashes. Run the real-asset tests after environment changes; successful loading/prediction does not establish camera-specific accuracy or universal cross-version compatibility. Water weights must expose `linear.weight` and `linear.bias` for the original `Linear(784, 2)` state dictionary. Different architectures require loader changes. Missing/incompatible files cause explicit errors. Only load serialized models from trusted sources.

The [asset manifest](../model/assets-manifest.json) records historical bundle names/hashes and the current entry's required assets; [regression provenance](../model/biometrics/provenance.json) records source revision, hashes, estimator types, coefficients and calibration evidence. The five monitoring weights are included. OBB/CNN weights and input videos must be supplied separately. Some inherited assets use Git LFS, but LFS pull does not retrieve the unpublished OBB/CNN bundle. Historical HBB entries in the manifest are not requirements of the current entry.

## Integration files and outputs

| File | Responsibility |
| --- | --- |
| `shrimp_monitoring/water.py` | Original preprocessing, checkpoint validation and classification |
| `shrimp_monitoring/biometrics.py` | OBB geometry, scaling, regression and valid-value summaries |
| `shrimp_monitoring/runtime.py` | First-frame policy, overlays, output fields and metadata |
| `shrimp_monitoring/cli.py` | Legacy CLI helper; not used by the TOML entry |
| `project_paths.py` | Portable default asset resolution |
| `general_track/modules/head_tail_pipeline.py` | Monitoring hooks for the retained `run_track` entry |

Original detection records gain `length_px`, `width_px`, `length_mm`, `width_mm`, `weight_g`, `width_source`, `weight_method`, `measurement_status` and enabled water fields. Pixels are reference-scaled, not raw source pixels. Per-ID summaries gain `measurement_samples` and valid-value means; the sample count counts valid length observations, not shrimp.

Enabled monitoring writes `monitoring.json` with status, model locations, reference size, scale, weight mode and width provenance. Water-enabled runs also write `water_quality.csv` with label, confidence, policy and action. A stopped source does not report an unwritten result video. Preview-only writes none of these files.

## Tests and limits

Tests cover regression feature order, rounding, rotation/resolution, water preprocessing, tracker/ID preservation, stop/report policies, first-frame handling, exports and cleanup. These checks do not establish physical accuracy or full-video endurance.

After installing the tracking dependencies, run `..\.venv\Scripts\python.exe -m pytest tests -q` from `tracking/`; the original water/regression assets are included. The [original upstream README](README-original.md) is preserved for attribution; use the current [tracking README](../README.md) for setup and known test limitations.
