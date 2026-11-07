# WO-<編號> — <短名>
**<一句話目標>**

```text
ISSUED_BY      = 總監  <YYYY-MM-DD HH:MM，讀 date>
REVISION       = 1    # 開工後每改一次 +1，並在 H 節加一列
TRACES_TO      = <這張工單服務的初衷卡、需求或決定編號，逗號分隔，例如 B-2, DD-03；有初衷卡時至少一個 B 編號（docs/12）；沒有寫 NONE>
BRIEF_REVISION        = <選用：初衷卡版次；不用就刪掉這兩行>
BRIEF_FINGERPRINTS_V1 = <選用：gate_check.py --brief BRIEF.md 印的 {"B-2": "<64 位雜湊>"}>
PRIMARY_WORKER = session「<名稱>」
MODEL / EFFORT = <模型> / <medium|high|xhigh>（理由見 docs/05）
FALLBACK       = <同 session 新對話，從 RESUME_STATE 接續 | 其他 worker>
GOVERNANCE     = <Direct | Standard | Strict>
BASE_REF       = <branch @ commit 或 tag>
NEW_BRANCH     = <分支名>
WORKTREE       = <路徑>
WORK_DIR       = <放報告、RESUME_STATE.md、輸出的資料夾>
BUDGET         = <US$0 | PO 核准的金額>
HEAVY_RESOURCE = <無 | 需先 TEST REQUEST：類型、預估分鐘>
```

兩個 `BRIEF_` 欄位是選用的：寫了以後，工單依據的初衷卡列被改掉時，`gate_check.py --order / --match --brief BRIEF.md` 印 `~ BRIEF_STALE`（舊條件驗過，新條件待重驗）；只是提示，不改結果。不寫照樣通過。

## A. 背景
需求、已知事實（附證據等級）、限制。只寫 worker 需要知道的。

## B. 目標
- MUST HAVE：
- OPTIONAL：
- OUT OF SCOPE：

可以改和不准碰的路徑（`tools/scope_check.py` 直接讀這兩份清單）：

```text
SCOPE:
- <相對 repo 根目錄的路徑或 glob，一行一個>
FORBIDDEN:
- <不准碰的路徑或 glob；沒有就寫 NONE>
```

`*` 不跨資料夾，`**` 跨資料夾，沒有萬用字元的名稱連底下全部都算。兩邊都符合時以 FORBIDDEN 為準。不要寫「相關檔案」這種話。

選用：一定要改到的路徑。`scope_check.py` 會查每一條都有對到改動，沒對到就印 `MISSING` 並判越界；每一條都要在 SCOPE 裡、不在 FORBIDDEN 裡（`gate_check.py --order` 會查）。不需要就整段不寫。比的是最後結果（2.2）：改了又改回的不算；總監審查時用 `scope_check.py --order 本工單 --repo <repo> --candidate <候選 commit>`。

```text
REQUIRED_CHANGES:
- <一定要改到的路徑或 glob，例如 src/parser.py>
```

## C. 執行前檢查
repo 與分支、工作樹乾淨、未提交修改、相關規範、相依、實際行為、能否重現、基準測試。路徑不存在先搜尋，不假設。
製作類工單先做既有資產盤點：未合併分支（`git log --all -- <路徑>`）、需求方提供過的檔案、舊報告；結果寫進 TASK REPORT 的 DONE（docs/02）。

## D. 實作要求
沿用現有架構；最小但完整；處理例外；必要的向後相容；補上直接相關的測試；不做無關重構。每項修改做成開關，方便批次驗證（docs/02）。

## E. 驗收條件
| ID | 類型 | 要求 | 驗證方法 | 預期 |
|---|---|---|---|---|
| AC-1 | <AUTO / REVIEW / PO> | | | |

- `AUTO`：有指令可以重跑。總監自己重跑後判定；驗證指令用 `evidence_record.py` 留紀錄。核准的指令寫在下面的 `CHECKS:`（選用，Strict 建議寫），一條 AUTO 一行，JSON 字串陣列、不經 shell；` #` 之後是註解，要保留 ` #` 就把整個項目用反引號包起來；派工雜湊會鎖住它，總監用 `evidence_record.py verify --rerun --order` 跑的就是這一行，worker 用同一個指令記錄（`evidence_record.py run --order <本工單>`）：

```text
CHECKS:
- AC-1: ["python", "-I", "-m", "unittest", "tests.test_parser"]
```

- `REVIEW`：要有人看成品。開工前寫明誰看、從哪個角度看、看多大範圍、看哪些常識閘門項目（docs/07）。worker 最多填 `READY_FOR_REVIEW`。
- `PO`：PO 保留的判定，例如最終驗收。worker 和總監都只填 `PENDING_PO`。同一個 commit 給 PO 看兩份以上成品時，報告寫 `CANDIDATE_ID: <PO_ACCEPTANCE 的 candidate_id>`（2.2）。
- 接手演練、要用 `metrics_report --run --compare` 比較的工單：run 資料夾的 `run.json` 要寫 `sampling` 標記（`complete`、`scenario`），否則比較結果是 UNKNOWN（2.2，`tools/README.md`）。
- 選用的 `追溯` 欄（加在表的最後一欄）：這條 AC 驗證 TRACES_TO 的哪些編號，例如 `DD-03`；沒有寫 `—`。不加這欄也照樣通過；加了之後 `trace_report.py` 每個編號一列，不必猜哪條 AC 服務哪個需求。

結果不寫在這裡，寫在 TASK REPORT 的 ACCEPTANCE 表。成品類交件另附常識閘門表（docs/07）。

## F. 安全與版控
照 docs/08。驗收條件和規格不准改，有問題回報 BLOCKED 由總監裁決（docs/02）。總監派工時記下本檔雜湊，交件時比對；改了會被查出來，但工具擋不住改動。本工單特別禁止：<...>

## G. 交付與停止規則
- DELIVERABLES：<檔案、commit / tag、審查包>
- 完成：一則 TASK REPORT 給總監（templates/TASK_REPORT.md）。
- STOP_RULES：同一根因 2 輪沒進展就停；超出 SCOPE 先問；超過測試上限 10 分鐘先停下回報。

## H. 變更紀錄
只有總監能改本工單。REVISION 1 不用寫；之後每改一次加一列，再把新的雜湊告訴 worker。

| 版本 | 時間 | 誰改 | 原因 | 影響的 AC |
|---|---|---|---|---|
