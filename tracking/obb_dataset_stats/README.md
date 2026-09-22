# OBB dataset statistics and crop extraction

This upstream utility is separate from the integrated monitoring entry points. It uses YOLO OBB `track()` without HBB or CNN inference; it does **not** add water, length, width or weight estimates.

From the monorepo root, `cd tracking`, activate the tracking environment, and supply the private head/tail OBB checkpoint and an input video:

```powershell
python -m obb_dataset_stats.build_obb_dataset_stats --video video/sample.mp4 --obb-model model/yolo/best-obb-yolo11m-head_tail.pt
```

`--video` may be repeated. Without it, the inherited defaults refer to six upstream inputs: `video/公蝦仰拍-1.mp4` through `公蝦仰拍-3.mp4` and `video/母蝦仰拍-1.mp4` through `母蝦仰拍-3.mp4`. These are filenames, not guaranteed bundled local media. Provide your own inputs or retrieve available upstream LFS objects. Model/setup requirements are in the [tracking README](../README.md).

The utility records video name, frame index, shrimp ID and OBB confidence per accepted crop. Summaries include video FPS, shrimp ID, observed-frame count and total video frames. OBB crops are rectified and aligned head-left: a unique enclosed `shrimp_head` takes priority; otherwise a unique `shrimp_tail` determines orientation. If neither can establish direction, that crop is not saved.

Default output:

```text
obb_dataset_stats/outputs/<timestamp>/
  frame_stats.csv
  shrimp_summary.csv
  <video_name>_dataset/
    ID_001/
      frame_000000_conf_0.9123.jpg
```

Use `--output-root`, `--tracker`, `--conf` and `--iou` as needed; `--help` shows current options. This documentation describes the retained upstream utility and does not claim a new real-model validation for it.
