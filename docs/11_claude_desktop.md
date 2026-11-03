# 11 在 Claude Desktop 上操作

只在 Claude Desktop（Code 分頁）上當總監時讀，不列入每輪必讀。規則照 `docs/01` 到 `docs/10`；這裡只寫「流程需要的能力，在 Desktop 上用哪個工具做」。

## 先找工具

- 工具名稱會隨 app 版本改變。下表是 2026-11 的名稱（括號內是完整名稱）。找不到時，用 `ToolSearch` 以**能力**的關鍵字搜尋（例如 `usage`、`session`、`schedule`），不要猜名稱。
- 表中工具大多是延後載入的：清單只列名稱，要先用 `ToolSearch` 載入才能呼叫。一次載入要用的全部：`select:mcp__ccd_session_mgmt__get_usage,mcp__ccd_session_mgmt__list_sessions,mcp__ccd_session_mgmt__get_session,SendMessage`。`start_session` 依它的說明單獨一則載入。
- 有些工具（`start_session` 這類）的說明會要求「單獨一則訊息載入」或「只在使用者要求時用」。照工具說明做；工具說明和本文件衝突時，以工具說明為準，並記進 `DIRECTOR_LOG`。

## 能力對照

| 流程需要 | Desktop 的做法 | 注意 |
|---|---|---|
| 開 worker | `start_session`（`mcp__ccd_session__start_session`） | 工單先落檔；提示只給工單路徑、RESUME_STATE 路徑和一句目標。**只有 PO 親自發的那一輪能直接開**，見下方「開 worker 的限制」。 |
| 傳訊息給 worker | `SendMessage`（`to` 填 `local_…` 開頭的 session id） | 只在 `docs/03` 的三種情況發。送達就會叫醒對方一輪（回傳「已送達」不代表已讀）；長內容寫檔，訊息只給路徑。 |
| 讀 session 清單和狀態 | `list_sessions`、`get_session`（`mcp__ccd_session_mgmt__…`） | `get_session` 的 `isRunning` 分辨在跑或閒置，`isArchived` 表示已封存。恢復時對照 `ACTIVE_WORKSTREAMS.md`，找閒置、中斷、等回覆的線（`docs/06`）。 |
| 讀額度和上下文視窗 | `get_usage`（`mcp__ccd_session_mgmt__get_usage`） | `plan` 是帳號的 5 小時、週額度與重置時間；`context` 是某個 session 的 `tokensUsed / contextWindow`（預設自己，可帶別的 session id）。不花額度。 |
| 調模型和思考程度 | `set_session_model`、`set_session_effort`（`mcp__ccd_session_mgmt__…`） | 依 `docs/05`；通常下一輪生效。 |
| 額度重置後喚醒 | 總監自己的背景計時器，加上 `scheduled-tasks` 的排程任務當備援 | 要電腦、app、網路都開著；先演練一次（`docs/06b`）。兩者都寫進 `GUARDS.md`。 |
| PO 待決頁 | 預設 `DIRECTOR/PO_PENDING.md` | 改用 Artifact 頁面（`Artifact` + `ArtifactData` 存回覆）會把專案內容放上 claude.ai，要先問 PO。 |
| 結束工作線 | `archive_session`（`mcp__ccd_session_mgmt__archive_session`） | 依權限模式可能要 PO 按核准。封存可以重開；不要刪除 session。封存不會刪資料夾，worktree 和輸出另外處理（`docs/06b` 刪檔前比對）。 |

## 開 worker 的限制

- `start_session` 只在 **PO 親自發話的那一輪**、而且 PO 用話要求開這條線時，才能直接開（`user_asked`）。被 worker 的訊息、計時器、排程任務叫醒的那一輪，直接開會被拒，只能留「提案卡」（`own_initiative`），要 PO 點了才會開。
- 所以：要開的 worker 先在待決頁列好（工單路徑、模型、effort），請 PO 在聊天裡一次說「開 W1、W2」；總監在那一輪全部開完。不要在被叫醒的那一輪空等提案卡。
- 提案卡不能指定工作資料夾（`cwd`），新 session 會落在總監的專案資料夾或它自己的 worktree。工作資料夾限制寫進工單的 SCOPE / FORBIDDEN，不要只靠 `cwd`。
- 新 session 的權限模式不一定和總監一樣（實測：從提案卡開出的 worker 是 `bypassPermissions`）。開完用 `get_session` 看；不能靠權限詢問擋住越界，要靠工單的 SCOPE / FORBIDDEN、`scope_check.py`，需要時加裝 `hook_guard.py`。
- worker 的資料夾要先寫好壓縮門檻（`tools/setup_project_settings.py --apply`）。沒寫的資料夾，`get_usage` 會看到上下文視窗 1,000,000。
- 額度重置後的喚醒（`docs/06b`）是被計時器叫醒的那一輪：只用 `SendMessage` 叫醒既有的 session，不開新的（從這種一輪送訊息是否可行，未實測）。

## 常見用法

- **確認壓縮門檻生效**（`BOOTSTRAP` 第 7.5 步）：`get_usage` 看自己的 `context.contextWindow`。設定只對之後開的 session 生效，建置中的 session 會是舊值；換到下一個 session 再讀一次，要是 `250000`。
- **98% / 99% 停工線**（`docs/04`）：每次喚醒先讀 `get_usage` 的週額度，不靠人看畫面。讀不到時 `plan.status` 會是 `unavailable`，記 UNKNOWN，不當成 0%。
- **換 session 的時機**：`context.percentUsed` 接近 `autoCompactsAtPercent` 時，先更新 RESUME_STATE 四行，再換新 session（`docs/04` 第 2 點）。
- **看 worker 是否還在跑**：先讀它的 RESUME_STATE；要叫醒它之前，先用 `get_session` 確認狀態，不為了問進度發訊息。`get_usage` 讀別的 session 的上下文視窗時，閒置的 session 可能讀得到（實測讀得到），也可能回 unavailable；讀不到不代表它中斷了。

## 為什麼

- 規則包原本只寫了「做什麼」。Desktop 上第一次走 BOOTSTRAP 時，以為沒有工具能看自己的上下文視窗，就記成 NOT_VERIFIED；其實 `get_usage` 就能讀。能力和工具的對照沒寫下來，新總監就要自己摸索，或誤判成做不到。
- 2026-11-04 用一個「被別的 session 交派任務」的桌面 session 只照本文件實測：讀額度順利；開 worker 被拒，只能留提案卡，PO 點了卡片 worker 才起來。之後傳訊息、讀狀態和上下文視窗、讀 worker 的 RESUME_STATE、封存都照表做成。上面的限制和權限模式，就是這次實測找到的。
- 寫成「能力 → 怎麼找工具」而不是寫死名稱，是因為 app 改版時名稱會變，但流程需要的能力不會。
