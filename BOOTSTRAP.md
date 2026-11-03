# BOOTSTRAP — 新總監的第一輪

照順序做。每一步做完才做下一步。標「問 PO」的，放上待決頁（第 6 步）並列進第一份回報，不自己做。
`<RULES>` 指本規則包在本機的位置，`<REPO>` 指新專案的 git repo，`<WS>` 指放共用狀態的位置（見第 3 步）。

## 0. 先確認環境（唯讀）

1. `git -C <REPO> rev-parse --show-toplevel`、`git -C <REPO> status`、`git -C <REPO> worktree list`。不是 git repo 就停下問 PO。
2. 讀專案現有的 `CLAUDE.md`（含 `CLAUDE.local.md`）、使用者層 `~/.claude/CLAUDE.md`（也算 PO 指示，只讀不改）、`README`、專案記憶索引（`~/.claude/projects/<專案資料夾>/memory/MEMORY.md`；`<專案資料夾>` 是 repo 絕對路徑把非英數字元都換成 `-`，例如 `D:\work\app` → `D--work-app`；沒有就記 NONE）。記下已經有的規則，之後衝突時以它們為準。
   語言分三層看：回報、文件與 CLAUDE.md 段落、程式碼與註解。同一層的要求不同才算衝突（例如啟動指示要中文回報、CLAUDE.md 要英文回報）：照 PO 最新的明確指示做，列進第一份回報第 4 點，並開一題待決項請 PO 確認。
3. 讀系統時鐘，要帶時區：Bash `date '+%Y-%m-%d %H:%M %z'`，PowerShell `Get-Date -Format 'yyyy-MM-dd HH:mm zzz'`。之後所有時間戳都從這裡來，寫入前一刻再讀一次，不估計。
4. 這一步不改任何檔案。

## 1. 取得規則包並讀完

1. 把本規則包放到專案外的位置：`git clone https://github.com/scottpuppylu/DIRECTOR-WORK <RULES>`（PO 給了本機路徑就直接用）。第 3 步再把整個 `tools/` 複製到 `DIRECTOR/tools/`。
   PO 給了連結，就算同意下載這一個專案。跑工具前先讀過它的程式碼；第一輪會跑 `setup_project_settings.py`、`context_probe.py`、`usage_report.py`、`memory_size_check.py`、`gate_check.py`，其他的等要用時再讀。
   記下規則包的版本（`git -C <RULES> rev-parse --short HEAD`），第 3 步寫進 `DIRECTOR_OPERATING_RULES.md`。
2. 讀 `README.md`、本檔、`docs/01` 到 `docs/10`（含 `06b`）。
3. 之後每輪只讀 README 標「每輪必讀」的檔。

## 2. 盤點專案（唯讀，結論寫檔）

下面幾項先記在對話裡，第 3 步建好資料夾後寫進 `DIRECTOR/DIRECTOR_STATE.md` 的「專案概況」。不寫檔、不跑會產生檔案的指令：
- 專案目標、目前階段、已知的 PO 決定（從 CLAUDE.md 和記憶來）。沒有產品方向就記下來，第 12 步開題問。
- repo、分支、worktree、未提交的修改（只記，不動）。
- 怎麼 build、怎麼測試、測試要多久（看文件或 CI 紀錄；要實跑才知道就寫 UNKNOWN，之後由 worker 量）。專案規則要求改完就跑的測試照跑；Python 加 `-B`，不在 repo 留 `__pycache__`。
- 有沒有**共用的重資源**：GPU、長時間 build、只能同時跑一個的工具、量測時要安靜的機器。有的話才需要總管（`docs/01`）。
- 輸出放哪裡、磁碟還剩多少。專案沒有輸出位置時，總監可以自訂一個 repo 外的位置，登記成 DD。
- 成品要怎麼看：畫面、聲音、文件、API 回應……（決定 `docs/07` 的常識閘門怎麼寫）。

## 3. 建立 DIRECTOR/ 資料夾

位置：多個 worktree 要共用同一份狀態，所以**預設放在 repo 外、所有 worktree 都看得到的位置**，例如 repo 的上一層 `<WS>/DIRECTOR/`。專案只有一個 checkout、PO 又希望版控時，可以放 repo 內。位置由總監決定（登記 DD），寫進第一份回報，不用開待決題。

```text
DIRECTOR/
  DIRECTOR_OPERATING_RULES.md   本專案版規則：只寫和本規則包不同的地方，其餘寫「照 <RULES>/docs/xx」
  DIRECTOR_STATE.md             總表：專案概況、目前階段、各工作線狀態、下一步
  ACTIVE_WORKSTREAMS.md         誰在做什麼：session 名稱、工單、RESUME_STATE 路徑、模型、effort、優先序
  DECISION_REGISTER.md          從 templates/DECISION_REGISTER.md 建立
  RISK_REGISTER.md              風險、影響、對策、負責人
  DIRECTOR_LOG.md               append-only，每個決定一行，時間從 date 讀
  RESUME_STATE.md               總監自己的（templates/RESUME_STATE.md）
  PO_PENDING.md                 PO 待決頁的檔案版（templates/PO_PENDING.md；有更好的位置就改用，這份留指向）
  GUARDS.md  BASELINE_METRICS.md  第 11、8 步
  orders/  reviews/  research/  research/ 放探測、用量、plugin 清單這類量測的原始輸出
  tools/                        整個 <RULES>/tools/ 複製過來；第 11 步的 guard_check.py 也放這裡
  director_work.json            從 director_work.example.json 改，範例裡的假 plugin 名稱要刪掉
```

沒有指定範本的檔案，骨架在 `templates/DIRECTOR_FILES.md`。

## 4. CLAUDE.md 加上總監段落

1. 把 `templates/CLAUDE_PROJECT_SECTION.md` 填好，加在專案 `CLAUDE.md` 的最上方，原內容一字不刪。
2. 把所有 `<...>` 換掉：`<RULES>`、總監名稱、`<DIRECTOR>` 位置、待決頁位置、回報語言、成品怎麼看、`<輸出位置>`。還不知道的寫「待 PO 指定（OD-xx）」。`<RULES>` 是本機路徑，不想讓它進版控，就把這段放進 `CLAUDE.local.md`，同一步把 `CLAUDE.local.md` 加進 `<REPO>/.git/info/exclude`。
3. 本機 commit 可以，但 repo 沒設 git 身分時不要自己改設定：PO 給過身分就用 `git -c user.name=... -c user.email=...`；沒給就暫用 `Director (Claude Code) <director@example.invalid>`，開待決題請 PO 指定。**push 要 PO 核准**。CLAUDE.md 保持精簡，細節指向 DIRECTOR/ 的檔案。

## 5. 決策登記與總監的 RESUME_STATE

1. PO 在啟動提示、專案和使用者層 CLAUDE.md 裡給過的指示，逐條登記成 `PO-01`、`PO-02`……，附來源。不知道 PO 何時說的，時間欄填讀到的時間並註明。
2. 寫總監自己的 `RESUME_STATE.md`，頂部四行（PROGRESS / DOING / NEXT_STEP / COMMS）一定要填。

## 6. PO 待決頁

1. 預設用 `DIRECTOR/PO_PENDING.md`。要改用外部服務的頁面（可共享、可記錄回覆的那種），先問 PO：專案內容會因此放上外部服務。
2. 格式照 `templates/PO_PENDING.md`。任何一步產生的問題都放這裡。
3. 從這一步起，總監每一輪的第一個動作都是讀待決頁上 PO 已回覆的項目（`docs/03`）。

## 7. 壓縮門檻（25 萬）

1. 填好 `DIRECTOR/director_work.json`（`window`: 250000，`plugins_off` 先留空）。
2. 報告模式：`python -I -X utf8 <WS>/DIRECTOR/tools/setup_project_settings.py --repo <REPO> --config <WS>/DIRECTOR/director_work.json`
3. 確認每個 worktree 都是 `MISSING` 或 `OK`。`NOT_IGNORED` 代表 `.claude/settings.local.json` 會被 commit；沒有 `.gitignore` 的新 repo 一定會這樣。處理：
   - 先把 `.claude/settings.local.json` 加進 `<REPO>/.git/info/exclude`（只在本機、不進版控，所有 worktree 共用）：`echo .claude/settings.local.json >> <REPO>/.git/info/exclude`。重跑報告模式要變成 `MISSING`。
   - 在待決頁開一題：要不要改成寫進 `.gitignore`（這會改 repo，要 commit）。PO 回覆前不動 `.gitignore`。
4. 寫入：同一行加 `--apply`。再跑一次報告模式，要全部 `OK`。
5. 驗證生效（不花額度）：`python -I -X utf8 <WS>/DIRECTOR/tools/context_probe.py --cwd <REPO> --json-out <WS>/DIRECTOR/research/probe-<日期>.json`（約 20 秒，會啟動一次完整的 claude CLI）。預期 `maxTokens: 250000`、`autoCompactThreshold: 217000`（25 萬減去預留緩衝，CLI 改版可能略有不同）；`autocompactSource` 說明是哪個鍵生效。
   設定只對之後開的 session 生效，建置中的這個 session 看不到。總監換到下一個 session 時再確認自己的上下文視窗；看不到就寫 NOT_VERIFIED，列進風險。
6. 「已設好」只在第 4、5 步都看到結果後才能寫。只寫了檔案不算。
7. `tools/hook_guard.py`（擋 push、`reset --hard` 等）是選用的；要不要裝放上待決頁。

## 8. 量基準（不花額度）

1. 用第 7.5 步存下的探測結果：各類別 token、記憶檔、skill 數量。
2. `usage_report.py --since <建置當天日期>`。新專案只會看到建置 session 自己的紀錄：數字另列、不當基準，建置前的歷史記 UNKNOWN。印 `NO_DATA` 時記 UNKNOWN，不記 0。
3. 結果寫進 `DIRECTOR/BASELINE_METRICS.md`（`templates/DIRECTOR_FILES.md`），日期從 `date` 讀。之後每週複查用同一套指令比較（`docs/04`）。

## 9. 無關 plugin 清單（問 PO）

1. 從第 8 步的探測結果，列出跟本專案無關的 plugin：名稱（`name@marketplace`）、估計每次呼叫多少 token、為什麼無關、是**使用者自己裝的**還是**桌面版 / claude.ai 帶進來的**。
   - `claude plugin list --json` 的 `id` 就是 `name@marketplace`。看 `scope`：`user` 是使用者裝的，`synced` 是桌面版 / claude.ai 帶進來的；`enabled: false` 的跳過。
   - `claude plugin details <id>` 估 token，用完整 id（短名稱不一定查得到）。在迴圈裡呼叫 `claude` 要加 `</dev/null`，不然它會吃掉迴圈的輸入。
   - `details` 的數字是估計（ESTIMATED），常比探測實測大，因為探測裡的 skill 清單會被截短。真正省多少，以關閉前後兩次探測的差為準。
   - 使用者層 MCP server 另列一類：工具是延後載入的，每次呼叫固定付的只有它的說明文字（探測的 MCP 那幾列）。
2. 放上待決頁讓 PO 勾。PO 勾完才寫進 `director_work.json` 的 `plugins_off`，跑 `--apply`，再探測一次確認數字下降。
3. 桌面版 / claude.ai 帶進來的 plugin 和 connector，只能在 claude.ai 設定關，而且會影響所有專案和之後所有新 session 的預設（專案設定能不能關，未實測）。只列出來，由 PO 決定，總監不動手。

## 10. 記憶索引

1. 第 0 步記為 NONE 就跳過這步。有索引時：`python -I -X utf8 <WS>/DIRECTOR/tools/memory_size_check.py --file <專案記憶索引>`。
2. 超過門檻就照 `docs/09` 整理：先備份整份索引，只移結案和歷史條目，規則類和進行中的條目不動，記憶檔本身不刪。

## 11. 機制清單（給續航用）

把建好的每個機制（壓縮設定、背景計時器、排程任務、監看程序）寫成一張表：擁有者、中斷會怎樣、怎麼檢查、重建指令。放在 `DIRECTOR/GUARDS.md`（`templates/DIRECTOR_FILES.md`）。檢查腳本照 `docs/06b` 自己寫成 `DIRECTOR/tools/guard_check.py`，沒有通用版；第一輪至少查兩項：`setup_project_settings.py` 報告模式全部 `OK`、`git -C <REPO> check-ignore -q .claude/settings.local.json` exit 0。沒有寫進表的機制，不算建好。

## 12. 工作線編制草案（問 PO）

在 `ACTIVE_WORKSTREAMS.md` 寫草案：要幾條 worker 線、各做什麼、要不要總管和清理員、各線的模型和 effort（`docs/05`）。第 2 步記下沒有產品方向時，先在待決頁問方向，草案寫成假設。**開新 session 會花額度，第一批由 PO 同意後才開。**

## 13. 第一份回報給 PO

用第 0 步決定的語言（PO 都沒指定就用繁體中文），先寫結論，20 行左右，細節放檔案：

1. 結論一句：建置完成 / 部分完成（缺什麼）。
2. 建了什麼：DIRECTOR 位置、CLAUDE.md 段落（是否已 commit）、待決頁位置。
3. 驗證結果：壓縮門檻（報告模式 OK 與探測數字）、固定成本基準、記憶索引大小。沒驗證的照實寫 NOT_VERIFIED。
4. 和本專案既有規則的衝突點，以及你照哪一邊做。
5. 待決頁上要 PO 處理的項目代號與一句話摘要（plugin 清單、工作線編制、git 身分……）。
6. 下一步：PO 回覆後要做的第一件事。

## 一定要先問 PO 的事

清單在 `docs/08`「要 PO 核准」。
