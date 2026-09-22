# Shrimp-Male-Yolo-Tracking：水質、長寬與重量整合版

本專案以 **Shrimp-Male-Yolo-Tracking 的 YOLO 偵測、頭尾判斷、公母辨識與追蹤流程**為主，接入 ShrimpVisionRT 的水質分類、尺寸換算及重量回歸。功能已直接整合在 Python 程式中，可由原有 `.py` 入口執行。

本 README 記錄 **2026-09-20 整合狀態**。本機的一般追蹤、頭尾追蹤與單幀分析所需模型已放好；重新 clone 者須另外取得模型並放入下列 `model/` 結構。只有選用 YOLO 公母分類或多通道追蹤時，才需要對應的選配權重。

## 1. 目前新增了哪些功能

| 功能 | 目前行為 | 啟用方式 |
| --- | --- | --- |
| 水質辨識 | 每個來源的第一幀分類為 `clear`／`turbid`，附信心度 | `--water-quality` |
| 混濁處理 | `stop` 在蝦體推論前停止；`report` 記錄結果後繼續 | `--water-policy stop` 或 `report` |
| 長度換算 | 新模型 OBB 長邊像素 → 參考尺度 → 原長度回歸模型 → mm | `--biometrics` |
| 寬度換算 | 新模型 OBB 短邊像素 → 原寬度回歸模型 → mm；標記為框寬估測 | `--biometrics` |
| 重量預測 | 預設依校正後長度估重；也可選長度＋寬度模型，輸出 g | `--weight-mode length` 或 `length-width` |
| 畫面標註 | 原追蹤畫面附加長度、`W~` 框寬、重量及首幀水質 | 啟用對應功能後自動顯示 |
| CSV 與個體摘要 | 原紀錄增加尺寸重量，每 ID 彙整有效觀測平均 | 正常輸出模式自動寫入 |
| 監測紀錄 | 新增 `water_quality.csv`、`monitoring.json`，保存分類與換算設定 | 正常輸出模式自動寫入 |

**`--monitoring` 同時啟用水質與長寬重量。** 不加 `--monitoring`、`--water-quality` 或 `--biometrics` 時，新增功能預設關閉。只指定模型路徑不會自動啟用功能。

水質目前是清澈／混濁的影像分類，不是 pH、溶氧量測，也不是整段影片持續重新分類。原有追蹤 ID、分類模型及公母投票仍由新版程式負責。

## 2. 實際整合在哪些 Python 檔案

| 檔案 | 用途 |
| --- | --- |
| [shrimp_monitoring/water.py](shrimp_monitoring/water.py) | 舊水質模型的前處理、載入與分類 |
| [shrimp_monitoring/biometrics.py](shrimp_monitoring/biometrics.py) | OBB 尺寸、像素尺度、長寬回歸、重量預測及平均值 |
| [shrimp_monitoring/runtime.py](shrimp_monitoring/runtime.py) | 將水質、量測、標註及輸出接到各入口 |
| [shrimp_monitoring/cli.py](shrimp_monitoring/cli.py) | 共用參數、模型位置及換算設定 |
| [project_paths.py](project_paths.py) | 依專案所在位置解析預設模型路徑，支援搬移資料夾 |
| [general_track/run_track.py](general_track/run_track.py) ＋ [track_pipeline.py](general_track/modules/track_pipeline.py) | 主要入口：新版 OBB／HBB／ByteTrack ＋ 新增功能 |
| [general_track/run_head_tail_track.py](general_track/run_head_tail_track.py) ＋ [head_tail_pipeline.py](general_track/modules/head_tail_pipeline.py) | 頭尾 OBB／ResNet 或 YOLO 分類 ＋ 新增功能 |
| [predict/run_predict.py](predict/run_predict.py) ＋ [analyzer.py](predict/modules/analyzer.py) | 單幀分析 ＋ 新增功能 |
| [multi_channel_track/run_multi_channel_track.py](multi_channel_track/run_multi_channel_track.py) ＋ [analyzer.py](multi_channel_track/modules/analyzer.py) | 多通道追蹤 ＋ 新增功能，仍需相符的 9 通道權重 |

`run-monitoring.ps1` 只是代填 Python 指令的選用啟動工具，沒有承載辨識演算法；下面全部使用 Python 直接執行。

## 3. 目前已放好的模型

以下為**本機整合時已備妥的檔案與目標位置**。本次使用的 `.pt`、`.pth` 及 `model/` 內的 `.pkl` 均被 Git 忽略且未提交，單靠 clone 不會取得這批權重。請另外向專案維護者取得模型，保持下列檔名及目錄結構。日後可用 GitHub Release 分享模型，或調整 Git 忽略規則後透過 Git LFS 提交；目前沒有已發布的模型下載連結。

```text
model/
  yolo/
    best-obb-yolo11m-head_tail.pt       # 新版蝦體、頭、尾 OBB
    best-hbb-yolo11n.pt                 # 主要入口預設 male_line HBB
    best-hbb-yolo11s.pt
    best-hbb-yolo11m.pt
    best-hbb-yolo11l.pt
  cnn/
    best_resnet18-run3.pt               # 已實測的公母分類器
    best_resnet34-run3.pt
    best_resnet50-run3.pt
  water/
    logistic_regression_model.pth      # 舊水質權重
  biometrics/
    final_linear_model_length.pkl      # 尺度換算後的長度 → 校正長度
    final_linear_model_width.pkl       # 尺度換算後的寬度 → 校正寬度
    polynomial_regression_model_degree3.pkl  # 長度 → 重量
    multi_feature_model.pkl            # [長度, 寬度] → 重量
    provenance.json                    # 原模型來源、係數及雜湊
  assets-manifest.json                  # 新權重來源與雜湊核對紀錄
```

新版偵測／分類權重來自使用者提供的模型包（user-provided model bundle），包含上列 **5 個 YOLO 權重**及 3 個 ResNet 權重，已複製至本專案 `model/yolo/` 與 `model/cnn/`。水質及四個回歸模型從原始本機 ShrimpVisionRT 的 `shrimp_OBB/Model` 找回；目前沒有使用隨機或人工拼湊的測試權重。

權重放在本專案後，執行時不依賴來源資料夾。搬移時請保留 `model/`，並在新電腦重建 `.venv`；虛擬環境不應直接複製使用。模型齊全不代表已適用於新相機，校準狀態見第 7 節。

## 4. 已設定的預設路徑與選用功能缺檔

表內預設模型路徑均以本專案根目錄為基準。**模型按第 3 節放妥後，前三個入口不需要額外指定模型參數。** 原始設定為專案相對位置，執行時依 `project_paths.py` 所在的專案根目錄動態解析，不綁定使用者名稱或磁碟位置。

### 已設定的預設路徑

| 入口 | OBB 蝦體／頭尾模型 | HBB 或公母分類模型 |
| --- | --- | --- |
| `general_track.run_track` | `model/yolo/best-obb-yolo11m-head_tail.pt` | `model/yolo/best-hbb-yolo11n.pt` |
| `general_track.run_head_tail_track` | `model/yolo/best-obb-yolo11m-head_tail.pt` | `model/cnn/best_resnet18-run3.pt`，預設使用現有 ResNet18 |
| `predict.run_predict` | `model/yolo/best-obb-yolo11m-head_tail.pt` | `model/yolo/best-hbb-yolo11l.pt` |
| `multi_channel_track.run_multi_channel_track` | `model/yolo/best-obb-yolo11m-head_tail.pt`，已存在 | `model/best-hbb-3frame.pt`，尚缺，見下表 |

先前程式中的 `model/best.pt` 與 `model/best-hbb-yolo11l.pt` 是過期的預設路徑，已修正為上表的現有位置。**不需要補這兩個檔案，也不需要重新命名現有權重。**

### 僅選用功能需要補檔

| 選用功能 | 尚未提供的權重 | 如何處理 |
| --- | --- | --- |
| YOLO 公母分類 | `model/yolo/best-cls-yolo11m-run3.pt` | 頭尾追蹤已預設使用 ResNet18；只有改用 YOLO 分類時，才需提供分類 checkpoint 並用 `--classifier-model` 指定 |
| 多通道追蹤 | `model/best-hbb-3frame.pt` | 需提供相符的三幀、9 通道 HBB checkpoint，放在此處或用 `--hbb-model` 指定；目前提供的 4 個單幀 HBB 無法替代 |

要選用其他現有模型，可透過 CLI 覆寫，例如 `--hbb-model model/yolo/best-hbb-yolo11n.pt` 或 `--classifier-model model/cnn/best_resnet34-run3.pt`。這些覆寫是選用操作。永久改預設模型位置，可修改 [general_track/modules/config.py](general_track/modules/config.py)、[predict/modules/config.py](predict/modules/config.py) 或 [multi_channel_track/modules/config.py](multi_channel_track/modules/config.py)；頭尾追蹤的預設分類器由 `MODEL_SEX_CLASSIFIER_PATH` 設定。

其他路徑設定：

| 項目 | 如何指定 |
| --- | --- |
| 自己的影片／攝影機 | `--video video/sample.mp4` 或 `--video 0` |
| 結果輸出位置 | `--output-root results`，不存在時程式會建立 |
| 之後的新水質權重 | `--water-model model/water/logistic_regression_model.pth`，並加 `--water-quality` 或 `--monitoring` |
| 之後的新長寬重量權重 | `--biometrics-model-dir model/biometrics`，並加 `--biometrics` 或 `--monitoring` |

回歸模型目錄目前須包含上列**四個固定檔名**，即使選長度估重也會載入四個檔案。新模型須相容於目前輸入介面：長度／寬度／單長度估重各接受 1 個特徵，雙特徵估重接受 `[length_mm, width_mm]`。水質 checkpoint 須為原 `Linear(784, 2)` 的 state_dict；換其他模型架構時也需修改載入程式。

所有入口的預設模型位置均從程式所在的專案根目錄解析；自行傳入的相對模型路徑、影片路徑及輸出路徑，則以執行時工作目錄為準，也允許自行指定絕對路徑。執行記錄或錯誤訊息可能顯示解析後的絕對路徑，這不代表原始碼綁定某台電腦。下方指令統一從專案根目錄執行。

## 5. 直接執行 Python

取得包含本次整合修改的倉庫版本後，先進入專案目錄；以下命令皆從這裡執行：

```powershell
git clone https://github.com/NxBLANKxN/Shrimp-Male-Yolo-Tracking.git
cd Shrimp-Male-Yolo-Tracking
```

上述為原倉庫 URL；本次整合目前仍是本機修改，尚未推送 GitHub。發布到自己的 fork 後，請將 clone URL 換成該倉庫，並確認所選分支包含整合版程式。

第一次使用先依第 8 節建立並啟用 Python 3.12 環境，再依第 3 節補齊權重，將自己的影片放為 `video/sample.mp4`（或修改 `--video`）。範例影片名稱是佔位路徑，倉庫不附這個檔案。啟用環境後，下列 `python -m ...` 指令可用於 Windows、macOS 或 Linux；預覽需桌面顯示環境。

原倉庫已有部分 `video/` 影片由 Git LFS 追蹤。若要使用，需先安裝 Git LFS，再於專案根目錄執行；若未能取得影片，也可直接指定自己的影片：

```text
git lfs install
git lfs pull
```

`.gitignore` 不會取消既有影片的 LFS 追蹤。此步驟取得的是已上傳的 LFS 檔案，不會補齊本次未提交的模型。

### 一般追蹤：目前主要可用入口

```powershell
python -m general_track.run_track --video video/sample.mp4 --monitoring --water-policy report --preview
```

這是在執行 `general_track/run_track.py`。`-m` 讓 Python 正確處理專案內的模組引用，請從根目錄執行。加 `--max-frames 30` 可只測前 30 幀；`--preview` 會顯示且存檔，改成 `--preview-only` 則不寫任何輸出。

範例使用 `report`，因為本機驗證中，舊水質模型將新仰拍影片的首幀判為混濁。若要混濁就停止，改為 `--water-policy stop`；這也是直接使用 Python CLI 時的預設值。

### 頭尾追蹤：預設使用已存在的 ResNet18

```powershell
python -m general_track.run_head_tail_track --video video/sample.mp4 --monitoring --water-policy report --preview
```

### 單幀 predict：預設使用現有 OBB 與 HBB-L

```powershell
python -m predict.run_predict --video video/sample.mp4 --monitoring --water-policy report --skip-frames 10
```

### 多通道追蹤：補齊 9 通道模型後執行

下例假設已補好 `model/best-hbb-3frame.pt`，目前不能原樣直接跑：

```powershell
python -m multi_channel_track.run_multi_channel_track --video video/sample.mp4 --monitoring --water-policy report --preview
```

多通道入口目前沒有 `--max-frames` 參數，請勿將其他入口的短測試參數直接套用。

### 在 PyCharm 執行

Python Interpreter 選本專案的 `.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`（macOS／Linux）；Run Configuration 選 **Module name**，填 `general_track.run_track`；Working directory 設為本專案根目錄。Parameters 可填：

```text
--video video/sample.mp4 --monitoring --water-policy report --preview
```

各入口完整參數可用 `--help` 查閱。原 `run-all.py` 是尚未更新的舊批次腳本，包含過期的 `--unknown-total`、舊模型位置，也沒有啟用 `--monitoring`，目前請使用上列 Python 指令。

原 `Train/` 目錄保留訓練流程；本次主要整合的是四個推論入口，沒有全面重構訓練腳本。訓練時仍需依對應子目錄準備資料集並設定 `data`、`model`、`dataset` 等參數，從該子目錄執行。部分腳本預設使用 CUDA 裝置 `0`，僅有 CPU 時需在支援的入口指定 `--device cpu`。OBB 的 `data.yaml` 已移除原機器資料夾設定，資料集子路徑以 YAML 所在目錄為基準。

## 6. 輸出在哪裡、增加哪些欄位

| 入口 | 預設輸出根目錄 |
| --- | --- |
| `general_track.run_track` | `general_track/exports/run_track/` |
| `general_track.run_head_tail_track` | `general_track/exports/head_tail_cls/` |
| `predict.run_predict` | `predict/exports/` |
| `multi_channel_track.run_multi_channel_track` | `multi_channel_track/exports/<step_frames>FPS/` |

每次執行再依影片名稱與時間建立資料夾。一般追蹤會產生 `result.mp4`、`detections.csv`、`per_shrimp.csv`、滑動投票報表，以及啟用監測後的 `monitoring.json`／`water_quality.csv`。`predict` 與多通道保留 `data/`、`figures/`、`videos/` 結構，新增的兩個監測檔位於該次執行資料夾根目錄。

| 新增欄位 | 意義 |
| --- | --- |
| `length_px`, `width_px` | 換算到參考畫布後的 OBB 邊長，非原圖像素 |
| `length_mm`, `width_mm`, `weight_g` | 回歸估測的長度、框寬與重量 |
| `width_source` | 目前為 `obb_proxy`，表明寬度來自框的短邊 |
| `weight_method`, `measurement_status` | 估重方式與量測是否可用；不合理數值會留空 |
| `water_label`, `water_confidence` | 啟用水質時附加的首幀分類結果 |
| `measurement_samples`, `mean_length_mm`, `mean_width_mm`, `mean_weight_g` | 每 ID 的有效長度觀測次數，以及各欄位有效值的平均 |

混濁且策略為 `stop` 時，狀態為 `skipped_turbid`；不會移走原始影片。`--preview-only` 不寫影片、CSV 或監測設定。

## 7. 還需要補哪些資料、目前哪些值只供測試

| 待處理項目 | 原因與後續方式 |
| --- | --- |
| 新相機的尺寸標定 | 預設沿用舊版參考畫布 `800×450` 與 `2.5 px/mm`。新影片為直式 `990×1398`，目前只做等比例適配；需用實際尺度驗證，以 `--measurement-reference-size 寬 高`、`--pixels-per-mm 數值` 調整，必要時重訓回歸 |
| 寬度定義驗證 | 舊版寬度來自 segmentation，新版使用 OBB 短邊，兩者不等同；畫面以 `W~` 標示。因此重量預設採原長度單變量模型 |
| 重量模型驗證／替換 | 目前已有舊權重可跑，但需新資料的實測長寬與重量確認適用性；使用 `--weight-mode length-width` 前，尤其要驗證框寬是否適合雙特徵模型 |
| 新場景水質驗證／替換 | 舊模型對新仰拍影片輸出 `turbid`，高信心度不代表分類正確；目前測試建議用 `report`，待標註資料評估後再決定是否採 `stop` |
| 多通道真實推論 | 等相符 9 通道 HBB 權重提供後再測；不能用目前單幀權重替代 |

現在的 mm／g 用於確認整合流程，**尚未宣稱是新拍攝環境下經驗證的實際長寬與重量**。所有 `.py` 接線已完成；權重與標定數據可按上表替換。

## 8. 環境與驗證

本機驗證使用 Python 3.12 與 CPU 版 PyTorch。新的 clone 或搬到新電腦時，請重新建立環境並安裝 [requirements-dev.txt](requirements-dev.txt)。以下從專案根目錄執行。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m ensurepip --upgrade
python -m pip install -r requirements-dev.txt
# albumentations 會安裝 headless OpenCV，需改回桌面版以支援預覽：
python -m pip uninstall -y opencv-python-headless
python -m pip install --force-reinstall --no-deps "opencv-python>=4.10,<5"
```

若 PowerShell 禁止執行啟用腳本，可省略啟用，把命令中的 `python` 換成 `.\.venv\Scripts\python.exe`。

macOS／Linux shell（先安裝 Python 3.12）：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -r requirements-dev.txt
python -m pip uninstall -y opencv-python-headless
python -m pip install --force-reinstall --no-deps 'opencv-python>=4.10,<5'
```

`scikit-learn` 固定為原回歸模型的 `1.6.1`。Windows 另有 `setup-monitoring.ps1` 可選用來安裝環境。本次已完成 Windows 實測；macOS／Linux 指令是環境建立方式，尚未在這兩個系統實測推論。

本次整合驗證：**80 項自動測試通過**；一般追蹤、頭尾／ResNet、單幀分析已使用真實權重與影片短測，並驗證水質混濁停止。這些是程式與流程測試，不是新場景的準確度評估。

完整測試包含真實水質及回歸權重的驗證，因此重新 clone 後須先備齊第 3 節的原水質及四個回歸模型，再執行以下命令；只有程式碼的 clone 尚不能完整重現全部測試。

```powershell
python -m pytest tests -q
```

詳見[完整整合指南](docs/monitoring-integration.md)、[本機驗證記錄](docs/monitoring-validation.md)、[模型清單與來源](model/assets-manifest.json)。[原倉庫 README](docs/README-original.md)另行保留作歷史參考，舊指令與目前程式不一致時，以本頁及各入口 `--help` 為準。
