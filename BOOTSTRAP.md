# BOOTSTRAP — 新總監的第一輪

照順序做。每一步做完才做下一步。標「問 PO」的，只列進第一份回報，不自己做。
`<RULES>` 指本規則包在本機的位置，`<REPO>` 指新專案的 git repo，`<WS>` 指放共用狀態的位置（見第 3 步）。

## 0. 先確認環境（唯讀）

1. `git -C <REPO> rev-parse --show-toplevel`、`git -C <REPO> status`、`git -C <REPO> worktree list`。不是 git repo 就停下問 PO。
2. 讀專案現有的 `CLAUDE.md`（含 `CLAUDE.local.md`）、`README`、專案記憶索引。記下已經有的規則，之後衝突時以它們為準。
3. 讀系統時鐘：`date`。之後所有時間戳都從這裡來，不估計。
4. 這一步不改任何檔案。

## 1. 取得規則包並讀完

1. 把本規則包放到專案外的位置：`git clone <REPO_URL> <RULES>`，或只複製 `tools/` 到第 3 步的 `DIRECTOR/tools/`。
   PO 給了連結，就算同意下載這一個專案。跑任何工具前，先讀過它的程式碼。
2. 讀 `README.md`、本檔、`docs/01` 到 `docs/10`。
3. 之後每輪只讀 README 標「每輪必讀」的檔。

## 2. 盤點專案（唯讀，結論寫檔）

把下面幾項寫進 `DIRECTOR/DIRECTOR_STATE.md` 的「專案概況」：
- 專案目標、目前階段、已知的 PO 決定（從 CLAUDE.md 和記憶來）。
- repo、分支、worktree、未提交的修改（只記，不動）。
- 怎麼 build、怎麼測試、測試要多久。
- 有沒有**共用的重資源**：GPU、長時間 build、只能同時跑一個的工具、量測時要安靜的機器。有的話才需要總管（`docs/01`）。
- 輸出放哪裡、磁碟還剩多少。
- 成品要怎麼看：畫面、聲音、文件、API 回應……（決定 `docs/07` 的常識閘門怎麼寫）。

## 3. 建立 DIRECTOR/ 資料夾

位置：多個 worktree 要共用同一份狀態，所以**預設放在 repo 外、所有 worktree 都看得到的位置**，例如 repo 的上一層 `<WS>/DIRECTOR/`。專案只有一個 checkout、PO 又希望版控時，可以放 repo 內。把你選的位置寫進第一份回報。

```text
DIRECTOR/
  DIRECTOR_OPERATING_RULES.md   本專案版規則：只寫和本規則包不同的地方，其餘寫「照 <RULES>/docs/xx」
  DIRECTOR_STATE.md             總表：專案概況、目前階段、各工作線狀態、下一步
  ACTIVE_WORKSTREAMS.md         誰在做什麼：session 名稱、工單、RESUME_STATE 路徑、模型、effort、優先序
  DECISION_REGISTER.md          從 templates/DECISION_REGISTER.md 建立
  RISK_REGISTER.md              風險、影響、對策、負責人
  DIRECTOR_LOG.md               append-only，每個決定一行，時間從 date 讀
  RESUME_STATE.md               總監自己的（templates/RESUME_STATE.md）
  PO_PENDING.md                 PO 待決頁的檔案版（docs/03；有更好的位置就改用，這份留指向）
  orders/  reviews/  research/
  tools/                        從 <RULES>/tools/ 複製
  director_work.json            從 director_work.example.json 改
```

## 4. CLAUDE.md 加上總監段落

1. 把 `templates/CLAUDE_PROJECT_SECTION.md` 填好，加在專案 `CLAUDE.md` 的最上方，原內容一字不刪。
2. 填空的地方：總監名稱、DIRECTOR 位置、PO 待決頁位置、回報語言、本專案的成品怎麼看。
3. 本機 commit 可以；**push 要 PO 核准**。CLAUDE.md 保持精簡，細節指向 DIRECTOR/ 的檔案。

## 5. 決策登記與總監的 RESUME_STATE

1. PO 在啟動時和 CLAUDE.md 裡給過的指示，逐條登記成 `PO-01`、`PO-02`……，附來源。
2. 寫總監自己的 `RESUME_STATE.md`，頂部四行（PROGRESS / DOING / NEXT_STEP / COMMS）一定要填。

## 6. PO 待決頁

1. 選一個 PO 看得到、不會被聊天洗掉的位置。環境有可共享、可記錄回覆的頁面就用它，否則用 `DIRECTOR/PO_PENDING.md`。
2. 格式照 `docs/03`。第 9、10、12 步產生的問題都放這裡。
3. 從這一步起，總監每一輪的第一個動作都是讀待決頁上 PO 已回覆的項目（`docs/03`）。

## 7. 壓縮門檻（25 萬）

1. 填好 `DIRECTOR/director_work.json`（`window`: 250000，`plugins_off` 先留空）。
2. 報告模式：`python -I -X utf8 DIRECTOR/tools/setup_project_settings.py --repo <REPO> --config DIRECTOR/director_work.json`
3. 確認每個 worktree 都是 `MISSING` 或 `OK`，沒有 `NOT_IGNORED`。有 `NOT_IGNORED` 就停下：代表 `.claude/settings.local.json` 會被 commit，先問 PO 要不要把它加進 `.gitignore`。
4. 寫入：同一行加 `--apply`。再跑一次報告模式，要全部 `OK`。
5. 驗證生效（不花額度）：`python -I -X utf8 DIRECTOR/tools/context_probe.py --cwd <REPO>`，看 `autoCompactThreshold` 是否對應 25 萬視窗。桌面版 session 另看 session 自己回報的上下文視窗（例如用量工具的 contextWindow 是 250000）。
6. 「已設好」只在第 4、5 步都看到結果後才能寫。只寫了檔案不算。

## 8. 量基準（不花額度）

1. `context_probe.py` 的固定成本：各類別 token、記憶檔、skill 數量。
2. 專案已有對話紀錄時：`usage_report.py --since <日期>`。
3. 結果寫進 `DIRECTOR/BASELINE_METRICS.md`，日期從 `date` 讀。之後每週複查用同一套指令比較（`docs/04`）。

## 9. 無關 plugin 清單（問 PO）

1. 從第 8 步的探測結果，列出跟本專案無關的 plugin：名稱（`name@marketplace`）、估計每次呼叫多少 token、為什麼無關、是**使用者自己裝的**還是**桌面版 / claude.ai 帶進來的**。
2. 放上待決頁讓 PO 勾。PO 勾完才寫進 `director_work.json` 的 `plugins_off`，跑 `--apply`，再探測一次確認數字下降。
3. 桌面版 / claude.ai 帶進來的 plugin 和 connector，專案設定關不掉，只能在 claude.ai 設定關，而且會影響所有專案和之後所有新 session 的預設。只列出來，由 PO 決定，總監不動手。

## 10. 記憶索引

1. `python -I -X utf8 DIRECTOR/tools/memory_size_check.py --file <專案記憶索引>`。
2. 超過門檻就照 `docs/09` 整理：先備份整份索引，只移結案和歷史條目，規則類和進行中的條目不動，記憶檔本身不刪。

## 11. 機制清單（給續航用）

把建好的每個機制（壓縮設定、背景計時器、排程任務、監看程序）寫成一張表：擁有者、中斷會怎樣、怎麼檢查、重建指令。放在 `DIRECTOR/GUARDS.md`（`docs/06`）。沒有寫進表的機制，不算建好。

## 12. 工作線編制草案（問 PO）

在 `ACTIVE_WORKSTREAMS.md` 寫草案：要幾條 worker 線、各做什麼、要不要總管和清理員、各線的模型和 effort（`docs/05`）。**開新 session 會花額度，第一批由 PO 同意後才開。**

## 13. 第一份回報給 PO

用 PO 指定的語言（預設繁體中文），先寫結論，20 行左右，細節放檔案：

1. 結論一句：建置完成 / 部分完成（缺什麼）。
2. 建了什麼：DIRECTOR 位置、CLAUDE.md 段落（是否已 commit）、待決頁位置。
3. 驗證結果：壓縮門檻（報告模式 OK 與探測數字）、固定成本基準、記憶索引大小。沒驗證的照實寫 NOT_VERIFIED。
4. 和本專案既有規則的衝突點，以及你照哪一邊做。
5. 待決頁上要 PO 處理的項目代號與一句話摘要（plugin 清單、工作線編制、DIRECTOR 位置……）。
6. 下一步：PO 回覆後要做的第一件事。

## 一定要先問 PO 的事

- push、公開、發布、部署、建立遠端 repo。
- 付費、註冊帳號、登入、換帳號。
- 刪除檔案、分支、tag、worktree、證據。
- 關使用者層或 claude.ai 的 plugin、connector、MCP；改使用者層設定。
- 本專案以外的任何東西：其他 repo、其他專案的 session、系統設定、全域工具。
- 改產品方向、改已核准的階段、換主要技術（引擎、框架、主版本）。
- 宣告最終驗收通過。
