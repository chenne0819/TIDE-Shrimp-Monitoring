# Single-frame prediction

`predict.run_predict` uses YOLO OBB `predict()`, not YOLO tracking. It retains the existing center-distance ID assignment and HBB analysis. It is suitable for sampled-frame analysis, CSV/figure/video exports and an optional OBB-only total-count prescan. Water, length, width-proxy and weight hooks are integrated as documented in the [monitoring guide](../docs/monitoring-integration.md).

From the monorepo root, `cd tracking`, activate its environment and supply the private models from the [tracking README](../README.md). Commands run from `tracking/`; provide your own `video/sample.mp4`.

```powershell
# Dynamic IDs, monitoring, and a short saved-output run.
python -m predict.run_predict --video video/sample.mp4 --monitoring --water-policy report --skip-frames 1 --max-frames 12

# Fixed expected count and sampled frames.
python -m predict.run_predict --video video/sample.mp4 --known-total --total-shrimp 6 --skip-frames 10 --monitoring --water-policy report

# Estimate total count with the existing OBB-only prescan.
python -m predict.run_predict --video video/sample.mp4 --auto-total --skip-frames 10 --monitoring --water-policy report
```

`--unknown-total` enables dynamic IDs and is the default. The inferred/prescribed count is not a deduplicated pond population. `--preview-only` shows the analysis without writing files; `--preview` displays and saves. Preview requires a desktop GUI. See `--help` for prescan, sampling, ground-truth and export options.

Default models are `model/yolo/best-obb-yolo11m-head_tail.pt` and `model/yolo/best-hbb-yolo11l.pt`. Use `--obb-model` or `--hbb-model` to override them. Defaults resolve from `tracking/`; explicit relative paths use the working directory. The obsolete `model/best.pt` and root-level HBB path are no longer needed.

Saved runs are placed under `predict/exports/`, retaining `data/`, `figures/` and `videos/`. Monitoring adds fields to existing records plus `monitoring.json` and, when enabled, `water_quality.csv` at the run root. Water is checked before prescanning/frame skipping; default Python policy is `stop`, while these examples explicitly continue with `report`. Physical size/weight accuracy requires calibration, and width is the OBB short-edge proxy.

| Module | Responsibility |
| --- | --- |
| `modules/analyzer.py` | Prediction workflow and monitoring hooks |
| `modules/obb_predict.py` | OBB `predict()` processing |
| `modules/config.py` | Default models and thresholds |
| `modules/id_assigner.py` | Center-distance ID assignment |
| `modules/preprocessing.py` | OBB crop rectification |
| `modules/reporting.py` | CSV, figures and result video |

The original tracking/sex project remains credited in the [tracking README](../README.md). Historical real-weight short-run evidence is in the [validation record](../docs/monitoring-validation.md); private weights are not included in a clone.
