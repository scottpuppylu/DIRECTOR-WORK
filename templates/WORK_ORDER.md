# WO-<編號> — <短名>
**<一句話目標>**

```text
ISSUED_BY      = 總監  <YYYY-MM-DD HH:MM，讀 date>
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

## C. 執行前檢查
repo 與分支、工作樹乾淨、未提交修改、相關規範、相依、實際行為、能否重現、基準測試。路徑不存在先搜尋，不假設。

## D. 實作要求
沿用現有架構；最小但完整；處理例外；必要的向後相容；補上直接相關的測試；不做無關重構。每項修改做成開關，方便批次驗證（docs/02）。

## E. 驗收條件
| ID | 要求 | 驗證方法 | 預期 | 實際 | 證據 | 狀態 |
|---|---|---|---|---|---|---|
| AC-1 | | | | | | PASS / FAIL / BLOCKED / UNVERIFIED |

成品類交件另附常識閘門表（docs/07）。

## F. 安全與版控
照 docs/08。驗收條件和規格不准改，有問題回報 BLOCKED 由總監裁決（docs/02）。本工單特別禁止：<...>

## G. 交付與停止規則
- DELIVERABLES：<檔案、commit / tag、審查包>
- 完成：一則 TASK REPORT 給總監（templates/TASK_REPORT.md）。
- STOP_RULES：同一根因 2 輪沒進展就停；超出 SCOPE 先問；超過測試上限 10 分鐘先停下回報。
