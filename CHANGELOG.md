# CHANGELOG

版本號在 `VERSION`。專案導入時把版本號和 commit 一起記進 `DIRECTOR_OPERATING_RULES.md`（`BOOTSTRAP` 第 1 步），升級時讀這份，照「遷移」做。

- **MAJOR**：已經通過的舊檔案或舊設定會變成不通過，例如工具檢查的格式改了、`director_work.json` 的 `schema_version` 升級。一定附遷移步驟。
- **MINOR**：新增規則、文件、工具或選項，舊檔案照樣通過。
- **PATCH**：修正文字、修 bug，規則不變。

## 0.11.0 — 2026-11-04

驗收證據可以機器核對，成效數字可以從檔案數出來。MINOR：`gate_check.py` 不帶 `--evidence-dir` 時行為不變；新的紀錄慣例只寫在需要時才讀的文件。

- `gate_check.py --match 報告 工單 --evidence-dir 資料夾`：AUTO 條件填 PASS 時，證據欄要寫 `evidence_record.py` 的 `.json` 檔名；紀錄的指令要 exit 0、沒逾時、產物沒有缺，紀錄的 git HEAD 要和報告寫的 HEAD 相同。紀錄時有未提交的改動、label 不是這條 AC，只印提示。報告沒寫 commit 雜湊時印提示、不比 HEAD。紀錄只證明指令跑過而且通過，不證明它測對了東西。
- 新增 `tools/metrics_report.py`：從 `DIRECTOR` 的裁決、工單、`DIRECTOR_LOG`、`PO_PENDING` 數出 `PURPOSE.md` 的成效數字（返工、中斷後重做、PO 介入、導入卡住）和規格審查的花費；來源檔不存在印 `UNKNOWN`。額度仍用 `usage_report.py`。
- 兩個紀錄慣例，給 `metrics_report.py` 數：`docs/06b` 恢復程序第 7 步的 `RESUMED` 行加 `redo=`，總監記進 `DIRECTOR_LOG`；`BOOTSTRAP` 卡住時在 `DIRECTOR_LOG` 記 `BOOTSTRAP_STUCK 第 n 步 原因`。
- `docs/02`、`templates/TASK_REPORT.md`、`tools/README.md` 寫明：AUTO 條件在最後一次 commit 之後記錄，證據欄寫 `.json` 檔名。
- `selftest.py` 加上面各項的正反案例（共 202 項）。

對齊初衷：
1. 幫到誰：v0.10 的 `--match` 只查證據欄有沒有寫字，worker 寫了不存在或失敗的紀錄也會通過；`PURPOSE.md` 列了五個成效指標，但沒有工具能數，改規則前後無從比較。
2. Desktop：工具只用標準函式庫、本機執行，selftest 在 Python 3.11 和 3.9 通過，也用真的 `evidence_record.py` 紀錄在暫存 git repo 跑過一次。在 Desktop 上拿真實 Strict 工單試用、量基準數字 NOT_VERIFIED。
3. 服務：成品要真的對（5，PASS 要有通過的紀錄）、PO 不用盯細節（3，總監用工具核對）、用數字決定規則留不留（PURPOSE.md 怎麼判斷有沒有效）。
4. 核心：每輪必讀不變（13,417 / 13,428 bytes）；`--evidence-dir` 是選用的，Direct 不受影響；PO 不多操作。新增的兩行紀錄由總監和 worker 寫。
5. 舊檔案：不帶新參數時照樣通過。用 `--evidence-dir` 時，舊報告的證據欄若不是 `.json` 檔名會不通過，所以只對新報告用。

遷移：把 `tools/` 整個重新複製到 `DIRECTOR/tools/`（含 `metrics_report.py`）。要核對證據時，總監審查改跑 `gate_check.py --match 報告 工單 --evidence-dir 證據資料夾`，並在派工時告訴 worker 證據欄要寫 `.json` 檔名、最後一次 commit 之後再記錄。

## 0.10.0 — 2026-11-04

驗收條件分類型、規格和結果分開放，加上 PO 定的初衷。MINOR：新檢查對舊檔案只印提示（`  ~ ` 開頭），不會讓舊檔案不通過；`gate_check.py` 不帶新參數時行為不變。

- 新增 `PURPOSE.md`：初衷、目的、不能破壞的九項核心、改規則前的五題檢查。只有 PO 能改；其他規則和它衝突時照它。`docs/01`（每輪必讀）加一行指向它，README、`BOOTSTRAP` 1.2 加進閱讀順序。
- 工單驗收條件加「類型」欄 `AUTO / REVIEW / PO`；實際、證據、狀態改寫在 TASK REPORT 的 ACCEPTANCE 表。worker 對 REVIEW 最多填 `READY_FOR_REVIEW`，對 PO 只填 `PENDING_PO`（`vocabulary.json` 的 `ac_worker_statuses`）。
- 工單加 `REVISION`、`TRACES_TO` 和 H 節變更紀錄；報告加 `ORDER`、`ORDER_SHA256`。
- `gate_check.py` 加 `--match 報告 工單`（逐條對照、狀態符合類型、PASS 附證據、工單雜湊相符）和 `--hash`。雜湊只能查出工單被改過，擋不住修改。
- 新增 `tools/trace_report.py`：從工單、報告、裁決產生追溯表；`director_work.json` 可選加 `trace_id_pattern` 檢查編號格式（不改 `schema_version`）。
- 新增 `templates/SPEC_REVIEW.md`：Strict 工單派工前用只讀 subagent 審規格；Standard 選用；記下花費和抓到的問題。
- `docs/07` 常識閘門：有成品的工單寫成 `REVIEW` 條件，開工前寫明誰看、從哪個角度、看多大範圍。
- `selftest.py` 加上面各項的正反案例，並檢查 `PURPOSE.md` 結構和每一版 CHANGELOG 有「對齊初衷」。

對齊初衷：
1. 幫到誰：使用中的專案出過「數字全對、成品動作方向相反」和「worker 自己判過要用眼睛看的條件」；規格和結果混在工單裡，規格被改也查不出來。
2. Desktop：工具只用標準函式庫、本機執行，selftest 通過；在 Desktop 上拿真實工單試用 NOT_VERIFIED。
3. 服務：成品要真的對（5）、PO 保留最終權力（6）、PO 不用盯細節（3）、中斷不丟進度（4，追溯表從檔案重建）。
4. 核心：每輪必讀維持在上限內（13,417 / 13,428 bytes）；Direct 不多步驟；規格審查只在 Strict 必做，花費要記錄，划不來就降回選用；PO 不多操作。
5. 舊檔案：照樣通過，只多提示。

遷移：把 `tools/` 整個重新複製到 `DIRECTOR/tools/`（含 `vocabulary.json`、`trace_report.py`）。新工單和報告改用新的 `templates/WORK_ORDER.md`、`TASK_REPORT.md`；舊工單不用改。要檢查編號格式時，在 `director_work.json` 加 `trace_id_pattern`。

## 0.9.0 — 2026-11-04

第一個版本號，涵蓋到這一版為止的全部內容。還不算定案：`v1.0.0` 要等完整開發循環實測過。

- 新增 `docs/11_claude_desktop.md`：在 Claude Desktop 上開 worker、傳訊息、讀額度和上下文視窗用哪個工具。不列入每輪必讀。
- `BOOTSTRAP` 第 7.5 步：Desktop 上用 `get_usage` 確認上下文視窗。
- `gate_check.py` 加 `--warn`（只警告、exit 0）和 `--since YYYY-MM-DD`（跳過較早的檔案）。不帶這兩個參數時行為不變。
- 固定用詞集中到 `tools/vocabulary.json`；`selftest.py` 檢查 `docs/02` 和範本的寫法跟它一致。
- `selftest.py` 檢查 README 標「每輪必讀」的文件合計不超過 13,428 bytes。
- `director_work.json` 加 `schema_version`（目前 1）。沒有這個欄位的設定檔視為 1；版本不認得時 `setup_project_settings.py` 會拒絕執行。
- 工單規則：worker 不改驗收條件和規格，有問題回報 `BLOCKED`，由總監裁決。
- GitHub Actions 在 Windows 上用 Python 3.9 和 3.12 跑 `selftest.py`。

對齊初衷（補記）：幫已在用的專案導入時不被舊檔案卡住（`--warn` / `--since`）、用詞不再漂移、必讀文件不再無聲變長；服務省額度（2）和中斷不丟進度（4）；舊檔案照樣通過。

遷移：不用改任何舊檔案。已建置的專案可以把 `"schema_version": 1` 加進 `director_work.json`，不加也一樣。把 `tools/` 整個重新複製到 `DIRECTOR/tools/`，`vocabulary.json` 要一起帶過去，否則 `gate_check.py` 會無法執行。
