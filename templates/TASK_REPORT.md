# TASK REPORT（一個 gate 一則，一次寫完整）

```text
首行：<一句話結論>
TASK_ID / WORKER / MODEL / BRANCH / BASE / HEAD / WORKTREE_CLEAN(yes|no)
ORDER: 工單路徑與 REVISION
ORDER_SHA256: <開工時跑 gate_check.py --hash 工單 的 64 位輸出>
RESULT: PASS | PARTIAL | BLOCKED | FAIL
  ENGINEERING: ...
  PRODUCT（成品）: ...
  PERFORMANCE: ...
  STABILITY: ...
DONE: 完成項目，每項附證據路徑
TESTS: 實際執行的測試與結果；沒跑的寫 NOT_RUN
SCOPE_CHECK: PASS | VIOLATION | NOT_RUN，貼 scope_check.py 的最後一行
EVIDENCE: 重跑指令與產物雜湊的紀錄路徑（evidence_record.py）；沒有就寫 NONE: 原因
ACCEPTANCE: 工單 E 節每條一列，不增不減。狀態：AUTO 填 PASS / FAIL / BLOCKED / UNVERIFIED；
  REVIEW 最多填 READY_FOR_REVIEW；PO 只填 PENDING_PO。交件前跑 gate_check.py --match 本報告 工單
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
