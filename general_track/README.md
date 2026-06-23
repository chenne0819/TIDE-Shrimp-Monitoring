# General Track

## Head/tail OBB + female/male ResNet18

```powershell
python -m general_track.run_head_tail_track --video video/example.mp4 --preview --save-crops
```

The classifier loader supports ResNet18, ResNet34, and ResNet50 checkpoints and detects the
architecture from the checkpoint's `architecture` or `model` metadata:

```powershell
python -m general_track.run_head_tail_track --video video/example.mp4 --cnn-model model/cnn/best_resnet50-head_tail.pt --preview-only
```

```powershell
python -m general_track.run_head_tail_track --video video/example.mp4 --cnn-model model/cnn/best_resnet34-head_tail.pt --preview-only
```

It also supports the YOLO11m classification model configured as
`MODEL_SEX_YOLO_CLS_PATH`:

```powershell
python -m general_track.run_head_tail_track --video video/example.mp4 --cnn-model model/yolo/best-cls-yolo11m.pt --preview-only
```

Preview without saving any output:

```powershell
python -m general_track.run_head_tail_track --video video/example.mp4 --preview-only
```

Add `--debug` to attach a debug panel to the right of the main preview. It vertically stacks all valid
rectified shrimp crops and marks the exact `[length/4, length-length/2]` by
`[height/5, height-height/5]` abdomen region sent
to ResNet18 in yellow. The list starts at the top of the panel. Press `D` while previewing
to show/hide the panel. The complete preview is proportionally fitted to the Windows desktop.
When `--debug` is supplied and output is enabled, the same main view and debug panel are
included in `result.mp4` on a fixed letterboxed canvas.

```powershell
python -m general_track.run_head_tail_track --video video/example.mp4 --preview-only --debug
```

This pipeline uses `best-obb-yolo11m-head_tail.pt`, associates head/tail centers with each
`shrimp` polygon, rectifies the shrimp with `minAreaRect` and a perspective warp, places the
head on the left, crops the `[length/4, length-length/2]` by `[height/5, height-height/5]`
region, and classifies it
with `best_resnet18-head_tail.pt`. A shrimp is skipped only when neither its head nor tail has
exactly one associated detection. Results include an annotated MP4, frame-level CSV, and a
per-track majority-vote CSV.

一般 YOLO OBB `track()` 分析入口，搭配單幀 HBB `male_line` 偵測。適合追蹤/攝影機預覽測試。

## Run

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
```

指定 tracker：

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --tracker bytetrack.yaml --preview-only
```

指定 HBB `male_line` 模型：

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --hbb-model "model\best-hbb-yolo11m.pt" --preview-only
```

攝影機測試：

```powershell
python -m general_track.run_track --video 0 --unknown-total --preview-only
```

目前此入口不開放 `--skip-frames`、`--max-frames`、`--keyframes`、`--window-sec`、`--truth-csv`、`--preview-scale`、`--preview-wait-ms`。

正式輸出會存到 `general_track/exports/`，包含 `videos/result_video.mp4`、每 ID 次數長條圖與每 10 秒公蝦機率折線圖。

輸出會依 OBB/HBB 模型分組，例如：

```text
general_track/exports/yolo11m-obb_and_yolo11m-hbb/公母蝦仰拍-1/analysis_<timestamp>/
general_track/exports/yolo11m-obb_and_yolo11s-hbb/公母蝦仰拍-1/analysis_<timestamp>/
```

## Local Modules

```text
modules/analyzer.py      track 分析流程
modules/obb_track.py     OBB track() 與 track id 抽取
modules/config.py        模型路徑與門檻
modules/id_assigner.py   ByteTrack id 到 Shrimp_ID 的映射
modules/preprocessing.py OBB crop/拉正
modules/reporting.py     輸出 CSV、圖表與結果影片
```
