# General Track

`general_track` 目前有兩個主要入口：

- `run_track`：head/tail OBB 校正蝦子方向，再用 HBB `male_line` 做滑動視窗投票。不使用 CNN。
- `run_head_tail_track`：head/tail OBB 校正蝦子方向，再用 ResNet/YOLO classification 做 female/male 分類。

兩個入口共用以下邏輯：

- `best-obb-yolo11m-head_tail.pt` 必須是 OBB 模型。
- OBB class 必須包含 `shrimp`, `shrimp_head`, `shrimp_tail`。
- 以 `shrimp` OBB 框為主裁切。
- 使用 `minAreaRect`、`getPerspectiveTransform`、`warpPerspective` 拉正蝦子。
- 依 head/tail 偵測結果把頭校正到左邊、尾巴在右邊。
- 預覽視窗會依螢幕大小等比例縮放。
- `--debug` 匯出時會把主畫面與右側 debug panel 一起寫進 `result.mp4`。

如果 `model/yolo/best-obb-yolo11m-head_tail.pt` 讀到的是：

```text
task=classify
names={0: 'female', 1: 'male'}
```

代表該檔案不是 head/tail OBB 模型，請換回正確模型。正確應為：

```text
task=obb
names={0: 'shrimp', 1: 'shrimp_head', 2: 'shrimp_tail'}
```

## run_track：OBB crop + HBB male_line + sliding window

這是目前主要的 tracking 入口。

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --debug
```

流程：

1. 使用 `best-obb-yolo11m-head_tail.pt` 以 YOLO `track()` + ByteTrack 偵測 `shrimp`, `shrimp_head`, `shrimp_tail`。
2. 以 `shrimp` OBB 框裁切並校正長寬方向。
3. 根據 head/tail 把頭校正到左邊。
4. 把整張校正後的 shrimp crop 送進 `best-hbb-yolo11n.pt` 偵測 `male_line`。
5. 不使用 CNN，也不再裁切腹部性徵區域。
6. 對每個 track ID 使用 300 frame 滑動視窗投票。

滑動視窗投票：

- 視窗長度預設 300 frames。
- 視窗為逐 frame 滑動，例如 `0~299`, `1~300`, `2~301`。
- 只輸出完整視窗。前 299 幀不產生 window；影片尾端不足 300 幀不另外補算。
- 投票值為：

```text
male_line 出現次數 / 滑動視窗長度
```

- 三種狀態用等分比例判斷：

```text
male_rate < 1/3        => female，顯示 F
1/3 <= male_rate < 2/3 => obs
male_rate >= 2/3       => male，顯示 M
```

- 如果某一幀突然沒偵測到 `male_line`，會等待 1 秒。1 秒內會沿用 male hit，避免短暫漏偵測造成投票跳動。

常用參數：

```powershell
python -m general_track.run_track `
  --video "video\公母蝦仰拍-1.mp4" `
  --obb-model "model\yolo\best-obb-yolo11m-head_tail.pt" `
  --hbb-model "model\yolo\best-hbb-yolo11n.pt" `
  --tracker bytetrack.yaml `
  --obb-conf 0.5 `
  --obb-iou 0.3 `
  --hbb-conf 0.0 `
  --window-frames 300 `
  --gt Male `
  --number-of-shrimps 5 `
  --debug
```

指定 GT 與蝦子數量後，會額外輸出 `video_info.csv` 與 `window_vote_summary.csv`：

```powershell
python -m general_track.run_track --video "video\公蝦仰拍-3.mp4" --gt Male --number-of-shrimps 5 --debug
python -m general_track.run_track --video "video\母蝦仰拍-2.mp4" --gt Female --number-of-shrimps 5 --debug
```

只測試前 100 frames：

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --debug --max-frames 100
```

只開預覽不保存：

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --preview-only --debug
```

注意：`--preview` / `--preview-only` 需要 OpenCV GUI backend。如果環境不能開視窗，請不要使用 preview；只用 `--debug` 仍可匯出含 debug panel 的影片。

輸出位置：

```text
general_track/exports/run_track/<video_name>/<timestamp>/
```

輸出檔案：

```text
result.mp4           主畫面；有 --debug 時包含右側校正蝦子 crop debug panel
detections.csv       每一幀、每隻蝦的 male_line 偵測與投票結果
sliding_windows.csv  每個 ID 的完整滑動視窗統計，window_length 預設為 300
per_shrimp.csv       每個 ID 的最後狀態與投票摘要
video_info.csv       獨立測試影片資訊
window_vote_summary.csv 滑動視窗投票結果總表
```

`video_info.csv` 欄位：

```text
Video, Ground Truth, Number of Shrimps, Duration, FPS, Total Frames, Valid Windows
```

`Valid Windows` 計算：

```text
max(0, Total Frames - window_frames + 1)
```

`window_vote_summary.csv` 欄位：

```text
Video, Ground Truth, Total Windows, Male Windows, Female Windows, Observation Windows, Final Prediction
```

`Final Prediction` 取 `Male Windows`、`Female Windows`、`Observation Windows` 三者最高者。

## run_head_tail_track：OBB crop + classifier

此入口保留給 CNN / YOLO classification 分類 female/male。

```powershell
python -m general_track.run_head_tail_track --video "video\公母蝦仰拍-1.mp4" --debug
```

流程：

1. 使用 `best-obb-yolo11m-head_tail.pt` 偵測 `shrimp`, `shrimp_head`, `shrimp_tail`。
2. 校正 shrimp crop，頭在左、尾在右。
3. 再裁切分類區域：

```python
left = total_length // 4
right = total_length - total_length // 2
top = horizontal_height // 5
bottom = horizontal_height - horizontal_height // 5
```

4. 把該 crop 送進 female/male classifier。

預設 classifier 在 `config.py`：

```python
MODEL_YOLO_CLS_PATH = "model/yolo/best-cls-yolo11m.pt"
```

如果要用 ResNet / ResNet-FPN，直接用參數指定：

```powershell
python -m general_track.run_head_tail_track --video "video\公母蝦仰拍-1.mp4" --classifier-model "model\cnn\best_resnet50-head_tail.pt" --debug
```

舊參數 `--cnn-model` 仍保留為相容別名：

```powershell
python -m general_track.run_head_tail_track --video "video\公母蝦仰拍-1.mp4" --cnn-model "model\cnn\best_resnet50_fpn-head_tail.pt" --debug
```

使用 YOLO classification 模型：

```powershell
python -m general_track.run_head_tail_track --video "video\公母蝦仰拍-1.mp4" --classifier-model "model\yolo\best-cls-yolo11m.pt" --debug
```

支援的 classifier：

- YOLO classification
- ResNet18
- ResNet34
- ResNet50
- ResNet50-FPN

只預覽不保存：

```powershell
python -m general_track.run_head_tail_track --video "video\公母蝦仰拍-1.mp4" --preview-only --debug
```

輸出檔案：

```text
result.mp4      主畫面；有 --debug 時包含右側 crop debug panel
detections.csv  每一幀分類結果
per_shrimp.csv  每個 track ID 的多幀 majority vote 結果
```

## Config

主要設定在：

```text
general_track/modules/config.py
```

重要模型路徑：

```python
MODEL_HEAD_TAIL_OBB_PATH = "model/yolo/best-obb-yolo11m-head_tail.pt"
MODEL_HBB_PATH = "model/yolo/best-hbb-yolo11n.pt"
MODEL_YOLO_CLS_PATH = "model/yolo/best-cls-yolo11m.pt"
MODEL_CNN_PATH = "model/cnn/best_resnet18_gray.pt"
IMGSZ_OBB = 640
IMGSZ_HBB = 416
HBB_CONF = 0.5
MIN_OBSERVATIONS_PER_SHRIMP = 3
```

## Local Modules

```text
run_track.py                     OBB + HBB male_line + sliding window 入口
run_head_tail_track.py           OBB + classifier 入口
modules/track_pipeline.py        run_track 的主要流程
modules/head_tail_pipeline.py    run_head_tail_track 的主要流程
modules/head_tail_common.py      OBB rows、head/tail 校正、preview/video/CSV 共用工具
modules/config.py                模型路徑與基礎參數
modules/obb_track.py             OBB track ID 抽取
```
