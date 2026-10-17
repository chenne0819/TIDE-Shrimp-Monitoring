# Tracking verification snapshot — 2026-10-17

This snapshot verifies software behavior in the current local environment. It
does not establish model accuracy, camera calibration or web integration success.

## Environment and assets

- Repository-root `.venv`, Python 3.14.3.
- torch 2.10.0+cu126, torchvision 0.25.0+cu126, scikit-learn 1.9.1.
- The four original biometrics regressors and water checkpoint are present.
  Their five SHA-256 hashes match the checked-in provenance/manifest.
- OBB and ResNet50 weights were supplied locally; they are not published as part
  of this verification. Input videos and generated outputs remain local.

## Actual checks

| Check | Result |
| --- | --- |
| Full tracking suite | 163 passed, 20 failed, 0 skipped, 34 warnings |
| Biometrics, water, pipeline, preview smoothing and EMA evaluation suites | 113 passed, 0 skipped, 34 warnings |
| Real-video monitoring smoke run | 8 decoded output frames, 38 detections, all 38 with finite positive length/width/weight |
| Water integration | First-frame classifier executed; report policy allowed inference to continue |
| Output contracts | Annotated MP4, detections/per-ID CSV, water CSV and monitoring JSON created |
| Display check | A decoded result frame contains measurement and water annotations |
| Configuration preservation | Checked-in TOML unchanged by the smoke run |

The smoke run enabled water and biometrics in memory, used `water_policy="report"`,
`weight_mode="length"`, reference size 800 × 450 and 2.5 pixels/mm, and ran the
CNN on CUDA. The real-asset regression tests also checked both weight modes.
No GUI preview window was launched for this verification.

## Known full-suite failures

- Ten failures reference deleted `Train/` sources: nine CNN training-contract
  cases and one training-dataset path case.
- Ten failures in `test_track_settings.py` copy the editable sample config into
  a temporary directory. It now enables biometrics, but those temporary fixtures
  do not include the four model files. These are fixture/config isolation issues;
  the sample also sets `cnn_threshold=0.03`, while an old assertion assumes it is
  omitted. No tests were removed, skipped or weakened for this document change.
- The 34 warnings include loading scikit-learn 1.6.1 estimators under 1.9.1.
  The focused parity and smoke checks pass in this environment, but cross-version
  warnings are retained and should not be interpreted as universal compatibility.

The full suite is **not green**. Update or restore obsolete training coverage and
isolate config fixtures as a separate test-maintenance change before claiming a
clean full-suite result. New-camera physical measurement accuracy still needs
independent measured ground truth.

## Reproduce

Run from `tracking/` using the existing root environment:

```powershell
..\.venv\Scripts\python.exe -B -m pytest tests -q -ra
..\.venv\Scripts\python.exe -B -m pytest tests/test_biometrics.py tests/test_water_monitoring.py tests/test_general_monitoring.py tests/test_preview_smoothing.py tests/test_evaluate_ema.py -q -ra
```

Use a unique writable `--basetemp` beneath the repository's ignored `test-results/`
if the system temporary directory is restricted. Test fixtures write temporary
files. A new verification can differ if the editable config, source code, model
assets or environment changes. Preserve the dated result rather than silently
rewriting it as a current guarantee.
