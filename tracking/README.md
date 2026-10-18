# TIDE tracking and monitoring

This directory is the Python inference component of **TIDE-Shrimp-Monitoring**. It retains YOLO detection, head/tail alignment, sex classification, voting and tracking from [Shrimp-Male-Yolo-Tracking](https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking), and integrates first-frame water classification, size conversion and weight regression from [ShrimpVisionRT](https://github.com/chenne0819/ShrimpVisionRT).

The integration runs in Python, not in the PowerShell launchers. The web application is a separate sibling directory, [`../web/`](../web/), with its own environment. Run inference commands from **`tracking/`**, not the monorepo root.

## Features and limits

| Feature | Behavior | Enable with |
| --- | --- | --- |
| Water appearance | Classify the first frame of each source as `clear` or `turbid`, with confidence | `water_quality = true` |
| Turbid-water policy | `stop` ends the source before shrimp inference; `report` records and continues | `water_policy = "stop"` or `"report"` |
| Estimated length | Original-frame OBB long edge, reference scaling, then the original length regressor; output in mm | `biometrics = true` |
| Estimated width | OBB short edge and width regressor; explicitly a bounding-box proxy, shown as `W~` | `biometrics = true` |
| Estimated weight | Calibrated length by default, or calibrated length plus width proxy; output in g | `weight_mode = "length"` or `"length-width"` |
| Overlays and exports | Append measurements to existing records and per-ID summaries; save monitoring settings | Automatic with enabled monitoring and saved output |

Set `water_quality = true` and `biometrics = true` in TOML to enable both features. The supplied config currently enables `biometrics` and disables `water_quality`; their five monitoring weights are included. Model paths alone do not enable a feature. The detector, tracker, IDs and final sex voting remain in charge. `preview_only = true` shows the annotated preview without saving files; use `preview_only = false` to export results.

Water appearance is not pH or dissolved oxygen and is not checked continuously throughout the video. Length, width and weight require physical validation and calibration for a new camera; current defaults do not establish measurement accuracy.

## Clone and create the tracking environment

```powershell
git clone https://github.com/chenne0819/TIDE-Shrimp-Monitoring.git
cd TIDE-Shrimp-Monitoring/tracking
py -3.14 -m venv ../.venv
..\.venv\Scripts\Activate.ps1
python -m ensurepip --upgrade
python -m pip install -r requirements-dev.txt
python -m pip uninstall -y albumentations albucore opencv-python-headless
python -m pip install --force-reinstall --no-deps 'opencv-python>=4.10,<5'
```

Tracking uses the repository-root `.venv` with Python 3.14; reuse it if it already exists. Do not create a separate `tracking/.venv`. If PowerShell activation is blocked, use `..\.venv\Scripts\python.exe` instead of `python` from `tracking/`. The optional Windows `setup-monitoring.ps1` performs equivalent setup and checks the interpreter version before installing packages. On Linux, use `python3.14 -m venv ../.venv` and `source ../.venv/bin/activate`, then the same pip commands. The maintained setup targets Windows/Linux with NVIDIA CUDA; other platforms require separate dependency configuration. Preview requires a desktop display and an OpenCV GUI backend.

`requirements.txt` contains runtime dependencies and pins the matching NVIDIA CUDA 12.6 builds `torch==2.10.0+cu126` and `torchvision==0.25.0+cu126` from the official PyTorch index, plus `scikit-learn==1.9.1`. `requirements-dev.txt` adds pytest. Use Python 3.14 on Windows/Linux and a compatible NVIDIA driver. The four regressors and water checkpoint are now included. The regressors were originally saved with scikit-learn 1.6.1; keep that historical version in provenance rather than treating it as the current dependency. Cross-version estimator loading can emit compatibility warnings, and functional checks do not establish camera-specific measurement accuracy. The other dependency ranges are not a complete environment lock. Recreate virtual environments on another computer instead of copying them.

Verify actual GPU execution after installation:

```powershell
..\.venv\Scripts\python.exe check-gpu.py
```

The check runs a CUDA matrix calculation and torchvision CUDA NMS without loading private model weights. The Windows setup helper runs this check and fails if CUDA is unavailable. YOLO automatically selects CUDA when available, and the CNN sex classifier does likewise; image decoding, OpenCV processing and the scikit-learn regressors still run on CPU. GPU wheels alone do not validate model accuracy or make every pipeline operation a GPU operation.

CUDA 12.6 is the wheel runtime, not the maximum CUDA version printed by `nvidia-smi`. A newer driver may report CUDA 13.0 while running these CUDA 12.6 wheels. This setup does not target macOS or AMD GPUs.

## Included monitoring models and additional detector assets

**The four original regression models and the water-classification checkpoint are included in this repository.** They are ordinary Git files, so cloning retrieves them without Git LFS. Their bytes match the [published ShrimpVisionRT models](https://github.com/chenne0819/ShrimpVisionRT/tree/b5e75baafc84cbcf1c88fe178d3512289e657e7c/shrimp_OBB/Model).

The trained YOLO detector and sex-classification bundle is still not included; obtain compatible weights separately from the maintainer. `git lfs pull` does not supply that omitted bundle. A prepared environment, original measurement spreadsheets/training datasets, and calibration for your camera are also not included.

Use this layout under `tracking/model/`; `water/` and the four files in `biometrics/` are already populated in a fresh clone:

```text
model/
  yolo/
    best-obb-yolo11m-head_tail.pt       # Required shrimp/head/tail OBB for the single tracking entry
  cnn/
    best_resnet18-run3.pt              # Optional alternative
    best_resnet34-run3.pt              # Optional alternative
    best_resnet50-run3.pt              # Default head/tail sex classifier
  water/
    logistic_regression_model.pth      # Included water classifier
  biometrics/
    final_linear_model_length.pkl     # Included length regression
    final_linear_model_width.pkl      # Included width regression
    polynomial_regression_model_degree3.pkl # Included length-only weight model
    multi_feature_model.pkl           # Included length + width weight model
    provenance.json                   # Included metadata, not a model
  assets-manifest.json                 # Included origins, filenames and hashes
```

Supply the required OBB checkpoint and one compatible sex-classification checkpoint. Water classification uses the included checkpoint; biometrics loads all four included regressors, even in length-only weight mode. Enable these features with the TOML `water_quality` and `biometrics` booleans. The entry does not accept `--monitoring`. The web worker enables both features in an independent per-job TOML and invokes `--config`.

| Entry point | Default models relative to `tracking/` |
| --- | --- |
| `general_track.run_track` | OBB above + `model/cnn/best_resnet50-run3.pt` |

Head/tail tracking defaults to ResNet50. Select compatible alternatives with the TOML `classifier_model` field; no HBB detection model is used.

The execution settings are in `general_track/config.toml`. Relative input, model and output paths resolve against that TOML file, independently of the working directory. Absolute paths are also supported.

The newer detection/classification bundle was user-provided. The bundled water and regression weights were recovered unchanged from the user's original local ShrimpVisionRT `shrimp_OBB/Model` directory; no random replacement weights were used. The [asset manifest](model/assets-manifest.json) and [regression provenance](model/biometrics/provenance.json) record origins, hashes and model details without personal source paths. The manifest also describes detector/classifier assets that must be obtained separately.

## Run inference

Use the repository-root inference environment and remain in `tracking/`. Edit [general_track/config.toml](general_track/config.toml): provide your own input video and OBB/CNN weights, set their paths, optionally uncomment `max_frames` for a short test, and configure the monitoring booleans. Private input recordings are not bundled; the sample video path must be adjusted on a fresh clone.

```powershell
..\.venv\Scripts\python.exe -m general_track.run_track
..\.venv\Scripts\python.exe -m general_track.run_track --config general_track/config.toml
```

The entry accepts only `--config` and `--help`; old inference flags are removed. Use an integer `video = 0` for a camera. Omit max_frames to process the full source. Preview and crops are TOML booleans. The optional Windows wrapper accepts `-Config` and does not automatically enable monitoring.

The web worker uses a per-job TOML with absolute asset paths and saves the existing result file schemas. See the [module guide](general_track/README.md) for behavior and module responsibilities. The old `Train/` directory is not part of this working tree; training-only tests were retired with those removed entry points. Runtime configuration tests use independent fixtures rather than the editable sample TOML.


## Outputs

| Mode | Default output root relative to `tracking/` |
| --- | --- |
| Head/tail tracking and classification | `general_track/exports/run_track/` |

Runs create video/timestamp subdirectories. Tracking produces `result.mp4`, `detections.csv` and `per_shrimp.csv`, retaining the head/tail classifier and majority votes. `save_crops = true` saves classifier inputs. Monitoring adds:

- `length_px`, `width_px`: OBB edges mapped to the reference canvas, not source pixels.
- `length_mm`, `width_mm`, `weight_g`, `width_source=obb_proxy`, `weight_method`, `measurement_status`: estimates and interpretation; invalid values remain empty.
- `water_label`, `water_confidence`: first-frame classification when enabled.
- `measurement_samples`, `mean_length_mm`, `mean_width_mm`, `mean_weight_g`: per-ID summaries. The count is valid length observations; each mean uses that field's valid values.
- `monitoring.json`: status/conversion settings; `water_quality.csv` when water classification is enabled.

A turbid source with `stop` records `skipped_turbid`, does not move the input and does not invent detection results. IDs are video-local; totals across videos are not a deduplicated pond population.

## Calibration and replacement models

Defaults retain the old **800 × 450 reference canvas and 2.5 px/mm**. For source `(W, H)`, `scale = min(800/W, 450/H)` is applied equally to the OBB long/short edges. Each reference edge is divided by pixels-per-mm, then passed to its original regressor. Length-only weight regression uses calibrated length. This does not alter detector input or tracking coordinates.

The short edge is an OBB width proxy; the original project used segmentation width. Overlays show `W~` and weight defaults to length only. Camera distance, field of view, lens, refraction and shrimp depth require physical validation and possibly new regressors.

Measure a known object at the shrimp plane. If the reference size equals source resolution, its scale is 1; otherwise apply the same reference scale before computing pixels-per-mm. **Example only:** if a 20 mm object measures 100 pixels in a 990 × 1398 reference canvas, use:

Update these TOML fields:

```toml
measurement_reference_size = [990, 1398]
pixels_per_mm = 5.0
weight_mode = "length"
```

These numbers are not a supplied calibration. Check against measured shrimp length, width and mass; retrain/replace regressors when needed. Keep differently calibrated recordings separate. Calibration belongs to each tracking TOML file. Web job-specific calibration must be addressed when its worker is migrated; editing a standalone config does not implement that migration.

`biometrics_model_dir` selects a replacement directory containing the same four filenames. Models must support `joblib.load`, `.predict()` and the expected feature count: one for length, width and length-only weight; `[length_mm, width_mm]` for two-feature weight. `water_model` requires the original `Linear(784, 2)` state dictionary. Different architectures require loader changes. Only load serialized models from trusted sources.

## Tests and upstream credits

For the six sex-labeled local videos, see [offline EMA threshold evaluation](docs/ema-evaluation.md).
The evaluator collects probabilities once and compares replay thresholds without changing the live settings.
The [tuning summary](docs/ema-threshold-results.md) is versioned; raw recordings and local evaluation outputs are not.

After installing the tracking dependencies, run from `tracking/`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
```

Unit tests use temporary fixtures. Real-asset checks also exercise the included water checkpoint and four regressors; they explicitly skip if those assets are removed. The full suite still includes legacy training-path checks and configuration fixtures tied to editable sample settings; any failures must be reported rather than described as a green suite. See the [integration guide](docs/monitoring-integration.md) for model contracts and outputs. Software checks do not validate physical measurement accuracy.

The [2026-10-17 verification snapshot](docs/validation-20261017.md) records actual
results: the focused monitoring/pipeline suites pass, while the full suite still
has twenty legacy-path/fixture failures. It also records cross-version warnings
and the short real-video monitoring check.

Tracking/sex inference is based on Shrimp-Male-Yolo-Tracking revision `5662c81ba1ad86b04cbc0bfe6206df1599dbc36a`. Water/regression compatibility is based on ShrimpVisionRT revision `dd876980b83e42986b54c1ebeb52017c0728f113`. The body of the [original upstream README archive](docs/README-original.md) is preserved verbatim in its original language, beneath an English archive note. Its old commands and paths are historical reference; this README and current CLI help are the maintained setup instructions.
