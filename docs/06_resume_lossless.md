# 06 無損續航

目標：額度用完、錯誤、當機、重開機、PO 手動停止之後，每條工作線都從最後一個已驗證的 checkpoint 接著做，不重做已完成的事，也不沿用半成品。

## 規則

### RESUME_STATE.md

- 每條工作線在自己的工作資料夾根目錄維護一份（`templates/RESUME_STATE.md`），路徑登記在 `ACTIVE_WORKSTREAMS.md`。
- **頂部固定四行** `PROGRESS / DOING / NEXT_STEP / COMMS`，只看這四行就要能接手。其餘欄位照範本逐欄寫齊，沒有就寫 NONE；IN_FLIGHT 列背景程序（PID、啟動時間、輸出檔、完成判定）、計時器和等待程序。
- **何時更新**：每個 checkpoint commit 之後、送 TEST REQUEST 之前、背景程序啟動和結束時、收到總監決定時、壓縮之前。寫完才做下一步。
- `UPDATED` 時間一律讀系統時鐘（`date`），不估計。
- 寫完用 `tools/gate_check.py --resume <檔案>` 檢查格式和大小（超過照 `docs/06b` 把舊紀錄原文搬走，近期不動）；內容對不對要靠 `LAST_VERIFIED_CHECKPOINT` 和 repo 核對。
- 有成果就 commit，不是快停才做；進度不能只留在對話裡。

### 恢復

任何 session 被打斷後，第一件事照 `docs/06b` 的恢復程序做。中斷的擷取、量測、打包、匯入一律重做，不沿用。

### 每輪第一步

總監每次喚醒、壓縮或恢復後只有一個第一步：先唯讀跑檢查腳本、收集輸入（含待決頁、選擇頁），再處理待決頁。見 `docs/06b`。

### 機制與重置喚醒

每個排程和防護機制都要能重建（`DIRECTOR/GUARDS.md`）；建立、修改機制或設重置喚醒時讀 `docs/06b`。

## 為什麼

- 其他理由見 docs/10。
