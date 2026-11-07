# 12 只靠聊天做出成品：模式、初衷卡、選擇頁

服務 `PURPOSE.md` 初衷 8。不列入每輪必讀：建置時讀一次，談需求、開選擇題、寫工單時再讀。

## 規則

### 一、先選模式

1. 使用者貼完啟動提示詞，總監的**第一則回覆只問一題**：一般模式還是小白模式。各附一句說明：
   - **一般模式**：會看到 plugin、工作線、設定這類技術問題，由你決定。
   - **小白模式**：你只要說想做什麼、看起來對不對；技術的事總監照預設決定，做完告訴你。
   啟動提示詞已經寫明模式，就不再問。
2. 記錄：第 3 步建好 `DIRECTOR/` 後，寫進 `director_work.json` 的 `"mode": "general"` 或 `"beginner"`，和 `DIRECTOR_OPERATING_RULES.md` 開頭；在 `DECISION_REGISTER.md` 登記成 PO 指示。使用者之後隨時能換模式，換了照樣登記。
3. 兩種模式的安全底線一樣：推送、公開、付費、刪除、帳號、影響其他專案的設定，都要使用者同意（`docs/08`）。小白模式只是把問法換成白話，例如「要把成品放到網路上讓別人看嗎？」，不是跳過。

### 二、小白模式改了哪些步驟

| BOOTSTRAP 步驟 | 一般模式 | 小白模式 |
|---|---|---|
| 6 待決頁 | `PO_PENDING.md`；要用外部頁面先問 | 用選擇頁（下面第四節）；在 Claude Desktop 以外用不了就用 `PO_PENDING.md`，聊天裡用白話問 |
| 7.7 `hook_guard.py` | 問要不要裝 | 不問、不裝 |
| 9 無關 plugin | 列清單問 | 不問；`plugins_off` 留空，什麼都不關 |
| 12 工作線編制 | 草案問 PO | 總監照 `docs/05` 定第一批（通常一條 worker 線），登記 DD，寫進初衷卡「由總監決定的事」 |
| 13 第一份回報 | 六點，含技術數字 | 三句白話：準備好了、接下來要聊需求、有什麼要你點頭的；技術細節只寫在檔案 |
| 每次問問題 | 可以問技術問題 | 只問「要做什麼、像什麼、好不好、可不可以」；問不出白話的，總監自己決定並登記 DD |

### 三、談需求，寫專案初衷卡

1. 開工前一定先有 `DIRECTOR/BRIEF.md`（`templates/BRIEF.md`），兩種模式都一樣。已有 `LOCKED` 的卡就跳過這一節。
2. 一次問一到三題，用使用者的話，從大到小：做給誰、要做出什麼、一定要有的、絕對不要的、做完長怎樣。使用者說不清楚時，給兩三個具體例子讓他挑，不要用術語追問。
3. 談到表裡每一列都填得出來，就把整張卡用白話貼給使用者看，問「這樣對嗎？」。使用者說對，才把狀態改成 `LOCKED`、記下時間（讀系統時鐘）、在 `DECISION_REGISTER.md` 登記。沒說對之前不派任何工單。
4. **鎖定後只有使用者能改。** 總監發現需要改（做不到、互相矛盾、使用者後來說的話跟卡不一樣），在選擇頁開一題問，不自己改。改了版次 +1，再請使用者確認一次。
5. 有選擇頁時，把卡的摘要同步寫進 db 的 `brief/current`，讓使用者隨時看得到。

### 四、選擇頁：要使用者選的放這裡

適用：中途有兩個以上做法、使用者看了才能決定的事，例如 A 風格或 B 風格、版面、配色、角色長相。不適用：純技術選擇（總監自己決定）、要使用者動手的事（照 `docs/03` 待決頁）。

前提：先問 PO，PO 同意且工具可用才發布；否則走聊天和本機 `PO_PENDING.md`（和 `BOOTSTRAP.md` 步驟 6、`docs/11`「選擇頁的授權與備援」一致）。

1. **發布**：複製 `templates/choice_page.html`，用 Artifact 工具發布，`capabilities` 給 `{"db": {}, "user": {}, "assets": {}, "comments": {}}`（`comments` 用來叫醒總監，見第六節），`icon` 用 `checklist`。私人頁面，只有使用者看得到；網址寫進 `DIRECTOR_OPERATING_RULES.md`，第一份回報附上。
2. **開題**（2.1 起）：題目內容和題目狀態分開放。先用 `ArtifactData` 寫一筆版本 `choiceRevisions/<編號>-r<版>`，寫了就不再改：

   ```json
   {"questionId": "CH-01", "revision": 1, "snapshotHash": "sha256:<register 印出的值>", "brief": ["B-2"],
    "title": "主畫面要哪一種風格？", "question": "兩種都照初衷卡 B-2 做，差在感覺。",
    "options": [{"key": "A", "label": "A 明亮", "desc": "白底、大字", "image": {"url": "<圖>", "caption": "A 的主畫面"}},
                {"key": "B", "label": "B 沉穩", "desc": "深色、細線", "image": {"url": "<圖>", "caption": "B 的主畫面"}}],
    "recommended": "A", "why": "B-1 說主要在白天用手機看，亮底比較清楚。"}
   ```

   再寫 `decisions/<編號>`：`{"code": "CH-01", "status": "open", "priority": 1, "revision": 1, "snapshotHash": "sha256:…"}`。
   - `snapshotHash` 用 `choice_reconcile.py register --snapshot <這一版的 JSON>` 算，同一份也記進本機帳本（第六節）。
   - **改題就開新版**：寫 `CH-01-r2`，再把 `decisions/CH-01` 的 `revision`、`snapshotHash` 改成新版。不要改舊版的內容；使用者對舊版的回覆仍照舊版的選項讀。
   - 每題都要有 `brief`（對到哪幾條 B）、`recommended` 和 `why`（總監建議和理由，用使用者的話）。對不到初衷卡的題目不要開，先回頭問要不要改卡。
   - 圖：先截真實成品的圖，用 Artifact 工具 `asset: true` 上傳到這一頁，`url` 用上傳結果給的網址。不要用示意圖假裝是成品。
   - 一題只問一件事；選項最多四個。
   - 2.0 開的舊題（`decisions` 裡直接放題目、沒有 `revision`）照樣能看能答；頁面標「舊題，當時選項未留存」，因為那時沒有存下使用者當時看到的選項。
3. **頁面送出什麼**：
   - 新題：頁面新增一筆 `choiceReplies`：`{"kind": "choice", "submissionId", "questionId", "revision", "snapshotHash", "choice", "selectedOptionSnapshot": {"key", "label", "desc"}, "note", "clientAt"}`。只新增、不改 `decisions`。同一個 `submissionId` 是同一次送出（網路重試），不是第二個答案。
   - 舊題：照 2.0 改 `decisions/<編號>` 為 `answered`，`answer` 多一個 `submissionId`。
   - 留言：新增 `notes`：`{"kind": "note", "submissionId", "text", "at", "status": "new"}`。
   - 頁面保證：重畫不會吃掉打到一半的字、游標和選取範圍；輸入法選字時不重畫；送出中同一題按不了第二次；送出前用最新資料確認題目還開著、選項還在；存好後只有字沒被改過才清空。這些由 `selftest.py` 的 `test_choice_page` 檢查。
4. **讀回覆**：每一輪第一個動作，用 `ArtifactData` 讀 `choiceReplies`、`decisions`（舊題看 `status == "answered"`）和 `notes`（`status == "new"`），存成一份 JSON，跑 `choice_reconcile.py ingest`，照第六節處理。
5. 聊天裡只說一句「選擇頁新增了 CH-01」，不在聊天裡重複整題。

### 五、不做歪的檢查

1. 每張工單的 `TRACES_TO` 寫它服務的 B 編號（可以和 DD、OD 並列）。選擇頁的決定派出的工單，另外寫上題號和版，例如 `CH-01 r2`，工單編號用 `choice_reconcile.py plan` 給的那一個。
2. 派工前、每個 gate 前跑：

   ```text
   python -I -X utf8 <WS>/DIRECTOR/tools/trace_report.py --orders <WS>/DIRECTOR/orders --reports <報告資料夾> --decisions <WS>/DIRECTOR/BRIEF.md --decisions <WS>/DIRECTOR/DECISION_REGISTER.md
   ```

   - 「TRACES_TO 找不到的編號」有東西：工單對到不存在的需求，改工單。
   - 「沒有工單的需求」有東西：還有沒做的需求，排進下一批，或問使用者是不是不要了。
3. 成品交件時，對著初衷卡每一列的「怎麼算做到」檢查，結果寫進 gate 報告；最後由使用者看成品說「對」。

### 六、選擇頁不漏讀

選擇頁和待決頁一樣不准漏讀（`docs/03`「PO 的訊息不漏讀」）。也不准重複做：同一題同一版只派一張工單。

1. **送出就叫醒**：使用者在頁面送出回覆或留言時，頁面用 comments 的 `sendToClaude` 留一則給總監的訊息，掛在頁面固定的標題上（不掛在會重畫的卡片上）。訊息只寫「選擇頁有新回覆：CH-01（第 2 版）」，不帶使用者寫的內容；內容一律從 db 讀。總監的對話開著、而且這一頁的監看是「auto-replies armed」時，總監馬上被叫醒。
   - 發布後、每次恢復（壓縮、換對話）後，用 `ArtifactComments` 列出監看，確認選擇頁是 armed。不是的，請使用者在聊天裡貼一次選擇頁網址，再用 `ArtifactComments` 的 watch 打開。
   - 叫醒只是加速。對話沒開、通知沒送到，第四節第 4 步照樣會在下一輪第一個動作讀到。但沒有人開始下一輪時不會被讀到：頁面會照實寫「沒有人開始下一輪時不會被讀到，請在聊天提醒總監」，使用者要在聊天說一聲。
2. **先記帳再動手**：本機帳本 `<WS>/DIRECTOR/choice_inbox.sqlite3`，用 `tools/choice_reconcile.py`：

   ```text
   python -I -X utf8 <WS>/DIRECTOR/tools/choice_reconcile.py ingest --db <WS>/DIRECTOR/choice_inbox.sqlite3 --export <讀回來的 JSON>
   python -I -X utf8 <WS>/DIRECTOR/tools/choice_reconcile.py plan --db <WS>/DIRECTOR/choice_inbox.sqlite3 --question CH-01 --revision 2 --orders <WS>/DIRECTOR/orders
   python -I -X utf8 <WS>/DIRECTOR/tools/choice_reconcile.py advance --db <WS>/DIRECTOR/choice_inbox.sqlite3 --question CH-01 --revision 2 --from QUEUED --to CLAIMED --session <你的名字>
   ```

   - `ingest` 把每筆回覆記一列，標出重複、同題不同答案、舊版、hash 不符、選項不存在。只有 `ok` 和 `legacy` 能派工；其他的照實回給使用者（寫回條 `resolution`），不要猜。
   - `plan` 給這一題這一版固定的工單編號；再跑一次還是同一張。工單照這個編號寫。
   - 狀態：`RECORDED → PLANNED → QUEUED → CLAIMED → RECEIPT_PENDING → CLOSED`。`advance` 只在狀態還是 `--from` 時才改；兩個總監同時接手，只有一個成功，另一個拿到 `LOST`，就不要再做。做到一半不知道有沒有做完的，改成 `RECONCILE`，先查證再決定。
   - 沒被採用的那幾列用 `settle` 結案：留言讀過 `--to NOTED`；被新回覆取代 `--to SUPERSEDED`；重複、衝突、不合格的回覆照實回給使用者後 `--to CLOSED`。已關閉的 2.0 舊答案直接記成 `CLOSED`。
   - 2.1 是 shadow：帳本只提示、不擋任何工具；資料壞了只印一行 `CHOICE_RECONCILE: SHADOW_ERROR <原因>`，exit 0。沒跑帳本不算違規，但重複派工要自己負責。
3. **回條**：總監每走一步，新增一筆 `choiceReceipts`：`{"questionId", "revision", "submissionId", "stage", "at", "wo", "resolution"}`，`stage` 是 `seen`、`claimed`、`handed`、`closed`。舊題照 2.0 也寫 `decisions` 的 `seenAt`，處理完改 `closed` 並寫 `resolution`、`closedAt`；留言改成 `read`。
   - 2.1 新題的選項讀不到時（`choiceRevisions` 還沒載入或沒有這一版），頁面顯示「載入中」或「這一版選項讀不到，請在聊天告訴總監」，不能送出。圖片和影片的網址只接受 `https:`、`/_blob/` 和相對路徑。
   - 頁面上每一筆回覆顯示三種狀態：沒有回條是「已儲存，等總監讀取」；`seen` 或 `claimed` 是「總監已收件，處理中」；`handed`、`closed` 或題目已關是「已交接／處理完成」。
   - 逾時分兩種：存好超過 10 分鐘還沒有回條，標「（沒收到）」，是叫醒或讀取出了問題；收件超過 30 分鐘還沒交接，標「（收到但卡住）」，是處理出了問題。使用者看得到卡在哪一步，可以在聊天裡提醒。
   - 處理晚了照實寫在 `resolution`：幾點才讀到、晚了多久。
4. 處理完，把叫醒用的留言串用 `ArtifactComments` resolve 掉。
5. 每輪結束前自查：跑 `choice_reconcile.py status`，`not_handed`、`stuck`、`receipts_pending`、`notes` 都是 0；選擇頁沒有「已回覆卻沒關閉」的題目。有總管時，總管例行查的「已回覆超過 10 分鐘還沒關閉」也包含選擇頁。

## 為什麼

- 使用者想做的東西會在對話裡慢慢變形：每一輪的小決定單看都合理，加起來卻偏離一開始想要的。把一開始的需求寫成使用者確認過、只有他能改的卡，每張工單都對回去，偏掉時馬上看得到。
- 風格這類選擇用文字很難描述，使用者看圖才知道要哪個；放在獨立的頁面，使用者有空時點一下就好，也不會在對話裡被其他訊息沖掉。
- 不懂技術的人被問「要不要關這個 plugin」只會卡住。小白模式把這些交給總監的預設，使用者只回答自己真的能回答的事。
