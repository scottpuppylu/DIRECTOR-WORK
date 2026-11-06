# 02 工單、Gate、報告與測試

## 規則

### 治理模式（依風險選）

- **Direct**：純查詢、文件、沒有風險。
- **Standard**：一般隔離開發，可以回退。
- **Strict**：核心邏輯、資料格式、存檔、對外介面、跨分支整合、發布。
- 流程：`Baseline → Plan → Isolated Change → Build/Test → 成品檢查 → Evidence → Gate → Checkpoint`。

### 工單

- 一律落檔：`DIRECTOR/orders/WO-<編號>-<短名>.md`，格式見 `templates/WORK_ORDER.md`。訊息只附路徑、一句摘要和必要的決定。
- 必填：`PRIMARY_WORKER / MODEL / EFFORT / FALLBACK / GOVERNANCE / BASE_REF / SCOPE / FORBIDDEN / ACCEPTANCE / DELIVERABLES / STOP_RULES`。
- 內容分段：A 背景、B 目標（MUST / OPTIONAL / OUT OF SCOPE，加上 SCOPE / FORBIDDEN 路徑清單）、C 執行前檢查、D 實作要求、E 驗收條件、F 安全與版控、G 完成定義。
- 驗收條件每項有：ID、類型、要求、驗證方法、預期。結果（實際、證據、狀態）寫在 TASK REPORT 的 ACCEPTANCE 表，不寫回工單。Mock 和單元測試不能當成真實環境的驗收。
- 類型 `AUTO / REVIEW / PO`：
  - AUTO：有指令可以重跑，總監重跑後判定。核准的指令寫在工單的 `CHECKS:`（`templates/WORK_ORDER.md` E 節），派工雜湊一起鎖住。
  - REVIEW：要有人看成品，獨立審查後由總監判定。開工前寫明誰看、從哪個角度看、看多大範圍、看哪些常識閘門項目（`docs/07`）。
  - PO：只有 PO 能判。
  - worker 能填的狀態以 `tools/vocabulary.json` 為準：REVIEW 最多填 `READY_FOR_REVIEW`，PO 只填 `PENDING_PO`。
- `TRACES_TO` 寫這張工單服務的需求或決定編號，沿用專案已有的編號；格式寫在 `director_work.json` 的 `trace_id_pattern`。
- Worker 不改工單的驗收條件和規格。發現條件做不到、互相矛盾或有錯，回報 `BLOCKED` 並寫明原因，由總監裁決後改工單。
- 總監改工單時 `REVISION` 加 1，在 H 節記一列（誰改、原因、影響的 AC）。派工時用 `gate_check.py --hash` 印出工單雜湊，把它印的 `DISPATCH <WO-ID> rev=<n> sha=<雜湊>` 那行原樣寫進 `DIRECTOR_LOG`（同一工單以最新一行為準）；worker 在報告填 `ORDER_SHA256`。審查時 `--match ... --dispatch-log DIRECTOR_LOG.md` 拿派工紀錄比對：工單被改過再重算雜湊也會被查出；DISPATCH 必須獨占一行，引用、縮排或圍欄裡的不算；沒有紀錄時各模式都失敗。這是事後查出，不是事前防止：誰都還是改得動工單。
- 發工單前想清楚需求、現有結構、相依、邊界條件、測試方法，一次給完整。
- 製作類工單的第一步固定是「既有資產盤點」：未合併的分支（`git log --all -- <路徑>`）、需求方提供過的檔案、舊報告。盤點結果寫進 gate 報告。
- 規格審查：Strict 工單放上待決頁前必做（Desktop 的做法見 `docs/11`），Standard 選用，Direct 不做。總監開一個短上下文、只讀的 subagent，照 `templates/SPEC_REVIEW.md` 審工單；結果只給總監參考，不增加 PO 的工作。每次在 `DIRECTOR_LOG` 記下花費（subagent 回報的 token）和抓到的問題；花費高過它省下的返工，就降回選用。

### Gate 與回報

- Worker 在 gate 完成、卡住、需要裁決、要偏離工單時回報，一個 gate 只送**一則完整**的 TASK REPORT（`templates/TASK_REPORT.md`）。
- 交件前 worker 跑三支工具，把結論行貼進 TASK REPORT：`tools/scope_check.py`（改動有沒有超出工單）、`tools/gate_check.py`（欄位和用詞）、`tools/evidence_record.py`（驗收指令留下重跑指令和產物雜湊）。AUTO 條件在最後一次 commit 之後記錄，ACCEPTANCE 表的證據欄寫紀錄的 `.json` 檔名；總監用 `gate_check.py --match 報告 工單 --evidence-dir 證據資料夾` 核對紀錄真的 exit 0、HEAD 相同。
- 總監審查時自己重跑 `scope_check.py`、`evidence_record.py verify 紀錄 --rerun --order 工單 --dispatch-log DIRECTOR_LOG.md --repo <候選 commit 的乾淨 worktree> --candidate <40 位>` 和 `gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md`，不只看報告怎麼寫。`--rerun` 跑的是工單 `CHECKS:` 裡核准的指令，不是 worker 寫在紀錄裡的；紀錄的指令不同或不是在候選 commit 記的，都算不符。它在候選 commit 的 tree 複製出來的暫存資料夾裡跑，仍會執行候選 commit 的測試碼，不是沙箱；`--repo` 用 `git worktree add --detach` 開的乾淨目錄。worker 記證據時加 `--order 工單`，紀錄就綁住工單版次；工單改版後要沿用舊證據，總監在 DIRECTOR_LOG 寫整行 `EVIDENCE_EQUIVALENT <WO-ID> rev=<舊> sha=<舊雜湊> to rev=<新>`，否則 Strict 失敗。Strict 工單再加 `--evidence-dir 證據資料夾 --candidate <git rev-parse worker 分支>`，少一個就失敗：報告、證據紀錄和裁決的 `CANDIDATE_HEAD` 都要指向同一個 commit。只有 `verify --rerun` 才算重跑驗證；`--match --evidence-dir` 和不加 `--rerun` 的 `verify` 只是讀 worker 自己寫的紀錄，`--rerun-recorded` 跑的也是紀錄裡寫的指令。`--match` 檢查每條驗收條件都有結果、狀態符合類型、PASS 附證據、工單雜湊和派工紀錄相符；不給 `--dispatch-log` 就只能和工單現在的樣子比。工具通過只代表格式、範圍和檔案對得上，不代表做對了；下面四階段照做。
- 總監審查四階段：
  1. 對照原始需求逐項核對，不接受 worker 自行縮減的驗收條件。REVIEW 條件交給獨立審查（`docs/07`），PO 條件放上待決頁。
  2. 審證據：修改範圍、意外修改、build、測試是否足夠、回歸、未驗證項。沒有親自取得的證據要寫「依 worker 報告」。
  3. 判定：`PASS / PASS_WITH_WARNINGS / CONDITIONAL_PASS / PARTIAL / HOLD / BLOCKED / FAIL / NOT_RUN`。
  4. 下一步只選一個：`ACCEPT_AND_CLOSE / CONTINUE_SAME_WORKER / SWITCH_TO_OTHER_WORKER / REQUEST_INDEPENDENT_REVIEW / REQUEST_OWNER_AUTHORIZATION / STOP_AND_REPORT_BLOCKER`。
- 裁決格式（`templates/GATE_VERDICT.md`）：A 判定 → B 已證實成果 → C 問題 P0/P1/P2 → D 取捨 → E 下一張工單（落檔）→ F 停止狀態（預設 NO MERGE / NO PUSH / NO FINAL ACCEPTANCE）。
- 證據等級：`VERIFIED_LOCAL / VERIFIED_REMOTE / REPORTED / SUPPORTED / ESTIMATED / ASSUMPTION / UNKNOWN / NOT_TESTED / INVALID`。
- 狀態分開寫：工程、功能、成品、效能、穩定性、整合、PO 驗收，不用一個 PASS 蓋過其他。
- 跳過的測試不算 PASS；既有失敗維持原樣寫 `NO_NEW_REGRESSION`，不是 ALL PASS。
- 交接時用 `RESUME_STATE.md`（`docs/06`）；原 worker 先停在安全狀態，接手者先核對 repo 和交接資料一致，不重做已通過的工作。
- 要看「哪個需求做到哪裡」時，用 `tools/trace_report.py` 從工單、報告和裁決產生追溯表（需求 → 工單 → AC → 證據 → 裁決），不另外人工維護。

### 重資源排程（有總管時）

- 用到共用重資源的工作，先送 `TEST REQUEST`（`templates/TEST_REQUEST.md`），等 `GO`，結束送 `DONE <內容> <實際分鐘>`；超時 10 分鐘以上要說明原因和新 ETA。
- **GO 寫在排程看板檔，不用訊息發。** 看板只有總管能寫，一行一筆：`GO <完整名稱> <內容> <開始> <上限分鐘>`、`QUIET <時段> <原因>`、`HOLD <名稱> <原因>`。
- Worker 送出申請後，用背景等待程序看板（不花額度），看到自己的 GO 才開始，並寫一行 ACK。看板讀寫用固定的小工具，名稱一律寫完整名稱，短名稱由工具換成全名。
- GO 後 N 分鐘內沒有 ACK，排程員直接找 worker 並告警；派工工具成功不等於對方確認。N 建議 3–5 分鐘；不准空等整段獨佔時段。
- 文件、git、打包、輕量 CPU 工作不用申請。
- 停機（QUIET、叫停）的對象是整條程序樹：由上往下，先停批次腳本（父 shell），再停子程序。停完依 CPU 用量列出所有程序，量一段時間內的 CPU 增量，確認沒有殘留，並回報已停的 PID；不能只比對程序名。下令的一方也獨立確認一次。
- 長批次腳本每一步開跑前檢查暫停旗標（看板的 QUIET）；有暫停就自己停下。
- 工具：`tools/pause_ctl.py on|off|status` 管暫停旗標，worker 的 `hook_guard.py --pause-flag` 在每個工具呼叫前檢查它；停完用 `pause_ctl.py procs` 依 CPU 增量確認沒有殘留（見 `tools/README.md`）。

### 測試預算

- 每個 TEST REQUEST 寫三件事：**目的**（回答哪個決定）、**最小範圍**（為什麼不能更小）、**上限分鐘**。缺一項退回。
- 預設上限：功能測試 30 分鐘、效能量測 20 分鐘；超過 60 分鐘要總監核准。超過上限 10 分鐘就先停下回報。
- 分級：
  - **第 0 級，每次修改後必做，不佔重資源**：離線編譯、CPU 上的單元測試、雜湊、數值檢查、量測腳本。能在這級發現的錯，不准拖到下一級。
  - **第 1 級，批次功能測試，預設**：同一 gate 裡互相獨立的修改累積起來一次驗。每項修改做成**開關**（命令列參數或設定值），同一個 build 跑出每一項的開 / 關對照。
  - **第 2 級，單項測試，例外，要寫理由**：P0 阻擋、PO 正在等、下一步依賴這個結果、修改互相耦合分不開、驗證單一根因假設。
- 不准的測試：程式沒變就重跑已通過的測試；為了「看起來完整」跑整個矩陣；gate 收尾以外的全量回歸；在成品 gate 之前跑效能量測。
- 統計型測試先算樣本數：失敗率約 10–20% 時，用 0/N 證明修好，N≈25–40 就夠（0.88^25 ≈ 5%），同時段跑對照組證明當時確實會重現。
- 一批之中某項失敗，其他項結果照記，不因一項失敗重跑全部。
- 輸出寫到 PO 指定的輸出位置，不寫進 repo；截圖預設 JPG，只有要做像素比對的近景才用 PNG。

## 為什麼

- 工單落檔，任何 session 中斷後都能重讀；訊息會被洗掉，也會讓每個收件者多一次完整上下文的成本。
- 四階段審查擋住最常見的問題：worker 偷偷縮小驗收範圍、把「跑過」說成「通過」。驗收條件只有總監能改，worker 改了就等於自己批准自己的交件。
- v0.10 以前，工單的驗收表同時放結果欄：worker 要填結果就得改工單，規格有沒有被動也就查不出來。所以規格留在工單，結果放報告，再用 `--match` 逐條對照。
- 原專案一段展示影片的工程數字全部正確，角色卻朝反方向動作：審查只看了被問到的部位，看的角度也由作者自己挑。所以要用眼睛看的條件，開工前就寫明誰看、怎麼看，實作者不能自己判過。
- 規格審查會花額度，所以只在 Strict 必做，而且要記下花費和抓到的問題，用數字決定要不要繼續做。
- 狀態分開寫，是因為一個面向 PASS 常被拿來蓋過其他面向沒驗。
- 規則只寫在文件裡，靠模型自律就會漏；寫成小程式才每次都擋得住，也不花額度。報告裡的「沒超出範圍」「測試通過」是自述，要能重跑才算證據。
- GO 用檔案發：系統可能限制一個 session 在使用者兩次發言之間自動發出的跨 session 訊息數量（原專案約 10 則就被暫停），排程員最先撞到。看板檔沒有這個限制，背景等待也不花額度。原專案曾因看板寫短名、監看等全名，獨佔時段空轉近半小時。
- 改一個測一個太慢；全部批次又分不出是哪一項造成的。開關讓一次 build 同時得到效率和可歸因的對照。
- 測試本身花時間、花資源、花額度。每個測試都要回答一個問題，否則不跑。
