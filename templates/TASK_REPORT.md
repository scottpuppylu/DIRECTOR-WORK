# TASK REPORT（一個 gate 一則，一次寫完整）

```text
首行：<一句話結論>
TASK_ID / WORKER / MODEL / BRANCH / BASE / HEAD / WORKTREE_CLEAN(yes|no)
  HEAD 寫 git rev-parse HEAD 的完整 40 位（Strict 一定要 40 位，總監拿它和審查的 commit 比）
ORDER: <WO-檔名.md> REVISION <n>（REVISION 要和工單現在的相同）
ORDER_SHA256: <開工時跑 gate_check.py --hash 工單 的 64 位輸出>
CANDIDATE_ID: <給 PO 看的成品 id，和 PO_ACCEPTANCE 紀錄的 candidate_id 相同；同一個 commit 有兩份以上成品時必填，只有一份可省>
  成品的 commit、入口檔與其 SHA-256、manifest 的 SHA-256 以 PO_ACCEPTANCE 紀錄為準，報告不重抄；trace_report 靠這個 id 找到那筆紀錄（2.2.0）
RESULT: PASS | PARTIAL | BLOCKED | FAIL
  ENGINEERING: ...
  PRODUCT（成品）: ...
  PERFORMANCE: ...
  STABILITY: ...
DONE: 完成項目，每項附證據路徑
TESTS: 實際執行的測試與結果；沒跑的寫 NOT_RUN
SCOPE_CHECK: PASS | VIOLATION | NOT_RUN，貼 scope_check.py 的最後一行
EVIDENCE: 重跑指令與產物雜湊的紀錄路徑（evidence_record.py）；沒有就寫 NONE: 原因
AUDIT_RANGE: （選用）audit_log.py cite 印出的那一行；有裝動作紀錄才寫
SESSION_ID: （選用）本 session 的 session_id；有裝動作紀錄才寫
RAN: （選用）一行一個實際跑過的指令：- `指令` exit=N at=HH:MM
  總監用 report_vs_audit.py 拿 RAN 和 TESTS / EVIDENCE / DONE 裡的 selftest、Unity、Blender、雜湊指令對動作紀錄
  自寫腳本和暫存輸出放 WORK_DIR，不放 scratchpad 或系統暫存資料夾（算工作區外，總監重跑不到；docs/02）
ACCEPTANCE: 工單 E 節每條一列，不增不減。狀態：AUTO 填 PASS / FAIL / BLOCKED / UNVERIFIED；
  REVIEW 最多填 READY_FOR_REVIEW；PO 只填 PENDING_PO。AUTO 填 PASS 時證據欄寫 evidence_record 的 .json 檔名。
  交件前跑 gate_check.py --match 本報告 工單 --evidence-dir 證據資料夾
| ID | 實際 | 證據 | 狀態 |
|---|---|---|---|
| AC-1 | | | |
COMMON_SENSE_GATE: 表格路徑（成品類必附）
UNVERIFIED:
KNOWN_ISSUES:
FAILED_ATTEMPTS: 試過但失敗的方法（避免下一個人重試）
PACKS: 路徑 + SHA-256
DECISIONS_NEEDED: 送總監（技術）或標明「PO 保留」；要 PO 看的圖片路徑
NEXT: 下一步與資源需求（重資源分鐘數）
```

不寫分數或 PASS 進盲審層；中途進度寫 RESUME_STATE，不另外發訊息。
