PROGRESS: <最後完成的一步、commit、證據路徑>
DOING: <正在做什麼，屬於哪張工單的哪一項>
NEXT_STEP: <接下來的精確動作，可以直接照做>
COMMS: <我在等誰（等什麼）／誰在等我（欠誰什麼）／做完要通知誰；沒有寫 NONE>

# RESUME_STATE — <TASK_ID>
UPDATED: <YYYY-MM-DD HH:MM ±TZ，讀 date>
ORDER: <工單路徑>
SESSION: <session 名稱>
WORKTREE / BRANCH / BASE / HEAD: <...>
LAST_VERIFIED_CHECKPOINT: <commit / tag + 一句話>
COMPLETED_STEPS:
- <步驟>（證據：<路徑>）
IN_FLIGHT: <背景程序 PID、啟動時間、輸出路徑、完成判定方式；自己設的計時器與等待程序> 或 NONE
COORDINATOR: <已送 / 已取得的 TEST REQUEST、GO> 或 NONE
PARTIAL_OUTPUTS_TO_DISCARD: <被中斷時要重做的輸出路徑> 或 NONE
KEEP_AS_EVIDENCE: <要保留的證據路徑>（同一路徑不得同時出現在可回收清單）
FIX_ROUNDS: <每個修過的缺陷一行：`- <缺陷>: round=<累計輪次> set=<組> study=<ROOT_CAUSE_STUDY.md 或 NONE>`> 或 NONE
OPEN_DECISIONS: <等總監 / PO 的決定> 或 NONE
DO_NOT_REPEAT: <已失敗的方法，不要重試> 或 NONE
