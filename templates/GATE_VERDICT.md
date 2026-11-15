# GATE VERDICT — <TASK_ID> <gate 名稱>
<YYYY-MM-DD HH:MM，用 ran_line.py --stamp 印，不手打（2.2.5）> 總監
ORDER: <WO-檔名.md> REVISION <n>
CANDIDATE_HEAD: <審查的 commit，40 位，git rev-parse worker 分支>
ORDER_SHA256: <選用：gate_check.py --hash 工單>
REPORT_SHA256: <選用：gate_check.py --hash 報告；寫了之後報告再被改，--match 會印 ~ VERDICT_RECORD>
SESSION_ID: <寫這份裁決的 session id；要和 TASK REPORT 的不同，相同 gate_check.py --sequence 判 FAIL（2.2.5）>

## A. 判定
<PASS | PASS_WITH_WARNINGS | CONDITIONAL_PASS | PARTIAL | HOLD | BLOCKED | FAIL | NOT_RUN>
分面向：工程 <…> / 成品 <…> / 效能 <…> / 穩定性 <…> / 整合 <…> / PO 驗收：未做（保留給 PO）
下一步：<ACCEPT_AND_CLOSE | CONTINUE_SAME_WORKER | SWITCH_TO_OTHER_WORKER | REQUEST_INDEPENDENT_REVIEW | REQUEST_OWNER_AUTHORIZATION | STOP_AND_REPORT_BLOCKER>
自己查證的證據（寫這份裁決的人自己跑的檢查：指令 + 結果，用 `ran_line.py` 印，不手打；2.3.0）：
- `<指令>` exit=<n> at=<HH:MM>
沒有這一行（或只有範例佔位），判定不能寫 PASS / PASS_WITH_WARNINGS / CONDITIONAL_PASS。`gate_check.py --verdict` 依專案設定 `verdict_self_check`：`warn`（2.3.x 預設，印 WARN）或 `fail`（判 FAIL）。worker 報告裡的指令不算。

## B. 已證實成果
| 項目 | 證據路徑 | 證據等級（VERIFIED_LOCAL / REPORTED / …） | 依 worker 報告？ |
|---|---|---|---|

總監重跑過的 AUTO 條件（`evidence_record.py verify --rerun` 印的 `LOG_LINE:`，整行也貼進 DIRECTOR_LOG；2.2）：
```text
EVIDENCE_RERUN <WO-ID> <AC> candidate=<40 位> result=ok record=<檔名>
```
重跑時加了 `--brief` 的，行尾多 `brief=ok|stale|unconfirmed`，照印出的整行貼；`stale` / `unconfirmed` 不算總監重跑過。

## C. 問題
- P0：
- P1：
- P2：

## D. 取捨
選了什麼、放棄什麼、為什麼。

## E. 下一張工單
`<DIRECTOR>/orders/WO-<編號>-<短名>.md`

## F. 停止狀態
NO MERGE / NO PUSH / NO FINAL ACCEPTANCE（除非 PO 另行核准，寫明核准來源）
這份裁決之後再改程式碼（不只文件），要再審、寫一份指向新 commit 的裁決；`gate_check.py --after-verdict` 預設判 FAIL（2.2.5）。

## G. 最終驗收清單（只有最終裁決填，2.2.5）
- 公開入口（ENTRY_POINT）：<交付物唯一的公開入口：CLI 指令或可呼叫的函式>
- 端到端證據：`evidence/E2E/<檔名>`：lead 照規格的情境，從上面的入口實際跑一次；每份紀錄寫一行 `ENTRY_POINT: <入口>`
- `gate_check.py --final <DIRECTOR 資料夾>` 的結論行：<原樣貼上；FAIL 不能給最終 PASS>
- DD 驗收案例：DECISION_REGISTER 每條 DD 的「驗收案例」都有對應的端到端案例和精確期望數字；`~ WARN DD_CASE` 的逐條寫原因
