# Grass Shrimp Sex Ratio Analyzer

草蝦公母比例分析工具。輸入透明桶底部仰拍影片，系統會偵測蝦體、裁切拉正、辨識公蝦性徵 `male_line`，再用多幀統計輸出每隻蝦與整桶的公母判定結果。

## 功能入口

目前主要功能已拆成三個獨立資料夾。每個資料夾都有自己的可執行檔與 `modules/`，不再使用舊的 `Fast-Stats.py`。

```text
predict/
  單幀 OBB predict() 偵測
  不使用 YOLO track()
  適合固定抽幀分析、輸出正式統計、auto-total 預掃描

general_track/
  YOLO OBB track() + 單幀 HBB male_line
  適合攝影機/影片即時預覽、一般追蹤測試

multi_channel_track/
  YOLO OBB track() + 3-frame 9-channel temporal HBB male_line
  適合測試多通道 HBB 模型與時間序列判斷
```

快速預覽：

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
python -m multi_channel_track.run_multi_channel_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
```

## 專案結構

```text
model/
  best.pt                      OBB 蝦體模型
  best-hbb-yolo11l.pt           單幀 HBB male_line 模型
  best-hbb-3frame.pt            3-frame 9-channel HBB 模型

predict/
  run_predict.py                predict 入口
  exports/                      predict 匯出資料
  modules/
    analyzer.py                 predict 分析流程
    obb_predict.py              OBB predict() 專屬邏輯
    config.py                   模型路徑與門檻設定
    id_assigner.py              ID 分配
    preprocessing.py            OBB crop/拉正
    reporting.py                CSV、圖表與結果影片輸出

general_track/
  run_track.py                  一般 track 入口
  exports/                      一般 track 匯出資料
  modules/
    analyzer.py                 track 分析流程
    obb_track.py                OBB track() 與 track id 抽取
    ...

multi_channel_track/
  run_multi_channel_track.py    多通道 track 入口
  exports/                      多通道 track 匯出資料
  modules/
    analyzer.py                 多通道 track 分析流程
    obb_track.py                OBB track()
    temporal_hbb.py             3-frame 9-channel HBB 輸入堆疊
    ...

compare_runs.py                 彙整多次 outputs 結果
video/                          影片輸入
Train/                          訓練資料與訓練腳本
```

若根目錄仍有舊的 `modules/`，目前三個新入口已不依賴它。確認沒有要保留的本地改動後可以移除。

## 安裝

建議使用 Python 3.9 以上版本。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install ultralytics opencv-python numpy pandas matplotlib tqdm
```

如果不使用 CUDA，請依照你的環境安裝對應的 PyTorch CPU 版本。

## 模型與主要參數

每個功能資料夾都有自己的 `modules/config.py`。一般 HBB 與多通道 HBB 已分開：

```python
# predict/modules/config.py
MODEL_OBB_PATH = "model/best.pt"
MODEL_HBB_PATH = "model/best-hbb-yolo11l.pt"

# general_track/modules/config.py
MODEL_OBB_PATH = "model/best.pt"
MODEL_HBB_PATH = "model/best-hbb-yolo11l.pt"

# multi_channel_track/modules/config.py
MODEL_OBB_PATH = "model/best.pt"
MODEL_HBB_3FRAME_PATH = "model/best-hbb-3frame.pt"
HBB_TEMPORAL_FRAMES = 3
HBB_TEMPORAL_STEP_FRAMES = 10
```

共用門檻與常用參數：

```python
IMGSZ_OBB = 960
IMGSZ_HBB = 416
HBB_CONF = 0.30

MALE_RATE_THRESHOLD = 0.50
OBS_RATE_MIN = 0.25
VOTE_WINDOW_SECONDS = 10.0
MALE_LINE_MISSING_GRACE_SECONDS = 1.0
MIN_OBSERVATIONS_PER_SHRIMP = 3
ID_MATCH_DISTANCE = 260
DEFAULT_SKIP_FRAMES = 10
DEFAULT_TOTAL_SHRIMP = 6
DEFAULT_KEYFRAMES = 12
```

預覽投票不是看單一幀，而是使用同一個 `Shrimp_ID` 最近 10 秒的滑動視窗觀測：

```text
Male_Rate = Male_Hits / Total_Seen
```

顯示規則：

```text
0.00 ~ 0.24  Female  綠色框
0.25 ~ 0.49  Obs     灰色框
0.50 以上    Male    藍色框
```

預覽畫面的外框顏色使用 10 秒滑動投票結果，而不是只看當幀 `male_line`。黃色小框仍只代表當幀實際偵測到的 `male_line` 位置。

若某隻蝦上一幀或近期剛偵測到 `male_line`，但後續短暫漏偵，系統會等待 `MALE_LINE_MISSING_GRACE_SECONDS`。預設 1 秒內的漏偵不會新增 female 票，也不會拉低投票百分比；超過 1 秒仍沒有偵測到 `male_line`，才會繼續把後續觀測納入投票分母。

輸出統計的 `per_shrimp_summary.csv` 仍保留整段影片的多幀彙整，用於正式分析結果。

## 執行方式

### 1. Predict 正式抽幀分析

適合產生正式 CSV、圖表與關鍵幀。

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --known-total --total-shrimp 6 --skip-frames 10 --window-sec 10
```

未知總數時，可使用動態 ID：

```powershell
python -m predict.run_predict --video "video\未知桶.mp4" --unknown-total --skip-frames 10
```

也可先用 OBB-only 預掃描估計總蝦數：

```powershell
python -m predict.run_predict --video "video\未知桶.mp4" --auto-total --skip-frames 10 --auto-total-percentile 90
```

預覽但不輸出檔案：

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
```

### 2. General Track 一般追蹤

`general_track` 會逐幀處理，以維持 YOLO tracker 連續性；目前不開放 `--skip-frames`、`--max-frames`、`--keyframes`、`--window-sec`、`--truth-csv`、`--preview-scale`、`--preview-wait-ms`。

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --known-total --total-shrimp 6 --preview-only
```

指定 tracker 設定：

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --tracker bytetrack.yaml --preview-only
```

指定一般 track 使用的 HBB `male_line` 模型：

```powershell
python -m general_track.run_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --hbb-model "model\best-hbb-yolo11m.pt" --preview-only
```

攝影機測試：

```powershell
python -m general_track.run_track --video 0 --unknown-total --preview-only
```

### 3. Multi-Channel Track 多通道追蹤

`multi_channel_track` 使用 YOLO track id 建立時間序列 crop buffer，將 3 個時間點的 RGB crop 堆疊成 9-channel HBB 輸入。

```powershell
python -m multi_channel_track.run_multi_channel_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --preview-only
```

調整 temporal HBB 取樣間隔：

```powershell
python -m multi_channel_track.run_multi_channel_track --video "video\公母蝦仰拍-1.mp4" --unknown-total --hbb-temporal-step-frames 10 --preview-only
```

## 常用參數

```text
--video                    影片路徑或攝影機編號，例如 0
--output-root              輸出根目錄，預設為各模式資料夾內的 exports
--known-total              使用固定總蝦數
--unknown-total            不限制總蝦數，依偵測/追蹤動態建立 ID，預設啟用
--total-shrimp             固定總蝦數，搭配 --known-total 使用
--preview                  分析時顯示即時預覽並輸出檔案
--preview-only             只顯示預覽，不輸出 CSV/圖表/結果影片
--tracker                  track 入口可指定 Ultralytics tracker YAML
--hbb-model                general_track 可指定 HBB male_line 模型路徑
--gt-male / --gt-female    整桶公母數真值
```

只有 `predict` 支援：

```text
--skip-frames
--max-frames
--window-sec
--truth-csv
--preview-scale
--preview-wait-ms
--auto-total
--auto-total-percentile
--auto-total-skip-frames
--auto-total-max-frames
```

只有 `multi_channel_track` 支援：

```text
--hbb-temporal-step-frames
```

## ID 指派

`predict` 使用蝦體中心點距離配對，將偵測結果分配到 `Shrimp_ID`。

`general_track` 和 `multi_channel_track` 預設使用 `--tracker bytetrack.yaml`，先由 YOLO `track()` / ByteTrack 產生 tracker id，再映射到固定或動態 `Shrimp_ID`。

原本自訂的 ID 回朔與外觀重連已移除。track 模式不再用中心點距離把新的 tracker id 回接到舊 ID；若 ByteTrack 產生新的 track id，系統會依目前模式建立新的 `Shrimp_ID` 或在固定總數已滿時標記 `overflow`。

若使用 `--known-total --total-shrimp 6`，固定 ID 範圍為：

```text
ID1 ~ ID6
```

同一幀超出固定總數的偵測會標記為：

```text
ID_Status = overflow
Include_In_Stats = False
```

overflow 仍會保留在 `detections.csv`，但不納入每隻蝦統計。

## 輸出

每次正式分析會建立：

```text
<mode>/exports/<video_name>/analysis_<timestamp>/
  data/
    bucket_summary.csv
    per_shrimp_summary.csv
    detections.csv
    time_window_summary.csv
    reliability_summary.csv
    evaluation_summary.csv
    error_cases.csv
    truth_template.csv
    auto_total_counts.csv       使用 --auto-total 時產生
    auto_total_summary.csv      使用 --auto-total 時產生
    confusion_matrix.csv        使用 --truth-csv 時產生
  figures/
    sex_ratio_summary.png
    per_shrimp_male_rate.png
    per_shrimp_detection_counts.png
    per_id_male_probability_10s.png
    temporal_sex_ratio.png
    auto_total_counts.png       使用 --auto-total 時產生
    single_vs_multiframe_accuracy.png  使用 --truth-csv 時產生
    confusion_matrix.png        使用 --truth-csv 時產生
  videos/
    result_video.mp4
```

預設輸出根目錄：

```text
predict/exports/
general_track/exports/<obb_model>_and_<hbb_model>/
multi_channel_track/exports/<step_frames>FPS/
```

例如：

```text
multi_channel_track/exports/30FPS/公母蝦仰拍-1/analysis_<timestamp>/
multi_channel_track/exports/10FPS/公母蝦仰拍-1/analysis_<timestamp>/

general_track/exports/yolo11m-obb_and_yolo11m-hbb/公母蝦仰拍-1/analysis_<timestamp>/
general_track/exports/yolo11m-obb_and_yolo11s-hbb/公母蝦仰拍-1/analysis_<timestamp>/
```

### 主要 CSV

```text
bucket_summary.csv
  整桶結果：Pred_Male, Pred_Female, Unknown, Male_Ratio_Pct, 使用模式、模型路徑與主要門檻

per_shrimp_summary.csv
  每隻蝦統計：Total_Seen, Male_Hits, Male_Rate_Pct, Final_Label, Track_IDs, Enough_Evidence

detections.csv
  每幀每個偵測：Frame, Time_Sec, Shrimp_ID, Track_ID, Pred_Label, Male_Conf, Vote_Male_Rate_Pct, ID_Status, Box 座標

reliability_summary.csv
  不需要人工真值的可靠性摘要：ID coverage、overflow rate、forced ID rate、male_line detection rate

truth_template.csv
  人工標記模板。填入 True_Label 後可用 --truth-csv 重新分析產生準確率與混淆矩陣
```

### 新增匯出項目

```text
videos/result_video.mp4
  每個分析幀的標註結果影片。

figures/per_shrimp_detection_counts.png
  每個 Shrimp_ID 的被辨識總次數與 male_line 公蝦性徵總次數長條圖。

figures/per_id_male_probability_10s.png
  每 10 秒區間中，每個 Shrimp_ID 的公蝦機率折線圖。
```

## 人工真值與評估

第一次分析後，系統會輸出：

```text
<mode>/exports/<video_name>/analysis_<timestamp>/data/truth_template.csv
```

在 `True_Label` 填入 `Male` 或 `Female` 後重新執行：

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --known-total --total-shrimp 6 --truth-csv "outputs\<video>\analysis_<timestamp>\data\truth_template.csv"
```

提供 `--truth-csv` 後會額外輸出：

```text
single_vs_multiframe_accuracy.png
confusion_matrix.csv
confusion_matrix.png
error_cases.csv
```

若只知道整桶公母數，可以用：

```powershell
python -m predict.run_predict --video "video\公母蝦仰拍-1.mp4" --known-total --total-shrimp 6 --gt-male 3 --gt-female 3
```

## 多次結果彙整

彙整所有分析：

```powershell
python compare_runs.py --outputs outputs
```

只取每部影片最新一次：

```powershell
python compare_runs.py --outputs outputs --latest-only
```

額外輸出比較圖：

```powershell
python compare_runs.py --outputs outputs --latest-only --extra-plots
```

輸出位置：

```text
outputs/comparison/
  model_comparison_summary.csv
  per_video_performance.png
  combined_confusion_matrix.csv
  combined_confusion_matrix.png    使用 --extra-plots 時產生
  count_accuracy_by_model.png      使用 --extra-plots 時產生
```

## 注意事項

- `Shrimp_ID` 是系統分配的統計 ID，不保證等於真實生物個體 ID。
- 水中遮擋、重疊、快速移動會造成 ID switch 或 forced ID。
- `Forced_ID_Rate_Pct` 偏高代表該 ID 統計可靠性較低。
- 最終公母判定應看 `per_shrimp_summary.csv` 的多幀彙整與結果影片，不建議只看單一幀。
- `preview-only` 不會建立 outputs。
- `general_track` 與 `multi_channel_track` 會逐幀處理，速度通常比 `predict` 抽幀慢。
