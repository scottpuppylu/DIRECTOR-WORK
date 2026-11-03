<!-- BOOTSTRAP 第 3 步其餘檔案的骨架。每段複製成 DIRECTOR/ 下的同名檔，把 <...> 換掉。 -->

## DIRECTOR_OPERATING_RULES.md

```text
# 本專案版規則 — <專案名稱>
只寫和規則包不同的地方；沒寫的照 <RULES>/docs/xx。
| 規則包位置 | 本專案的做法 | 來源（PO-xx / DD-xx） |
```

## DIRECTOR_STATE.md

```text
# DIRECTOR_STATE — <專案名稱>
UPDATED: <讀 date>
## 專案概況
目標 / 目前階段 / 已知 PO 決定 / repo、分支、worktree / build 與測試方式、時間 / 共用重資源 / 輸出位置與磁碟 / 成品怎麼看
## 各工作線狀態
| 工作線 | 工單 | 狀態 | 下一個 gate |
## 下一步
```

## ACTIVE_WORKSTREAMS.md

```text
# ACTIVE_WORKSTREAMS
| session 名稱 | 角色 | 工單 | RESUME_STATE 路徑 | worktree / branch | 模型 | effort | 優先序 | 狀態（草案 / 執行中 / 停止） |
```

## RISK_REGISTER.md

```text
# RISK_REGISTER
| ID | 風險 | 影響 | 可能性 | 對策 | 負責人 | 狀態 |
```

## DIRECTOR_LOG.md

```text
# DIRECTOR_LOG（append-only，一行一件事）
<YYYY-MM-DD HH:MM ±TZ> | <決定 / 事件> | <依據或 DD-xx / PO-xx>
```

## GUARDS.md

```text
# GUARDS（docs/06、docs/06b）
| 機制 | 擁有者 | 中斷會怎樣 | 怎麼檢查 | 重建指令 |
```

## BASELINE_METRICS.md

```text
# BASELINE_METRICS
| 日期（讀 date） | 指令 | 指標 | 數值 | 證據等級（VERIFIED_LOCAL / ESTIMATED / UNKNOWN） |
固定成本：context_probe 的 totalTokens 與各類別；歷史用量：usage_report 的上下文中位數、≥25 萬讀入比例。
沒有資料寫 UNKNOWN，不寫 0。
```
