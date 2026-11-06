# 06 無損續航

目標：額度用完、錯誤、當機、重開機、PO 手動停止之後，每條工作線都從最後一個已驗證的 checkpoint 接著做，不重做已完成的事，也不沿用半成品。

## 規則

### RESUME_STATE.md

- 每條工作線在自己的工作資料夾根目錄維護一份（`templates/RESUME_STATE.md`），路徑登記在 `ACTIVE_WORKSTREAMS.md`。
- **頂部固定四行**，只看這四行就要能接手：
  ```text
  PROGRESS: 做到哪裡（最後完成的一步、commit、證據路徑）
  DOING: 正在做什麼（屬於哪張工單的哪一項）
  NEXT_STEP: 接下來的精確動作，可以直接照做
  COMMS: 我在等誰（等什麼）／誰在等我（欠誰什麼）／做完要通知誰；沒有就寫 NONE
  ```
- 下面的欄位照 `templates/RESUME_STATE.md` 逐欄寫齊，沒有就寫 NONE；IN_FLIGHT 要列出背景程序、自己設的計時器和等待程序。
- **何時更新**：每個 checkpoint commit 之後、送 TEST REQUEST 之前、背景程序啟動和結束時、收到總監決定時、壓縮之前。寫完才做下一步。
- `UPDATED` 時間一律讀系統時鐘（`date`），不估計。
- 寫完用 `tools/gate_check.py --resume <檔案>` 檢查四行有沒有寫齊。它只看格式，內容對不對還是要靠 `LAST_VERIFIED_CHECKPOINT` 和 repo 核對。
- 平常就要做，不是快停才做：有成果就 commit。進度不能只留在對話裡。

### 恢復

任何 session 被打斷後（包括 PO 手動停止後再繼續），第一件事照 `docs/06b` 的恢復程序做。中斷的擷取、量測、打包、匯入一律重做，不沿用。

### 總監自身的恢復

1. 讀待決頁上 PO 已回覆的項目和新留言（`docs/03`）。
2. 讀 `DIRECTOR_LOG.md` 最後 30 行，找出還沒處理完的 PO 指示。
3. 讀 `ACTIVE_WORKSTREAMS.md`、未讀的 worker 訊息；有 session 清單工具就對照各 session 的狀態。
4. 跑機制檢查腳本，缺的重建。
5. 補發被中斷的工單或決定。

### 機制與重置喚醒

每個排程和防護機制都要有檔案紀錄、檢查方法、重建指令，寫在 `DIRECTOR/GUARDS.md`，總監每次喚醒、壓縮或恢復後先跑檢查腳本。建立或修改機制、設定額度重置後的喚醒時，讀 `docs/06b`。

## 為什麼

- 四行頂部是因為恢復時最需要的就是這四件事，而且它們要能在幾秒內讀完。
- 其他理由見 docs/10。
