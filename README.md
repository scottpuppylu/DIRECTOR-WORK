# DIRECTOR-WORK

這是一套給 Claude Code 的「總監制」多 session 開發流程：一個叫「總監」的 session 當專案擁有者（PO）的代理人，派工、看證據、裁決，其他 session 依工單實作。

## 30 秒說明

- **PO** 決定方向、預算、公開發布和最終驗收。其他事交給總監。
- **總監** 寫工單、分派給 worker session、審查證據、裁決每個 gate。要 PO 決定的事集中放在一個「待決頁」。
- **Worker** 照工單做事，把進度寫在自己的 `RESUME_STATE.md`。只在 gate 完成、卡住或需要決定時回報。
- **所有狀態寫在檔案裡，不靠對話記憶。** 額度用完、當機或重開機後，每條工作線都能從最後一個 checkpoint 接著做。
- **上下文保持短。** 每次呼叫模型都會重送整段上下文，所以這是額度最大的槓桿：自動壓縮門檻設 25 萬、每個 gate 換新 session、大量閱讀交給 subagent。
- **數字不能代替看成品。** 測試通過不等於成品對。成品要另外看、另外判，最後由 PO 驗收。

本流程源自一個 3D 遊戲專案的實戰（多個 session 同時開發，運作數週）。文中的數字是那個專案量到的案例，換了方案、版本或專案，數字可能不同，請自己量（`tools/`）。

## 在新專案啟用

1. 在新專案的資料夾開一個 Claude Code session，取名「總監」。
2. 把下面的啟動提示詞貼給它。
3. 總監照 `BOOTSTRAP.md` 建置完成後，會給你第一份回報，裡面有要你勾選或決定的事。
4. 你回覆以後，總監開始派工。

### 啟動提示詞（可直接貼）

```text
你是這個專案的「總監」（Development Director），是我（PO）的代理人。
請使用這套流程：https://github.com/scottpuppylu/DIRECTOR-WORK

1. 依序讀 README.md → BOOTSTRAP.md → docs/ 全部（01 到 10）。
2. 照 BOOTSTRAP.md 在本專案建置總監制：DIRECTOR/ 資料夾、CLAUDE.md 的總監段落、
   你自己的 RESUME_STATE、決策登記、PO 待決頁、壓縮門檻設定、記憶索引檢查。
3. 會影響其他專案或使用者層設定的事（關 plugin 或 connector、帳號、付費、推送、
   公開發布、刪除），一律先列清單問我，不要自己做。
4. 建置完成後，照 BOOTSTRAP.md 最後一步給我第一份回報，用繁體中文。

本專案已有的規則（CLAUDE.md、我給過的指示）永遠優先於這套流程。
兩者衝突時照本專案的規則做，並在回報裡列出衝突點。
```

## 檔案地圖

「每輪必讀」是總監每次恢復或換新 session 時要讀的；「需要時才讀」只在做那件事時讀。檔案寫得短，讀它本身就省額度。

| 檔案 | 內容 | 何時讀 |
|---|---|---|
| `README.md` | 本檔 | 第一次 |
| `BOOTSTRAP.md` | 新總監第一輪的逐步建置清單 | 第一次 |
| `docs/01_roles_authority.md` | 角色、權限、總監可自行決定與必須送 PO 的事 | **每輪必讀** |
| `docs/02_work_orders_gates.md` | 工單、gate、TASK REPORT、裁決、測試排程與預算 | 派工、裁決時 |
| `docs/03_communication.md` | 什麼時候發訊息、PO 待決頁、PO 訊息不漏讀 | **每輪必讀** |
| `docs/04_quota_efficiency.md` | 額度成本模型、省額度的槓桿、怎麼量 | 設定時、每週複查時 |
| `docs/05_models_effort.md` | 模型與思考程度（effort）怎麼選 | 開新工作線時 |
| `docs/06_resume_lossless.md` | RESUME_STATE、中斷後恢復、額度重置喚醒 | **每輪必讀**（恢復時） |
| `docs/07_quality_gates.md` | 工程與成品分開、盲審包、常識閘門、修正上限 | 審查成品時 |
| `docs/08_safety_rules.md` | 要 PO 核准的事、git 與檔案的禁止事項 | **每輪必讀** |
| `docs/09_memory.md` | 記憶索引的大小與整理 | 每週、超過門檻時 |
| `docs/10_lessons_learned.md` | 原專案的教訓 | 第一次；寫新規則前 |
| `templates/` | CLAUDE.md 段落、工單、報告、RESUME_STATE、測試申請、決策登記、裁決 | 建置與派工時 |
| `tools/` | 設定寫入、免費探測、用量統計、記憶大小檢查；交件檢查（格式、範圍、證據紀錄） | 見 `tools/README.md` |
| `director_work.example.json` | 工具設定範例 | 建置時 |

## 原則

- **PO 的專案特有規則永遠優先。** 這套流程是預設值，不是更高層的規則。
- 這套流程只管總監被任命的那個專案。其他專案、使用者層設定、全域工具，都要 PO 決定。
- 規則都是「規則 → 為什麼」。改規則時，把「為什麼」一起改。

## 授權

MIT，見 `LICENSE`。
