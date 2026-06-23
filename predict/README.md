# Predict

單幀 OBB `predict()` 分析入口，不使用 YOLO tracking。適合固定抽幀正式分析、產生 CSV/圖表/結果影片，以及使用 `--auto-total` 預估桶內總蝦數。

## Run

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
```

正式輸出會存到 `predict/exports/`：

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --known-total --total-shrimp 6 --skip-frames 10
```

自動估總數：

```powershell
python -m predict.run_predict --video "video\未知桶.mp4" --auto-total --skip-frames 10
```

## Local Modules

```text
modules/analyzer.py      predict 分析流程
modules/obb_predict.py   OBB predict() 專屬邏輯
modules/config.py        模型路徑與門檻
modules/id_assigner.py   中心點距離 ID 分配
modules/preprocessing.py OBB crop/拉正
modules/reporting.py     輸出 CSV、圖表與結果影片
```
