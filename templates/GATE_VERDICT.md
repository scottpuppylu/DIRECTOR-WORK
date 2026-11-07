# GATE VERDICT — <TASK_ID> <gate 名稱>
<YYYY-MM-DD HH:MM，讀 date> 總監
ORDER: <WO-檔名.md> REVISION <n>
CANDIDATE_HEAD: <審查的 commit，40 位，git rev-parse worker 分支>
ORDER_SHA256: <選用：gate_check.py --hash 工單>
REPORT_SHA256: <選用：gate_check.py --hash 報告；寫了之後報告再被改，--match 會印 ~ VERDICT_RECORD>

## A. 判定
<PASS | PASS_WITH_WARNINGS | CONDITIONAL_PASS | PARTIAL | HOLD | BLOCKED | FAIL | NOT_RUN>
分面向：工程 <…> / 成品 <…> / 效能 <…> / 穩定性 <…> / 整合 <…> / PO 驗收：未做（保留給 PO）
下一步：<ACCEPT_AND_CLOSE | CONTINUE_SAME_WORKER | SWITCH_TO_OTHER_WORKER | REQUEST_INDEPENDENT_REVIEW | REQUEST_OWNER_AUTHORIZATION | STOP_AND_REPORT_BLOCKER>

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
