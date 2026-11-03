# 04 額度與效率

## 成本模型

- **每一次模型呼叫，都會把整段上下文再送一次。** 一次工具呼叫 = 一次呼叫。所以成本 ≈ 呼叫次數 × 當時的上下文長度。
- 上下文 = 固定成本（系統工具、工具清單、記憶檔、skill 清單、CLAUDE.md）+ 對話累積（每個工具輸出、每張圖都留著，直到壓縮）。
- 讀入多半是快取讀取。快取有效期有限（原專案觀察約 1 小時沒用就失效），壓縮、設定變動、工具清單變動也會讓快取重建。快取讀取對週額度的確切權重沒有公開。
- 跨 session 訊息和定時任務，每次都會讓對方開一輪完整上下文。

### 原專案的實測案例（數字照抄，你的專案請自己量）

- 每次呼叫的上下文中位數 46.5 萬 token；上下文 ≥ 25 萬的呼叫，佔全部讀入的 92%。
- 每次呼叫的固定成本約 4.1 萬：系統工具 1.55 萬、延後載入的工具清單約 2 萬、記憶檔 1.23 萬、skill 清單約 9.9k（skill 清單有上限，skill 變少 token 不一定變少）。
- 圖片留在上下文裡，之後每次呼叫都重送。
- Bash 輸出佔所有工具結果字元數的 6 成。
- subagent 佔 15% 的呼叫，只佔 5% 的讀入。
- 記憶索引從 8.4k 壓到 2.5k token。

## 規則（依效益排序）

1. **自動壓縮門檻 25 萬（每個專案、每個 worktree）**
   - 在專案的 `.claude/settings.local.json` **同時**寫：
     ```json
     { "autoCompactWindow": 250000, "env": { "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "250000" } }
     ```
   - 單獨跑 CLI 時，只寫 `autoCompactWindow` 就有效；桌面版只有環境變數確定有效（桌面版的原因是推論，沒有隔離證明）。兩個都寫最保險。官方允許 10 萬到 100 萬。
   - `settings.local.json` 通常被 git 排除，所以每個新 worktree 都要重新寫入。用工具：`tools/setup_project_settings.py`，不要手寫。
   - 使用者層設定不動。
   - 驗證：用 `tools/context_probe.py` 看 `autoCompactThreshold`；桌面版看 session 回報的上下文視窗是不是 250000（如果是 100 萬就是沒生效）。
2. **每過一個 gate 就換新 session 接手**：先更新 RESUME_STATE 四行和工單進度，新 session 照 `docs/06` 接手。不要一個 session 連做好幾天。
3. **大量閱讀交給 subagent**：長 log、整份文件、大量搜尋結果，交給 subagent 讀完回傳結論，主 session 不吞原文。
4. **一次做完多步**：互不依賴的工具呼叫放在同一則回覆；多步檢查寫成一支腳本一次跑完。每多一次呼叫，就多付一次整段上下文。
5. **長輸出寫檔，對話只放結論**
   - 預期超過約 50 行的指令輸出、log、JSON、搜尋結果，一律導到檔案，對話只看 `tail`、計數或一行結論。
   - 新腳本預設只印結論，細節加 `--verbose`。
   - 讀長檔用 offset / limit；網頁擷取要帶明確問題，不整頁拿回來。
6. **看圖在短上下文做**：一次要看 3 張以上、或看連續影格時，交給新開的 subagent 或短 session，主 session 只收結論和疑點清單，自己只開少數疑點裁切。
7. **固定成本瘦身**
   - CLAUDE.md 目標 200 行內；細節放在需要時才讀的文件或 skill。
   - 記憶索引 < 3k token（`docs/09`）。
   - 和本專案無關的 plugin：用專案設定 `"enabledPlugins": {"name@marketplace": false}` 只在本專案關掉**使用者自己安裝的** plugin，其他專案不受影響（原專案實測）。
   - 桌面版 / claude.ai 帶進來的 plugin，專案設定關不掉，只能在 claude.ai 設定關，會影響所有專案；claude.ai connector 的開關也會變成所有新 session 的預設。**這兩類由 PO 決定。**
   - 不用的 MCP 也一樣：先列清單和估計 token，給 PO 勾。PO 說不關的，之後不要再自動提議。
8. **少叫醒**：定時檢查間隔用 30 分鐘而不是 5 分鐘；等待用背景程序或閒置通知（`docs/03`）。
9. **routine 工作線用較省的模型**（`docs/05`）。

## 週額度收尾

- **「全速」不等於思考和 token 可以隨便用。** 不因額度快用完就停工，額度到上限就停，重置後接續；但思考程度照 `docs/05`，不發沒有行動價值的訊息、不重複研究、不做無謂的測試。
- 週額度用好用滿：重置時接近用完、而且用在有價值的工作上，剩下沒用也是浪費。預估用不完時，向 PO 建議把排隊中的關鍵工作提前或加開工作線（PO 同意才開）。
- **98%**：開始收尾。能在額度用完前完成的就完成，所有工作存檔。
- **99%**：確定做不完。總監通知所有人強制存檔：本機 commit、更新 RESUME_STATE 四行、停掉自己的排程，等重置後恢復（`docs/06`）。

## 怎麼量（不花額度）

- **固定成本**：`tools/context_probe.py`。原理是把兩行 control request 餵給 `claude --input-format stream-json --output-format stream-json --verbose --no-session-persistence`：
  ```text
  {"type":"control_request","request_id":"i1","request":{"subtype":"initialize"}}
  {"type":"control_request","request_id":"c1","request":{"subtype":"get_context_usage"}}
  ```
  讀 `c1` 的回應（categories、autoCompactThreshold、skills、memoryFiles）。**不呼叫模型。**
- **絕對不要用 `claude -p "/context"` 量**：那會真的呼叫模型、花額度。
- **歷史用量**：`tools/usage_report.py` 讀本機對話紀錄的 usage 欄位，只彙總數字，不印內容。
- **讀不到數字不等於 0，估計值不能當實測。** 拿不到就寫 `UNKNOWN`，估的就標 `ESTIMATED`。上下文變小也不等於額度省了：改完重量一次，用同樣的工具比前後的數字，才算省到。

## 週期性複查

- 每週一次（或額度重置時）：跑 `usage_report.py` 和 `context_probe.py`，和上週的 `BASELINE_METRICS.md` 比較：每次呼叫上下文中位數、≥25 萬的讀入比例、固定成本、圖片數、Bash 輸出量。
- 壓縮太頻繁、工作線一直重讀同樣的檔案，就調整門檻（10 萬到 100 萬之間）。
- 新 session 第一次呼叫就很大（原專案中位數 22 萬），代表恢復時帶了太長的摘要：壓縮前先把狀態寫進 RESUME_STATE，讓摘要可以短。

## 為什麼

- 原專案先以為訊息太多是主因，量了才知道是上下文太長：同一則訊息，上下文 50 萬時的成本是 5 萬時的十倍。
- 壓縮門檻是單一最大槓桿，因為它同時壓低每一次呼叫。
- 換新 session、subagent、長輸出寫檔、短上下文看圖，都是同一件事：不讓原文留在主上下文裡被重送幾百次。
- 固定成本每次呼叫都付，幾千 token 乘上幾千次呼叫就很可觀；但會影響其他專案的開關，不是總監能決定的。
- 量測要不花額度，否則量測本身就變成成本。
