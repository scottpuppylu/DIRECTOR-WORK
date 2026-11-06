# CHANGELOG

版本號在 `VERSION`。專案導入時把版本號和 commit 一起記進 `DIRECTOR_OPERATING_RULES.md`（`BOOTSTRAP` 第 1 步），升級時讀這份，照「遷移」做。

- **MAJOR**：已經通過的舊檔案或舊設定會變成不通過，例如工具檢查的格式改了、`director_work.json` 的 `schema_version` 升級。一定附遷移步驟。
- **MINOR**：新增規則、文件、工具或選項，舊檔案照樣通過。
- **PATCH**：修正文字、修 bug，規則不變。

## 0.12.0 — 2026-11-06

補上審查工具查不出來或會誤報的地方：worker 改工單後重算雜湊、只有 `{"exit_code": 0}` 的證據檔、檔名排序選錯報告、沒資料時印 0、檔案被悄悄略過。版本照總監派工單定為 MINOR；會讓舊檔案不通過的項目列在「對齊初衷」第 5 題和遷移。

- `gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md`：LOG 裡 `DISPATCH <WO-ID> rev=<n> sha=<雜湊>`（`--hash` 會印好）要和工單現在的雜湊相同。worker 改了工單又重算 `ORDER_SHA256`，報告和工單仍一致，只有這條查得出來。LOG 沒有紀錄：Strict 失敗、Standard 提示、Direct 不查。
- 驗收表（工單和報告）：同一個 AC 兩列、表頭兩欄同名、某列欄數和表頭不同都失敗，不再悄悄取最後一列；反引號裡的 `|` 和 `\|` 不當成欄位分隔。
- `--evidence-dir`：證據檔要有 `evidence_record.py run` 寫的每個欄位且型別正確；沒有 `schema` 的舊紀錄照讀並提示。報告的 HEAD 要是 7 到 40 位十六進位。紀錄時有未提交改動、label 沒寫這條 AC、HEAD 不是雜湊：Strict 失敗，Standard 提示。label 可以寫多條 AC，一份紀錄給多條 AC 共用。
- `evidence_record.py verify` 分三項報告：完整性（檔案雜湊）、測試（紀錄的 exit code，加 `--rerun` 才重跑）、產物（有沒有缺）。只有 `verify --rerun` 算重跑驗證；`gate_check.py` 只讀紀錄。
- `gate_check.py --since`：找不到日期的檔案也跳過，印 `UNDATED`，最後一行另計；要查它就不加 `--since`。
- `metrics_report.py`：沒有裁決時返工印 `UNKNOWN`，沒有 `RESUMED` 行時中斷重做印 `UNKNOWN`，不再印 0。像工單卻沒算進去的檔案、`--since` 略過的和沒有日期的工單，列在文末「沒計入的檔案」。PO 介入的來源可在 `director_work.json` 設 `po_pending_files`、`po_item_pattern`、`po_open_pattern`，加 `--config`；每項的 `CREATED:` 給 `--since` 用，沒寫的照算並標 `UNDATED`。設定或規則式寫壞時印 FAIL、exit 1。
- `trace_report.py`：沒算進去的檔案列在文末。同一工單多份報告時，依 `ORDER:` 行的 REVISION、`ATTEMPT: n`、報告裡第一個日期取最新的，不看檔名；全部相同就都不取並寫明。另列每份報告和選了哪份。
- `templates/PO_PENDING.md` 加 `CREATED:`；`director_work.example.json` 加三個 `po_` 欄位（選用，`schema_version` 不變）。
- `selftest.py` 加上面各項的正反案例（共 285 項）。另一組照外部稽核的跑法同時加 `--order`、`--report`、`--match`、`--evidence-dir`：紀錄由 `evidence_record.py run` 寫出、欄位完整，每案只改壞一項（報告 HEAD、紀錄 HEAD、未提交改動、label）。Strict 每項單獨 exit 1 且只有這一條問題；Standard 下紀錄 HEAD 不符仍 exit 1，其他三項只提示。

對齊初衷：
1. 幫到誰：外部深度分析報告和總監的對抗測試找到的漏洞，在隔離 fixture 逐項重現後才修。worker 放寬或刪掉驗收條件再重算雜湊會通過（對抗測試 T7–T9）。只有 `{"exit_code": 0}` 的檔案能當證據。`report-9.md` 會蓋過 `report-10.md`。真實專案 21 份工單只算 17 份，沒有說明。沒有裁決時返工印 0。
2. Desktop：在 Desktop Code 分頁的 worker session 實作。selftest 在 Python 3.11 通過；3.9 只用 `ast` 檢查語法，實跑交給 GitHub Actions。用真實 `DIRECTOR` 資料唯讀重跑三個工具；真實專案還沒有 `DISPATCH` 紀錄，`--dispatch-log` 在真實工作上 NOT_VERIFIED。
3. 服務：成品要真的對（5）：證據要完整，工單被改查得出。PO 不用盯細節（3）：總監用工具核對，不靠讀檔猜。用數字決定規則留不留：沒資料印 UNKNOWN，不印 0。零成本（7）：只用標準函式庫。
4. 核心：每輪必讀不變（13,417 / 13,428 bytes）。Direct 不多步驟（`--dispatch-log` 對 Direct 不查）。PO 不多操作：`CREATED:` 由總監寫。
5. 舊檔案：可能新不通過的有三種。驗收表有重複 AC、重複欄或欄數不符；加 `--evidence-dir` 時證據紀錄欄位不全；Strict 工單的證據有未提交改動、label 不符或 HEAD 不是雜湊。用真實 21 份工單比對 0.11.1 和本版的 `gate_check.py --warn` 輸出，完全相同。舊檔案先用 `--warn` 只警告。`PURPOSE.md` 第 5 題要「先只警告，或升 MAJOR」；本版靠 `--warn` 過渡，0.x 升 MAJOR 等於 1.0，要 PO 決定。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。
2. 派工時把 `gate_check.py --hash 工單` 印出的 `DISPATCH` 行記進 `DIRECTOR_LOG`；審查改跑 `gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md`。
3. 要用 `--evidence-dir` 的工單，請 worker 用新版 `evidence_record.py run` 重記證據。
4. `PO_PENDING.md` 新項目加 `CREATED:`。待決事項放在別的檔案或格式的專案，在 `director_work.json` 設 `po_pending_files`、`po_item_pattern`、`po_open_pattern`。
5. 同一工單重做時，報告的 `ORDER:` 行寫 REVISION；同一版重做加 `ATTEMPT: n`。
6. `--since` 印 `UNDATED` 的檔案，另外不加 `--since` 查一次。

沒做：
- 這次不做（留給 PO 決定）：`hook_guard` 擴到 Write／Edit 和 `python -c`、`scope_check` 檢查 repo 外的檔案、`context_probe` 固定等 20 秒、`doctor` 指令、SQLite 狀態庫、`worker_task.py`、HTML 面板、多 CLI 轉接。
- 沒有 git 時 HEAD 排不出先後，只列出。多份裁決仍取路徑排最後的。
- `--dispatch-log` 是事後偵測：沒有 `DISPATCH` 紀錄就查不出「改完重算」。

## 0.11.1 — 2026-11-04

修第一次在 Desktop 上跑完整 Strict 工單時找到的工具誤判和文件缺漏。PATCH：規則不變，原本通過的檔案照樣通過。

- `gate_check.py` 的模糊詞檢查不再把檔名裡的 `todo`（例如 `todo.py`）當成模糊詞；單獨寫 `todo`、`etc.` 照樣擋。
- `gate_check.py --report` 不再把程式碼區段裡的 `<...>`（例如 `` `AC-<n>` ``）和 `<名稱@主機>` 這種地址當成沒填的占位字；其他 `<...>` 照樣擋。
- `gate_check.py --report`：`SCOPE_CHECK` 欄照範本貼上 `scope_check.py` 最後一行時，那行本身開頭的 `SCOPE_CHECK:` 會被拿掉再判斷，不再誤判成沒跑檢查。
- `metrics_report.py` 只把 `## A` 節裡有「下一步」的檔案算成裁決；決策紀錄、工單也有 `## A`，之前會被多算。
- `BOOTSTRAP` 第 8 步：`usage_report.py` 的 `--since` 是 UTC 日期；建置 session 不是從專案資料夾開的要加 `--project-dir`。
- `docs/11`：Strict 工單的規格審查要在 PO 發話的同一輪等到結果再開 worker；直接開 worker 可以帶 `cwd`。
- `selftest.py` 加上面各項的正反案例（共 209 項）。

對齊初衷：
1. 幫到誰：拿新專案在 Desktop 上跑一張真實 Strict 工單，總監被工具誤判卡了三次（檔名 `todo.py`、報告裡的格式說明、照範本貼的 `SCOPE_CHECK` 行），成效數字也把決策紀錄算成裁決。
2. Desktop：這次的問題就是在 Desktop 上實測找到的；修完用同一批真實工單、報告、`DIRECTOR` 資料夾重跑，三項都通過，裁決數字從 3 份變成 1 份。selftest 在 Python 3.11、3.12、3.14 通過；本機沒有 3.9，交給 GitHub Actions。
3. 服務：PO 不用盯細節（3，誤判會讓總監停下來問）、用數字決定規則留不留（數字要算對）。
4. 核心：每輪必讀不變（13,417 / 13,428 bytes）；只放寬誤判，擋的範圍沒有變大；PO 不多操作。
5. 舊檔案：原本通過的照樣通過；原本被誤判的現在通過。

遷移：把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。

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
