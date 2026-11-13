# CHANGELOG

版本號在 `VERSION`。專案導入時把版本號和 commit 一起記進 `DIRECTOR_OPERATING_RULES.md`（`BOOTSTRAP` 第 1 步），升級時讀這份，照「遷移」做。

- **MAJOR**：已經通過的舊檔案或舊設定會變成不通過，例如工具檢查的格式改了、`director_work.json` 的 `schema_version` 升級。一定附遷移步驟。
- **MINOR**：新增規則、文件、工具或選項，舊檔案照樣通過。
- **PATCH**：修正文字、修 bug，規則不變。

## 2.2.1 — 2026-11-14

PATCH（版本號照總監的工單）：依 DeepSeek 版與 2.2.0 的比較報告 A 節，修 `report_vs_audit` 的截斷 bug，`setup_check` 多查三個檔案（shadow），新增從 transcript 重建動作紀錄的工具。照上面的定義，新增工具和選項（`transcript_audit.py`、`setup_check --strict`）算 MINOR；版本號是否改成 2.3.0 待總監決定。舊檔案、舊紀錄照樣能讀；結果會變的只有 `report_vs_audit` 原本判錯的幾類（下面）。

### report_vs_audit.py：截斷的紀錄行（bug）與指令比對

- bug：紀錄的 `input` 超過 500 字時被截成 `…` 結尾。2.2.0 直接用文字切出 command，`\"` 和 `\\` 沒有還原，含引號或反斜線路徑的長 Windows 指令永遠比不到。2.2.1 照 JSON 規則把截斷的字串解回來；只有「字串沒收尾、行尾是 `…`」才當成截斷。
- 比對加強：去掉 `&`、`cmd /c`、啟動程式（python、py、pwsh、powershell、node、bash 等）和它的啟動旗標；`...`、`…`、`<名稱>` 當萬用字；單一檔名可以對到以它結尾的較長路徑；靠詞比對時至少要 2 個實詞，只寫啟動程式或只有萬用字不算證明；只比 Bash / PowerShell 的紀錄。
- 紀錄有 `kind=rebuild` 行（`transcript_audit.py` 重建的）時多印 `~ note: a log was rebuilt from a transcript ...`。
- 結果會變：21 個案例，2.2.0 判對 10 個，2.2.1 判對 21 個。其中 2.2.0 把只寫 `python -I -X utf8` 的主張判成 PASS（假通過），2.2.1 判 FAIL。

### setup_check.py：PO_PENDING、RESUME 表頭、director_work.json（shadow）

- 給資料夾、或檔名是 `DIRECTOR_STATE.md` 時，連旁邊三個檔案一起查。
  - `PO_PENDING.md`：每筆的 ID、STATUS、QUESTION、OPTIONS、RECOMMENDED、SOURCE、ANSWER 各一次；STATUS 合法；answered / closed 要有真的答案；ID 不重複。
  - `RESUME_STATE.md`：前四行依序是 PROGRESS、DOING、NEXT_STEP、COMMS 而且有填；UPDATED 有日期（和 `gate_check.py --resume` 同一條規則）。
  - `director_work.json`：JSON 物件、`schema_version` 1、已知鍵的型別和值、`*_pattern` 是合法正規式；不認得的鍵只印提示。
- 先 shadow：問題印成 `  ~ shadow: ...`，exit code 只看待決頁兩行（和 2.2.0 相同）；加 `--strict` 才算失敗。檔案還沒產生只印提示。
- 已知：從範本複製、還沒填的資料夾會看到 shadow 提示（PO_PENDING 範本的範例條目、RESUME 範本的佔位）。改成 strict 之前，要先決定範本怎麼寫。

### 新 tools/transcript_audit.py：從 transcript 重建動作紀錄

- 沒裝 hook 做完的工作，可以從本機 Claude Code transcript（`.jsonl`，含 subagents）重建一份 hook 格式的紀錄，`audit_log.py verify` 和 `report_vs_audit.py` 照讀。欄位、遮罩、截斷都用 `audit_log.py` 的同一段程式。
- 第 1 行是 `kind=rebuild`，記來源 transcript 的名稱、sha256、大小，以及沒有結果、重複、讀不到時間、壞行的數目，所以重建的紀錄不會被當成 hook 當時寫的。
- 限制：`result.sha256` 算的是 transcript 裡的工具結果，和 hook 紀錄的不能互比；沒有 `duration_ms`；hook_guard 的 decision 行無法重建。transcript 格式是 Claude Code 自己的、沒有文件，格式改了會找不到工具呼叫並 exit 2。重建的紀錄只表示 transcript 裡有什麼，不能證明沒做別的事；hook 紀錄加 AUDIT_HEAD 錨點仍是較強的證據。
- 只讀 transcript、只寫 `--out`（已存在要 `--force`）。

### 遷移

- 不用遷移。舊報告用 `report_vs_audit` 重跑，結果可能和 2.2.0 不同（見上）；`setup_check` 的新檢查是 shadow。

### 數字

- 每輪必讀（`docs/01`、`03`、`06`、`08`）沒改，仍是 9,549 bytes。
- `selftest.py`：2.2.0 的 2,302 項 → 本版 2,391 項（+89：新增 report_vs_audit 31 項、setup_check 33 項、transcript_audit 23 項；另 2 項是既有的逐檔檢查涵蓋到新檔 transcript_audit.py，例如 py39 newline 掃描）。

對齊初衷：
1. 幫到誰：用動作紀錄核對 TASK REPORT 的總監（截斷的長指令不再誤判，只寫啟動程式不再假通過）、建置新專案的總監（三個檔案的格式問題一開始就看得到）、沒裝 hook 的專案（事後也能有一份能驗的紀錄）。依據：DeepSeek 版與 2.2.0 的比較報告 A 節。
2. Desktop：三支都是本機命令列工具，Desktop Code 分頁的 session 照常用；沒有在真的 Desktop 流程裡全程跑過。
3. 服務：初衷 5（成品要真的對）：核對不假通過；初衷 4（中斷不丟進度）：沒有 hook 也能事後重建紀錄；初衷 7（零成本）：只用標準庫。
4. 核心：每輪必讀不變；新檢查先 shadow。
5. 舊檔案和舊指令：照樣能讀；結果會變的只有 `report_vs_audit` 原本判錯的那幾類。

## 2.2.0 — 2026-11-08

MINOR：GPT 對 v2.1.0 的獨立審查（`DIRECTOR-WORK-v2.1.0-review.md`，21 項發現 F01–F21，每項附重現）PO 2026-11-08 決定全部併進 2.2.0，另加「建置時強制做出待決頁並置頂」。每項由負責的 worker 修前先重現、修後再跑 `repro_dw210.py` 確認不再重現（W1–W4 的 TASK REPORT 附輸出）。新的檢查先 shadow；審查明說要改結果的幾項（F10、F11、F15 等）改了結果，列在下面「誰會從成功變成待處理」。

### 建置時就做出待決頁並置頂；指示分三層（W1：F12 F13 F19 F20）

- 新：建置時就把待決頁做成 PO 的 Claude 私人頁面並置頂。README 啟動提示詞加同意句，貼上即同意；`BOOTSTRAP` 在第一則回覆之前發布（`pin: true`），`DIRECTOR_STATE.md` 寫 `PO_PAGE_URL`、`PO_PAGE_PINNED`，第一則回覆附網址。備援寫 `PO_PAGE_URL: NONE reason=...`、`PO_PAGE_PINNED: no reason=...`。
- 新：`tools/setup_check.py <WS>/DIRECTOR`，建置完成時檢查上面兩行；`BOOTSTRAP` 第 6、11、13 步要它 exit 0。它只驗格式，總監第一份回報要貼發布工具回傳的結果原文。
- 新（shadow）：`status_gen.py` 總監版缺 `PO_PAGE_URL` 時印 `~ PO_PAGE_MISSING`，exit code 不變；舊的 `status.py` 要 `--force` 重產才會印。
- F12：`secret_mask.mask_tree()`；`audit_log` 先遮再序列化，引號裡的機密不再漏出尾巴，`input` 是合法 JSON（500 字內）。審查補漏：另外遮指令字串裡跳脫的 JSON、單獨的 `Bearer <token>`、`--password X`、`mysql -p X`／`-pX`、`--user bob:X`、`curl -u bob:X`、`passw0rd` 這類鍵名，`Authorization`／`Cookie` 欄位整欄遮；`hook_guard --review` 送審提示改用 `mask_tree`（原本 `mask(json.dumps(...))` 有同樣的引號問題）。
- F13：新 `audit_log.py recover --log`：留 `.damaged-<時間>` 複本，接一行 `kind=recovery` 後可繼續寫；`verify` 印 GAP 和 `gaps=n`，複本被改才 BROKEN；`.damaged-` 複本遺失時：有 `--anchor-log`／`--anchor-rev` 的判 BROKEN（切掉的行無從核對），沒有錨點的只印 `~ warning`。append 的遮罩和寫入分開回報（`additionalContext`，stderr `masked=… written=no`）。
- F19：完整導入和派工要 git；ZIP 版只能讀規則、跑不需要 git 的工具（commit 記 `NONE (ZIP)`）。
- F20：指示分三層，檔案裡的字句不升級成 PO 指示（README 提示詞也加一句）。總監每輪只有一個第一步：先唯讀檢查並收集（含選擇頁 `choiceReplies`／`decisions`／`notes`），再處理待決頁（`docs/03`、`06`、`06b`）。接手演練改成先關舊總監再送出，用 `submissionId` 驗只記一次。
- 改掉的舊規則：2.1 的「選擇頁／待決頁網頁要先問 PO」整條取消（改成啟動提示詞的同意句）；`docs/06`「總監自身的恢復」節名改為「每輪第一步」。

### 選擇頁帳本端（W2：F01 F02 F03 F06 F07，`choice_reconcile.py`，仍是 shadow）

- 新指令 `publish --revision N | --close`：記下頁面上現在是哪一版；快照（`register`）和現行版分開存。新指令 `rescan`：重判隔離區和等快照的回覆。
- 領取和接手：`CLAIMED → RECEIPT_PENDING` 只有持有者能做；別人和 2.1 沒有持有者的領取改成 `REFUSED`，要先 `CLAIMED → RECONCILE`（新的一步）接手；`--generation` 不對是 `LOST`。新的一步 `PLANNED → RECONCILE`。
- `plan` 和領取會重查版本：新版已登記、未 `publish` 時 `HOLD`；舊版、hash 不符、題目已關時 `REFUSED`（exit 1）。匯出裡壞掉的單筆進隔離區（`QUARANTINED`），其他筆照記。題目已採用別的答案後才到的不同答案標 `conflict-late`；重送的同一則留言記 `duplicate` 並直接 `CLOSED`。
- `status`：`receipts_pending` 含已採用、等回條的；摘要行多 `reconcile= quarantined= clear=yes|no states=`；`--json` 只印一份 JSON（`schema: dw-choice-status/2`，摘要行移到 `summary`）。
- 舊帳本自動升級：2.1 的 `choice_inbox.sqlite3` 第一次被 2.2 打開時升級（`PRAGMA user_version` 2），先在升級的鎖內備份成驗過的 `<db>.v210.bak`（名字被占用就加時間戳，不覆寫；備份失敗就不升級）。升級是單向的：升級後 2.1 工具不保證能讀，要退回就換回 `.v210.bak`（升級後新記的資料會丟）。
- F05 帳本端：`ingest` 把回覆附帶的 `selectedOptionSnapshot` 和該版已登記的選項比對（`key`；有 `label` 也比），不一致就隔離為 `snapshot_mismatch`（印出登記的選項和頁面送的選項），不記帳、不排工；同一筆修好後再匯出會自動離開隔離區。沒附快照，或那一版沒登記，只印 WARNING，照 2.1 記帳；`register` 之後重判，對不上的改標 `snapshot_mismatch`、留在 `RECEIPT_PENDING`，`plan` 不會排。

### 選擇頁頁面端（W3：F04 F05 F07，`templates/choice_page.html`）

- 回覆與回條依 `questionId + revision + snapshotHash + submissionId` 配對，只有總監採用的回覆顯示交接結果；指紋對不上或缺欄位（舊格式）的回覆不算作答，題目仍留在待選。
- 版本文件指紋與 `decisions` 登記的不同、或沒登記指紋時，該版文字與選項不採用、禁止送出並顯示原因；所選選項從登記快照重建。
- 回覆與留言新增 `pageSource`、`pageVersion`；留言重送沿用同一個 `submissionId`；選擇回覆在內容改變後換新 `submissionId`。
- 新 `tools/browser_check.py`：用 headless Chrome 跑頁面行為（W3 加，CI 的 browser job 用；沒有 Chrome 時 SKIP，`DW_REQUIRE_BROWSER=1` 時失敗）。

### 追溯、驗收、證據、範圍、指標（W4：F08 F09 F10 F14 F15 F16 和 v2.1.0 已知問題）

- F08 `trace_report`：「這版有驗證紀錄」拆成 worker 自述／證據有效／綁鎖定依據／總監重跑四欄；worker 自己的 PASS 只顯示「自述全過」，四欄齊才是「有」。新 LOG 行 `EVIDENCE_RERUN`，由 `evidence_record verify --rerun` 印出（`LOG_LINE:`）。
- F09 `gate_check`／`trace_report`：PO 驗收綁到成品身分（`candidate_id`、commit、entry、`entry_sha256`、`manifest_sha256`）並核對檔案。新增 `--artifact-root`、紀錄的 `manifest` 欄、報告的 `CANDIDATE_ID:`（`templates/TASK_REPORT.md` 也加了這一欄，W5）。
- F10 `evidence_record`：`verify --rerun` 遇到 symlink 或 submodule 的 tree 是 NOT_RUN（exit 2）。
- F14 `scope_check`：REQUIRED_CHANGES 和最後結果比，新參數 `--candidate`，多一行 `REQUIRED_BASIS:`。
- F15 `evidence_record`：`--log` 開不了是 NOT_RUN（exit 2，不寫紀錄）；寫一半失敗記 `log_error`、exit 4；`gate_check` 會提示。
- F16 `metrics_report`：`run.json` 的 `sampling` 標記、每個數字的完整度；`--compare` 只比完整而且同劇本的 run；怪 kind 隔離；回覆要對得到發問。
- v2.1.0 已知問題已修：`evidence_record run --log` 上層資料夾不存在時自動建立（建不出來是 NOT_RUN）；`verify --rerun` 加 `--brief`／`--order-history`，用 `gate_check` 同一組函式比初衷卡指紋；五支工具讀到非 UTF-8 檔只印一行 NOT_RUN、exit 2，不再印 traceback；`PO_PRODUCT_REVIEW` 只認整行（`docs/07` 已寫明，完整驗收要用 `PO_ACCEPTANCE.json`）。

### 容器、CI、發布（W5：F11 F17 F18 F21）

- F11：`run_worker.sh` 在 DIRECTOR（唯讀的 `/director`）和任何可寫掛載（`--clone`／`--worktree`／`--git-common`）重疊時 exit 2，不開容器。重疊 = 真實路徑（`pwd -P`）相同、一方在另一方底下、同一個 inode，或 `/mnt/*` 底下只差大小寫的別名。理由：重疊時 worker 可以改自己「唯讀」的規則。
- F17：`--git-common` 是**仍支援的舊模式**（WARN K1、doctor 報 NOT_ENFORCED），只在 major 版移除，最早 3.0；不再說「2.0 拿掉」。要遷移就用 `worker_clone.sh create` + `run_worker.sh --clone`。
- F18：文件寫清楚實際擋了什麼：443 只放行開容器時白名單名稱解析到的 **IPv4 目的 IP:443**（不看 TLS 名稱或 HTTP Host）；IPv6 在開容器時用 docker `--sysctl` 關掉（映像 `dw-worker:1.2.0` 不變）；所有容器 worker 共用同一個可寫登入 volume `dw-claude-home`（clone 隔離不等於登入隔離），要分開就給每個 worker 設不同的 `DW_CLAUDE_HOME_VOLUME`（名稱有格式檢查）。`README.md`、`docs/11`、`tools/README.md` 同步。
- F21：`.github/workflows/selftest.yml` 三個 job：Windows（原有）、Linux（Python 3.9／3.11／3.12，含非 ASCII 與有空格的路徑、沒有 git 的一輪、SKIP 摘要）、browser（runner 內建的 Chrome 跑 `tools/browser_check.py`，`DW_REQUIRE_BROWSER=1`）。actions 都鎖到 commit SHA；不加付費服務。
- 整合時修的（第一次 Linux CI 才抓到）：(a) 暫停中的 `pause_ctl.py status|procs|off` 放行名單在路徑有空格時對不上（`hook_guard` 剖析後去掉引號再比對，空格路徑就拆成好幾個字）。現在比對前把含空白的字重新加回引號，`guard_rules.json` 的三條樣式多認一種「加引號、檔名剛好是 `pause_ctl.py`」；沒加引號的舊寫法照舊，檔名不是 `pause_ctl.py` 或前面多一支別的腳本照樣被擋。selftest 的 `ctl` 也改成加引號，並新增四個反例。(b) Linux 與 browser 兩個 job 的 runner 從 `ubuntu-latest` 固定成 `ubuntu-24.04`：latest 已變成 26.04，沒有 Python 3.9，浮動映像會讓矩陣悄悄少一格。

### 誰會從成功變成待處理，怎麼回到成功

| 項目 | 以前 | 現在 | 回到成功 |
|---|---|---|---|
| 容器：DIRECTOR 放在 repo／clone／worktree 內或同一個資料夾 | 照開 | `run_worker.sh` exit 2 | DIRECTOR 放到 repo 和 clone 外面（例如 repo 的上一層 `<WS>/DIRECTOR/`），重開 |
| 選擇頁：decisions 沒有 `snapshotHash` 的 2.1 新題、或版本文件指紋和登記不同 | 可以送出 | 頁面禁止送出，顯示原因 | 總監用 `choice_reconcile.py register` 重新登記，讓 `decisions` 與 `choiceRevisions` 指紋一致；舊格式回覆需總監在帳本確認 |
| `choice_reconcile`：`advance` 到 `CLAIMED`／`RECONCILE` | `--session` 可省 | 沒給 exit 2；接手（`CLAIMED → RECONCILE`）一定要 `--generation` | 補參數 |
| `choice_reconcile`：帳本被鎖超過 `--busy-timeout` | `SHADOW_ERROR`、exit 0 | `CHOICE_RECONCILE: BUSY`、exit 1 | 當成「沒跑」，稍後重試 |
| `choice_reconcile`：回覆的 `selectedOptionSnapshot` 和登記的選項對不上（例如 `choice: A` 附 B 的快照） | 記帳、排工 | 隔離 `snapshot_mismatch`，不記帳不排工 | 查頁面送錯的原因；請 PO 重送，或修正快照後重新匯出（同一筆自動離開隔離區） |
| `choice_reconcile`：2.1 留下沒有持有者的 `CLAIMED`、非持有者交件 | 照走 | `REFUSED` | 先 `advance --from CLAIMED --to RECONCILE --session <你> --generation 1`，查證後再往下走 |
| `trace_report`：只有 worker 自述的 B | 「這版有驗證紀錄：有」 | 「部分（缺：…）」 | 給 `--evidence-dir`、`--director-log`（含 `BRIEF_LOCKED`），總監跑 `verify --rerun`，把 `EVIDENCE_RERUN` 行貼進 LOG |
| PO 驗收紀錄沒有成品檔可核對 | 已驗收 | 成品待核對或 `UNBOUND_PO_REPLY` | 補 `entry_sha256`、`manifest`，成品檔放在紀錄旁邊或用 `--artifact-root` |
| `trace_report`：LOG 裡帶 `brief=stale`／`brief=unconfirmed` 的 `EVIDENCE_RERUN` | 算總監重跑 | 不算 | 初衷卡和工單指紋對上（必要時重開工單），用最新鎖定的初衷卡再跑 `verify --rerun --brief`，貼 `brief=ok` 那行 |
| `scope_check`：改了又改回的 REQUIRED_CHANGES | PASS | VIOLATION（`MISSING`） | 最後結果真的要有那個改動，或改工單 |
| `evidence_record`：`--log` 開不了／寫一半失敗 | exit 0 並留紀錄 | exit 2 不寫紀錄／exit 4 | 修好 log 路徑和權限再跑 |
| `verify --rerun`：tree 有 symlink 或 submodule | OK | NOT_RUN（exit 2） | 另外驗那些 AC，不要靠 `--rerun` |
| `metrics_report --compare`：沒有 `sampling` 的 run | 出數字 | UNKNOWN | `run.json` 補 `sampling` |
| `metrics_report`：「已回覆」數 | 有 `answer_received` 就算 | 要有同一個 `decision_id + ask_id`、時間更早的 `asked` | 補對應的 `asked` 事件，或修正 ask_id 和時間；對不到的列在「回覆對不到發問」 |
| 五支工具讀到非 UTF-8 檔（`metrics_report` 的 `--run` 資料夾也算） | traceback（exit 1）或略過該檔照算（exit 0） | 一行 NOT_RUN、exit 2 | 把該檔另存成 UTF-8；看 exit 1 判斷的腳本改看 2 |
| `audit_log verify`：`recover` 留下的 `.damaged-` 副本不在日誌旁邊，而且有 `--anchor-log`／`--anchor-rev` | 副本遺失只算 GAP、OK | 判 BROKEN（切掉的行無從核對），exit 1；沒有錨點時只印 `~ warning`，仍 OK | 把 `.damaged-<時間>` 副本放回日誌旁邊（sha256 要和復原行記的一樣）；副本真的沒了就重新設錨點（`audit_log head` 取新的 `AUDIT_HEAD`，記進 DIRECTOR_LOG） |

### 遷移（已在用的專案，照順序做）

1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`（W4 的五支工具、`choice_reconcile.py`、新的 `setup_check.py`、`browser_check.py`）。
2. 有選擇頁帳本的專案：換上新工具後跑一次 `choice_reconcile.py status --db <帳本>`（這一步會升級帳本），確認產生了 `.v210.bak`（或 `.v210.bak.<時間戳>`）；頁面上不是最新登記的那一版，跑 `publish --revision <頁面那一版>`；`status` 提示「2.1 舊領取，沒有持有者」的，逐筆 `advance --from CLAIMED --to RECONCILE --session <你> --generation 1`；每輪自查改看 `clear=yes`。
3. 選擇頁用新範本重新發布（網址不變、資料不動）；沒有 `snapshotHash` 的題目用 `register` 補登記。
4. `DIRECTOR_STATE.md` 加 `PO_PAGE_URL`、`PO_PAGE_PINNED` 兩行（先問 PO 要不要置頂的私人頁面），跑 `setup_check.py` 到 exit 0；總監版 `status.py` 用 `status_gen.py --force` 重產。
5. 用容器 worker 的：確認 DIRECTOR 不在 repo／clone 內（否則 exit 2）；想分開登入的設 `DW_CLAUDE_HOME_VOLUME`。
6. 用 `evidence_record run --log` 的：log 資料夾不用先建；總監重跑改用 `verify --rerun --brief <初衷卡> [--order-history ...]`，貼 `brief=ok` 那行；PO 驗收的 `PO_ACCEPTANCE.json` 補 `entry_sha256`、`manifest`；報告寫 `CANDIDATE_ID:`。
7. 每輪必讀沒有變大（`docs/01`、`03`、`06`、`08` 合計仍在 9,550 bytes 內）；`docs/03`、`06` 的措辭有改，現任總監下一輪重讀一次。

### 已知問題（不擋發布，下一版處理）

- 規則式遮罩的極限（`secret_mask`，F12）：沒見過格式的 token、沒有關鍵字的位置參數（`tool login bob X`）、鍵名不像機密的欄位（`{"name":"DB_PASS","value":"X"}`）、名稱裡沒有關鍵字的變數（`PASS=X`、`MY_KEY=X`）、URL 編碼或 base64 包住的機密、跨行的引號值、中文鍵名、`pwd=X`（刻意不遮，和 shell 的 `PWD` 同名）、少於 8 字且前面沒有 `Authorization` 的 `Bearer X`、以 `-` 開頭的旗標值，以及被 `|`、`;`、`&` 隔開的 `mysql -p`／換行後的 `curl -u`，都遮不到。完整清單在 W1 報告。
- `audit_log` 的 `input` 超過 500 字時截斷加 `…`，不是合法 JSON（短的才保證）；`recover` 只保留第一個壞行之前的行，壞行之後的好行只留在複本。
- `choice_reconcile`：隔離區自動解除只對有 `id` 的列有效（`missing-id`、`bad-answer` 要手動 `settle --key <隔離鍵> --to CLOSED`）；`status` 打開 2.1 帳本時會升級它，不是唯讀；沒有 `publish` 的新版會讓舊版一直 `HOLD`（`status` 會提示）。
- `choice_reconcile`：在不支援 `os.link` 的檔案系統（FAT／exFAT、部分網路磁碟）上，舊帳本升級會中止，只印一行 OSError（`SHADOW_ERROR`、exit 0）。不會掉資料，但要手動備份後再升級。
- `choice_reconcile`：同一筆回覆，一次匯出有 `source`、一次沒有，又沒給 `--source`，會用兩個不同的冪等鍵，重複記帳；系統只印 WARNING。舊匯出請一律帶 `--source`。
- 選擇頁頁面端只比對指紋字串，內容防竄改靠帳本端；兩個分頁同時送出由帳本標 conflict，頁面不仲裁。
- 容器：真實 Docker 行為（`--sysctl` 實際關掉 IPv6、重疊掛載在 Docker Desktop 上的別名）只在本機模擬測過，沒有在真的容器裡跑；Linux 與 browser 兩個 CI job 已在 GitHub 上跑過且通過（見「數字」），但 CI 裡也沒有實際起 Docker。
- 2.1 專案自己複製的 `guard_rules.json` 沒有新的帶引號樣式：專案路徑有空格時，暫停中 `pause_ctl status`／`procs`／`off` 還是會被擋。處理：從 2.2.0 範本更新 `guard_rules.json` 的 `pause.allow_shell`（`hook_guard.py` 也要用 2.2.0 版，`quote_blank` 在那裡）。
- 外部 GPT 審查的重現腳本只認 v2.1.0 的版本字串；`repro_dw210.py` 對 2.2.0 的結果見 PR 說明，仍顯示「重現」的項目逐項列在那裡。

### 數字

- 每輪必讀（`docs/01`、`03`、`06`、`08`）：2.1.0 的 9,532 → 本版 9,549 bytes（上限 9,550，`MUST_READ_LIMIT` 不變；增加的是 W1 的待決頁與三層指示句）。量法是先把 CRLF 換成 LF 再數（selftest 的 `test_must_read_size` 就這樣量）；Windows checkout 的檔案是 CRLF，用 `wc -c` 直接量會顯示約 9,698。
- `selftest.py`：2.1.0 的 1,946 項 → 本版 2,302 項（W1–W5 新增 356 項）。整合樹 cae6162（之後只改 CHANGELOG 與報告）本機 Python 3.11、3.9 各 2,302/2,302 全過；PATH 上沒有 git 時 1,140/1,140 全過，22 組依賴 git 的照名稱 skip；3.11 也在放在有空格與中文路徑的匯出樹裡跑過一次（CI 的 Linux job 用這種路徑）。之後只改了 CHANGELOG、報告和 CI 設定檔（無 git 那一步在 Linux 要保留 `ps`，見上面的 W5 整合修正）。GitHub CI（PR #20，push 與 pull_request 各一輪，全綠）：Windows 3.9／3.12 各 2,303/2,303（無 git 1,140/1,140，skip 22 組）；Linux 3.9／3.11／3.12（`ubuntu-24.04`，checkout 路徑 `dw 專案 路徑`）各 2,281/2,281（Windows 專屬的項目在 Linux 照名稱 skip），無 git 1,140/1,140（skip 22 組）；browser job（runner 的 Chrome）通過。
- 外部審查重現器（`repro_dw210.py`，改版本字串後對整合樹跑）：19 個案例，14 個「不再重現」、1 個仍顯示重現、4 個本機跳過（`rerun_symlink`、`container_mount`、`container_legacy` 要 Linux／WSL／Docker；`browser` 要 `--chrome`，由 CI browser job 跑）。仍顯示重現的一個：`audit_cut_line`（斷行後 `audit_log` 仍拒寫並印 BROKEN，這是設計；2.2.0 多了 `recover` 出口，重現器的判斷不認得它；F13 已修的證明——`recover` 後 `verify` 印 `GAP`、副本 sha256 吻合——在 PR 說明和 W5 報告）。逐項狀態在 PR 說明。

對齊初衷：
1. 幫到誰：PO 和之後所有用 DW 的人。依據是外部獨立審查（GPT）對 v2.1.0 的 21 項發現，和 PO 2026-11-08 對「建置時就要有待決頁」的要求。
2. Desktop：總監和五位 worker 都在 Desktop Code 分頁的 session 做；selftest 與 CI 的結果見上；真的 Claude Desktop 流程（手機送出選擇頁、置頂私人頁面實際發布、容器內的防火牆）沒有在這次全程跑過，列在「已知問題」。
3. 服務：初衷 8（只跟總監聊天就能做出成品）：待決頁一開始就在、選擇頁不送錯不漏讀；初衷 5（成品要真的對）：驗收綁到成品本身、證據分四欄；初衷 4（中斷不丟進度）：帳本可接手、稽核鏈可修復；初衷 7（零成本）：CI 只用標準庫與 runner 內建的 Chrome。
4. 核心：每輪必讀不超過 9,550 bytes；新的檢查先 shadow；改結果的幾項都列在上面的表，附回到成功的步驟。
5. 舊檔案和舊指令：舊專案檔案、舊帳本（自動升級並備份）、舊稽核鏈照樣能讀；結果會變的只有上表。

## 2.1.0 — 2026-11-08

含未發布的 2.0.1（PR #18）：選擇頁不漏讀。

MINOR：五份外部研究提出的問題一次修完，2.0.1 一起併入。PO 2026-11-08：「這些都修正成2.1版」。研究是外部 GPT 在 2026-11-08 針對 v2.0.0（`15f0460`）做的五個題目，每份都附重現腳本：題1 初衷卡改版後的追溯、題2 選擇頁可靠性、題3 小白模式的第一輪、題4 只跟總監聊天的演練、題5 跨帳號導入與每輪成本。報告內容是研究者自述，每一項都由負責的 worker 自己重現過才修，重現不到的不修，列在「沒重現的」。新的檢查都用影子模式：只提示，exit code 不變，不擋。舊檔案和舊指令照樣通過，所以是 MINOR。

2.0.1 的內容列在第一節。

### 選擇頁不漏讀（原 2.0.1）

PO 要求「專案選項頁你不會漏讀，跟我們的那個待決頁一樣」。原本選擇頁只靠總監每輪第一個動作去查，總監的對話沒在動時，回覆會一直放著，使用者也看不出總監讀了沒。

- 送出就叫醒：`templates/choice_page.html` 的 capabilities 加 `comments`。使用者送出回覆或留言後，頁面用 `comments.sendToClaude` 在那一題留一則給總監的訊息；總監的對話開著、這一頁的監看是 armed 時，總監馬上被叫醒。不能送（沒權限、沒有對話、使用者關掉）就顯示「總監下一輪會讀到」，已寫進 db 的回覆不受影響。
- 已讀回條：總監讀到回覆時同一輪先寫回條（2.1.0 起改成分階段回條，見下一節）。已回覆卻很久沒有回條的題目會標出來，提醒使用者在聊天裡講一聲；「已回覆」列表每分鐘自己更新一次。
- 補充文字不再消失：資料同步進來時，正在打的補充文字連游標一起放回。
- 規則：`docs/12` 新增第六節「選擇頁不漏讀」；`docs/03`、`docs/06` 的「讀待決頁」各加一句「含選擇頁」。

### 選擇頁不漏字、不送錯、不重複執行（題2）

題2 在 Chromium 實測：資料同步會整區重畫開放題，清掉補充文字、選取範圍和焦點；刪掉 B 選項後仍能送出 B；送出中的按鈕被改選或重畫後又能按；`seenAt` 寫成功反而讓卡住的題目從逾時提示裡消失；兩個總監可能同時處理同一筆回覆。

- 重畫分區（P-1）：`render` 拆成待選、已回覆、已結束、留言四區，初衷卡和留言的資料進來只重畫自己那區。重畫前後保留輸入框的內容、選取範圍和焦點；輸入法組字中延後重畫。送出前確認選的選項還在目前的選項裡；新題的選項還沒讀到時顯示「載入中」或「這一版選項讀不到，請在聊天告訴總監」，都不能送。每題送出中上鎖（`S.inFlight`），晚到的寫入不會蓋掉已結束的題目；留言送出成功後，只有文字沒被改過才清空。
- 題目改版不覆蓋（P-2）：題目每改一版留一份（`choiceRevisions`）；回覆只新增（`choiceReplies`），帶 `submissionId`、`revision`、`snapshotHash` 和當時的選項內容。沒有版本紀錄的舊題照樣顯示，標「舊題，當時選項未留存」。
- 本機收件帳本（P-3，影子模式）：新工具 `tools/choice_reconcile.py`，帳本是 `<DIRECTOR>/choice_inbox.sqlite3`（revisions、inbox、decisions、effects 四張表；指令 register、ingest、plan、advance、settle、status）。每筆回覆的狀態 RAW → RECORDED → PLANNED → QUEUED → CLAIMED／RECONCILE → RECEIPT_PENDING → CLOSED；`plan` 在 `BEGIN IMMEDIATE` 裡固定工單編號、可重跑，`advance` 用 compare-and-set，兩個總監同時處理同一筆，只有一個拿得到。帳本出錯只印一行 `CHOICE_RECONCILE: SHADOW_ERROR <原因>`，exit 0。
- 頁面看得出卡在哪（P-4）：回條分三階段（`choiceReceipts`），每題顯示「已儲存，等總監讀取」／「總監已收件，處理中」／「已交接／處理完成」；逾時提醒分成「（沒收到）」（10 分鐘沒有收件回條）和「（收到但卡住）」（收件後 30 分鐘沒交接）。叫醒訊息只送事件提示，掛在固定的標題 anchor（`#h-open`、`#h-note`）上。頁面裡的連結只接受 `https:`、`/_blob/` 和相對路徑。
- `docs/12` 第四～六節照上面更新；`tools/README.md` 加 `choice_reconcile` 一節。
- 重現：題2 的 F-1、F-2、F-4 在 headless Chrome 加題2 的 stub 重跑，修前重現、修後 13/13 FIXED；F-3（兩個總監搶同一筆）和 F-6（`seenAt` 讓卡住的題目消失）瀏覽器重現不到，在帳本模型和 selftest 修好（兩個行程同時 claim 只有一個成功）；F-5 只修一部分，見「沒重現的」。

### 初衷卡改了，用舊驗證的工單會被標出來（題1、題4 P-2）

題1 重現：B-2 的內容改版後，`trace_report.py` 和 Strict gate 照樣顯示舊條件的 PASS；只提高工單版次，仍可能把舊證據帶進新版；追溯表分不出「報告寫了 PASS」「證據還在」「使用者看過」。題4 重現：兩份候選都核對成功，試用連結換了之後，PO 的「對，可以收貨」分不出批准的是哪一份。

- 工單記初衷卡版次和逐條指紋（題1 P-1）：`templates/WORK_ORDER.md` 加選填欄位 `BRIEF_REVISION`、`BRIEF_FINGERPRINTS_V1={"B-2":"<sha256>"}`。指紋 = sha256(UTF-8(`"brief-row-v1\n"` + 精簡 JSON [編號, 類別, 內容, 怎麼算做到]))；`gate_check --brief BRIEF.md` 單獨跑會印出這兩行，貼進工單即可。重複或認不出的列顯示「依據未確認」。沒有這兩欄的舊工單照樣通過。
- 追溯表三欄（題1 P-2）：`trace_report.py --brief` 分成「有人負責」「這版有驗證紀錄」「你看過這個成品嗎」，另有 `--director-log`、`--evidence-dir`、`--acceptance`。看過成品的依據是 `DIRECTOR_LOG` 的 `PO_PRODUCT_REVIEW` 紀錄；裁決紀錄可選擇帶 `ORDER_SHA256`、`REPORT_SHA256`、`CANDIDATE_HEAD`。
- 改版快照與影子提示（題1 P-4）：初衷卡鎖定時存快照 `DIRECTOR/brief-history/<rev>-<hash>.md`（原子寫入）並記 `BRIEF_LOCKED`；`gate_check --brief` 印影子提示 `~ BRIEF_STALE WO-001 B-2 AC-1`，exit code 不變。沿用的證據要對照舊工單當時的指紋，不能跨條文沿用（題1 F-4）：`--hash 工單 --snapshot DIR` 留下工單原檔，`--match --order-history DIR` 拿 `EVIDENCE_EQUIVALENT` 沿用的舊工單指紋比，條件變了印 `BRIEF_STALE`，找不到舊工單印 `BRIEF_UNCONFIRMED`。
- `--decisions BRIEF.md` 單獨使用時，不再把合法的 DD-1 報成找不到（題1 F-2）：初衷卡用清單列出的 DD 也算找得到，不列成缺漏，也不列進「沒有工單的需求」；圍欄裡的清單不算。表格裡沒有 PO 編號時，提示再加一次 `--decisions DECISION_REGISTER.md`。
- 收貨紀錄（題4 P-2）：`PO_ACCEPTANCE.json` 綁定候選 ID、完整 commit、入口檔、manifest 的 SHA-256 和訊息參照；`gate_check --po-acceptance` 和 `trace_report --acceptance` 讀得到，PO 的回覆沒綁到候選時印 `~ UNBOUND_PO_REPLY`。PO 打開試用後照常回話即可，由總監寫這份檔。
- `templates/GATE_VERDICT.md`、`docs/02`、`docs/07`、`tools/README.md` 的對應段落同步。

### 小白模式第一輪就談需求；一句話確認初衷卡並開工（題3、題2 P-5、題1 P-3）

題3 重現：小白模式的第一次需求訪談排在完整建置之後，而建置在新 repo 上會出錯（沒有 `.gitignore` 時 `setup_project_settings.py` exit 1；PATH 上沒有 CLI 時 `context_probe.py` exit 1，成功時還要先等 20 秒）。確認初衷卡和同意開工是兩個決定，原本沒有合併回覆的範本。題2 F-7：`BOOTSTRAP` 和 `docs/11` 對小白模式要不要先問才用 Artifact 寫法矛盾。

- 小白模式選完模式的同一輪就開始談需求（題3 P-1）：`BOOTSTRAP` 加「小白快速路徑」，先做唯讀檢查，只在 repo 外寫最少的續航狀態，完整建置延到開第一位 worker 之前；一般模式的順序不變。
- 壓縮門檻改在開第一位 worker 前才設（題3 P-2，`BOOTSTRAP` 步驟 7）：只對 worker 資料夾，`setup_project_settings.py --repo <worker> --only-this` 先看報告 → `--apply` → `git check-ignore` → 開線 → `get_usage`，結果記進 GUARDS；讀不到寫 NOT_VERIFIED。
- 一句回覆同時確認初衷卡、授權開工（題3 P-3，`docs/12` 第三節）：加同意範本（店員班表的例子，回覆句「卡片對，請開一位 AI 助手做這一批」）和三種狀態 `LOCK_ONLY`、`NO_START`、`LOCK_AND_USER_ASKED`。
- 初衷卡可以只鎖「第一階段」；要看到真的畫面才能選的事（例如配色）放在「待預覽」段，不編 B 號（題3 P-4，`templates/BRIEF.md`）。
- 選擇頁一定先問（題2 P-5、F-7）：兩種模式都預設用聊天加本機 `PO_PENDING.md`；Artifact 選擇頁要先問、PO 同意、而且能用時才開。小白模式的問法：「需要我把選擇題和圖片放在你自己的 Claude 頁面，讓你點選嗎？直接在這裡回答也可以。」頁面不能用時，經 `PO_PENDING.md` 和聊天的 4 步備援。`BOOTSTRAP` 步驟 6 和 `docs/11` 新節「選擇頁的授權與備援」不再矛盾。
- 追溯指令改成兩次 `--decisions`（題1 P-3）：`--decisions <WS>/DIRECTOR/BRIEF.md --decisions <WS>/DIRECTOR/DECISION_REGISTER.md`；只有 B 列算待做項目。`docs/12`、`BOOTSTRAP`、`templates/BRIEF.md`、`tools/README.md` 同步。
- `README.md` 的開始步驟 3～6、模式表、提示詞第 0／2／5 項同步；文件表 `docs/12` 那一列沒改（內容仍對）。

### 沒有 git 也能跑；每輪必讀變小；總監先想怎麼派工（題5、題4 P-1/P-3/P-4、題2 P-3、PO 2026-11-08）

題5 重現：從 `git archive` 解出來、沒有 `.git` 的規則包跑 selftest 是 1,743/1,744，唯一失敗的是 `status.py full`；沒有 git 執行檔時，`evidence_record run` 照樣執行了指令，卻沒留下紀錄。四份每輪必讀還帶著只在某些情境才用的操作細節。

- 沒有 git 不再失敗（題5 F-1、F-2）：selftest 的 `status_gen` 測試改用自建的 git fixture；PATH 上沒有 git 時，依賴 git 的組別依名稱 skip（`SKIP <group>: needs git, none on PATH`），其餘照跑。`evidence_record run` 沒有 git 照樣留紀錄（`git` 欄為 null，stderr 說明）；`verify --rerun` 沒有 git 是 NOT_RUN、exit 2；`doctor --repo` 沒有 git 是 exit 2 加訊息。CI 多跑一次沒有 git 的 selftest。
- 題5 其餘各項：F-4 做一部分（`docs/06b` 寫合併 PO 入口時要保留真實回覆；總監版 `status.py` 的待決頁項目還是 `STATUS: open` 卻已填 `ANSWER` 時多印一行 `PO hint`，影子模式）；F-5 做一部分（`doctor` 的「not inside a git repo」分成「沒有 git」和「dubious ownership」）；F-9 只修 `doctor` 的編碼（子程序輸出一律用 UTF-8 讀，不再用 cp950）。F-6、F-7、F-8 和 F-5、F-9 的其餘部分在 `context_probe`、`docs/11`、`docs/12`、選擇頁、`BOOTSTRAP`、`setup_project_settings` 裡，不在這次 W4 的範圍，沒改。
- 每輪必讀變小（題5 P-3）：純理由移到 `docs/10`「每輪必讀規則的理由」，按需才做的步驟移到 `docs/05`、`docs/06b`，規則留在原處；四份必讀 12,433 → 9,550 bytes，`MUST_READ_LIMIT` 12,440 → 9,550，理由寫在 `selftest.py`。每輪的本機讀取合併成較少的工具呼叫，所有有效的 PO 入口照樣每輪掃完（題5 P-4，`docs/06b`）。
- `docs/03` 待決頁兩句改短（題2 P-3）：「每輪第一步讀待決頁（任何喚醒）：照待決頁程序（含選擇頁）讀回覆和新留言，同輪執行或派工並關閉；未能完成則寫續辦紀錄。」「每輪結束前自查：待決頁已讀、本輪 PO 訊息已處理並登記、已回覆項目已關閉或留有續辦紀錄。」
- 總監每次派工先做派工規劃（PO 2026-11-08）：PO 原話「記住不要讓總監自己做事，這是不符合初衷的，總監制的目的就是提高效率的同時穩定研發」，並補充「總監不是只派工…是讓他不要攬著所有事情自己做」。總監的職責範圍不變；要加的是每次有工作，先想要不要開 worker、開幾位、依檔案歸屬怎麼切（兩人不改同一檔）、平行或先後、各自的模型和 effort、誰整合，寫進工單或 `DIRECTOR_LOG` 的 `DISPATCH` 紀錄。`docs/01` 加一句，細節放 `docs/05`「派工規劃」（非必讀）。
- 八步演練（題4 P-1）：`docs/06b`「接手演練」，中斷點放在 PO 送出 A/B 選擇之後、舊總監讀到之前；接手通過要有證據顯示選擇只套用一次，沒有重問、重派或重做。
- 量得到「少問幾次」（題4 P-3/P-4）：`metrics_report.py --run <資料夾> [--compare <基準>]`（影子模式）算決定事件（提出／已回覆／還在等／撤回）、第一個可用預覽的分鐘數、重問次數、PO 操作數；省下的操作 = 基準 − 本次，加百分比。不加 `--run` 時輸出和 2.0.1 相同。
- `docs/10` 新增第 48 條 L-057（總監把實作攬在自己身上，上下文變長、平行變排隊、自己驗收自己）和第 49～58 條 L-047～L-056（W1～W4 的教訓：通知錨點、分階段回條、共用函式跨 SCOPE、lacks 測試、指紋格式標籤、預設寫在三處、未定案不編號、selftest 不假設有 git、中文與 CRLF 檔的改法、selftest 排進背景）。

### README 重整：啟動提示詞放最上面（PO 2026-11-08）

PO 要求重新整理 README，把啟動提示詞放到最上面。

- 標題下先寫「怎麼用：開一個新的 Claude Code 對話，把下面整段貼上」，接著是整段啟動提示詞（內容沒改），再用兩行說明一般模式和小白模式的差別，然後才是「這是什麼」。
- 其餘照新手閱讀順序：這是什麼、解決什麼 → 準備和怎麼開始 → 第一份回報 → 用起來長怎樣 → 平常要做的事 → 常見問題 → 名詞 → 檔案地圖 → 防護 → 已知限制 → 原則 → 授權。
- 原本兩節「防護是安全帶，不是剎車（1.3.1）」和「執行期防護（1.1.0）」合成一節「防護：哪些真的擋、哪些只提醒」，標題不寫版號。
- 內容只搬不刪，規則句都留著；只有「怎麼開始」第 2 步改成「把本頁最上面的啟動提示詞整段貼給它」。
- selftest 新增 `test_readme_prompt_first`：啟動提示詞的 text 區塊一定在「## 這是什麼」之前，防護只有一節，標題不帶版號。

### 數字

- 每輪必讀（`docs/01`、`03`、`06`、`08`）：2.0.0 的 12,363 bytes → 2.0.1 的 12,433 → 本版 9,550（少 2,883，約 23%）。`MUST_READ_LIMIT` 12,392 → 12,440 → 9,550。
- `selftest.py`：2.0.0 的 1,744 項 → 2.0.1 的 1,756 → 本版 1,946 項（W1 選擇頁與帳本、W2 指紋與收貨、W3 小白第一輪、W4 沒有 git 與指標、README 重整），本機 Python 3.9、3.11、3.12 各跑一次全過；PATH 上沒有 git 時 821/821 項全過，19 組依賴 git 的照名稱 skip。GitHub CI 跑 Python 3.9、3.12 和一次沒有 git 的 selftest，全綠才合併（L-046）。

### 已知問題（不擋發布，下一版處理）

- `evidence_record run --log <路徑>` 的資料夾不存在時會出錯，不會自己建（W4）。
- `evidence_record verify --rerun` 還不做題1 F-4 的舊工單指紋比對：這段比對和 `gate_check` 共用同一個函式，而 `evidence_record.py` 在 W2 工單的 FORBIDDEN 裡；新的綁定鍵一律用 `.get` 讀，所以 `evidence_record` 照舊運作，只是不比（W2）。
- W2 新增的檔案讀取用嚴格 UTF-8，遇到非 UTF-8 的檔案會印 traceback，而不是一行錯誤。
- 只給 `--decisions` 時，`trace_report` 的提示文字變了（exit code 不變）；有腳本比對舊提示字串的要更新。
- `PO_PRODUCT_REVIEW` 只認整行的紀錄，寫在句子中間的不算（W2）。
- 同一個舊題（沒有版本紀錄）在不同分頁各還能送出一次（W1）。
- `choice_reconcile register` 出錯時 exit 2，不是影子模式的 exit 0：頁面需要它算出的雜湊（W1，已接受）。

### 沒重現的、沒驗證到的

- 題2 F-3（兩個總監搶同一筆）、F-6（`seenAt` 讓卡住的題目消失）瀏覽器重現不到，只在帳本模型和 selftest 驗證。
- 題2 F-5：頁面沒有回合可跑時叫不醒總監，是 Desktop 的行為，不在這次範圍；改成頁面顯示「（沒收到）」、總監的 `status` 看得到沒交出去的，`docs/12` 第 6.1 節寫明「沒有人開始下一輪時不會被讀到，請在聊天提醒總監」。
- 題1 P-3：工具本來就支援兩次 `--decisions`，只改文件。題3 F-3／F-4、題2 F-7 是文件和規則前後矛盾，靠讀文字重現，不是跑程式。
- 題5 F-6、F-7、F-8 不在範圍，沒改，也沒重跑報告的重現腳本；F-5 只重現了 `doctor` 的訊息，`BOOTSTRAP` 的資料夾碰撞沒重現。
- 選擇頁的修正在 headless Chrome 加題2 的 stub 驗證，不是真的 Artifact SDK；輸入法只用事件模擬，沒用真的輸入法。
- 五份研究都沒有在 Claude Desktop 跑完真的流程；這次也沒有：手機上送出選擇頁並看到總監被叫醒、另一個 Claude 帳號的導入、小白模式同輪開線（`user_asked`）、八步演練全程，都是 NOT_VERIFIED。影子提示的誤報率要等真實專案的資料。

遷移（已在用的專案，全部選做；不做也照樣通過）：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。新的檢查都是影子模式，只多提示，exit code 不變。
2. 選擇頁：用新範本重新發布，`capabilities` 改成 `{"db": {}, "user": {}, "assets": {}, "comments": {}}`；網址不變，資料不動。舊頁不改照樣能用，只是沒有叫醒、分階段回條和三種狀態。
3. 想用收件帳本：照 `tools/README.md` 的 `choice_reconcile` 一節建 `<DIRECTOR>/choice_inbox.sqlite3`；帳本和 `DIRECTOR/` 裡其他檔案放在一起，本版沒有改 ignore 規則。
4. 想讓初衷卡改版標得出來：新工單填 `BRIEF_REVISION` 和 `BRIEF_FINGERPRINTS_V1`（`gate_check --brief BRIEF.md` 會印出來），舊工單不用改；跑 `gate_check --brief` 看 `BRIEF_STALE` 提示。
5. 追溯指令：原本只給 `--decisions DIRECTOR/BRIEF.md` 的，改成兩次 `--decisions`（BRIEF 和 DECISION_REGISTER）。
6. 每輪必讀變了：現任總監下一輪重讀 `docs/01`、`03`、`06`、`08` 一次。

對齊初衷：
1. 幫到誰：PO 和之後所有用 DW 的人，特別是小白模式的使用者和換帳號導入的人。依據是五份外部研究的重現結果（每項由 worker 重新重現），和 PO 2026-11-08 對 2.0.1 選擇頁、總監派工的兩次要求。
2. Desktop：總監和五位 worker 都在 Desktop Code 分頁的 session 做；selftest 在本機 Python 3.9、3.11、3.12 各跑一次，另跑一次 PATH 上沒有 git 的，合併前看 GitHub CI 全綠（L-046）。選擇頁在 headless Chrome（題2 的 stub）重現 13 案，修後都 FIXED；不是 Desktop 內建瀏覽器，也不是真的 Artifact SDK。Desktop 全流程（手機送出叫醒、同輪開線、跨帳號導入、八步演練）沒有實跑，寫 NOT_VERIFIED。
3. 服務：初衷 8（只跟總監聊天就能做出成品）：小白模式第一輪就談需求、一句話確認並開工、選了不會漏、不會送錯；初衷 5（成品要真的對）：初衷卡改版後舊驗證會被標出來，收貨綁定到哪一份候選；初衷 4（中斷不丟進度）：收件帳本和八步演練；初衷 1（一條連結就能開工）：沒有 git、換帳號也跑得起來；初衷 2（省額度）：每輪必讀變小、工具呼叫合併；初衷 3（PO 不用盯）：總監先派工規劃，不攬著自己做。零成本（7）：只用標準庫和 Artifact 內建能力。
4. 核心：每輪必讀 12,433 → 9,550 bytes（少約 23%），移走的只有理由和按需步驟，規則沒少（總監讀 diff 確認）；派工規劃只在 `docs/01` 加一句。新的檢查全是影子模式；工作線隔離（核心 4）照檔案歸屬切成四位 worker，必讀四檔只有一人改。Direct 工作不多步驟；PO 的操作變少（確認初衷卡和開工合成一句）。
5. 舊檔案和舊指令：都照樣通過。沒有新欄位的工單、沒有版本紀錄的選擇題、沒有 `PO_ACCEPTANCE.json` 和收件帳本的專案都照舊；新提示只多印，不改 exit code。輸出有變的只有：只給 `--decisions` 時 `trace_report` 的提示文字；沒有 git 時 `doctor` 的訊息分成兩種、`evidence_record run` 多留一份紀錄。

## 2.0.0 — 2026-11-08

MAJOR（PO 定的）：初衷變了。PO 在 2026-11-07 加了第 8 條初衷「只跟總監聊天就能做出成品」：使用者給初始提示詞、選模式後，一直跟總監聊需求，聊到能寫成初衷卡、確認了才開工；中途要選的 A/B 放在獨立的選擇頁；每張工單都對回初衷卡，不做歪。舊檔案和舊指令都照樣通過；升 MAJOR 是因為目標變了，不是格式變了。

- `PURPOSE.md`：新增初衷 8，「為什麼」記下 PO 加上的日期和原因。
- 模式選擇：總監讀完啟動提示詞，第一則回覆只問「一般模式還是小白模式」（`BOOTSTRAP` 新增「先問模式」、README 啟動提示詞第 0 點、README 新增兩種模式對照表）。小白模式不問技術問題：plugin 清單不問、什麼都不關，hook 不裝，工作線由總監照 `docs/05` 定並登記 DD，第一份回報三句白話；推送、公開、付費、刪除、帳號照樣要使用者同意，只是改用白話問。`director_work.json` 新增選用的 `mode`（`general` / `beginner`），工具不讀它。
- 專案初衷卡：新範本 `templates/BRIEF.md`（B-1、B-2… 每列有「怎麼算做到」）。`BOOTSTRAP` 新增第 14 步：開工前談需求、寫卡、使用者確認才 `LOCKED`，鎖定後只有使用者能改。工單的 `TRACES_TO` 寫 B 編號；不做歪的檢查直接用現有的 `trace_report.py --decisions DIRECTOR/BRIEF.md`（找不到的編號、沒有工單的需求），沒有新工具。範例設定的 `trace_id_pattern` 加上 `B`。
- 選擇頁：新範本 `templates/choice_page.html`，從原專案的 PO 待決頁改成通用版：拿掉專案專屬的排程區，上方顯示初衷卡摘要（db `brief/current`），每個選項可附圖，附「總監建議」和理由，題目標出對到哪幾條 B。總監用 Artifact 工具發布、用 `ArtifactData` 開題和讀回覆。
- 新文件 `docs/12_chat_to_product.md`：模式、小白模式改了哪些步驟、談需求、選擇頁的欄位、不做歪的檢查。不列入每輪必讀。
- `selftest.py`：初衷 7 → 8 條；新增模式、初衷卡、選擇頁的檢查，和「用初衷卡範本跑 trace_report」的正反案例（1,724 → 1,744 項）。

遷移（已在用的專案，全部選做）：
1. 想用小白模式：在 `DIRECTOR/director_work.json` 加 `"mode": "beginner"`，照 `docs/12` 第二節改做法。
2. 想要初衷卡：照 `BOOTSTRAP` 第 14 步跟 PO 談、寫 `DIRECTOR/BRIEF.md`；之後新工單的 `TRACES_TO` 加 B 編號。用了 `trace_id_pattern` 的，把 `B` 加進去，不然 B 編號會列在「編號格式不符」。
3. 想要選擇頁：照 `docs/12` 第四節發布 `templates/choice_page.html`。已經有自己的待決頁的，可以繼續用。

對齊初衷：
1. 幫到誰：PO 和之後所有用 DW 的人，特別是不懂技術、只想說要做什麼的使用者。PO 在 2026-11-07 描述的流程（一直聊、確認後才做、A/B 給獨立的地方選、不違背一開始的目的）。
2. Desktop：總監在 Desktop Code 分頁的 session 做；選擇頁範本用 Artifact 工具實際發布成私人頁面、用 `ArtifactData` 寫一題範例再讀回來；selftest 在本機 Python 3.9、3.11、3.12 各跑一次，發布前看 GitHub CI。
3. 服務：新初衷 8；PO 不用盯細節（3）：要選的事集中在一頁、附建議；成品要真的對（5）：每張工單對回使用者確認過的初衷卡。零成本（7）：只用標準庫和 Artifact。
4. 核心：每輪必讀文件（docs/01、03、06、08）一個位元組都沒加；Direct 工作不多步驟；一般模式的 PO 多一件事（確認初衷卡），這是初衷 8 要的；小白模式的 PO 操作變少。
5. 舊檔案和舊指令：都照樣通過。沒有 BRIEF、沒有 `mode`、沒有選擇頁的專案照舊；`trace_report` 輸出不變。

## 1.3.3 — 2026-11-07

PATCH：追溯表顯示的證據要是現在的證據。外部審查（v1.3.2 優化報告的 P1）指出：`trace_report.py` 取同一工單最新的報告，卻沒有比對工單現在的 REVISION 和雜湊，工單改到第 2 版後，表內照樣顯示第 1 版報告的 PASS；另外工單 TRACES_TO 有幾個編號，每條 AC 就被乘幾次，看起來每個需求都被每條 AC 驗證過。`gate_check --match` 本來就會擋版次和雜湊不符，所以這是顯示問題，不是判定問題。

- 過期報告：選中的報告 `ORDER:` 行的 REVISION 比工單現在舊，狀態欄寫「過期：報告是 REVISION 1，工單現在是 REVISION 2（報告寫 PASS）」；比工單新寫「版次不符」；`ORDER_SHA256` 和工單現在的雜湊不同寫「過期：工單在報告之後改過」。表後新增一節「報告過期或版次不符」。沒寫這兩行的舊報告不判斷。
- 不再交叉配對：一列一條 AC。工單 AC 表可加選用的 `追溯` 欄（`gate_check.py` 認得 `追溯` / `traces`），每個編號一列，空的寫「（未指定）」，並列出 AC 追溯但 TRACES_TO 沒寫、和 TRACES_TO 寫了但沒有 AC 驗證的編號。沒有這欄、TRACES_TO 有兩個以上編號時，需求欄寫「DD-1、DD-2（工單層）」。`--decisions` 也查 AC 追溯的編號。
- 影子模式：只提示，不擋，exit code 不變；不新增必讀內容（docs/01、03、06、08 一個位元組都沒加）。說明在 `tools/README.md` 和 `templates/WORK_ORDER.md`。
- `selftest.py` 加上面各項的正反案例（1,715 → 1,724 項）；原本「選較高 REVISION 的報告」和「裁決配對」的測試，工單改成同樣是 REVISION 2，不然新規則會把報告標成版次不符。

對齊初衷：
1. 幫到誰：PO 和總監。看追溯表時，舊報告的 PASS 不會被當成現在的結果；一個需求被哪幾條 AC 驗證，看得出來，不再被交叉配對灌水。
2. Desktop：總監在 Desktop Code 分頁的 session 做；selftest 1,724/1,724 在本機 Python 3.9、3.11、3.12 各跑一次，發布前看 GitHub CI。
3. 服務：PO 不用盯細節（3）：表上的狀態就是現在的狀態。省額度（2）：不用為了確認是不是舊報告再去翻檔案。零成本（7）：只用標準庫。
4. 核心：每輪必讀文件不變；判定仍由 `gate_check --match` 做，追溯表只提示。Direct 不多步驟，工單不加必填欄。
5. 舊檔案和舊指令：都照樣通過。沒有 `追溯` 欄的工單照舊；TRACES_TO 只有一個編號時輸出和以前一樣；改變的只有過期報告的狀態欄文字和多編號工單的列數。

## 1.3.2 — 2026-11-07

PATCH：1.3.0 和 1.3.1 在 GitHub CI 的 Python 3.9 上 selftest 都沒過（3 項），當時發布前沒看 CI。

- 原因：`status_gen.py` 的 `audit.globs` 含 `*`，程式用 `Path.resolve()` 轉絕對路徑；runner 上的 Windows Python 3.9 遇到萬用字元，會丟 `WinError 123`。本機較新的 3.9.25 不會，所以本機三版都過。
- 修正：改用 `os.path.abspath(os.path.join(...))` 轉換，不碰檔案系統。
- 發布流程（docs/07 新增一節）：合併前先看 `gh pr checks`，CI 全綠才合併、才打 tag。本機三版通過不能取代 CI。

對齊初衷：
1. 幫到誰：PO 和所有使用 DW 的人。CI 綠的才是能用的版本，PO 不必再發現「發布沒過」。
2. Desktop：總監在 Desktop Code 分頁的 session 修；本機 py3.11 selftest，CI 跑 py3.9、py3.12。
3. 服務：PO 不用盯細節（3）：發布前看 CI 變成固定一步。零成本（7）：只用標準庫。
4. 核心：每輪必讀文件不變；`docs/07` 加一節發布前看 CI。
5. 舊檔案和舊指令：都照樣通過，沒有新選項。

## 1.3.1 — 2026-11-07

核准就執行：防護改成預設只提醒。PO 在對話裡同意的 push，被 1.3.0 的 hook_guard 照樣擋下，只能先拆 hook 才推得出去；裝了 hook 的工作線連該做的事都不敢做（L-045）。PO 說的是「不是讓你上保險，不是讓你什麼都不敢做」：防護是安全帶，不是剎車。版本號照總監工單定為 1.3.1；照本檔政策，新選項（`--guard-mode`、`--by-session`）本來算 MINOR，預設行為從擋改成提醒是放寬，舊設定不會變成不通過。

- `hook_guard.py --mode remind|ask|block`：
  - `remind`（預設）：標出的指令照跑（exit 0），stdout 一行 JSON：`systemMessage` 給使用者、`additionalContext` 給模型，註明「只是提醒；使用者已在對話裡核准就直接做、不要再問」。
  - `ask`：回 `permissionDecision: "ask"`，交給使用者當場決定。
  - `block`：明確 opt-in 的嚴格模式，exit 2，就是 1.3.0 以前的行為。
  - 暫停旗標是人明確設下的停止，每個模式都擋。機密規則（G50–G52：讀 `.env`、`~/.ssh`、`gh auth token` 等，類別 `secret`）的 deny 也是每個模式都擋（exit 2）：讀機密不在「PO 核准就執行」的範圍，1.3.0 也擋，不能退化（總監裁定）。自動暫停和 `--review` 只在 block 模式作用。動作紀錄的 `result.status` 多了 `remind`。
  - docstring 刪掉「PO 核准的 push 由 PO 自己執行，或先移除 hook」那句；正式路徑是使用者核准後 AI 直接執行，不必拆設定。
- 引號和 here-document 裡的字不算指令（L-044）。`cat <<'EOF' ... EOF`、`<<-`、不加引號的 `EOF` 的內容是資料；不加引號時內容裡的 `$(...)` 和反引號照樣會執行，照樣檢查；找不到結尾行的照原文檢查；`<<<` 和 `$((1<<2))` 不是 here-document。
- `setup_project_settings.py --guard-mode remind|ask|block`（設定檔 `guard_mode`）：預設 remind，指令不加 `--mode`；ask / block 在指令加 `--mode X`；沒給時沿用已裝項目的模式。規則權限跟著模式：block 照舊寫 `permissions.deny` / `ask`，ask 全部寫進 `permissions.ask`，remind 只寫機密規則（G50）的 `permissions.deny`（ask 模式的 G50 也留在 deny），其他規則權限從清單拿掉（不然 Claude Code 照樣擋），使用者自己加的不動。hook 測試依模式要得到 `2` / `ask` / `remind`。`templates/settings.runtime-guard.json` 改成 remind 的樣子（`permissions` 只有 G50 的 deny）。
- `doctor.py`：hook_guard 那行寫出模式；清單裡還留著這個模式不要的規則權限 → MISSING（那條照樣會擋）。
- `guard_rules.json` G02（push）、G10 / G11（刪除）、G20 / G21（對外發布、送出，含 `gh pr merge`）的理由改成「PO 在對話裡核准了就執行，沒核准才回報」；不再寫「由 PO 自己執行」或「改成回報」。
- `usage_mix.py`：
  - 原本 `shell_other` 拆成 `file_ops`（cat、sed、cp、mv、mkdir、rm、echo、Copy-Item 等）、`shell_search`（grep、rg、findstr、Select-String）、`build`（make、cmake、msbuild、dotnet、cargo、npm、gcc、pip 等）、`sys_query`（程序、版本、環境變數、網路）；git 原本就是 `git`。
  - python 執行（`python_other`）也認得 `py -3`、`pytest`、`uv run` 和直接跑 `.py`。
  - `build` 和 `python_other` 算實際動手，其他算讀和查。
  - 新的 `--patterns` 鍵：`python`、`build`、`shell_search`、`file_ops`、`sys_query`。
  - `--by-session`：每個 session 一行，列出佔比、呼叫數、等價量、五大類比例和花最多的五個細類。
- 文件：
  - README、`docs/04`、`docs/05` 加一節「防護是安全帶，不是剎車」：使用者核准就執行，已核准的事不重問，阻擋只留給明確 opt-in。
  - README 的防護表、`docs/08` 的 hook 那句、`tools/README.md` 改成依模式說明。
  - `docs/10` 加第 45–47 條（L-043 設定只從啟動資料夾讀、L-044 here-document 誤判、L-045 阻擋型防護卡住已核准的動作）。
- `selftest.py` 加上面各項的正反案例（1,648 → 1,714 項）。

對齊初衷：
1. 幫到誰：PO 和每條工作線。PO 核准的事 AI 直接做，PO 不用自己跑、不用拆設定、不用被重問；工作線不會因為裝了防護就不敢動手。總監看 `usage_mix --by-session`，就知道每條線的額度花在哪一種 shell 指令上。
2. Desktop：在 Desktop Code 分頁的 worker session 做，只用 DW 自己的 selftest 和合成的 hook 輸入實測；`usage_mix` 拆分前後對這台電腦 11 月的紀錄各跑一次。selftest 1,714/1,714，在 Python 3.9、3.11、3.12 各跑一次。沒有在真的 Claude Code session 裡觀察提醒的顯示方式（NOT_VERIFIED：remind 的 JSON 欄位照官方 hook 文件寫）。
3. 服務：PO 不用盯細節（3）：核准一次就做完，不再為同一件事被問兩次。省額度（2）：少掉重問、拆設定、重推的往返；`usage_mix` 看得到 shell 指令花在哪。零成本（7）：只用標準庫，沒有下載。
4. 核心：每輪必讀 `docs/08` 只改一句（仍在 `MUST_READ_LIMIT` 以內），規則本身不變：push、刪除、付費仍要 PO 核准，核准仍是一次一件。改的是防護不再把已核准的事擋下來。Direct 不多步驟。
5. 舊檔案和舊指令：都照樣通過。舊的 hook 項目沒有 `--mode`，複製新 `tools/` 之後就是提醒模式；要維持擋下見遷移第 2 步。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。之後舊的 hook 項目（沒有 `--mode`）就是提醒模式。
2. 重跑原本的 `setup_project_settings.py ... --apply`（不加 `--guard-mode` 就是 remind），把舊安裝留下的 `permissions.deny` / `ask` 規則權限拿掉；不重跑，doctor 會報 MISSING，那些規則照樣由 Claude Code 擋。真的要維持擋下（例如沒有人看的無人值守線），改成 `--guard-mode block --apply`。不要預設把 block 裝到工作線。
3. 在每個 session 的**啟動資料夾**重跑（L-043）；改完新開 session，跑 `doctor.py` 看 hook_guard 那行的 `mode`。

沒做：
- 沒有「這一次 PO 已核准」的單次放行旗標：remind 模式本來就照跑，ask 模式由使用者當場點頭，block 模式要換模式。

## 1.3.0 — 2026-11-07

用量結構：量出額度花在哪一類動作，對照門檻（讀和查 ≤ 30%、實際動手 ≥ 30%），並用實測回答「開新 session 划不划算」。另外把一週現場回報的 21 條教訓（L-022 到 L-042）做成工具和規則。全部是新工具、新選項和選用欄位，不加參數時舊行為不變，舊檔案照樣通過，照本檔政策是 MINOR。

- `usage_mix.py`：讀 `~/.claude/projects` 的對話紀錄（含 subagent），每次呼叫算額度等價量（輸入 1、快取寫入 1.25、快取讀取 0.1、輸出 5），平分給它選的工具呼叫，歸成五大類：讀和查、協調、看圖與審查、實際動手、等待。同一個 `message.id` 拆成幾行的先合併（L-035），分叉或續接的 session 重複的只算一次。`--check` 沒達到門檻 exit 1。RESTART 行列出新 session 的起步成本、依上下文大小的單價和損益兩平點。專案自己的字放 `--patterns` 檔，工具裡只有通用的字。
- `status_gen.py`：替每條工作線產生一支只讀、只用標準庫、最多 60 行的 `status.py`（log 尾段、雜湊、磁碟 GiB、git、最新輸出；L-042）。總監版（`templates/status_director.json`）再加待決頁計數、未結案工單、未送出訊息、最近 1 小時的動作紀錄和常駐程序。
- `round_check.py`：RESUME_STATE 的 `FIX_ROUNDS:`。從第 4 輪起，每做完一組 3 輪都要有根因研究，寫 `WHERE` / `ALTERNATIVES` / `DECISION`（L-032）。
- `gate_check.py --test-request`：TEST REQUEST 每個欄位都要填；單位要寫 GiB，不能寫 GB；擷取量和時長要對得上；寫入量要涵蓋 build、擷取和快取；時長不能超過上限（L-030、L-031、L-033）。`templates/TEST_REQUEST.md` 加 `BUILD_GB`、`CAPTURE`、`CACHE_GB`、`DURATION`。
- `poll_hint.py`：PostToolUse hook。同一個 session 10 分鐘內第 3 次讀同一份 log 時，提示「等完成通知」，只提示、不擋（L-041）。`report` 從動作紀錄算各 session 讀 log 的次數，給總監寫週報用。
- `hook_guard.py --sessions <檔>`：從同一個資料夾啟動的 session 共用一份 settings，所以改依 hook 輸入的 `session_id` 選 director / worker / cleaner。`protected` 列的路徑任何角色都不能刪或搬（L-023、L-026）。`setup_project_settings.py --session-map` 負責安裝。
- `doctor.py`：settings 只從啟動資料夾讀。doctor 依對話紀錄數出最近 30 天各 worktree 啟動過幾個 session，有防護卻沒人從那裡啟動，報 `settings unread`；從沒防護的 worktree 啟動，報 `WARN launch folder unguarded`。也檢查 sessions 檔的權限。
- `report_vs_audit.py`：用動作紀錄核對 TASK REPORT 說跑過的指令，包括 `RAN:` 行，以及 TESTS / EVIDENCE / DONE 裡的 selftest、Unity、Blender、雜湊檢查：有沒有跑、exit 對不對、時間對不對。紀錄的雜湊鏈斷了算 FAIL。`templates/TASK_REPORT.md` 加選用的 `SESSION_ID:` 和 `RAN:`。
- 文件：
  - `docs/04` 加「用量結構」一節，含門檻、量法和這一週的比例，以及「開新 session 划不划算」實測表。實測結論：重開的起步成本從來回收不了，所以撤回「過 gate 就換新 session」，改成「不為了縮上下文換新 session，交給壓縮」（L-036）。`docs/01`、`docs/11`、README、`templates/CLAUDE_PROJECT_SECTION.md` 一起改。
  - `docs/02`、`docs/07`、`docs/06b` 補上：同一輪等 GO（L-029）、用事件條件代替固定時間（L-024）、run script 不設預設設定（L-025）、修正輪數成組計算、狀態腳本、session 對照表和啟動資料夾。
  - `docs/10` 加第 24–44 條。第 3、18 條註明「換新 session」已撤回。
  - `tools/README.md` 補上新工具。
- `selftest.py` 加上面各項的正反案例（1,480 → 1,648 項）。

對齊初衷：
1. 幫到誰：總監和 PO。總監要知道額度是不是花在實際動手上，也要知道 worker 報告說跑過的指令是不是真的跑過；PO 不用自己看 log 就能知道每條線的狀態。21 條教訓都來自一週的現場回報。
2. Desktop：在 Desktop Code 分頁的 worker session 做，只用 DW 自己的小工單和 selftest 實測。`usage_mix` 對這台電腦一週的紀錄跑過；`status_gen` 產生的 DW 版 `status.py` 跑出 16 行。總監版用的是範本裡的佔位路徑，真實路徑要總監填。`report_vs_audit` 和 `poll_hint report` 只用合成的動作紀錄測過。selftest 1,648/1,648，在 Python 3.9、3.11、3.12 各跑一次。
3. 服務：省額度（2）：先量出花在哪，再談怎麼省；撤回一條實測後證明更貴的規則。PO 不用盯細節（3）：`status.py` 一頁看完一條線；`report_vs_audit` 替總監核對報告。成品要真的對（5）：報告說跑過，就要在動作紀錄裡找得到。零成本（7）：只用標準庫，沒有下載。
4. 核心：每輪必讀從 12,392 降到 12,333 bytes。`docs/01` 的規則改了一句：「上下文長了交給壓縮」取代「過 gate 換新 session」。核心 3「上下文要短」仍然靠壓縮門檻做到；實測顯示，換新 session 起步就要讀回大約 100K，比留著原 session 繼續做更貴。Direct 不多步驟，新工具都是選用的。
5. 舊檔案和舊指令：都照樣通過。新欄位（`FIX_ROUNDS`、TEST REQUEST 的四個欄位、`SESSION_ID`、`RAN`）只有用到對應的新工具或新選項時才檢查。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。
2. 要用 session 對照表時，從 `templates/guard_sessions.json` 複製一份，填入 `session_id`，再重跑 `setup_project_settings.py --hooks --rules --session-map <檔> --apply`。hook 輸入只有 `session_id`，沒有 session 名稱。
3. 要用 `poll_hint` 時，在專案的 `.claude/settings.local.json` 加 PostToolUse hook（`tools/README.md`）。
4. 總監版 `status.py`：從 `templates/status_director.json` 複製一份，把路徑改成專案自己的，再跑 `status_gen.py --config`。
5. 原本照「過 gate 換新 session」做的工作線，改成留在原 session，交給自動壓縮。

沒做：
- `report_vs_audit` 和 `poll_hint report` 沒有拿現場的動作紀錄跑過，只用合成紀錄測過。
- hook 輸入沒有 session 名稱，`--sessions` 只能依 `session_id` 判斷。
- L-023（刪除前的檢查）寫在 `docs/06b`，沒有寫進每輪必讀的 `docs/08`，以免必讀檔變大。
- `usage_mix` 讀的對話紀錄格式不是官方介面，改版後可能讀不到；讀不到時印 UNKNOWN。

## 1.2.0 — 2026-11-07

容器 worker 的三個已知缺口補上：每個 worker 有自己的 clone，碰不到原 repo 的 ref（K1）；容器裡只解析白名單名稱（DNS）；同一個 repo 開幾個容器 worker，動作紀錄都各寫各的（K6）。舊的 `--git-common` 保留一版，只印 WARN、doctor 報 NOT_ENFORCED，舊指令照樣能跑，照本檔政策是 MINOR。

- `tools/container/worker_clone.sh`（K1）：
  - `create --repo --base --branch --dir`：做一份完整的 clone（`--no-local`，沒有 hardlink 和 alternates），只留一條分支，沒有 remote 和 tag，`.git/config` 重寫、`.git/hooks` 清空，裡面沒有任何東西指回原 repo。`--dir` 必填、沒有預設，而且不能已經存在；建議放 WSL 的 ext4。
  - `collect --repo --branch --dir --name`：在離線、沒有 capability、clone 唯讀掛載的拋棄式容器裡打包那一條分支，再交給 `import`。
  - `import`：bundle 要剛好一個 ref `refs/heads/<分支>`，過 `git bundle verify`，objects 先在隔離 repo 過 `index-pack --strict` 和 `fsck --strict`，tip 要是 commit，才複製進原 repo 並設 `refs/dw-workers/<名稱>/<分支>`。原 repo 的其他 ref 一律不動。
  - worker 不能 push，由總監 `collect`。
- `run_worker.sh --clone <資料夾> --name <名稱>`：`/work` 是 worker 自己的 clone，`.git/config` 和 `.git/hooks` 另外唯讀蓋上，原 repo 不掛進容器。`--git-common` 印 `WARN K1`，2.0 拿掉。容器多設 `DW_WORKER_NAME` 和 `DW_GIT_MODE`（`clone` / `shared`）。
- 容器 DNS：`tools/container/dns_allow.py`（只用標準庫）以使用者 `dwdns` 在容器裡跑，沒有 capability。它只回答白名單名稱的 A / AAAA：其他名稱回 NXDOMAIN，其他型別回 REFUSED，送上游的查詢重新組過（新的隨機 ID、名稱轉小寫）。
  - 防火牆只讓 `dwdns` 連 `DW_DNS_UPSTREAM` 的 53；`127.0.0.1` 的 53 轉到它，其他位址的 53 一律拒絕。沒有關閉開關。
  - 名稱清單是 `--allow-file`（預設 `tools/container/dns_allow.txt`，只有 `api.anthropic.com`），加上 `--login`、`--allow`。`*.` 開頭的名稱只解析、不開 443。不合法的名稱或空清單 exit 2。
  - 上游是 `DW_DNS_UPSTREAM`，沒設就用主機 `/etc/resolv.conf` 裡不是 `127.x` 的 IPv4。
- 動作紀錄（K6）：`audit_log.py` 的路徑可寫 `{worktree}` 和 `{container}`。`{worktree}` 取 `DW_WORKER_NAME`，`{container}` 在 hook 執行時換成容器 ID 前 12 碼（容器外是 `host`），其他 `{名稱}` 一律報錯。`setup_project_settings.py --runtime-guard` 的預設改成 `<git common dir>/director-audit/{worktree}-{container}.jsonl`，每份各自一條鏈。
- `doctor.py`：
  - `--probe` 在容器裡查六項，多了 `example.com` 解析不到（DNS 白名單）和 `.git` 是 worker 自己的（K1）。
  - `DW_GIT_MODE=shared` 或 linked worktree 在容器裡，不加 `--probe` 也報 isolation NOT_ENFORCED（K1 shared .git）。
  - `worker_clone.sh` 做的 clone，`worktree` 一項報 ENFORCED（the worker's own clone）。
- README 的安全表加上 K1 和 DNS 兩列，缺口表改寫；`tools/README.md` 的 container 一節改成 clone 的流程，補上 1.2.0 實測和 K2 速度數字；`docs/11` 的容器 worker 開法改成 `create`、`--clone`、`collect`。
- `selftest.py` 加上面各項的正反案例（1,344 → 1,480 項），其中惡意 bundle 12 種都拒收，拒收後原 repo 的 ref 和 objects 都不變。

對齊初衷：
1. 幫到誰：總監。1.1.0 容器 worker 的三個缺口是總監的對抗測試找到的：worker 能改別的分支和 tag、能把資料藏在 DNS 查詢裡送出、兩個 worker 的紀錄寫進同一份。每個缺口都先在拋棄式 clone 上重現，再修，再用容器實測。
2. Desktop：在 Desktop Code 分頁的 worker session 做，全部在 WSL docker 的拋棄式 clone 上實測，沒掛真正的 repo。結果：K1 9/9、DNS 20/20、doctor 8/8；selftest 1,480/1,480，在 Python 3.9、3.11、3.12 各跑一次。容器登入（C6）、真實工單（C7）和登入後的 doctor（C8b）還沒做，要等 PO 登入。
3. 服務：PO 不用盯細節（3）：worker 弄壞的只會是它自己的 clone，總監只收一條分支。成品要真的對（5）：doctor 照實報，`--git-common` 報 NOT_ENFORCED。零成本（7）：只用標準庫和已有的 docker image，沒有下載。
4. 核心：每輪必讀不變；Direct 不多步驟。容器 worker 多兩個指令（`create` 和 `collect`），由總監執行，PO 不多操作。
5. 舊檔案和舊指令：`--git-common` 照樣能跑，多印一行 WARN，doctor 從 ENFORCED 變成 NOT_ENFORCED（設計如此）。1.1.0 裝的 `{worktree}.jsonl` 照舊能用。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`，在 WSL 裡 `docker build -t dw-worker:1.2.0 tools/container`。
2. 容器 worker 改用 `worker_clone.sh create` → `run_worker.sh --clone` → `worker_clone.sh collect`（`tools/README.md` 的 container 一節）。驗收用 `git rev-parse refs/dw-workers/<名稱>/<分支>` 取候選 commit。
3. 動作紀錄要換成新檔名：重跑 `setup_project_settings.py --runtime-guard ... --apply`。舊檔留著不動。
4. 主機 `/etc/resolv.conf` 只有 `127.x` 時（例如 systemd-resolved），開容器前設 `DW_DNS_UPSTREAM`，否則 `run_worker.sh` exit 2。

沒做：
- 容器登入（C6）、真實工單試跑（C7）、登入後在容器裡跑 doctor（C8b）：要 PO 用 account B 登入。
- DNS 剩下的路：白名單名稱的查詢仍會到上游（看得到名稱、型別、時間）；查詢時間點可當很慢的隱密通道；443 的 IP 只在開容器時解析一次。
- `--git-common` 這版沒拿掉（2.0 拿掉）；`--dns-open` 之類的關閉開關不做，要另提案。
- 1.1.0「沒做」裡的 DNS、K1、K6 三項這版做了；那段是當時的紀錄，不改。

## 1.1.0 — 2026-11-07

執行期防護：worker 的每個工具呼叫先過規則檔，危險動作擋下或等人點頭，機密不讀、輸出遮罩，每個動作記進可驗證的紀錄，可以一鍵暫停；`doctor.py` 照實報哪些真的生效。另提供在 WSL docker 容器裡跑 worker 的腳本。全部是新工具和選項，不加參數時舊行為不變，照本檔政策是 MINOR。這是防手滑，不是安全邊界（README「執行期防護」一節）。

- `hook_guard.py --rules tools/guard_rules.json --profile worker|director`：每個工具呼叫比對規則檔（shell 的 argv，含 wrapper 和 `bash -c` / `cmd /c` / `powershell -c`；Write / Edit 的路徑 glob；MCP 的動作字，get/list/read/search/query/status 一律不擋）。deny 是 exit 2，ask 回 PreToolUse 的 ask JSON；取最嚴的結果，同級取最小 ID，規則順序不影響結果。規則檔壞了 exit 1。內建 G00 保護規則檔和 `hook_guard.py` 本身（含 Bash / PowerShell 的寫入、`sed -i`、重導向）。`setup_project_settings.py --guard-profile` 裝 matcher `*` 的 hook，並把規則寫進 `permissions.deny` / `permissions.ask`。
- 規則：G02 擋 `git send-pack`、`http-push`、`git-*` 執行檔和設定 alias（`-c alias.*=`、`--config-env=alias.*`、`git config alias.*`）；G40 擋 Write / Edit 和 shell 寫入（`sed -i`、`tee`、`cp` 目的地、`Set-Content`、`>`、`[IO.File]::Write*`）設定檔、憑證、CLAUDE.md、`.mcp.json`；重導向目標從原始指令行讀，`{}>` 這類寫法藏不住。
- 機密：G50 擋讀憑證檔（Read / Grep / Glob 和讀檔指令，含 Windows 的 `%APPDATA%/GitHub CLI/hosts.yml`），G51 擋印出環境變數或機密變數，G52 擋印 token 的指令。`secret_mask.py` 把 key、token、JWT、bearer、URL 密碼和機密賦值遮成 `[MASKED:種類]`，`--check` 只列種類。
- 暫停：`pause_ctl.py on|off|status` 寫或刪 `DIRECTOR/PAUSE`，記 `PAUSE` 行進 `DIRECTOR_LOG.md`；`procs` 依 CPU 變化列出程序樹裡還在跑的 PID，從不結束程序。`hook_guard --pause-flag` 暫停時只放行規則檔 `pause` 段列的讀取和回報動作；allowlist 裡的 shell 行有輸出重導向就不放行。worker 600 秒內 5 次 deny 自動暫停（總監不開），`pause_ctl.py off` 解除。
- 動作紀錄：`audit_log.py` 當 PostToolUse / PostToolUseFailure hook，每個工具呼叫寫一行 JSONL（輸入遮罩後取 500 字，輸出只記 sha256 和長度），前後雜湊串成鏈；`verify` 找第一個斷點，可用 `DIRECTOR_LOG.md` 已 commit 的錨點比對；`head` 印 `AUDIT_HEAD`，`cite` 印給 TASK_REPORT 的 `AUDIT_RANGE`。`hook_guard --audit` 另記 deny / ask / 暫停的決定。
- `hook_guard --review`（預設關）：規則分類是 push、delete、send、config 的 ask，先給 `claude -p`（無工具、無 hook）看遮罩後的輸入；只有回 block 才把 ask 改成 deny，其他回答、逾時、錯誤一律維持 ask。只會多擋。
- `doctor.py`：實際生效的 claude 版本和 PATH 上每一個 claude、合併後的設定層、實跑一次 hook_guard、`audit_log verify`、permissions、子程序環境清洗、隔離（`--probe` 查四項，只印憑證類變數的名稱）、worktree。每項標 ENFORCED / CONFIGURED_NOT_VERIFIED / NOT_ENFORCED / MISSING。
- `setup_project_settings.py --runtime-guard`：一次寫入 worker profile、`--pause-flag`、動作紀錄（預設放 git common dir 下）和 `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`；`templates/settings.runtime-guard.json` 是同一組的範本，selftest 檢查兩者相同。hook 實測不帶 `--pause-flag`、`--audit`、`--review`，測試的 deny 不會算進真 worker 的自動暫停。
- `tools/container/`：Dockerfile（base 以 digest 鎖定、Claude Code 鎖版本、不自動更新）、entrypoint（以 root 設防火牆後 `setpriv` 成 `dw`，丟掉所有 capability、no_new_privs）、`init_firewall.sh`（只放行 `DW_ALLOW_DOMAINS` 名稱的 443，啟動時解析；IPv6 全擋）、`run_worker.sh`（worktree 可寫、DIRECTOR 唯讀、`.git` 的 `hooks/`、`config`、`worktrees/` 唯讀，不設 GIT_DIR，`gc.auto=0`）。
- README 新增「執行期防護：哪些真的擋、哪些只是提醒」一節；`docs/10` 加第 23 條（只印環境變數名稱，不印值）；`docs/11` 補容器 worker 的開法。
- `selftest.py` 加上面各項的正反案例（524 → 1,326 項）。
- 修正：Python 3.9 相容。`Path.write_text(newline=)` 要 3.10，3.9 的自動暫停會崩潰；四處改用 `open(..., newline="\n")`，selftest 靜態掃 `tools/*.py` 不得再出現。

對齊初衷：
1. 幫到誰：worker 在 bypass 模式下能做的事太多，PO 看不到它做了什麼。批次 1 交付後總監的對抗測試找到的繞路（git alias、send-pack、shell 寫規則檔、Windows 的 gh hosts.yml、暫停中的重導向、`{}>`）先重現才修，修完重跑。
2. Desktop：在 Desktop Code 分頁的 worker session 實作，Python 3.11 跑 selftest 1,326/1,326。容器在 WSL docker 的拋棄式 clone 上實測：繞路探測 35/35 擋下，容器裡 selftest 1,304/1,304（Windows 專屬案例 SKIP），doctor 在 linked worktree 報 enforced=5、not_enforced=0。`--review` 只用假的 claude 測過、Monitor 沒有實際取樣，兩項 NOT_VERIFIED；容器登入（C6）和真實工單（C7）還沒做。
3. 服務：PO 不用盯細節（3）：危險動作擋下或等人點頭，事後有可驗證的紀錄。成品要真的對（5）：doctor 照實報，沒生效的不說生效。零成本（7）：只用標準函式庫；容器只用免費的 docker 和公開 image。
4. 核心：每輪必讀不變。Direct 不多步驟：全部是選用參數。PO 不多操作：容器第一次 `/login` 要 PO 做一次。
5. 舊檔案和舊指令：不加新參數時輸出不變，已通過的不會變不通過。裝了 `--runtime-guard` 的 worker 會被擋下以前放行的動作（設計如此）。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。
2. 要用執行期防護：`setup_project_settings.py --runtime-guard --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply`，再在 worker 資料夾跑 `tools/doctor.py`。原生 Windows 上隔離一項永遠是 NOT_ENFORCED，所以 doctor 一定 exit 1。
3. 要在容器裡跑 worker：照 `tools/README.md` 的 container 一節在 WSL 裡 build 和開；同一個 repo 一次只開一個容器 worker（K6）。

沒做：
- 容器登入（C6，要 PO 用 account B 做第一次 `/login`）和真實工單試跑（C7）。
- `--review` 和 Monitor 的指令沒有實際取樣，NOT_VERIFIED。
- WSL2 sandbox 範本拿掉（要另裝 bubblewrap 和 socat 才能實測）；依使用者決定不啟用 `blockWritesOutsideWorkingDirectories`、不縮小 gh token scope。
- 容器的 DNS 對 resolver 放行，資料能藏在 DNS 查詢送出；這版沒有白名單 resolver。
- 容器裡 `.git` 除了 `hooks/`、`config`、`worktrees/` 都可寫（K1）：worker 能動別的 branch 的 ref 和 tag，總監用 `git rev-parse` 取候選。容器裡不能 `git worktree add`，有別的 worktree 時 `git gc` exit 128。
- 容器的動作紀錄一律叫 `work.jsonl`，同 repo 兩個容器 worker 會撞（K6）。
- 0.12.0「沒做」裡的 `doctor` 指令這版做了；那段是當時的紀錄，不改。

## 1.0.0 — 2026-11-06

正式版。程式、規則和遷移步驟都與 1.0.0-rc.1 相同，只改版號（`VERSION`）。Owner 2026-11-06 確認發布。從 0.12.x 升級照下方 1.0.0-rc.1 段的「遷移」做。

對齊初衷：沒有新的規則或工具，初衷和核心的對照與 1.0.0-rc.1 段相同。

## 1.0.0-rc.1 — 2026-11-06

把 Strict 的證據鏈綁在一個候選 commit 上，讓重跑只執行總監核准的檢查，並讓工單版次和 Git 狀態對得上。另外把每輪必讀文件縮小 1,025 bytes。

版本：已經通過的 Strict 審查和舊指令會變成不通過（「對齊初衷」第 5 題、遷移），照本檔政策是 MAJOR。Owner 2026-11-06 定為 1.0.0-rc.1；打 tag 和發布由總監獨立重跑後再做。原本寫成 0.13.0 的段落沒有發行過，併進這一段。

- `evidence_record.py verify --rerun` 改成跑工單 `CHECKS:` 裡核准的指令（JSON 字串陣列，不經 shell，工單雜湊包含它，所以派工時的 `DISPATCH` 行已鎖住）。要給 `--order`、`--dispatch-log`、`--repo`、`--candidate`，少一個就 `NOT_RUN`、exit 2。工單雜湊和版次要等於最新的 `DISPATCH` 行，repo 的 HEAD 要等於候選 commit 而且工作樹乾淨。紀錄的指令不同、或不是在候選 commit 記的，都是 `MISMATCH`。舊行為改名 `--rerun-recorded`，結論寫 `test=recorded-command-passed source=record`，絕不印 `test=passed`。
- `evidence_record.py`：欄位型別不對（例如 `artifacts=42`、`command=[1]`）印 `NOT_RUN not an evidence record`、exit 2，不再丟 traceback（`gate_check.py` 也一樣）。
- `gate_check.py --order` 查 `CHECKS:` 格式；Strict 工單有 AUTO 條件卻沒有 CHECKS 只提示。`--match --evidence-dir` 時紀錄的指令要和核准的指令相同（Strict 失敗、Standard 提示）。
- `gate_check.py --match` 新增 `--candidate <40 位>`。Strict 工單少了 `--dispatch-log`、`--candidate`、有 AUTO 列填 PASS 卻沒給 `--evidence-dir`、報告 HEAD 不是完整 40 位、證據是舊紀錄或沒有 git HEAD、紀錄或報告的 HEAD 不等於候選 commit，都失敗。Standard 和 Direct 給了 `--candidate` 才比對。
- 版次：`DISPATCH` 的 `rev=` 要等於工單的 REVISION；報告 `ORDER:` 行的 REVISION 要等於工單（沒寫：Strict 失敗、Standard 提示）。`templates/GATE_VERDICT.md` 加 `ORDER:` 和 `CANDIDATE_HEAD:` 兩行。`trace_report.py` 的裁決欄只放和選中報告同版次的裁決，對不到版次或 HEAD 的列在「裁決對不到報告版次」。
- `trace_report.py --decisions 檔案`（選用，可重複）：列出 TRACES_TO 寫了卻不在需求或決定檔裡的編號，以及沒有任何工單追溯的需求。
- `scope_check.py` 看四種 Git 狀態的聯集：已 commit、已暫存、未暫存、沒被忽略的新檔。已 commit 或已暫存、之後在工作樹改回原樣的修改也看得到。結論行上面多一行 `STATES: committed=n staged=n unstaged=n untracked=n`；結論行格式不變。
- 工單可加選用的 `REQUIRED_CHANGES:` 清單：`scope_check.py` 對每條沒對到改動的 glob 印 `MISSING`、判越界，結論行多 ` missing=n`（沒有這個清單，輸出和以前一樣）。`gate_check.py --order` 查每條都在 SCOPE 裡、不在 FORBIDDEN 裡。
- 每輪必讀文件 13,417 → 12,392 bytes（LF，−1,025），分兩件事：
  - 搬理由：docs/01、03、06、08「為什麼」段裡純理由的 8 條，原文逐字搬到 `docs/10` 的「每輪必讀規則的理由」。有規範句的條目留在原處，每份留一行 `- 其他理由見 docs/10。`。
  - 欄位引用範本：docs/06 的 RESUME_STATE 欄位清單改成「照 `templates/RESUME_STATE.md` 逐欄寫齊」（範本已逐欄列出）。IN_FLIGHT 的最小欄位（背景程序的 PID、啟動時間、輸出檔、完成判定，以及計時器和等待程序）仍寫在 docs/06 本身。
  - 「## 規則」段其他部分逐位元組不變。`MUST_READ_LIMIT` 降到 12,392。
- `docs/11`：Strict 工單的規格審查（`SPEC_REVIEW`）在放上 PO 待決頁之前做完；PO 說「開」的那一輪只寫 `DISPATCH` 行和開 worker。`docs/02`、`templates/SPEC_REVIEW.md` 同步。
- `setup_project_settings.py --hooks --protect-director <DIRECTOR> [--director-worktree <總監的 worktree>]`（或 config 的 `protect_director`、`director_worktree`）：worker 的 hook matcher 改成 `Bash|PowerShell|Write|Edit`，`hook_guard.py --protect` 擋 Write / Edit 改 `orders/` 和 `DIRECTOR_LOG.md`（處理相對路徑、大小寫、`..`、junction、8.3 短檔名）。總監自己的 worktree 維持舊項目。舊的 hook_guard 項目在 `--apply` 時就地換掉，不重複追加。不加 `--protect-director` 和 v0.12 完全相同。這只是防手誤，不是安全隔離（限制見 `docs/11`、`tools/README.md`）。
- Codex 對抗式審查後的修正：
  - `DISPATCH` 只認整行的固定格式（前面可加 `<日期> |`，後面可加 `| <依據>`）。引文、縮排、`>` 開頭和 code fence 裡的都是資料，不算派工（R01、R01b）。`gate_check.py` 和 `evidence_record.py --rerun` 共用同一個 parser。給了 `--dispatch-log` 卻找不到這張工單的 DISPATCH 行，各治理模式都失敗。
  - 工單身分：標題 ID 和檔名 ID 要一致；工單改了 GOVERNANCE 或 ID，雜湊就對不上派工紀錄，不能自己降級（G01）。報告的 `ORDER:` 行要指這張工單（G02）；HEAD、ORDER、ORDER_SHA256、RESULT 各只能寫一次（G02b）。
  - 裁決綁工單和 commit：`--verdict` 搭 `--match` / `--candidate` 時，裁決的 `ORDER:` 行要指到比對的工單和版次，`CANDIDATE_HEAD:` 要等於候選 commit（G04）。`trace_report.py` 不顯示 CANDIDATE_HEAD 和報告 HEAD 不同的裁決，沒有可配的就寫「未配對」（G04b）。
  - 證據：Strict 只收本版讀得懂的 schema（Standard 提示），`git.dirty` 必須是 false（G03、G03a）。紀錄列出的產物重新算雜湊（相對路徑以紀錄的 cwd 為準；沒有 cwd 的舊紀錄只提示），不見或變了：Strict 失敗、Standard 提示（G03c）。
  - `verify --rerun` 由審查端自己物化候選：git 一律關掉 replace objects；有 `refs/replace/`、assume-unchanged 或 skip-worktree 的檔案就拒跑；從 git 物件把候選的 tree 寫進新的暫存資料夾（逐個 blob 驗雜湊），在那裡跑核准的檢查、算產物雜湊；跑完再讀一次 repo（HEAD、tree、狀態、標記）。核准指令的程式要是絕對路徑、候選裡的路徑或 `python`，不讓 PATH 決定（R02–R06）。
  - `scope_check.py`：三段 diff 分開取（base..HEAD、HEAD..index、index..worktree），已暫存或已 commit 的改名不再重複算成未暫存（S01）。一律 `--ignore-submodules=none`，設定擋不掉 FORBIDDEN 的 submodule（S04）。assume-unchanged / skip-worktree 的檔案拿去和 index 比雜湊，不同就算未暫存，另印一行 `FLAGGED:`（S03）。清單項目用反引號包起來就照字面讀，檔名裡的 ` #` 不會被切掉；`gate_check.py --order` 會提示沒包反引號、` #` 後面緊接著字而被切掉的項目（S02）。
  - `hook_guard.py --protect`（Windows）：去掉磁碟或 UNC 路徑的 `\\?\`、`\\.\` 前綴，NTFS 資料流算檔案本身，其他裝置路徑（GLOBALROOT、volume GUID）一律擋（H01、H02）。目標或它的上層資料夾已存在時，再用檔案識別（磁碟序號＋檔案編號）和 `DIRECTOR_LOG.md`、`orders/` 底下每個項目比對，UNC 別名和既有檔案的 hardlink 也擋得到。
  - `setup_project_settings.py`：已裝的 hook_guard 指令和這份工具要寫的不是逐字相同，就是 `MISSING (hooks.PreToolUse command)`，`--apply` 換掉。項目到位後實際跑一次 hook（一筆要放行、一筆要擋，有 `--protect` 時再加一筆寫進 `orders/` 的 Write），答得不對是 `HOOK_FAIL`、exit 1（H04）。
  - `gate_check.py --preflight 報告 工單`（只讀）：舊版本做的審查要照現在的 Strict 重審前，一項一行 `LACKS` 列出缺什麼，並給補法（M01–M03，見遷移第 7 步）。
  - 證據綁工單（G03b）：`evidence_record.py run --order 工單` 把工單 ID、REVISION 和雜湊寫進紀錄的 `order` 欄；雜湊就是 `gate_check.py --hash` 印給 DISPATCH 行的那一個（同一個函式、同樣讀工單檔的位元組）。`--match --evidence-dir` 時，有綁的紀錄要和工單現在的 ID、版次、雜湊相同，或 `--dispatch-log` 有總監寫的整行 `EVIDENCE_EQUIVALENT <WO-ID> rev=<舊> sha=<舊雜湊> to rev=<新>`（和 DISPATCH 用同一套整行規則：引文、縮排、code fence、寫在 NOTE 句子裡的都不算）。沒綁的紀錄：REVISION 1 照收，印 `WARN evidence not bound to the order`；REVISION 2 以上 Strict 失敗、Standard 提示。`--preflight` 對 REVISION 2 以上沒綁的紀錄印 `LACKS`。`evidence_record.py verify --rerun` 也用同一套規則（同一個 `check_binding`）比對紀錄的 `order` 欄：Strict 工單綁錯工單、綁舊版次又沒有 EVIDENCE_EQUIVALENT 行、或 REVISION 2 以上沒綁，結論是 `MISMATCH`、exit 1；Standard 印 `~` 提示。
- `selftest.py` 加上面各項的正反案例（285 → 524 項）。

對齊初衷：
1. 幫到誰：外部稽核（Codex）和 SDD 報告指出的漏洞，先在暫存 fixture 逐項重現才修：Strict 少給旗標只出提示、`--rerun` 會執行紀錄裡被竄改的指令、`artifacts=42` 丟 traceback、DISPATCH 版次不同照收、已暫存後改回的 FORBIDDEN 修改看不到、裁決配到別版的報告。重現腳本修正前 A01–A11 是 exit 0 或 traceback，修正後是 1 或 2。第二輪 Codex 對抗式審查找到的繞道（改 GOVERNANCE 自己降級、引文裡的 DISPATCH 被當授權、別的 commit 的 PASS 裁決、用 replace refs 或 assume-unchanged 騙過重跑、用裝置路徑繞過 hook）也先用審查附的重現腳本重現，修完再跑一次。
2. Desktop：在 Desktop Code 分頁的 worker session 實作，Python 3.11 跑 selftest 全過。junction 和 8.3 短檔名案在 Windows 實跑，沒有 SKIP；一般帳號沒有建立 symlink 的權限（WinError 1314），symlink 沒測。`--protect-director` 還沒在真實 worker 資料夾裝過；`CHECKS` 和 `--candidate` 還沒在真實工單上跑過，都是 NOT_VERIFIED。
3. 服務：成品要真的對（5）：重跑只跑總監核准的檢查，證據、報告、裁決指向同一個 commit。PO 不用盯細節（3）：工具查得出版次和 Git 狀態不一致。零成本（7）：只用標準函式庫。
4. 核心：每輪必讀變小（13,417 → 12,392 bytes），規則沒有刪，理由搬到 `docs/10`。Direct 不多步驟。PO 不多操作：新參數都是總監下的。
5. 舊檔案和舊指令：可能新不通過的有四種。Strict 審查少了 `--candidate`、`--dispatch-log` 或 `--evidence-dir`；單獨寫 `verify --rerun` 沒給 `--order`（exit 2）；`scope_check.py` 看到以前漏掉的已暫存或已 commit 修改（當 bug 修，Standard 也會報）；DISPATCH 或報告的版次和工單不同。審查修正後再加四種：LOG 裡引用、縮排或放在 code fence 的 DISPATCH 不再算派工；報告 header 欄位重複；Strict 證據的 `git.dirty` 沒寫或 schema 不認得；候選裡有 assume-unchanged / skip-worktree 檔案或 `refs/replace/` 時重跑拒跑；REVISION 2 以上的 Strict 工單，證據沒用 `--order` 綁版次（G03b）。沒有 `CHECKS` 和 `REQUIRED_CHANGES` 的舊工單，`--order` 結果不變。這些照本檔政策是 MAJOR；0.x 升 MAJOR 等於 1.0，Owner 定為 1.0.0-rc.1。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。
2. Strict 的審查指令補上三個參數：`gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md --evidence-dir 證據資料夾 --candidate <git rev-parse worker 分支>`。少一個就失敗。
3. `CHECKS:` 在 v0.13 只是建議：Strict 工單有 AUTO 條件卻沒寫，只印提示。v0.14 起會變成必要，現在就開始在工單 E 節寫。
4. `evidence_record.py verify --rerun` 改成執行工單核定的檢查：`verify 紀錄 --rerun --order 工單 --dispatch-log DIRECTOR_LOG.md --repo <候選 commit 的乾淨 worktree> --candidate <40 位>`。舊行為（跑紀錄裡寫的指令）改名 `--rerun-recorded`，不算重跑驗證。重跑會執行候選 commit 的測試碼，在 `git worktree add --detach` 開的乾淨目錄跑。
5. 報告的 `ORDER:` 行寫 REVISION；裁決加 `ORDER:` 和 `CANDIDATE_HEAD:` 兩行（`templates/GATE_VERDICT.md`）。
6. 要擋 worker 改工單：重跑 `setup_project_settings.py --hooks --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply`，舊的 hook 項目會被換掉，裝好後印出 hook 實測結果。
7. 舊版本做的審查要照新 Strict 重審，先跑 `gate_check.py --preflight 報告 工單 --evidence-dir 證據資料夾 --dispatch-log DIRECTOR_LOG.md --repo <受信任的 checkout>`，照每行 `LACKS` 補：
   - 報告 HEAD 不是完整 40 位（M01）：在受信任的 checkout 用 `git rev-parse <短碼>` 解出完整 commit（給 `--repo` 時 preflight 直接印出），寫進新報告，舊報告留著當紀錄。解不出唯一的 commit，就請 worker 重交。
   - 只用 `--match` 比對格式不需要 `CHECKS`，舊工單照樣相容（M02）。要用核准重跑（`verify --rerun`），總監要先寫 `CHECKS:`、升 REVISION、記新的 DISPATCH 行，worker 在新版次重新收證。
   - 證據紀錄沒有 `schema`、`git.head` 不是 40 位或 `git.dirty` 不是 false（M03）：在候選 commit 用這版 `evidence_record.py` 重新收證（或 `verify --rerun`）。已結案的審查保留原檔不動。
8. `DIRECTOR_LOG.md` 的 DISPATCH 行頂格寫成一整行（`gate_check.py --hash` 印的那行）；引用、縮排、放進 code fence 的不算派工。報告和裁決的 header 欄位各寫一次。
9. 證據綁工單（G03b）：worker 收證一律加 `--order`。REVISION 2 以上的 Strict 工單，沒綁的舊證據要在候選 commit 重新收，例如：
   `python -I -X utf8 DIRECTOR/tools/evidence_record.py run --out-dir <證據資料夾> --label AC-1 --order DIRECTOR/orders/WO-001-parser.md -- python -I -m unittest tests.test_parser`
   舊版次的證據確定仍然有效時，總監改在 `DIRECTOR_LOG.md` 頂格寫一整行 `EVIDENCE_EQUIVALENT WO-001 rev=1 sha=<紀錄 order 欄的 sha> to rev=2`，不必重收。
   Codex 重現腳本的 M-C05（對照組，REVISION 2 配沒綁的紀錄）和 M-C03（同一份對照組用 `verify --rerun` 重跑，重跑本身通過，但 `--rerun` 也比對工單綁定）因此從 0 變 1：這是預期變更（G03b 優先），不是退步。

Deprecated：
- 證據未綁工單，下個 MAJOR 起必填 `--order`。現在 `evidence_record.py run` 不加 `--order` 仍可用；REVISION 1 的工單照收，但 `gate_check.py --match --evidence-dir` 會印 WARN。

沒做：
- 兄弟 repo 共用 `<上層>/DIRECTOR/director_work.json`（稽核 P1-5 / A12）：要設計 config 綁 repo 的欄位，延到 v0.14。
- hook 不擋 MultiEdit、NotebookEdit 和用 Bash / PowerShell 寫檔：延到 v0.14 評估。
- `CHECKS` 從提示改成失敗：v0.14。
- `REQUIRED_CHANGES` 對 SCOPE / FORBIDDEN 的檢查是把每一條當路徑比對，glob 對 glob 只是近似。
- `hook_guard.py --protect` 的已知限制（審查 H03、H05）：經由別名（網路磁碟、`subst`、UNC 共用）建立還不存在的 `DIRECTOR_LOG.md` 或 `orders/` 資料夾、hook 執行時目標還不存在的 junction、沒權限建立而沒測的 symlink、MultiEdit、NotebookEdit 都擋不到。真的要擋，請用作業系統的寫入權限保護 DIRECTOR 資料夾。
- 清單項目沒包反引號時，` #` 之後仍是註解（設計如此，S02）；檔名含 ` #` 請用反引號包起來。
- 派工後沒有 ACK 的閒置監看工具（`NO_ACK` 狀態）：這版只在 `docs/06b` 寫規則和三個測試案例的規格，`tools/` 沒有監看工具，延到之後的版本。

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
