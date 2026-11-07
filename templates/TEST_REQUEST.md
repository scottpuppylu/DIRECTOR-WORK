# TEST REQUEST（送總管；沒有總管時寫進 RESUME_STATE 自己守）

```text
TEST REQUEST: <FUNC|BENCH> <內容> <上限分鐘>
FROM: <完整 session 名稱>
PURPOSE: 這次測試要回答哪一個決定或驗收項
MIN_SCOPE: 最小範圍，以及為什麼不能更小
TIER: 1 批次（預設） | 2 單項（寫理由：P0 / PO 在等 / 下一步依賴 / 耦合無法用開關分 / 單一根因驗證）
CHANGES: 這次 build 包含的每一項修改，以及對應的開關
SWITCHES: 要跑的開 / 關組合
EXCLUSIVE_MIN: 需要獨佔安靜時段的分鐘數（沒有寫 0）
NORMAL_MIN: 一般時段的分鐘數
BUILD_GB: <新 build 資料夾的 GiB>
CAPTURE: <組數> x <每組張數> x <單張 MiB> = <GiB>（沒有擷取寫 NONE）
CACHE_GB: <Library 重匯入和暫存的餘量 GiB>
WRITE_GB: <預計寫入的 GiB，至少 BUILD_GB + CAPTURE + CACHE_GB>
DURATION: <組數> x <單組實測分鐘（含逾時）> = <分鐘>
TIER0_DONE: 第 0 級（CPU、離線）檢查已做完的項目
```

空間一律寫 GiB（2^30 位元組），以排程負責人實測的值為準。時長用實測的單組時間，每組都可能跑滿逾時，就照逾時算。送出前跑 `gate_check.py --test-request <檔案>`，FAIL 的 TR 不發 GO。

收到 GO 後寫 ACK；結束送 `DONE <內容> <實際分鐘>`；超過上限 10 分鐘先停下回報。
