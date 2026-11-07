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
| PO 待決頁 | `Artifact` 發布 `templates/choice_page.html`（`pin: true`），回覆用 `ArtifactData` 存；本機帳 `DIRECTOR/PO_PENDING.md` | 兩種模式都在第一則回覆之前發布並置頂（`BOOTSTRAP` 第 6 步），啟動提示詞的同意句就是授權；網址記在 `DIRECTOR_STATE.md` 的 `PO_PAGE_URL`。用不了或使用者說不要，照下面「待決頁網頁的授權與備援」在聊天做完。 |
| 結束工作線 | `archive_session`（`mcp__ccd_session_mgmt__archive_session`） | 依權限模式可能要 PO 按核准。封存可以重開；不要刪除 session。封存不會刪資料夾，worktree 和輸出另外處理（`docs/06b` 刪檔前比對）。 |

## 開 worker 的限制

- `start_session` 只在 **PO 親自發話的那一輪**、而且 PO 用話要求開這條線時，才能直接開（`user_asked`）。被 worker 的訊息、計時器、排程任務叫醒的那一輪，直接開會被拒，只能留「提案卡」（`own_initiative`），要 PO 點了才會開。
- 首批開線的同意可以和初衷卡確認併成一句回覆（`docs/12` 第三節）：貼出卡和開工說明的那則之後，使用者回「卡片對，請開一位 AI 助手做這一批」，就是 PO 親自發話、明確要求開線，可以直接開（`user_asked`）。回覆只確認卡、或只說「好」「收到」，不開。這句白話能否讓 `start_session` 接受，以工具當下的檢查為準；被拒就改留提案卡，並記進 `DIRECTOR_LOG`（NOT_VERIFIED：2.1.0 起尚未在 Desktop 實測）。呼叫送出了卻沒收到結果時，先用 `list_sessions` 和 `DISPATCH` 紀錄查有沒有已經開出來的，再決定要不要重開，避免開出第二條線。
- 所以：要開的 worker 先在待決頁列好（工單路徑、模型、effort），請 PO 在聊天裡一次說「開 W1、W2」；總監在那一輪全部開完。不要在被叫醒的那一輪空等提案卡。
- Strict 工單的規格審查（`templates/SPEC_REVIEW.md`）在**放上待決頁之前**做完：總監寫好工單的那一輪就跑 subagent，採納修改、重算 `gate_check.py --hash`，再把工單放上待決頁，列出工單路徑、REVISION、雜湊和 `SPEC_REVIEW ... adopted=` 那行。PO 說「開」的那一輪只做兩件事：把 `DISPATCH` 行寫進 `DIRECTOR_LOG`，然後 `start_session`，不在這一輪等 subagent。審完後工單又改版，就重審，更新待決頁上的 REVISION 和雜湊。原因：subagent 在背景跑時先結束這一輪，就只能留提案卡（實測 2026-11-04：在 PO 發話那一輪等審查約 4 分鐘）。
- 直接開（`user_asked`）可以帶 `cwd` 指定 worker 的資料夾（實測 2026-11-04）。提案卡不能指定工作資料夾（`cwd`），新 session 會落在總監的專案資料夾或它自己的 worktree。工作資料夾限制寫進工單的 SCOPE / FORBIDDEN，不要只靠 `cwd`。
- 新 session 的權限模式不一定和總監一樣（實測：從提案卡開出的 worker 是 `bypassPermissions`）。開完用 `get_session` 看；不能靠權限詢問擋住越界，要靠工單的 SCOPE / FORBIDDEN、`scope_check.py`，需要時加裝 `hook_guard.py`。`bypassPermissions` 只略過權限詢問，不略過 hook（實測 2026-11-04：worker 資料夾的 `.claude/settings.local.json` 裝了 `hook_guard.py`，`git push`、`git clean -fd` 照樣被擋）。
- 安裝時加 `--protect-director <DIRECTOR 路徑> --director-worktree <總監的 worktree>`，worker 的 hook 也會擋 Write / Edit 改 `orders/` 和 `DIRECTOR_LOG.md`，總監自己的 worktree 不受影響。這只是防手誤，不是安全隔離：Bash / PowerShell 寫檔、MultiEdit、NotebookEdit 都擋不到，改了工單還是靠 `--dispatch-log` 的雜湊比對查出（`docs/02`）；細節見 `tools/README.md`。
- 1.1.0 起用 `setup_project_settings.py --runtime-guard` 一次裝好整組防護，再在 worker 的資料夾跑 `tools/doctor.py`，看哪些真的生效（原生 Windows 上隔離一項永遠是 NOT_ENFORCED）。
- 要 OS 隔離和網路出口管制，worker 改在 WSL 的容器裡開：`tools/container/run_worker.sh`（用法、掛載和實測見 `tools/README.md`）。這種 worker 是 CLI，不是 `start_session` 開的 Desktop session，不會出現在 `list_sessions`；進度只看它的 RESUME_STATE 和分支。第一次要 PO 在容器裡 `/login`（account B），DW 不碰帳密。1.2.0 起每個容器 worker 用自己的 clone（K1）：總監先 `worker_clone.sh create`，再 `run_worker.sh --clone` 開；worker 不能 push，做完由總監 `worker_clone.sh collect` 收進 `refs/dw-workers/<名稱>/<分支>`，驗收用 `git rev-parse refs/dw-workers/<名稱>/<分支>` 取候選 commit。舊的 `--git-common` 讓容器能改 repo 的每個 ref，doctor 報 NOT_ENFORCED；仍支援，最早 3.0（major）才移除，遷移改用 `worker_clone.sh create` + `run_worker.sh --clone`。2.2.0 起 DIRECTOR 和 clone／worktree／`--git-common` 重疊（相同、在裡面或包住）就 exit 2：用容器 worker 時，DIRECTOR 放在 repo 和 clone 外面。
- worker 的資料夾要先寫好壓縮門檻，而且**只在開第一位 worker 前**才需要做：`setup_project_settings.py --repo <worker 的資料夾> --only-this` 報告模式，確認忽略規則後加 `--apply`，再報告一次要 `OK`；開線後用 `get_usage` 讀該 worker 的 `contextWindow`（要是 250000；讀不到記 NOT_VERIFIED）。沒寫的資料夾，`get_usage` 會看到上下文視窗 1,000,000。設好後寫進 `GUARDS.md`（`BOOTSTRAP` 第 7、11 步）。
- 額度重置後的喚醒（`docs/06b`）是被計時器叫醒的那一輪：只用 `SendMessage` 叫醒既有的 session，不開新的（從這種一輪送訊息是否可行，未實測）。

## 待決頁網頁的授權與備援

- **原則（兩種模式一樣）**：啟動提示詞的「建置時就把待決頁做成我的 Claude 私人頁面並置頂」就是同意，涵蓋本專案指定的題目、成品截圖、初衷摘要與回覆存到使用者自己的 Claude 私人頁面。總監在第一則回覆之前就發布並置頂（`BOOTSTRAP` 第 6 步），不另外問；同意登記成 PO 指示（來源、日期、頁面網址）。對外分享另循 `docs/08`。
- **沒有這句的舊專案**：2.2.0 以前的啟動提示詞沒有這句。狀態工具印 `~ PO_PAGE_MISSING` 時，在聊天用一句白話取得同意，例如「我把要你決定的事放在你自己的 Claude 私人頁面並置頂，好嗎？直接在這裡回答也可以。」使用者同意就照 `BOOTSTRAP` 第 6 步補建；說不要就寫 `PO_PAGE_URL: NONE reason=PO 不要網頁`，登記成 DD。不要求使用者額外設定、安裝、登入其他服務或回傳文件。
- **備援 4 步**（使用者說不要、沒有 Artifact 工具、Artifact 被停用、斷線、沒有權限，都走這條；有圖的題目也一樣）：
  1. 總監先在 `PO_PENDING.md` 登記題號、當版問題、選項、建議，狀態 `open`，再在同一個聊天放簡短選項和建議，例如「首頁想要 A 明亮還是 B 沉穩？我建議 A，白天用手機比較清楚。」有圖，就用本機預覽或使用者現在看得到的連結加文字描述；沒有真實畫面就留在 `PO_PENDING.md` 的「待預覽」，不替使用者猜視覺偏好。
  2. 使用者可以只回「B，字再大一點」。總監依聊天上下文綁到題號，把原文寫進 `ANSWER`，`STATUS: answered`，寫收到時間，再照同一套流程處理。多題且意思真的不清楚時，才用一句白話問。
  3. 每輪開始照樣讀 `PO_PENDING.md` 和聊天裡還沒處理的回答。仍有同意、Artifact 又可用時，兩邊都查；同一題以先落檔的答案為準，不要求使用者重答。晚到而且不同的答案，保留原文並問使用者是不是改了主意，不直接覆蓋。Artifact 斷線記在 `RESUME_STATE`。
  4. 處理後寫 `RESOLUTION`、時間、`STATUS: closed`，保留原條目；聊天只報結果。Artifact 恢復且同意仍在時，先匯入沒讀過的回覆，再對仍開著的題恢復頁面展示；使用者已在聊天答過的題不重開。使用者說不要網頁，就寫 `PO_PAGE_URL: NONE reason=<原因>`、登記成 DD，只走本機，之後不再碰雲端。

## 常見用法

- **確認壓縮門檻生效**（`BOOTSTRAP` 第 7.5 步）：`get_usage` 看自己的 `context.contextWindow`。設定只對之後開的 session 生效，建置中的 session 會是舊值；換到下一個 session 再讀一次，要是 `250000`。
- **98% / 99% 停工線**（`docs/04`）：每次喚醒先讀 `get_usage` 的週額度，不靠人看畫面。讀不到時 `plan.status` 會是 `unavailable`，記 UNKNOWN，不當成 0%。
- **快壓縮時**：`context.percentUsed` 接近 `autoCompactsAtPercent` 時，先更新 RESUME_STATE 四行，讓壓縮後的摘要可以短；不為了縮上下文換新 session（`docs/04` 第 2 點）。
- **看 worker 是否還在跑**：先讀它的 RESUME_STATE；要叫醒它之前，先用 `get_session` 確認狀態，不為了問進度發訊息。`get_usage` 讀別的 session 的上下文視窗時，閒置的 session 可能讀得到（實測讀得到），也可能回 unavailable；讀不到不代表它中斷了。

## 為什麼

- 規則包原本只寫了「做什麼」。Desktop 上第一次走 BOOTSTRAP 時，以為沒有工具能看自己的上下文視窗，就記成 NOT_VERIFIED；其實 `get_usage` 就能讀。能力和工具的對照沒寫下來，新總監就要自己摸索，或誤判成做不到。
- 2026-11-04 用一個「被別的 session 交派任務」的桌面 session 只照本文件實測：讀額度順利；開 worker 被拒，只能留提案卡，PO 點了卡片 worker 才起來。之後傳訊息、讀狀態和上下文視窗、讀 worker 的 RESUME_STATE、封存都照表做成。上面的限制和權限模式，就是這次實測找到的。
- 寫成「能力 → 怎麼找工具」而不是寫死名稱，是因為 app 改版時名稱會變，但流程需要的能力不會。
