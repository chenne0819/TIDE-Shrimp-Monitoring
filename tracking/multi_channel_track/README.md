# Multi Channel Track

YOLO OBB `track()` + 3-frame 9-channel HBB 分析入口。此模式會依 track id 累積 crop buffer，將 3 個時間點的 RGB crop 堆疊成 9-channel 輸入，用於 temporal HBB `male_line` 偵測。

## Run

```powershell
python -m multi_channel_track.run_multi_channel_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
```

調整 temporal 取樣間隔：

```powershell
python -m multi_channel_track.run_multi_channel_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --hbb-temporal-step-frames 10 --preview-only
```

目前此入口不開放 `--skip-frames`、`--max-frames`、`--keyframes`、`--window-sec`、`--truth-csv`、`--preview-scale`、`--preview-wait-ms`。

正式輸出會存到 `multi_channel_track/exports/`，包含 `videos/result_video.mp4`、每 ID 次數長條圖與每 10 秒公蝦機率折線圖。

輸出會依 `--hbb-temporal-step-frames` 分組，例如：

```text
multi_channel_track/exports/30FPS/公母蝦仰拍-1/analysis_<timestamp>/
multi_channel_track/exports/10FPS/公母蝦仰拍-1/analysis_<timestamp>/
```

## Local Modules

```text
modules/analyzer.py      多通道 track 分析流程
modules/obb_track.py     OBB track() 與 track id 抽取
modules/temporal_hbb.py  3-frame 9-channel 輸入堆疊與座標還原
modules/config.py        模型路徑與門檻
modules/id_assigner.py   ByteTrack id 到 Shrimp_ID 的映射
modules/preprocessing.py OBB crop/拉正
modules/reporting.py     輸出 CSV、圖表與結果影片
```
