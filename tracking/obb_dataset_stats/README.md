# OBB Dataset Stats

獨立於 `general_track` 的統計與裁切工具。

功能：

- 使用 YOLO-OBB `track()`，不使用 YOLO-HBB、不使用 CNN。
- 預設處理：
  - `video/公蝦仰拍-1.mp4`
  - `video/公蝦仰拍-2.mp4`
  - `video/公蝦仰拍-3.mp4`
  - `video/母蝦仰拍-1.mp4`
  - `video/母蝦仰拍-2.mp4`
  - `video/母蝦仰拍-3.mp4`
- 每一幀統計：影片名稱、frame index、蝦子 ID、OBB 信心分數。
- 整合統計：影片名稱、影片幀率、蝦子 ID、該蝦子出現總 frame 數、整部影片總 frame。
- 依 OBB 框裁切蝦子，校正長寬方向，並用 `shrimp_head` / `shrimp_tail` 把頭校正到左邊。
- 每支影片建立 `<影片名稱>_dataset`，同 ID 的裁切影像放在同一個 ID 資料夾。

## 使用方式

```powershell
python -m obb_dataset_stats.build_obb_dataset_stats
```

指定模型：

```powershell
python -m obb_dataset_stats.build_obb_dataset_stats --obb-model "model\yolo\best-obb-yolo11m-head_tail.pt"
```

輸出位置：

```text
obb_dataset_stats/outputs/<timestamp>/
```

輸出檔：

```text
frame_stats.csv
shrimp_summary.csv
公蝦仰拍-1_dataset/
  ID_001/
    frame_000000_conf_0.9123.jpg

裁切方向校正邏輯：

- 優先使用該 `shrimp` 框內唯一的 `shrimp_head` 判斷方向。
- 如果 head 不是唯一，改用該 `shrimp` 框內唯一的 `shrimp_tail` 判斷方向。
- 如果 head/tail 都無法唯一判斷，該幀該蝦 crop 不保存。
```
