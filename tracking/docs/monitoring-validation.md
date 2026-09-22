# 本機整合驗證（2026-09-20）

- 來源：ShrimpVisionRT `dd876980b83e42986b54c1ebeb52017c0728f113`。
- 目標：Shrimp-Male-Yolo-Tracking `5662c81ba1ad86b04cbc0bfe6206df1599dbc36a` 加本機修改。
- Python 3.12.12、scikit-learn 1.6.1、PyTorch 2.14.0 CPU、Ultralytics 8.4.156、OpenCV 4.14.0 WIN32UI。

## 自動檢查

執行 `.\.venv\Scripts\python.exe -m pytest tests -q`：**80 passed**。

涵蓋真實回歸模型公式／特徵順序／四捨五入、不同解析度與旋轉框、直式影片等比例換算、缺失或無效數據、與舊版 torchvision 水質前處理一致性、分類器實權重數值、四入口的監測接線、追蹤參數與 ID 保留、混濁停止／繼續、每個來源只查首幀、預掃描與攝影機首幀、CSV 與摘要、preview 不寫檔及異常清理。

四入口 `--help`、Python compileall、git diff --check、兩個 PowerShell 腳本語法檢查均通過。啟動腳本已實際執行。

## 使用真實模型及影片

| 驗證 | 結果 |
| --- | --- |
| 一般 OBB + HBB + ByteTrack，公母蝦仰拍-1，最終整合版 12 幀 | 72 筆觀測、6 個 ID；尺寸重量、水質、每 ID 摘要及 MP4 輸出成功；影片可重新解碼 |
| 頭尾 OBB + ResNet18 + ByteTrack，同影片 | 初次 8 幀；等比例換算修正後 4 幀再次通過 |
| 單幀 predict + 新 OBB/HBB，同影片 | 4 幀完成，產生原有分析報表與附加監測欄位 |
| 原混濁影片 + 預設 stop | 首幀 turbid 0.923580，停止推論，輸出 skipped_turbid；未產生假結果影片 |
| 原清水影片首幀分類 | clear 0.986840 |
| 新公母蝦仰拍-1 首幀分類 | turbid 0.999953；實際追蹤測試使用 report 繼續 |

最終一般追蹤範例輸出位於 `general_track/exports/run_track/公母蝦仰拍-1/20260920_091931/`；預覽圖在 `validation_outputs/final_preview.jpg`。其他測試輸出在 `validation_outputs/`，這些資料已排除 Git 追蹤。

模型複本 SHA256 已與使用者提供的原檔核對，詳見 `model/assets-manifest.json`；四個舊回歸模型的來源與係數在 `model/biometrics/provenance.json`。

## 驗證界線

這是程式整合與短片推論驗證，沒有使用新影片人工尺寸／重量／水質真值評估準確度。舊水質模型對新拍攝條件有適用性問題；OBB 框寬不是舊 segmentation 寬度，新相機尚未校準，所以尺寸重量是流程測試估測值。

多通道的 9 通道 temporal HBB 權重未提供；已透過測試確認其資料與監測流程，未宣稱完成該權重的真實推論。預設 YOLO 性別分類權重也未提供，頭尾流程使用使用者提供的 ResNet18 明確指定測試。舊專案原始碼保持不變；所有修改只存在本機，未推送 GitHub。

## 預設模型路徑修正與再驗證

同日核對使用者提供的模型包中 `yolo/` 子目錄後，已將 `predict` 的預設 OBB/HBB 與多通道的 OBB 直接指向專案內現有 `model/yolo/` 權重；頭尾分類預設改為同批提供的 `model/cnn/best_resnet18-run3.pt`。上節「明確指定 ResNet18」描述的是最初測試，現在不必指定即可使用。

- `general_track.run_head_tail_track` 不加任何模型覆寫參數，真實影片 1 幀執行成功。
- `predict.run_predict` 不加任何模型覆寫參數，真實影片 1 幀執行成功。
- 相關 general／predict／multi-channel 流程測試再次執行，34 passed。
- 逐一載入五個 YOLO checkpoint：四個 HBB 均為 `detect`、3 通道、`male_line` 類別；OBB 為 3 通道且包含 `shrimp`、`shrimp_head`、`shrimp_tail`。

不需要再補 `model/best.pt` 或複製 HBB 到 `model/` 根目錄。尚未提供的 YOLO 公母分類器僅作選配；9 通道模型則只影響多通道入口。

## 搬移與 GitHub 分享

本文件記錄的是上述本機驗證；本次使用的模型被 Git 忽略且未提交，其他人 clone 後須另外取得模型。完整自動測試需備齊原水質及四個回歸模型。原倉庫已有部分 `video/` 影片透過 Git LFS 追蹤，安裝 Git LFS 後可執行 `git lfs install`、`git lfs pull` 取得；也可自行提供影片。本次模型未提交，LFS pull 不會取得這批權重。

模型預設設定使用專案相對位置，執行時從程式的專案根目錄動態解析；來源 manifest 已移除個人絕對路徑，保留來源描述、雜湊及模型係數。自行指定的相對模型、影片與輸出路徑以工作目錄為準；執行 `python -m ...` 時請位於專案根目錄。環境建立與模型放置方式見 [README](../README.md)。

同日執行 `python -m pytest tests/test_project_paths.py -q`，**6 passed**。確認更換工作目錄後三組推論設定仍指向專案內模型、CLI 明確傳入的路徑保持原意，並將相關 Python 程式與真實水質／回歸權重複製到含中文及空白的新專案路徑，從另一個工作目錄成功載入與推論。搬移測試未複製大型 YOLO 權重，不代表在新作業系統完成 YOLO 推論。

原 OBB 訓練 YAML 的個人絕對路徑已移除；以 Ultralytics 的實際資料集解析函式確認搬移後依 YAML 所在目錄找到資料夾。沒有啟動訓練。本輪另有 43 項既有流程／水質測試通過，未重新執行全部測試；上方 80 passed 保留為先前完整測試紀錄。

## 最新完整測試與實際執行確認

完成路徑修改後，同日再次執行 `python -m pytest tests -q`：**86 passed in 55.02s**，exit code 0，沒有錯誤或警告。

以本機 `video/公母蝦仰拍-1.mp4`、目前預設模型及 `--monitoring --water-policy report --max-frames 8` 分別執行下列三個 Python 入口，沒有覆寫模型路徑。單幀分析另加 `--skip-frames 1`：

| 入口 | 實際執行結果 | 輸出檢查 |
| --- | --- | --- |
| `general_track.run_track` | 8 幀完成、exit code 0 | 48 筆長寬重量紀錄、水質紀錄、8 幀影片均正常 |
| `general_track.run_head_tail_track` | 8 幀完成、exit code 0 | 48 筆長寬重量紀錄、水質紀錄、8 幀影片均正常 |
| `predict.run_predict` | 8 幀完成、exit code 0 | 48 筆長寬重量紀錄、水質紀錄、8 幀影片均正常 |

輸出位於 `validation_outputs/smoke_20260920_portable/` 下的 `general/`、`head_tail/`、`predict/`。三份 `monitoring.json` 均為 `completed`；CSV 中尺寸重量均為有限正值；三支 MP4 均重新解碼至第 8 幀成功。這次使用存檔模式，未開啟預覽視窗。這些是短片執行與檔案驗證，不是準確度或全片長時間穩定性評估；缺少 9 通道權重的多通道模式仍未做真實模型推論。
