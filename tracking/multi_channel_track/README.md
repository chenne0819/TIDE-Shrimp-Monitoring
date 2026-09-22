# Temporal multi-channel tracking

This entry point combines YOLO OBB `track()` with a three-frame, nine-channel HBB. It buffers rectified RGB crops per track ID and stacks crops from three time points for temporal `male_line` detection. It also contains the shared [water/size/weight monitoring hooks](../docs/monitoring-integration.md).

**A compatible nine-channel HBB checkpoint is required and is not bundled.** Ordinary single-frame, three-channel HBB weights cannot substitute for it. The code integration has automated coverage, but real temporal inference has not been verified. No private weights are included in this publication.

From the monorepo root, `cd tracking`, activate its environment and follow the [model setup](../README.md#private-model-assets-required-after-cloning). After supplying your own video and the compatible checkpoint:

```powershell
python -m multi_channel_track.run_multi_channel_track --video video/sample.mp4 --monitoring --water-policy report --preview-only

# Select a different spacing between the three temporal crops.
python -m multi_channel_track.run_multi_channel_track --video video/sample.mp4 --hbb-temporal-step-frames 10 --monitoring --water-policy report --preview-only
```

Defaults are `model/yolo/best-obb-yolo11m-head_tail.pt` and `model/best-hbb-3frame.pt`, resolved from the tracking directory. Override with `--obb-model` and `--hbb-model`; explicit relative overrides use the working directory. Dynamic IDs (`--unknown-total`) are the default; use `--known-total --total-shrimp N` when supplying an expected count.

This CLI does not expose `--skip-frames`, `--max-frames`, `--keyframes`, `--window-sec`, `--truth-csv`, `--preview-scale` or `--preview-wait-ms`. Do not copy those options from predict/general-tracking examples. Preview requires a display and GUI OpenCV. Remove `--preview-only` to save output, optionally adding `--preview` to display it as well.

Output is grouped by temporal frame spacing, for example `multi_channel_track/exports/10FPS/<video_name>/analysis_<timestamp>/`. The inherited `FPS` folder suffix is a naming convention for **frame spacing**, not a measured processing frame rate. Existing exports include `videos/result_video.mp4`, per-ID count charts and time-window sex summaries. Monitoring files appear at the run root; preview-only writes none.

Water checks the first frame only. Direct Python policy defaults to `stop`; examples use `report`. Size and weight retain legacy calibration and need physical validation for new cameras; the OBB short edge is a width proxy.

| Module | Responsibility |
| --- | --- |
| `modules/analyzer.py` | Temporal tracking flow and monitoring hooks |
| `modules/obb_track.py` | OBB `track()` and track-ID extraction |
| `modules/temporal_hbb.py` | Nine-channel stacking and coordinate recovery |
| `modules/config.py` | Default paths and thresholds |
| `modules/id_assigner.py` | Tracker-to-shrimp ID mapping |
| `modules/preprocessing.py` | OBB crop rectification |
| `modules/reporting.py` | CSV, figures and result video |

See [upstream credits and setup](../README.md) and [monitoring requirements](../docs/monitoring-integration.md).
