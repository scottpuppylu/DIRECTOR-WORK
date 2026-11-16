# GATE FEASIBILITY — <TASK_ID> <gate 名稱>（2.5.0）
<YYYY-MM-DD HH:MM，用 ran_line.py --stamp 印，不手打>
ORDER: <WO-檔名.md> REVISION <n>
BASELINE: <試跑用的現況 commit，40 位>
CHECKED_BY: <寫這份的人；放寬量法那一節要另一個人>

核准一個閘門之前填這份。目的：條件在核准前就證明量得到、跑得動、做得到，不要等到驗收才發現閘門根本過不了或什麼都抓不到。

## A. 每個條件
| 條件 | 量它的現有工具（路徑 + 指令） | 在 BASELINE 試跑一次（RAN 行：指令 exit at） | 試跑結果 | 原則上達得到？（理由，或要先改什麼） | 狀態 |
|---|---|---|---|---|---|
| AC-1 | `<tools/x.py --y>` | `<RAN ...>` | <數值 / 輸出結尾> | <是：…／否：…> | FEASIBLE / NO_TOOL / NOT_RUN / UNREACHABLE |

- 沒有現有工具量得到的條件標 `NO_TOOL`：先做工具或改寫條件，不能核准一個沒人量得到的條件。
- 沒在 BASELINE 試跑過的標 `NOT_RUN`，不能當成可行。
- 原則上達不到（例如要的精度超過量測本身的誤差）標 `UNREACHABLE`，改條件。

## B. 放寬量法（沒有放寬就寫「無」）
LOOSENED_RULE: <原本的量法 → 放寬後的量法>
KNOWN_DEFECT: <一個已知有缺陷的樣本（路徑或 commit）>
CHECKED_BY_OTHER: <不是放寬量法的人；換人或換模型>
RESULT: <放寬後的量法對 KNOWN_DEFECT 跑一次：仍然抓到 yes / 沒抓到 no + RAN 行>

放寬後抓不到已知缺陷（`no`），或沒有 KNOWN_DEFECT 可以試，這個放寬就不能用。

## C. 結論
FEASIBILITY: <FEASIBLE | NOT_FEASIBLE | NOT_VERIFIED>
全部條件 FEASIBLE、B 節是「無」或 `yes`，才寫 FEASIBLE；有任何一格 `NOT_RUN` 就是 NOT_VERIFIED。
