# Historical local integration validation — 2026-09-20

This record describes runs in the original local integration checkout, before packaging the monorepo. It does not assert that private weights or validation outputs are included in the publication, or that those model runs were repeated in this publication copy. Current setup is in the [tracking README](../README.md); run its commands from `TIDE-Shrimp-Monitoring/tracking/`.

- Monitoring source: ShrimpVisionRT revision `dd876980b83e42986b54c1ebeb52017c0728f113`.
- Tracking source: Shrimp-Male-Yolo-Tracking revision `5662c81ba1ad86b04cbc0bfe6206df1599dbc36a` plus the integration changes.
- Recorded environment: Python 3.12.12, scikit-learn 1.6.1, PyTorch 2.14.0 CPU, Ultralytics 8.4.156, OpenCV 4.14.0 with WIN32UI.

## Initial integration checks

`python -m pytest tests -q` initially completed with **80 passed**. Coverage included real-regressor formulas/feature order/rounding, rotated polygons and source resolutions, uniform scaling of portrait video, invalid/missing values, equivalence to original torchvision water preprocessing, actual classifier outputs, all four integration hooks, retained tracking parameters/IDs, stop/report policies, first-frame-only handling before prescans and for cameras, CSV/per-ID fields, preview-only and exceptional cleanup.

All four entry points' `--help`, Python compilation, `git diff --check`, and both PowerShell scripts' syntax checks passed. The launcher was also executed.

| Real-model check | Recorded result |
| --- | --- |
| General OBB + HBB + ByteTrack, bottom-view input `公母蝦仰拍-1.mp4`, 12 frames | 72 observations, six IDs, water/size/weight/per-ID output and a decodable MP4 |
| Head/tail OBB + ResNet18 + ByteTrack, same input | Initial eight-frame run; another four-frame run after uniform-scaling correction |
| Single-frame predict + newer OBB/HBB, same input | Four frames completed with existing reports and added monitoring fields |
| Original turbid input + default stop | First-frame `turbid`, confidence 0.923580; `skipped_turbid`, with no fabricated result video |
| Original clear input, first frame | `clear`, confidence 0.986840 |
| New bottom-view input, first frame | `turbid`, confidence 0.999953; tracking smoke runs used `report` |

The general-tracking output was recorded at `general_track/exports/run_track/公母蝦仰拍-1/20260920_091931/`, with `validation_outputs/final_preview.jpg` and other evidence under `validation_outputs/`. These were local artifacts, excluded from Git and not supplied with the publication.

Copied model SHA-256 values were checked against the supplied originals. The [asset manifest](../model/assets-manifest.json) and [regression provenance](../model/biometrics/provenance.json) preserve origins, hashes and coefficients without personal filesystem paths.

## Default model-path correction

After checking the supplied `yolo/` bundle, predict's OBB/HBB and temporal tracking's OBB defaults were corrected to `model/yolo/`. Head/tail classification now defaults to `model/cnn/best_resnet18-run3.pt`; initial runs had explicitly selected ResNet18.

- Head/tail tracking and predict each completed a real-video one-frame run without model overrides.
- The related general/predict/temporal integration tests passed again: **34 passed**.
- All five YOLO checkpoints were inspected: four HBB checkpoints were three-channel `detect` models with `male_line`; the three-channel OBB model contained `shrimp`, `shrimp_head` and `shrimp_tail`.

No replacement `model/best.pt` or root-level `model/best-hbb-yolo11l.pt` was needed. The unavailable YOLO sex classifier is optional; the unavailable nine-channel checkpoint affects only temporal mode.

## Portability checks

Defaults resolve relative to the tracking code, while explicit relative CLI paths retain working-directory semantics. Six portability tests passed, including changing the working directory and copying relevant code plus lightweight real water/regression assets into a temporary directory containing spaces and Chinese characters. Loading and inference succeeded there. Large YOLO checkpoints were not copied during this relocation test, and this was not an operating-system portability test.

The personal absolute path was removed from the OBB training dataset YAML. Ultralytics' actual dataset resolver confirmed that the dataset directories were resolved from the YAML location after relocation; training was not started. A further **43 integration/water tests** passed during that change. Those targeted runs did not initially replace the earlier complete-suite result.

## Latest complete run and real execution

After the portability changes, the complete suite was rerun on the same date: **86 passed in 55.02 seconds**, exit code 0, with no errors or warnings.

Using `video/公母蝦仰拍-1.mp4`, the current model defaults and `--monitoring --water-policy report --max-frames 8`, the following entry points ran without model overrides. Predict additionally used `--skip-frames 1`:

| Entry point | Execution | Output verification |
| --- | --- | --- |
| `general_track.run_track` | Eight frames, exit code 0 | 48 measurement records, water record and eight-frame video |
| `general_track.run_head_tail_track` | Eight frames, exit code 0 | 48 measurement records, water record and eight-frame video |
| `predict.run_predict` | Eight frames, exit code 0 | 48 measurement records, water record and eight-frame video |

Outputs were under `validation_outputs/smoke_20260920_portable/{general,head_tail,predict}/`. All three `monitoring.json` files reported `completed`; measurements were finite and positive; all three MP4 files decoded through frame eight. These were saved-output runs without preview windows.

## Publication-copy regression check — 2026-09-22

The publication copy passed **86 tests** with the original private water and regression assets supplied locally. Those assets remain ignored and are not included in Git. This was a regression test run; the historical real-video model runs above were not repeated for publication.

## Limits and reproduction

This validates software integration and short-video execution, not accuracy against new-camera ground truth or full-video endurance. The water classifier's high turbid confidence does not establish correctness for the new view. OBB width differs from legacy segmentation width, and the new camera was not physically calibrated. Real nine-channel temporal-HBB inference was not performed because its weights were unavailable. The default ResNet classifier, rather than the missing optional YOLO classifier, was validated.

The original integration left the old ShrimpVisionRT source unchanged. At the time of the recorded runs, the work was local; this historical statement does not describe the later monorepo's publication status.

A fresh clone needs the private water and four regression assets to reproduce the full test suite, plus the relevant newer detector/classifier assets and an input video for real inference. Some inherited videos use Git LFS, but LFS pull does not retrieve the omitted model bundle. From the monorepo root, `cd tracking`, prepare the environment/assets, then run `python -m pytest tests -q`. See the [maintained setup guide](../README.md) for paths and calibration requirements.
