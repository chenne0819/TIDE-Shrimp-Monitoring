# 水質辨識與長寬重量整合指南

本次把 [ShrimpVisionRT](https://github.com/chenne0819/ShrimpVisionRT) 的水質分類與尺寸、重量回歸整合到本專案。蝦體偵測、頭尾判斷、性別分類、追蹤與 ID 邏輯繼續使用本專案的流程與模型。監測功能預設關閉；啟用後將估測值附加到原有紀錄及畫面。

## 先執行已實測的入口

新電腦先依 [README 的環境建立與模型準備說明](../README.md) 建立 Python 3.12 `.venv`，取得被 Git 忽略的權重，並依 `model/` 結構放妥。以下 Python 指令在專案根目錄執行，需先啟用虛擬環境。`video/sample.mp4` 代表自己的影片，倉庫不附此檔案。

若使用原倉庫已有的 `video/` 影片，需安裝 Git LFS 並執行 `git lfs install`、`git lfs pull` 取得真正的影片內容；也可透過 `--video` 指定自己的影片。本次新增的模型未提交，無法單靠 LFS pull 取得。

可直接使用整合版啟動腳本：

```powershell
.\run-monitoring.ps1 -Video video/sample.mp4 -MaxFrames 30 -Preview
# 換影片並分析完整影片：
.\run-monitoring.ps1 -Video video/sample.mp4 -Preview
# 若要混濁時立即停止：
.\run-monitoring.ps1 -Video video/sample.mp4 -WaterPolicy stop
```

這是 Windows 的選用啟動方式，演算法仍在 Python 程式。腳本預設啟用水質、長寬與重量，水質策略採 `report`，並使用新版一般追蹤。Windows 也可透過 `.\setup-monitoring.ps1` 建立環境；它使用 Python 3.12，並處理 HBB checkpoint 所需的 albumentations 與桌面版 OpenCV 衝突，保留預覽視窗功能。搬移到新電腦時須重建 `.venv`，不要直接複製舊環境。

完整驗證記錄見 [本機驗證結果](monitoring-validation.md)。

一般 OBB 追蹤加 HBB 性徵辨識：

```powershell
python -m general_track.run_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 12
```

本機驗證以 `公母蝦仰拍-1.mp4` 及真實 OBB/HBB 權重完成同一流程的 12 幀推論，產生結果影片與 CSV。`--max-frames 12` 是短測試限制；移除此參數可處理完整影片。

頭尾追蹤加 ResNet 性別分類：

```powershell
python -m general_track.run_head_tail_track --video video/sample.mp4 --monitoring --water-policy report --max-frames 8
```

此入口也已使用真實 ResNet18 模型完成 8 幀推論。預設分類器已設為現有的 `model/cnn/best_resnet18-run3.pt`，不需另外指定 `--classifier-model`。只有選用 YOLO 公母分類時，才需提供尚未包含的 YOLO 分類 checkpoint，再以 `--classifier-model` 指定。

兩個範例使用 `--water-policy report`：本機驗證中，水質模型把新仰拍影片的第一幀判為 `turbid`，信心度約 `0.99995`。使用預設 `stop` 會在蝦體推論前停止；`report` 會記錄此結果並繼續處理，適合檢查新拍攝情境的相容性。

## 四個入口

| 入口 | 原有用途 | 此次整合狀態 |
| --- | --- | --- |
| `general_track.run_track` | OBB 追蹤、頭尾校正、單幀 HBB 性徵與滑動投票 | 支援水質、尺寸、重量；已做上述真實模型短測試 |
| `general_track.run_head_tail_track` | OBB 追蹤、頭尾校正、ResNet 或 YOLO 性別分類 | 支援水質、尺寸、重量；預設使用已實測的現有 ResNet18 |
| `predict.run_predict` | 單幀 OBB 偵測與 HBB 分析、原有 ID 分配 | 支援水質、尺寸、重量；預設 OBB 與 HBB-L 路徑已接上現有權重 |
| `multi_channel_track.run_multi_channel_track` | OBB 追蹤與三幀、9 通道 temporal HBB | 程式已接上監測；目前缺少相符的 temporal HBB 權重，尚未完成該模型的真實推論驗證 |

`predict` 使用本機現有新模型的指令，無需額外指定模型路徑：

```powershell
python -m predict.run_predict --video video/sample.mp4 --monitoring --water-policy report --max-frames 12
```

其預設模型為 `model/yolo/best-obb-yolo11m-head_tail.pt` 與 `model/yolo/best-hbb-yolo11l.pt`。若要選用先前短測試使用的 HBB-N，可另外加 `--hbb-model model/yolo/best-hbb-yolo11n.pt`；這是選用覆寫。

多通道入口的 OBB 也已預設使用現有 `model/yolo/best-obb-yolo11m-head_tail.pt`；仍需真正接受三幀、9 通道輸入的 HBB checkpoint。取得相符權重後，放在預設 `model/best-hbb-3frame.pt` 或以該入口的 `--hbb-model` 指定。現有單幀、3 通道 HBB 無法替代；其餘監測參數與下表相同。

## 共用監測參數

| 參數 | 用途與預設值 |
| --- | --- |
| `--monitoring` | 同時啟用水質分類及長寬重量估測 |
| `--water-quality` | 僅啟用水質分類 |
| `--biometrics` | 僅啟用長寬重量估測 |
| `--water-policy stop` | 預設策略；第一幀為混濁時停止該來源的蝦體推論 |
| `--water-policy report` | 記錄並顯示水質，混濁時仍繼續蝦體推論 |
| `--water-model PATH` | 指定水質權重；預設為專案的 `model/water/logistic_regression_model.pth` |
| `--biometrics-model-dir DIR` | 指定四個原回歸權重所在目錄；預設為專案的 `model/biometrics` |
| `--pixels-per-mm 2.5` | 校準參考影像上的每毫米像素數；預設保留舊專案的 `2.5` |
| `--measurement-reference-size 800 450` | 尺寸換算使用的參考影像寬、高；預設保留舊專案的 `800 × 450` |
| `--weight-mode length` | 預設使用校正後長度估重 |
| `--weight-mode length-width` | 明確改用長度與 OBB 寬度代理值共同估重，需先驗證此寬度定義適用於資料 |

所有入口的預設模型設定為專案相對位置，由 `project_paths.py` 根據自身檔案位置找到專案根目錄後動態解析，不綁定使用者名稱或磁碟。自行提供的相對模型路徑、影片路徑及輸出路徑以執行時工作目錄為準；也可自行提供絕對路徑。執行記錄可能顯示解析後的絕對路徑，搬移後會依新位置解析。`python -m ...` 指令請從專案根目錄執行。

水質在每個來源的第一幀檢查一次，輸出描述的是這一幀，並非整段影片的持續水質監控。清水與混濁為視覺分類，不提供 pH、溶氧或其他水質化學指標。

## 尺寸與重量的意義

尺寸計算直接讀取新模型產生的原圖 OBB 四角座標。座標以 `min(參考寬 / 原圖寬, 參考高 / 原圖高)` 作為水平與垂直方向相同的縮放倍率，保持長寬比適配預設 `800 × 450` 的參考畫布，不把不同方向各自拉伸。相鄰邊的較長、較短者作為長度與寬度像素值，除以 `2.5 px/mm` 後送入舊專案的長度及寬度回歸模型。這項換算不改動偵測器的輸入或追蹤座標。

`800 × 450` 和 `2.5 px/mm` 來自舊專案的拍攝與處理設定。本次新影片是 `990 × 1398` 直式影像，與舊設定的長寬比不同，因此必須使用上述等比例換算；目前數值僅用於確認處理流程，尚未為新相機重新標定。拍攝距離、視野、鏡頭、折射與蝦體深度不同時，需要用實際量測資料驗證或重新校準。取得實測標定後，以 `--measurement-reference-size` 與 `--pixels-per-mm` 指定對應設定，並驗證原回歸模型是否仍適用；只把新影片縮放到相同解析度，不能保證毫米值正確。

寬度是**新 OBB 短邊的代理估測值**。舊專案曾利用另一個 segmentation 模型測量蝦體寬度，這次依需求維持新專案的模型組合，因此兩種寬度定義並不相同。畫面以 `W~` 表示此估測；紀錄保留 `width_source=obb_proxy` 與 `measurement_status`。

預設重量使用舊專案的長度單變量回歸，避免直接把尚未驗證的 OBB 寬度帶入雙變量模型。需要評估雙變量模式時，使用 `--weight-mode length-width`。不合理或非正的回歸結果會留空並記錄狀態，不會以零重量當成有效量測；長度仍有效但寬度無法取得時，預設模式可保留長度及可用的長度估重。

尺寸附加於各入口原本保留的蝦體紀錄。尤其兩個 `general_track` 入口仍依原流程過濾頭尾方向不明等無效紀錄，並未藉此新增或更改性別投票樣本。

## 權重來源

本機整合的新偵測與分類權重由使用者提供的模型包（user-provided model bundle）複製至 `model/yolo` 與 `model/cnn`。其中 `yolo` 子目錄包含 5 個檔案：1 個頭尾 OBB，以及 `n`、`s`、`m`、`l` 四個單幀 HBB；均已複製。各入口使用：

- `model/yolo/best-obb-yolo11m-head_tail.pt`
- 一般追蹤預設 `model/yolo/best-hbb-yolo11n.pt`
- 單幀分析預設 `model/yolo/best-hbb-yolo11l.pt`
- 頭尾分類預設 `model/cnn/best_resnet18-run3.pt`

原先 `predict`／多通道設定中的 `model/best.pt` 與 `predict` 的 `model/best-hbb-yolo11l.pt` 已修正為現有位置，不需要補檔或改名。僅選用 YOLO 公母分類時缺分類 checkpoint，選用多通道追蹤時缺 9 通道 HBB；詳細路徑表見 [README 第 4 節](../README.md#4-已設定的預設路徑與選用功能缺檔)。

ShrimpVisionRT 的 GitHub 版本雖在 README 列出水質與回歸權重，實際未提交這些檔案。本次已從使用者原有的本機 `shrimp_OBB/Model` 找回原權重，沒有使用隨機權重或另行訓練的替代模型：

```text
model/water/
  logistic_regression_model.pth

model/biometrics/
  final_linear_model_length.pkl
  final_linear_model_width.pkl
  polynomial_regression_model_degree3.pkl
  multi_feature_model.pkl
  provenance.json
```

[回歸模型來源紀錄](../model/biometrics/provenance.json) 包含原倉庫 revision、來源描述、四個檔案的 SHA-256、模型類型、係數與校準依據；原模型儲存時的 scikit-learn 版本為 `1.6.1`。遺失檔案或模型格式不相容時，程式會明確報錯。

本次使用的 `.pt`、`.pth` 與 `model/` 下的 `.pkl` 被 Git 忽略且未提交。新的 clone 需要另外取得這批檔案；目前沒有已發布的模型下載連結。未來可由維護者透過 GitHub Release，或調整忽略規則後使用 Git LFS 分享模型，接收者仍按上述相對目錄放置。模型來源 JSON 保留檔名、雜湊及來源描述，不包含原電腦的個人路徑。

## 輸出內容

各入口仍使用原有輸出目錄；可透過 `--output-root` 更改。啟用尺寸估測後，原偵測 CSV 附加 `length_px`、`width_px`、`length_mm`、`width_mm`、`weight_g`、`measurement_status` 等欄位。每隻蝦的彙整增加 `measurement_samples`、`mean_length_mm`、`mean_width_mm`、`mean_weight_g`；樣本數是有效長度觀測次數，不是蝦隻數，平均值使用各欄位有效的觀測。

啟用水質或尺寸監測時另有：

- `monitoring.json`：執行狀態、模型位置、量測參考解析度、像素比例、重量模式及寬度來源。
- `water_quality.csv`：僅在啟用水質時產生，記錄第一幀的 `water_label`、`water_confidence`、策略及 `action`。

混濁且採用 `stop` 時，狀態為 `skipped_turbid`，不會產生偽造的尺寸或性別統計；尚未開始輸出的結果影片也不會回報為已生成。原始影片保留在原位置。`--preview-only` 不寫入影片、CSV 或監測檔案。

## 已確認的範圍與測試

原水質權重在舊專案兩支範例的第一幀得到：

| 影片 | 分類 | 該分類信心度（約） |
| --- | --- | --- |
| `2024-01-01-00_11_15.mp4` | `clear` | `0.98684` |
| `2024-01-08-06_53_42.mp4` | `turbid` | `0.92358` |
| 本機 `公母蝦仰拍-1.mp4` | `turbid` | `0.99995` |

這些是單幀模型輸出與流程驗證，信心度不是新拍攝情境的辨識準確率。上述 12 幀及 8 幀測試確認真實模型、估測、追蹤、輸出可銜接，也不代表已驗證毫米或克數的準確度。

完整自動測試包含真實模型驗證。先取得原水質權重與四個回歸權重，按上面的 `model/` 結構放妥，再在專案環境執行：

```powershell
python -m pytest tests -q
```

測試涵蓋水質前處理與分類、尺寸回歸、原追蹤參數與 ID 保留、濁水停止／僅回報策略、結果欄位、預覽不存檔與資源釋放。多通道 temporal HBB 的真實模型驗證仍待相符權重提供後執行。
