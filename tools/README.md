# tools

Python 3.9 以上，只用標準函式庫。一律用 `python -I -X utf8 <tool> ...` 執行（`-I` 不從目前資料夾載入模組）。
每支都有 `--help`。沒有任何寫死的本機路徑：路徑都從參數、目前資料夾或 git 推導。

| 工具 | 做什麼 | 會寫檔嗎 | 花額度嗎 |
|---|---|---|---|
| `setup_project_settings.py` | 在一個 git repo 的每個 worktree 寫入壓縮門檻（`autoCompactWindow` + 環境變數）和要關掉的使用者 plugin | 只有加 `--apply` 才寫，只寫 `<worktree>/.claude/settings.local.json` | 不花 |
| `context_probe.py` | 免費探測每輪固定成本：類別 token、`autoCompactThreshold`、記憶檔、skill | 不寫（`--json-out` 除外） | **不花**：只送 control request，不呼叫模型 |
| `usage_report.py` | 從本機對話紀錄只彙總 usage 數字：呼叫數、上下文分佈、模型、快取重建、工具輸出量、圖片數 | 不寫（`--json-out` 除外） | 不花 |
| `memory_size_check.py` | 檢查記憶索引大小，超過門檻 exit 1 | 不寫 | 不花 |
| `gate_check.py` | 檢查 RESUME_STATE、工單、TASK REPORT、裁決的欄位和用詞 | 不寫 | 不花 |
| `scope_check.py` | 比對實際改動和工單的 SCOPE / FORBIDDEN | 不寫 | 不花 |
| `evidence_record.py` | 跑驗收指令，留下 exit code、輸出結尾、產物 SHA-256；之後可重新比對 | `run` 寫一份小 JSON，不覆蓋舊的 | 不花 |
| `selftest.py` | 用正反案例測上面三支 | 只寫暫存資料夾，結束刪除 | 不花 |

## setup_project_settings.py

```text
python -I -X utf8 setup_project_settings.py --repo <repo>                     # 只回報
python -I -X utf8 setup_project_settings.py --repo <repo> --apply             # 寫入
python -I -X utf8 setup_project_settings.py --config <DIRECTOR>/director_work.json --apply
python -I -X utf8 setup_project_settings.py --plugins-off a@m,b@m --apply     # PO 勾過的才放
```

- 預設 `--repo` = 目前資料夾所在的 git repo，預設處理它的所有 worktree（`--only-this` 只處理一個）。
- 寫入前先確認 `.claude/settings.local.json` 已被 git 忽略；沒有就 `NOT_IGNORED`，不寫。
- 已存在的檔案先備份到 `--backup-dir`（預設 `<git common dir>/director-settings-backup/`，不會被 commit）。
- 合併寫入，保留其他設定鍵；寫完重讀確認。
- 使用者層設定（家目錄的 `.claude/`）絕不碰。
- 設定檔欄位見 `../director_work.example.json`；命令列參數優先於設定檔。
- 新開 worktree 後要再跑一次（這個檔案不跟著 git 走）。

## context_probe.py

```text
python -I -X utf8 context_probe.py --cwd <project>
python -I -X utf8 context_probe.py --claude <path-to-claude> --cwd <project> --json-out <file>
```

- 送兩行 control request（initialize、get_context_usage）給 `claude --input-format stream-json --output-format stream-json --verbose --no-session-persistence`，讀回應後結束。
- **不要改用 `claude -p "/context"`**：那會呼叫模型、花額度。
- 回應欄位隨 CLI 版本可能不同；拿不到時印 `NO_ANSWER`。

## usage_report.py

```text
python -I -X utf8 usage_report.py                         # 目前資料夾對應的專案
python -I -X utf8 usage_report.py --project-dir <name> --project-dir <name2> --since 2026-01-01
python -I -X utf8 usage_report.py --all --json-out <file>
```

- 只印數字，不印對話內容。輸出可能很長時用 `--json-out` 存檔，對話只看結論。

## memory_size_check.py

```text
python -I -X utf8 memory_size_check.py --file <memory-index> [--max-bytes 6144]
```

## gate_check.py

```text
python -I -X utf8 gate_check.py --resume <RESUME_STATE.md>
python -I -X utf8 gate_check.py --order <WO.md> --report <報告.md> --verdict <裁決.md>
```

- 每個檔案印一行 `OK` / `FAIL`，有問題逐條列出；任何一個失敗就 exit 1。
- 沒填的範本一定不過（`<...>` 算沒填）。工單的 SCOPE / FORBIDDEN 不能寫 `**` 或「相關檔案」這類話。
- RESULT 寫 PASS 但有 `NOT_RUN` 的測試、越界或沒查範圍，都不過。
- 只查格式和用詞，內容對不對要看證據。

## scope_check.py

```text
python -I -X utf8 scope_check.py --order <WO.md> --repo <worktree>
python -I -X utf8 scope_check.py --order <WO.md> --base <ref>        # 取代工單的 BASE_REF
```

- 改動＝和 BASE_REF 的 merge base 比（已提交、已暫存、未暫存都算），再加上沒被 git 忽略的新檔案。在 worktree 裡也能用。
- 看不到被 git 忽略的檔案和 repo 外的檔案。
- 最後一行貼進 TASK REPORT。exit 0 通過、1 越界、2 沒辦法檢查（`NOT_RUN`）。

## evidence_record.py

```text
python -I -X utf8 evidence_record.py run --out-dir <資料夾> --label AC-1 --artifact <檔案或資料夾> -- <指令> <參數>
python -I -X utf8 evidence_record.py verify <紀錄.json>
python -I -X utf8 evidence_record.py verify <紀錄.json> --rerun
```

- 紀錄放 repo 外的工作資料夾。只留最後 40 行（`--tail`）、每行最多 400 字；要完整輸出就加 `--log <檔案>`。
- 螢幕只印一行結論，指令本身的 exit code 原樣傳回。
- 指令和輸出結尾會照原樣存檔，不要把密鑰放進指令。
- `verify` 比對產物雜湊；`--rerun` 先重跑指令，並比對 exit code。會變動的產物（含時間戳）重跑後一定不同，這種就只比 exit code 和人工看的部分。

## selftest.py

```text
python -I -X utf8 selftest.py
```

改過上面三支就跑一次。

## 建議另外寫的（依專案）

- **guard_check**：逐項檢查續航機制（計時器、排程、監看、壓縮設定、記憶大小）並印重建指令，見 `docs/06`。各專案機制不同，所以沒有通用版。
- **排程看板工具**：有總管時，看板的讀寫（go / wait / ack / quiet / hold）用一支小工具統一，名稱檢查和 ACK 逾時警示寫在工具裡，見 `docs/02`。
