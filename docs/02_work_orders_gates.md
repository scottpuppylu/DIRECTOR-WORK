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
- 驗收條件每項有：ID、要求、驗證方法、預期、實際、證據、狀態。Mock 和單元測試不能當成真實環境的驗收。
- 發工單前想清楚需求、現有結構、相依、邊界條件、測試方法，一次給完整。

### Gate 與回報

- Worker 在 gate 完成、卡住、需要裁決、要偏離工單時回報，一個 gate 只送**一則完整**的 TASK REPORT（`templates/TASK_REPORT.md`）。
- 交件前 worker 跑三支工具，把結論行貼進 TASK REPORT：`tools/scope_check.py`（改動有沒有超出工單）、`tools/gate_check.py`（欄位和用詞）、`tools/evidence_record.py`（驗收指令留下重跑指令和產物雜湊）。
- 總監審查時自己重跑 `scope_check.py` 和 `evidence_record.py verify`，不只看報告怎麼寫。工具通過只代表格式、範圍和檔案對得上，不代表做對了；下面四階段照做。
- 總監審查四階段：
  1. 對照原始需求逐項核對，不接受 worker 自行縮減的驗收條件。
  2. 審證據：修改範圍、意外修改、build、測試是否足夠、回歸、未驗證項。沒有親自取得的證據要寫「依 worker 報告」。
  3. 判定：`PASS / PASS_WITH_WARNINGS / CONDITIONAL_PASS / PARTIAL / HOLD / BLOCKED / FAIL / NOT_RUN`。
  4. 下一步只選一個：`ACCEPT_AND_CLOSE / CONTINUE_SAME_WORKER / SWITCH_TO_OTHER_WORKER / REQUEST_INDEPENDENT_REVIEW / REQUEST_OWNER_AUTHORIZATION / STOP_AND_REPORT_BLOCKER`。
- 裁決格式（`templates/GATE_VERDICT.md`）：A 判定 → B 已證實成果 → C 問題 P0/P1/P2 → D 取捨 → E 下一張工單（落檔）→ F 停止狀態（預設 NO MERGE / NO PUSH / NO FINAL ACCEPTANCE）。
- 證據等級：`VERIFIED_LOCAL / VERIFIED_REMOTE / REPORTED / SUPPORTED / ESTIMATED / ASSUMPTION / UNKNOWN / NOT_TESTED / INVALID`。
- 狀態分開寫：工程、功能、成品、效能、穩定性、整合、PO 驗收，不用一個 PASS 蓋過其他。
- 跳過的測試不算 PASS；既有失敗維持原樣寫 `NO_NEW_REGRESSION`，不是 ALL PASS。
- 交接時用 `RESUME_STATE.md`（`docs/06`）；原 worker 先停在安全狀態，接手者先核對 repo 和交接資料一致，不重做已通過的工作。

### 重資源排程（有總管時）

- 用到共用重資源的工作，先送 `TEST REQUEST`（`templates/TEST_REQUEST.md`），等 `GO`，結束送 `DONE <內容> <實際分鐘>`；超時 10 分鐘以上要說明原因和新 ETA。
- **GO 寫在排程看板檔，不用訊息發。** 看板只有總管能寫，一行一筆：`GO <完整名稱> <內容> <開始> <上限分鐘>`、`QUIET <時段> <原因>`、`HOLD <名稱> <原因>`。
- Worker 送出申請後，用背景等待程序看板（不花額度），看到自己的 GO 才開始，並寫一行 ACK。看板讀寫用固定的小工具，名稱一律寫完整名稱，短名稱由工具換成全名。
- 總管寫 GO 後幾分鐘內確認對方真的開始；沒開始就提醒。不准空等整段獨佔時段。
- 文件、git、打包、輕量 CPU 工作不用申請。

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
- 四階段審查擋住最常見的問題：worker 偷偷縮小驗收範圍、把「跑過」說成「通過」。
- 狀態分開寫，是因為一個面向 PASS 常被拿來蓋過其他面向沒驗。
- 規則只寫在文件裡，靠模型自律就會漏；寫成小程式才每次都擋得住，也不花額度。報告裡的「沒超出範圍」「測試通過」是自述，要能重跑才算證據。
- GO 用檔案發：系統可能限制一個 session 在使用者兩次發言之間自動發出的跨 session 訊息數量（原專案約 10 則就被暫停），排程員最先撞到。看板檔沒有這個限制，背景等待也不花額度。原專案曾因看板寫短名、監看等全名，獨佔時段空轉近半小時。
- 改一個測一個太慢；全部批次又分不出是哪一項造成的。開關讓一次 build 同時得到效率和可歸因的對照。
- 測試本身花時間、花資源、花額度。每個測試都要回答一個問題，否則不跑。
