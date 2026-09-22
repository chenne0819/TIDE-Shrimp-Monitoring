# TIDE tracking and monitoring

This directory is the Python inference component of **TIDE-Shrimp-Monitoring**. It retains YOLO detection, head/tail alignment, sex classification, voting and tracking from [Shrimp-Male-Yolo-Tracking](https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking), and integrates first-frame water classification, size conversion and weight regression from [ShrimpVisionRT](https://github.com/chenne0819/ShrimpVisionRT).

The integration runs in Python, not in the PowerShell launchers. The web application is a separate sibling directory, [`../web/`](../web/), with its own environment. Run inference commands from **`tracking/`**, not the monorepo root.

## Features and limits

| Feature | Behavior | Enable with |
| --- | --- | --- |
| Water appearance | Classify the first frame of each source as `clear` or `turbid`, with confidence | `--water-quality` |
| Turbid-water policy | `stop` ends the source before shrimp inference; `report` records and continues | `--water-policy stop` or `report` |
| Estimated length | Original-frame OBB long edge, reference scaling, then the original length regressor; output in mm | `--biometrics` |
| Estimated width | OBB short edge and width regressor; explicitly a bounding-box proxy, shown as `W~` | `--biometrics` |
| Estimated weight | Calibrated length by default, or calibrated length plus width proxy; output in g | `--weight-mode length` or `length-width` |
| Overlays and exports | Append measurements to existing records and per-ID summaries; save monitoring settings | Automatic with enabled monitoring and saved output |

`--monitoring` enables both water classification and biometrics. Without `--monitoring`, `--water-quality` or `--biometrics`, the additions remain disabled. A model-path argument alone does not enable a feature. The newer detector, tracker, IDs and sex-voting logic remain in charge; the old YOLO, segmentation and Norfair inference stack is not loaded.

Water appearance is not pH or dissolved oxygen and is not checked continuously throughout the video. Length, width and weight require physical validation and calibration for a new camera; current defaults do not establish measurement accuracy.

## Clone and create the tracking environment

```powershell
git clone https://github.com/chenne0819/TIDE-Shrimp-Monitoring.git
cd TIDE-Shrimp-Monitoring/tracking
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m ensurepip --upgrade
python -m pip install -r requirements-dev.txt
# Albumentations also installs headless OpenCV; restore the GUI build for preview.
python -m pip uninstall -y opencv-python-headless
python -m pip install --force-reinstall --no-deps 'opencv-python>=4.10,<5'
```

If PowerShell activation is blocked, use `.\.venv\Scripts\python.exe` instead of `python`. The optional Windows `setup-monitoring.ps1` performs equivalent setup. On macOS/Linux, after installing Python 3.12, use `python3.12 -m venv .venv` and `source .venv/bin/activate`, then the same pip commands. Recorded inference validation used Windows with CPU PyTorch; macOS/Linux inference and CUDA configurations have not been validated here. Preview requires a desktop display and an OpenCV GUI backend.

`requirements.txt` contains runtime dependencies; `requirements-dev.txt` adds pytest. `scikit-learn==1.6.1` matches the original serialized regressors. These are dependency constraints, not a complete environment lock. Install a suitable CUDA PyTorch build separately if needed. Recreate virtual environments on another computer instead of copying them.

## Private model assets required after cloning

**This publication includes code and provenance metadata, not the private weights, a prepared environment, or calibrated camera data.** Obtain compatible weights separately from the maintainer. There is currently no public model download; `git lfs pull` does not supply the omitted bundle.

Place assets under `tracking/model/` with these filenames:

```text
model/
  yolo/
    best-obb-yolo11m-head_tail.pt       # Shrimp/head/tail OBB, shared by all modes
    best-hbb-yolo11n.pt                # Default general-tracking HBB
    best-hbb-yolo11l.pt                # Default single-frame predict HBB
    best-hbb-yolo11s.pt                # Optional single-frame alternative
    best-hbb-yolo11m.pt                # Optional single-frame alternative
  cnn/
    best_resnet18-run3.pt              # Default head/tail sex classifier
    best_resnet34-run3.pt              # Optional alternative
    best_resnet50-run3.pt              # Optional alternative
  water/
    logistic_regression_model.pth
  biometrics/
    final_linear_model_length.pkl
    final_linear_model_width.pkl
    polynomial_regression_model_degree3.pkl
    multi_feature_model.pkl
    provenance.json                   # Included metadata, not a model
  assets-manifest.json                 # Included origins, filenames and hashes
```

Only the detector/classifier for your selected mode is required. Water classification requires its checkpoint; biometrics requires all four regressors, even in length-only weight mode.

| Entry point | Default models relative to `tracking/` |
| --- | --- |
| `general_track.run_track` | OBB above + `model/yolo/best-hbb-yolo11n.pt` |
| `general_track.run_head_tail_track` | OBB above + `model/cnn/best_resnet18-run3.pt` |
| `predict.run_predict` | OBB above + `model/yolo/best-hbb-yolo11l.pt` |
| `multi_channel_track.run_multi_channel_track` | OBB above + `model/best-hbb-3frame.pt` |

The optional YOLO sex classifier at `model/yolo/best-cls-yolo11m-run3.pt` was also unavailable. Head/tail tracking defaults to ResNet18 instead. Select alternatives with `--classifier-model` or `--hbb-model`. A normal three-channel HBB cannot replace the temporal mode's three-frame, nine-channel checkpoint. The obsolete `model/best.pt` and root-level `model/best-hbb-yolo11l.pt` are not required.

Default model locations resolve relative to `project_paths.py`, so they follow the `tracking/` directory when it moves. Explicit relative model, video and output paths use the working directory. Logs may display resolved absolute paths; defaults are not tied to a user account or drive.

The newer detection/classification bundle was user-provided. The water and regression weights were recovered unchanged from the user's original local ShrimpVisionRT `shrimp_OBB/Model` directory; no random replacement weights were used. The [asset manifest](model/assets-manifest.json) and [regression provenance](model/biometrics/provenance.json) record origins, hashes and model details without personal source paths. These describe previously available local assets, not weights included in a fresh clone.

## Run inference

Activate the tracking environment and remain in `tracking/`. Replace `video/sample.mp4` with your own video; that example file is not bundled. A camera index such as `--video 0` is accepted. Some inherited upstream videos use Git LFS; `git lfs install` and `git lfs pull` retrieve available LFS objects, or supply your own input.

```powershell
# General OBB + HBB + ByteTrack, limited to a short smoke test.
python -m general_track.run_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 30 --preview

# Head/tail tracking with the default ResNet18 classifier.
python -m general_track.run_head_tail_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 30

# Single-frame detection with existing ID assignment, not YOLO tracking.
python -m predict.run_predict --video video/sample.mp4 --monitoring --water-policy report --skip-frames 10

# Only after obtaining the compatible nine-channel HBB checkpoint.
python -m multi_channel_track.run_multi_channel_track --video video/sample.mp4 --monitoring --water-policy report
```

Remove `--max-frames` for a full source. The temporal entry point does **not** expose `--max-frames` or `--skip-frames`. `--preview` displays and saves output; `--preview-only` displays without writing video, CSV or monitoring files. Omit preview on a machine without a GUI.

Examples use `report` because the original water model classified the new bottom-view smoke video as turbid. The direct Python CLI defaults to `stop`. Confidence is not evidence of accuracy in that new setting.

The optional Windows wrapper `.\run-monitoring.ps1 -Video video/sample.mp4 -MaxFrames 30 -Preview` runs the general Python entry point with monitoring and `report`; always supply your own `-Video` after cloning. In PyCharm, choose the tracking `.venv` interpreter, working directory `tracking/`, and module name `general_track.run_track`. Use each entry point's `--help` for current options.

Module guides: [general tracking](general_track/README.md), [predict](predict/README.md), [temporal tracking](multi_channel_track/README.md), and [OBB dataset extraction](obb_dataset_stats/README.md). The inherited `run-all.py` is an outdated batch example with incompatible general-tracking arguments and old model paths; use the commands above. `Train/` retains upstream training code, requiring separate datasets and per-script configuration. This integration did not retrain the models or comprehensively refactor training.

## Outputs

| Mode | Default output root relative to `tracking/` |
| --- | --- |
| General tracking | `general_track/exports/run_track/` |
| Head/tail classification | `general_track/exports/head_tail_cls/` |
| Single-frame predict | `predict/exports/` |
| Temporal tracking | `multi_channel_track/exports/<step_frames>FPS/` |

Runs create video/timestamp subdirectories. General tracking preserves `result.mp4`, `detections.csv`, `per_shrimp.csv` and voting reports. Predict/temporal modes retain `data/`, `figures/` and `videos/`. Monitoring adds:

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

```powershell
python -m general_track.run_track --video video/sample.mp4 --monitoring --water-policy report --measurement-reference-size 990 1398 --pixels-per-mm 5.0 --weight-mode length
```

These numbers are not a supplied calibration. Check against measured shrimp length, width and mass; retrain/replace regressors when needed. Keep differently calibrated recordings separate. Website worker calibration is configured in the web project; one-off CLI overrides do not change future website jobs.

`--biometrics-model-dir` selects a replacement directory containing the same four filenames. Models must support `joblib.load`, `.predict()` and the expected feature count: one for length, width and length-only weight; `[length_mm, width_mm]` for two-feature weight. `--water-model` requires the original `Linear(784, 2)` state dictionary. Different architectures require loader changes. Only load serialized models from trusted sources.

## Tests and upstream credits

After supplying the original water checkpoint and four regressors, run from `tracking/`:

```powershell
python -m pytest tests -q
```

The full suite includes real-asset checks; a code-only clone cannot reproduce all of them without those files. See the [integration guide](docs/monitoring-integration.md) for model contracts and outputs.

Tracking/sex inference is based on Shrimp-Male-Yolo-Tracking revision `5662c81ba1ad86b04cbc0bfe6206df1599dbc36a`. Water/regression compatibility is based on ShrimpVisionRT revision `dd876980b83e42986b54c1ebeb52017c0728f113`. The body of the [original upstream README archive](docs/README-original.md) is preserved verbatim in its original language, beneath an English archive note. Its old commands and paths are historical reference; this README and current CLI help are the maintained setup instructions.
