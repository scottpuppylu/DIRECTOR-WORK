<!-- 貼在專案 CLAUDE.md 最上方。把 <...> 換掉後刪除本行。 -->
## 總監制（Director mode）

本專案用總監制開發，規則包：https://github.com/scottpuppylu/DIRECTOR-WORK（本機：<RULES>）。本專案的規則和 PO 指示永遠優先於規則包。

- **總監**：session「<總監名稱>」，是 PO 的代理人。Worker 接總監的工單（`<DIRECTOR>/orders/WO-*.md`），在 gate 完成、卡住、需要決定時，送一則完整的 TASK REPORT 給總監（`<RULES>/templates/TASK_REPORT.md`）。只有總監說可以時才直接找 PO。
- **狀態寫檔**：每條工作線在自己的工作資料夾維護 `RESUME_STATE.md`，頂部四行 PROGRESS / DOING / NEXT_STEP / COMMS，每個 checkpoint 更新。任何中斷後，先照 `<RULES>/docs/06b_on_demand_procedures.md` 的恢復程序做。
- **訊息**：只在 gate 報告、需要決定、要對方立刻改行動時發；不回 ACK；給同一人的內容一次發完。
- **要 PO 回覆的事**：先報總監（標題 `PO_REPLY_NEEDED`），由總監放上待決頁（<待決頁位置>）。
- **上下文短**：長輸出寫檔、只看結論；大量閱讀和看圖交給 subagent；壓縮前更新 RESUME_STATE，不為了縮上下文換新 session。新 worktree 先跑 `python -I -X utf8 <DIRECTOR>/tools/setup_project_settings.py --config <DIRECTOR>/director_work.json --apply`。
- **品質**：工程狀態和成品狀態分開回報；數字不能代替看成品（<本專案的成品怎麼看>）；成品交件附常識閘門表；每個缺陷最多 3 輪假設驅動修正；不破壞已通過的基準；最終驗收屬 PO，絕不自稱通過。
- **安全**：push、公開、刪除、付費、帳號、使用者層設定都要 PO 核准；不 force push、不 `reset --hard`、不 `git clean`、不用裸 `git stash`；不批次刪證據；只停自己的 PID；測試輸出寫到 <輸出位置>，不寫進 repo。
- **語言**：所有回報用 <繁體中文>；程式碼、檔名、commit 訊息、識別字可用英文。
- **時間**：時間戳一律讀系統時鐘。
