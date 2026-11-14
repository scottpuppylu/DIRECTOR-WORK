# Decision Register（append-only；新決定加在對應段落末尾，舊的不刪，被取代的標 SUPERSEDED）

## A. PO 決定（不再詢問）
| ID | 日期時間 | 決定 | 為什麼 | 來源（聊天 / 待決頁 OD-xx / CLAUDE.md） | 狀態 |
|---|---|---|---|---|---|
| PO-01 | | | | | ACTIVE |

## B. 總監決定（可回退，事後記錄）
| ID | 日期時間 | 決定 | 理由 | 影響範圍 | 回退方式 | 驗收案例 | 狀態 |
|---|---|---|---|---|---|---|---|
| DD-01 | | | | | | | ACTIVE |

驗收案例（2.2.5）：一個端到端案例，從產品的公開入口跑、有精確的期望數字，例如 `report.build("a.csv") → total=42`。
最終驗收時 `gate_check.py --final` 對沒有案例的 DD 印 `~ WARN DD_CASE`（SUPERSEDED 的不算）。

## C. 待 PO 決定（鏡像待決頁；以待決頁為準）
| ID | 開立時間 | 問題 | 建議 | 狀態（open / answered / closed） |
|---|---|---|---|---|
| OD-01 | | | | open |
