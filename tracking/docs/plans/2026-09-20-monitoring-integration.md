# Shrimp monitoring integration implementation plan

Historical plan completed on 2026-09-20 in the original integration checkout. Model-copy steps below describe local development; private weights are excluded from this publication. Current setup and required assets are in the [tracking README](../../README.md).

**Goal:** Port ShrimpVisionRT water classification, size calibration and weight regression into the new project's existing inference entry points.

**Architecture:** A shared `shrimp_monitoring` package consumes original-frame shrimp OBB polygons after the new project's detection/tracking. It does not load the old YOLO/segmentation/Norfair stack. First-frame water classification runs before detection, with an optional stop policy. CLI opt-in keeps existing workflows compatible.

**Tech Stack:** Python 3.12, NumPy/OpenCV/Pillow, existing Ultralytics/PyTorch, joblib/scikit-learn, pytest.

## Source evidence

- Old source revision: `dd876980b83e42986b54c1ebeb52017c0728f113`.
- New source revision: `5662c81ba1ad86b04cbc0bfe6206df1599dbc36a`.
- `shrimp_OBB/logistic_water.py`: gray 28x28 -> normalized 784-vector -> Linear(784,2), class order turbid/clear; preserve legacy ndarray channel interpretation.
- `shrimp_OBB/utils/plots.py`: longest OBB edge / 2.5 -> length regression -> round(1); segmentation width / 2.5 -> width regression -> round(1); length+width or length-only weight model.
- Upstream omitted regression/water assets, but matching original code and model files were recovered from the original local ShrimpVisionRT `shrimp_OBB/Model` directory. Provenance records retain hashes and model metadata without a machine-specific personal path.
- New project's short OBB side is a width proxy, not the original segmentation measurement. Default weight uses the original length-only fallback; length+width mode is explicit and requires recalibration/validation.

## Tasks

1. Create `shrimp_monitoring/biometrics.py` and `tests/test_biometrics.py`: validated OBB geometry, real regression loading, scaling/rounding, invalid outputs, explicit width provenance and weight mode; copy the four original model assets with provenance hashes.
2. Create `shrimp_monitoring/water.py`, `runtime.py`, `cli.py`, `__init__.py` and water/runtime tests: cached classifier, first-frame gate, safe result export, shared arguments and drawing/summary helpers. Copy original water checkpoint.
3. Update `general_track/run_track.py`, `run_head_tail_track.py` and their two active pipelines. Add fields to per-detection/per-ID outputs and overlays, while preserving original model calls and voting. Test with controlled detectors and actual regression models.
4. Update `predict` and `multi_channel_track` CLI/analyzers with the same shared hooks. Keep first-frame water check before auto-total scans and frame skipping. Preserve tracking and temporal input.
5. Add requirements, a maintained integration guide with exact commands, model manifest and calibration limitations. Confirm model availability independently from software tests.
6. Run targeted pytest, all four `--help` entry points, compile checks and real-asset parity checks; run a short real-video smoke if the new detector weights are available. Record any missing assets explicitly.

## Acceptance checks

- New detection and tracker classes/weights are retained.
- Source-resolution geometry, scale, model feature order and rounding match old formulas.
- Water clear/turbid labels and confidence match old preprocessing and real weights.
- Turbid gate writes a clear status and does not invoke detection, move source videos or lose resources.
- Existing CLI behavior remains available without monitoring flags; preview-only creates no outputs.
- Tests use synthetic fixtures only as labeled test inputs, never as replacement deployed weights.

## Completion

All six implementation tasks were completed. Four entry points were integrated, the initial suite passed 80 tests, and the three entry points with available compatible weights passed real-video smoke checks. The later complete suite passed 86 tests. The nine-channel model remains unavailable. See the [validation record](../monitoring-validation.md) for scope and evidence. Reference mapping was corrected to uniform aspect-preserving scaling after checking the original `scale_polys` and the new portrait video; source-camera calibration is still required for physical accuracy.
