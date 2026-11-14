# HANDOFF — <WO-編號> <worker 名稱>（2.2.5）
<YYYY-MM-DD HH:MM，用 ran_line.py --stamp 印> 停下原因：<到 80 輪 | context 到 60% | 工單寫的上限 | 其他：…>

worker 到上限就停，寫這份交給 lead；lead 開新的 worker 從這裡接續，不讀原 worker 的完整過程（`docs/02`）。
一份不超過 40 行，細節寫在下面列的檔案裡。

```text
BRANCH / HEAD: <分支> <git rev-parse HEAD 的 40 位>   WORKTREE_CLEAN: <yes | no：沒 commit 的檔>
RESUME_STATE: <路徑>
DONE:      <做完的項目，一項一行，附證據路徑或 commit>
REMAINING: <還沒做的項目，照工單 AC 編號>
NEXT:      <接手的人第一步做什麼（一句）>
FILES:     <接手要讀的檔案路徑，最少的那幾個>
RISKS:     <做到一半、容易做錯或已經試過不行的地方；沒有寫「無」>
```
