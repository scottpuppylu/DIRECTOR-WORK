# tools

Python 3.9 以上，只用標準函式庫。一律用 `python -I -X utf8 <tool> ...` 執行（`-I` 不從目前資料夾載入模組）。
每支都有 `--help`。沒有任何寫死的本機路徑：路徑都從參數、目前資料夾或 git 推導。

| 工具 | 做什麼 | 會寫檔嗎 | 花額度嗎 |
|---|---|---|---|
| `setup_project_settings.py` | 在一個 git repo 的每個 worktree 寫入壓縮門檻（`autoCompactWindow` + 環境變數）、要關掉的使用者 plugin，以及可選的 `hook_guard` hook | 只有加 `--apply` 才寫，只寫 `<worktree>/.claude/settings.local.json` | 不花 |
| `context_probe.py` | 免費探測每輪固定成本：類別 token、`autoCompactThreshold`、記憶檔、skill | 不寫（`--json-out` 除外） | **不花**：只送 control request，不呼叫模型 |
| `usage_report.py` | 從本機對話紀錄只彙總 usage 數字：呼叫數、上下文分佈、模型、快取重建、工具輸出量、圖片數 | 不寫（`--json-out` 除外） | 不花 |
| `memory_size_check.py` | 檢查記憶索引大小，超過門檻 exit 1 | 不寫 | 不花 |
| `gate_check.py` | 檢查 RESUME_STATE、工單、TASK REPORT、裁決的欄位和用詞；`--match` 逐條對照報告和工單的驗收條件，加 `--evidence-dir` 再核對證據紀錄；`--hash` 印工單雜湊 | 不寫 | 不花 |
| `trace_report.py` | 從工單、報告、裁決產生追溯表：需求 → 工單 → AC → 證據 → 裁決 | 不寫 | 不花 |
| `metrics_report.py` | 從總監的檔案數出 `PURPOSE.md` 的成效數字：返工、中斷後重做、PO 介入、導入卡住，以及規格審查的花費 | 不寫 | 不花 |
| `vocabulary.json` | 判定、下一步、RESULT、治理模式、證據等級等固定用詞的唯一來源；`gate_check.py` 讀它 | — | — |
| `scope_check.py` | 比對實際改動和工單的 SCOPE / FORBIDDEN | 不寫 | 不花 |
| `evidence_record.py` | 跑驗收指令，留下 exit code、輸出結尾、產物 SHA-256；之後可重新比對 | `run` 寫一份小 JSON，不覆蓋舊的 | 不花 |
| `hook_guard.py` | PreToolUse hook：擋下 push、`reset --hard`、`git clean`、裸 stash、刪 worktree / 分支 / tag、依名稱結束程序；加 `--protect` 時另擋 Write / Edit 改工單和 `DIRECTOR_LOG.md` | 不寫 | 不花；放行時不輸出 |
| `selftest.py` | 用正反案例測 gate_check、trace_report、metrics_report、scope_check、evidence_record、hook_guard 和 `--hooks` 安裝；查用詞、必讀文件大小、`PURPOSE.md` 結構和 CHANGELOG 的「對齊初衷」 | 只寫暫存資料夾，結束刪除 | 不花 |

## setup_project_settings.py

```text
python -I -X utf8 setup_project_settings.py --repo <repo>                     # 只回報
python -I -X utf8 setup_project_settings.py --repo <repo> --apply             # 寫入
python -I -X utf8 setup_project_settings.py --config <DIRECTOR>/director_work.json --apply
python -I -X utf8 setup_project_settings.py --plugins-off a@m,b@m --apply     # PO 勾過的才放
python -I -X utf8 setup_project_settings.py --hooks --apply                   # 加裝 hook_guard
python -I -X utf8 setup_project_settings.py --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply
```

- 預設 `--repo` = 目前資料夾所在的 git repo，預設處理它的所有 worktree（`--only-this` 只處理一個）。
- 寫入前先確認 `.claude/settings.local.json` 已被 git 忽略；沒有就 `NOT_IGNORED`，不寫。
- 已存在的檔案先備份到 `--backup-dir`（預設 `<git common dir>/director-settings-backup/`，不會被 commit）。
- 合併寫入，保留其他設定鍵；寫完重讀確認。
- 使用者層設定（家目錄的 `.claude/`）絕不碰。
- 設定檔欄位見 `../director_work.example.json`；命令列參數優先於設定檔。
- 新開 worktree 後要再跑一次（這個檔案不跟著 git 走）。
- `--hooks`：加一個 `Bash|PowerShell` 的 PreToolUse hook，用目前的 Python 跑 `hook_guard.py`；已有就不重複加。
- `--protect-director <DIRECTOR>`（設定檔 `protect_director`，隱含 `--hooks`）：hook 的 matcher 改成 `Bash|PowerShell|Write|Edit`，指令加 `--protect "<DIRECTOR>"`。`--director-worktree`（設定檔 `director_worktree`）指定的總監 worktree 維持原本的 hook，總監照常改工單。
- 已裝的 hook_guard 項目和要的不同時，`--apply` 就地換掉，不另外追加：
  - matcher 或 `--protect` 不同：`MISSING (hooks.PreToolUse matcher)`。
  - 指令不是逐字相同（換了 Python、hook_guard.py 搬走或不存在）：`MISSING (hooks.PreToolUse command)`。
  - 沒給 `--protect-director` 時，沿用已裝項目的 `--protect`（或沒有）。
- 項目到位後，實際跑一次 hook：一個要放行的指令（exit 0）、一個要擋的指令（exit 2），有 `--protect` 時再加一個寫進 `orders/` 的 Write（exit 2）。結果印在 OK / SET 那行：`(hook test: allow=0 block=2 block-write=2)`；不對就是 `HOOK_FAIL`，exit 1。

## hook_guard.py

- Claude Code 每次執行 Bash / PowerShell 前把指令以 JSON 傳進來；違反 `docs/08` 的指令 exit 2，理由印到 stderr，指令不執行。
- 只在引號外拆 `&&`、`;`、`|`、`$(...)`。引號裡的字串只有被執行時才檢查：`bash` / `sh -c`、`cmd /c`、`powershell -Command`、`eval`、`Invoke-Expression`，以及雙引號裡的 `$(...)`。所以 `grep "git stash"`、`git commit -m "...git push..."` 不會被擋。
- 略過 `git -C <dir>`、`-c k=v` 這類全域選項；`C:\...\git.exe` 這種反斜線路徑也認得。
- 依名稱結束程序：`Stop-Process` 沒帶 `-Id` 一律擋，包括 `Get-Process x | Stop-Process`。
- 放行：`git stash push -m <標記>`、`stash apply / list / show`、`git clean -n`、`reset --soft`、`taskkill /PID`、`Stop-Process -Id`。
- **沒有涵蓋刪檔**：`rm -rf`、`Remove-Item -Recurse` 照常執行，刪檔照 `docs/08` 和 `docs/06b`「刪檔之前」。
- 清理員的 session 不裝這個 hook：它要刪 worktree，而 `worktree remove / prune` 會被擋。
- 只是安全帶，不是安全邊界：寫在腳本檔裡或執行時才組出來的指令看不到。PO 核准的 push 由 PO 自己執行，或先移除 hook。
- `--protect <DIRECTOR>`：Write / Edit 的 `file_path` 落在 `<DIRECTOR>/orders/` 底下或就是 `<DIRECTOR>/DIRECTOR_LOG.md` 時 exit 2。相對路徑以 hook 輸入的 `cwd` 為準；兩邊都先 resolve（展開 junction、symlink、`..`），Windows 再展開 8.3 短檔名、不分大小寫比對。
- Windows 路徑先正規化：去掉 `\\?\` 和 `\\.\` 前綴（磁碟或 UNC 路徑）；NTFS 資料流（`DIRECTOR_LOG.md::$DATA`、`x.md:note`）視為檔案本身。其他裝置路徑（GLOBALROOT、volume GUID）不比對，一律擋下並請改用磁碟或 UNC 路徑。
- 目標或它的上層資料夾已存在時，再用檔案識別（磁碟序號＋檔案編號）和 `DIRECTOR_LOG.md`、`orders/` 底下的每個檔案和資料夾比對，所以同一個物件換個名字（UNC 別名、既有檔案的 hardlink）也會擋下。
- `--protect` 只防手誤，擋不到：用 Bash / PowerShell 寫檔、MultiEdit、NotebookEdit、MCP 工具寫檔、經由別名（網路磁碟、`subst` 磁碟代號、UNC 共用）建立還不存在的 `DIRECTOR_LOG.md` 或 `orders/` 資料夾，以及 hook 執行時目標還不存在的 junction。symlink 會先 resolve，但一般帳號沒有建立 symlink 的權限（WinError 1314），selftest 只測 junction。真的要擋，請用作業系統的寫入權限保護 DIRECTOR 資料夾。

## context_probe.py

```text
python -I -X utf8 context_probe.py --cwd <project>
python -I -X utf8 context_probe.py --claude <path-to-claude> --cwd <project> --json-out <file>
```

- 送兩行 control request（initialize、get_context_usage）給 `claude --input-format stream-json --output-format stream-json --verbose --no-session-persistence`，讀回應後結束。
- **不要改用 `claude -p "/context"`**：那會呼叫模型、花額度。
- 兩行之間等 `--wait` 秒（預設 20）讓 MCP 連上；一啟動就問會漏掉 MCP 那幾列。印出 `note: no MCP tokens` 而專案有用 MCP 時，加大 `--wait` 重跑。
- 回應欄位隨 CLI 版本可能不同；拿不到時印 `NO_ANSWER`。

## usage_report.py

```text
python -I -X utf8 usage_report.py                         # 目前資料夾對應的專案
python -I -X utf8 usage_report.py --project-dir <name> --project-dir <name2> --since 2026-01-01
python -I -X utf8 usage_report.py --all --json-out <file>
```

- 只印數字，不印對話內容。輸出可能很長時用 `--json-out` 存檔，對話只看結論。
- 找不到紀錄時印 `NO_DATA` 並 exit 1，不是實測的 0。

## memory_size_check.py

```text
python -I -X utf8 memory_size_check.py --file <memory-index> [--max-bytes 6144]
```

## gate_check.py

```text
python -I -X utf8 gate_check.py --resume <RESUME_STATE.md>
python -I -X utf8 gate_check.py --order <WO.md> --report <報告.md> --verdict <裁決.md>
python -I -X utf8 gate_check.py --verdict <裁決.md> --match <報告.md> <WO.md> --candidate <40 位>   # 裁決要指向這張工單的這個版次和這個 commit
python -I -X utf8 gate_check.py --match <報告.md> <WO.md>     # 逐條對照驗收條件
python -I -X utf8 gate_check.py --match <報告.md> <WO.md> --evidence-dir <證據資料夾>   # 再核對 AUTO 的證據紀錄
python -I -X utf8 gate_check.py --match <報告.md> <WO.md> --dispatch-log <DIRECTOR_LOG.md>   # 再和派工紀錄的雜湊比
python -I -X utf8 gate_check.py --match <報告.md> <WO.md> --evidence-dir <證據資料夾> --dispatch-log <DIRECTOR_LOG.md> --candidate <40 位>   # Strict 的審查要三個都給
python -I -X utf8 gate_check.py --hash <WO.md>                # 印工單 SHA-256（CRLF 當 LF 算）和要記進 LOG 的 DISPATCH 行
python -I -X utf8 gate_check.py --preflight <報告.md> <WO.md> --evidence-dir <證據資料夾> --dispatch-log <DIRECTOR_LOG.md> --repo <受信任的 checkout>   # 舊審查升到新 Strict 前缺什麼
```

- 每個檔案印一行 `OK` / `FAIL`，有問題逐條列出；任何一個失敗就 exit 1。
- 沒填的範本一定不過（`<...>` 算沒填）。工單的 SCOPE / FORBIDDEN 不能寫 `**` 或「相關檔案」這類話。
- RESULT 寫 PASS 但有 `NOT_RUN` 的測試、越界或沒查範圍，都不過。
- 只查格式和用詞，內容對不對要看證據。
- `  ~ ` 開頭的是提示，不會讓檔案失敗：舊格式工單沒有「類型」欄、沒有 REVISION 或 TRACES_TO、驗收表還有結果欄，報告沒有 ACCEPTANCE 表。照新範本補上就不會再出現。
- 工單有 `REVISION` 就要是數字；大於 1 時 H 節變更紀錄要有 2 到 n 每一版的列。「類型」只能是 `AUTO / REVIEW / PO`。
- 工單可以加 `CHECKS:` 清單，每條 AUTO 條件一行 `- AC-1: ["python", "-I", "-m", "unittest", "tests.test_parser"]`：總監核准的檢查指令，JSON 字串陣列，不經 shell。工單雜湊包含它，所以派工時的 DISPATCH 行已經把它鎖住。`--order` 查格式（要能解析成非空的字串陣列）、AC 要存在而且類型是 AUTO、同一 AC 不能寫兩行；Strict 工單有 AUTO 條件卻沒有 CHECKS 只印提示。` #` 之後會被當成註解切掉；指令裡要有 ` #` 時，整個項目用反引號包起來。
- `--match 報告 工單`（可重複）：工單每條 AC 在報告都有一列，不多不少；狀態要在該類型允許的範圍（`vocabulary.json` 的 `ac_worker_statuses`），所以 REVIEW 或 PO 條件填 PASS 會失敗；PASS 要有證據、PASS / FAIL 要寫實際；有一列是 FAIL / BLOCKED / UNVERIFIED 時 RESULT 不能是 PASS；報告的 `ORDER_SHA256` 要和工單現在的雜湊相同。工單沒寫類型的 AC 當 AUTO 查，另印提示。同時給 `--order` 和 `--report` 不會自動對照，行為和以前一樣。
- 驗收表（工單和報告都查）：同一個 AC 出現兩列、表頭有兩欄同名、某列欄數和表頭不同，都失敗，不會悄悄取最後一列。反引號裡的 `|` 和寫成 `\|` 的 `|` 不會被當成欄位分隔。
- `--evidence-dir <資料夾>`（配 `--match`）：AUTO 條件填 PASS 時，證據欄要寫 `evidence_record.py` 產生的 `.json` 檔名，檔案在這個資料夾裡；紀錄的指令 exit 0、沒逾時、產物沒有缺；紀錄的 git HEAD 要和報告的 HEAD 相同，所以最後一次 commit 之後再記。檔案要有 `run` 寫的每個欄位而且型別正確（`schema, label, command, cwd, started, finished, exit_code, timed_out, git, artifacts`），缺一個或型別不對就不算證據，例如只有 `{"exit_code": 0}` 的檔案會失敗；沒有 `schema` 的舊紀錄照舊讀。舊紀錄、沒有 git HEAD 的紀錄、紀錄時有未提交的改動、label 不是這條 AC：Strict 失敗，Standard 只印提示；一份紀錄要給兩條 AC 共用，label 寫兩個（`--label "AC-1 AC-2"`）。Strict 另外要 `schema` 是這版讀得懂的（Standard 提示），`git.dirty` 要明寫 false。紀錄列出的產物會重新算雜湊（相對路徑以紀錄的 cwd 為準），不見或變了：Strict 失敗，Standard 提示；沒有 cwd 的舊紀錄不重算，只提示。報告的 HEAD 要是 7 到 40 位十六進位：Strict 失敗，Standard 和 `--report` 只印提示。工單有 CHECKS 時，紀錄的 command 要和這條 AC 核准的指令完全相同：Strict 失敗，Standard 提示。不加這個參數就和以前一樣，只查有沒有寫證據。這裡只讀紀錄、不重跑；只有 `evidence_record.py verify --rerun --order ...` 才算重跑驗證。紀錄是 worker 自己寫的 JSON，只證明指令跑過而且通過，不證明它測對了東西。
- `--dispatch-log <DIRECTOR_LOG.md>`（配 `--match`）：LOG 裡要有 `DISPATCH <WO-ID> rev=<n> sha=<64 位雜湊>` 一行（`--hash` 會印好給你貼；WO-ID 是工單標題第一個字或檔名，同一工單以最新一行為準），工單現在的雜湊要和它相同。worker 改工單（放寬條件、刪 REVIEW / PO 列、把 REVIEW 改成 AUTO）後重算 `ORDER_SHA256`，報告和工單彼此一致，只有這條會查出來。DISPATCH 必須獨占一行（前面可有 `<日期> |` 欄、後面可有 `| <依據>` 欄）；寫在說明裡、縮排、`>` 引用或 ``` / ~~~ 圍欄裡的都不算。LOG 沒有這張工單的紀錄：各治理模式都失敗。工單標題和檔名的編號要一致，報告 ORDER 行也要指向這張工單。最新一行的 `rev=` 要等於工單的 REVISION，不同就失敗。
- 報告的 `ORDER: <檔名> REVISION <n>` 要和工單的 REVISION 相同，不同就失敗（報告回答的是另一版工單）；沒寫 REVISION：Strict 失敗，Standard 提示。
- `--candidate <40 位>`（配 `--match`）：審查的 commit，總監自己用 `git rev-parse <worker 分支>` 取得，不抄報告。報告的 HEAD 要是它（Strict 以外前綴相同即可），每份證據紀錄的 git HEAD 也要是它（Strict 要完全相同）。不是 40 位十六進位就 exit 2。
- **Strict 的審查綁在一個 commit 上**：Strict 工單做 `--match` 時，沒給 `--candidate`、沒給 `--dispatch-log`、有 AUTO 列填 PASS 卻沒給 `--evidence-dir`、報告 HEAD 不是完整 40 位，都失敗；舊紀錄和沒有 git HEAD 的紀錄也失敗。v0.12 的 Strict 審查指令要補上這三個參數。
- `--preflight 報告 工單`（可重複，只讀）：舊版本做的審查要照現在的 Strict 重審前，逐項列出缺什麼，一項一行 `LACKS`：報告 HEAD 不是 40 位（給 `--repo` 時在那個 checkout 解出完整 commit；解不出來就要 worker 重交）、報告 `ORDER:` 行沒寫 REVISION、LOG 沒有這一版的 DISPATCH 行、AUTO 條件沒有 CHECKS（要用核准重跑就要補）、證據紀錄沒有支援的 schema、git.head 不是 40 位或 `git.dirty` 不是 false（要重新收證）。沒給 `--evidence-dir` / `--dispatch-log` 的部分印 `NOT_CHECKED`。有缺就 exit 1。
- `--hash`：派工時記下，交件時比對。**這是事後偵測，不是事前防止**：任何人都還是改得動工單，只是改了會被查出來；沒有派工紀錄就查不出「改完重算」。
- 固定用詞（判定、下一步、RESULT、治理模式、證據等級）只在 `vocabulary.json` 定義；改用詞時改它，再改 selftest 點名的文件和範本。
- 已有舊檔案的專案導入時：`--warn` 只警告、exit 0；`--since YYYY-MM-DD` 跳過較早的檔案（工單看 ISSUED_BY、RESUME_STATE 看 UPDATED、報告和裁決看第一個日期）；找不到日期的檔案無從比較，也跳過，印 `UNDATED` 並在最後一行另計，要查它就不加 `--since`。先用 `--warn` 看全貌，新工單再用 `--since` 嚴格檢查。舊檔案不追溯修改。

## trace_report.py

```text
python -I -X utf8 trace_report.py --orders <DIRECTOR>/orders --reports <報告資料夾> [--verdicts <DIRECTOR>/reviews] [--config <DIRECTOR>/director_work.json] [--decisions <需求或決定檔.md> ...]
```

- 只讀，印 Markdown 表：需求 | 工單 | AC | 類型 | 狀態 | 證據 | 裁決。需要存檔就自己導到檔案。
- 需求取自工單的 `TRACES_TO`；報告靠 `ORDER:` 行裡的工單檔名對應，沒有就用 TASK_ID 開頭的工單編號；裁決靠標題裡的工單編號。同一工單有多份報告時不看檔名，依序比 `ORDER:` 行的 REVISION、`ATTEMPT: n` 行、報告裡第一個日期（可帶 HH:MM），取最新的；全部相同就兩份都不取，表內寫「多份報告分不出先後」。這些工單會在「同一工單有多份報告」一節列出每份報告和選了哪份。HEAD 只列出，沒有 git 排不出先後。裁決只配選中報告的版次（看裁決的 `ORDER:` 行）：同版多份取日期較晚的，分不出先後就都不取；沒標版次的舊裁決只有一份時照列，加註「未標版次」。`CANDIDATE_HEAD:` 不是報告 HEAD 的裁決一律不放進表，剩不下就寫「未配對」。
- 表後列出：沒有 TRACES_TO 的工單、不符 `trace_id_pattern` 的編號、對不到工單的報告、裁決對不到報告版次（含 `CANDIDATE_HEAD:` 不是報告 HEAD 的）。沒設 `trace_id_pattern` 就不檢查格式。
- `--decisions 檔案`（可重複）：讀專案需求或決定檔裡表格列第一欄的 `XX-數字` 編號。TRACES_TO 寫了、卻不在這些檔裡的，列在「TRACES_TO 找不到的編號」；檔裡有、卻沒有任何工單追溯的，列在「沒有工單的需求」。不給這個旗標，輸出和以前相同。
- 不悄悄略過檔案：三個資料夾裡不是該類檔案的 `.md`（工單沒有 `ISSUED_BY =`、報告沒有 `TASK_ID`、裁決沒有 `## A`）列在「沒計入的檔案」，寫數量和檔名。舊格式工單要算進來，補一行 `ISSUED_BY = <誰> <日期>`。
- 只看檔案寫了什麼，不判斷做得對不對。資料夾或 `--decisions` 檔不存在 exit 1，其他情況 exit 0。

## metrics_report.py

```text
python -I -X utf8 metrics_report.py --director <DIRECTOR> [--since YYYY-MM-DD] [--config <DIRECTOR>/director_work.json]
```

- 只讀，印 Markdown 表，對應 `PURPOSE.md` 的五個成效指標。改規則前後各跑一次，數字寫進該版 CHANGELOG 的「對齊初衷」。
- 返工：裁決的下一步是 `CONTINUE_SAME_WORKER` 或 `SWITCH_TO_OTHER_WORKER` 的次數，另列工單改版（REVISION 大於 1）次數。
- 中斷後遺失的工作：`DIRECTOR_LOG` 裡 `RESUMED ... redo=` 不是 `NONE` 的行（`docs/06b` 恢復程序第 7 步）。
- PO 介入：`PO_PENDING.md` 的 OD / ACT 項目數；每項的 `CREATED:` 日期給 `--since` 用，沒寫的照算並標 `UNDATED`。待決事項放在別的檔案或別的格式時，在 `director_work.json` 設 `po_pending_files`、`po_item_pattern`、`po_open_pattern`（見 `../director_work.example.json`），不改程式。導入卡住：`DIRECTOR_LOG` 的 `BOOTSTRAP_STUCK` 行（`BOOTSTRAP`）。規格審查：`SPEC_REVIEW ... tokens= adopted=` 行的合計。
- 額度不在這裡算，跑 `usage_report.py`。沒有東西可數時印 `UNKNOWN`，不印 0：來源檔不存在、一份裁決都沒有（返工）、一份工單都沒有（改版）、`DIRECTOR_LOG` 沒有 `RESUMED` 行（中斷後遺失）。只數得到檔案裡記下的事。
- 文末「沒計入的檔案」列出像工單（檔名 `WO-` 開頭或放在 `orders` 資料夾）卻沒有 `ISSUED_BY =` 行的檔案；加 `--since` 時另列被略過的工單和沒有日期、照算的工單。

## scope_check.py

```text
python -I -X utf8 scope_check.py --order <WO.md> --repo <worktree>
python -I -X utf8 scope_check.py --order <WO.md> --base <ref>        # 取代工單的 BASE_REF
```

- 改動＝三段 diff 的聯集：merge base..HEAD（已提交）、HEAD..index（已暫存）、index..工作樹（未暫存），再加上沒被 git 忽略的新檔案。改名的兩邊都算。在 worktree 裡也能用。
- submodule 一律比對，不管 `submodule.*.ignore` 或 `diff.ignoreSubmodules` 怎麼設。
- 標成 assume-unchanged 或 skip-worktree 的檔，git diff 看不到它的修改，所以另外算雜湊和 index 比；不同就算未暫存，並多印一行 `FLAGGED: n file(s) marked ...; m differ from the index`。skip-worktree 而工作樹沒有這個檔，視為 sparse checkout、不算改動。
- 看不到被 git 忽略的檔案和 repo 外的檔案。
- 清單項目裡 ` #` 之後是註解。檔名本身有 ` #` 時，整個項目用反引號包起來：`` - `src/x #draft.txt` ``，反引號裡的字照原樣讀（檔名不能含反引號）。`gate_check.py --order` 看到沒包反引號、` #` 後面緊接著字（像 `a #1.txt`）而被切掉的項目會印提示；`# 說明`（`#` 後面有空格）當一般註解，不提示。
- 工單有 `REQUIRED_CHANGES:` 清單時，每一條 glob 都要對到至少一個改動的檔案；沒對到的印 `MISSING   <glob>`，結果是 VIOLATION，最後一行多一個 ` missing=n`。沒有這個清單，輸出和以前一樣。`gate_check.py --order` 另外查每一條都在 SCOPE 裡、不在 FORBIDDEN 裡，否則這張工單做不到。
- 最後一行貼進 TASK REPORT。exit 0 通過、1 越界或缺必要改動、2 沒辦法檢查（`NOT_RUN`，包括 SCOPE / FORBIDDEN 下一行不是 `- 項目`）。

## evidence_record.py

```text
python -I -X utf8 evidence_record.py run --out-dir <資料夾> --label AC-1 --artifact <檔案或資料夾> -- <指令> <參數>
python -I -X utf8 evidence_record.py verify <紀錄.json>
python -I -X utf8 evidence_record.py verify <紀錄.json> --rerun --order <WO.md> --dispatch-log <DIRECTOR_LOG.md> --repo <候選 commit 的乾淨 checkout> --candidate <40 位>
python -I -X utf8 evidence_record.py verify <紀錄.json> --rerun-recorded   # 跑紀錄裡寫的指令，不算重跑驗證
```

- 紀錄放 repo 外的工作資料夾。只留最後 40 行（`--tail`）、每行最多 400 字；要完整輸出就加 `--log <檔案>`。
- 螢幕只印一行結論，指令本身的 exit code 原樣傳回。
- 指令和輸出結尾會照原樣存檔，不要把密鑰放進指令。
- `verify` 先查紀錄有沒有 `run` 寫的每個欄位（缺欄位或型別不對：`NOT_RUN not an evidence record`，exit 2；沒有 `schema` 的舊紀錄照讀，印提示），再比對產物雜湊。結論行把三件事分開印：`integrity=same|changed`（產物和紀錄時相同）、`test=not-rerun|passed|failed(...)`（只有 `--rerun` 跑核准的檢查而且 exit 0 才是 `passed`；不重跑就是 `not-rerun`，不算重跑過）、`artifacts=N missing=M`（紀錄時就缺的、現在不見的都算 missing）。有任何一項不對就是 `MISMATCH`，exit 1；產物缺了絕不會 OK。會變動的產物（含時間戳）重跑後一定不同，這種就只比 exit code 和人工看的部分。
- `--rerun` 跑的是總監核准的檢查，不是紀錄裡寫的指令，四個參數都要給，少一個就 `NOT_RUN`、exit 2，什麼都不跑：
  1. 工單的雜湊和 REVISION 要等於 LOG 裡這張工單最新的 DISPATCH 行，不同就 exit 2。
  2. 用紀錄的 label 找 AC，取工單 `CHECKS:` 裡那條 AC 的指令；沒有就 exit 2。
  3. `--repo` 的 HEAD 要是 `--candidate`（40 位）；不能有修改或未追蹤檔、不能有標成 assume-unchanged 或 skip-worktree 的檔（git status 看不到它們的修改）、不能有 `refs/replace/`（它能讓別的 tree 冒用候選 commit 的名字），否則 exit 2。git 一律關掉 replace 物件來讀。
  4. 指令的程式要是絕對路徑、候選 commit 裡的檔（`./tools/check`）或 `python` / `python3`（就是跑這支工具的 Python）；只寫程式名、要靠 PATH 找的一律 exit 2，避免 PATH 換掉程式。
  5. 從 git 物件把候選 commit 的 tree 寫進新的暫存資料夾，每個檔案都核對雜湊，在那裡跑核准的指令，不在 `--repo` 的工作樹裡跑。紀錄的 git HEAD 不是候選 commit、或紀錄的 command 和核准的不同，都是 `MISMATCH`、exit 1；紀錄的 command 只拿來比對，不會執行。產物在暫存資料夾裡、照它相對紀錄 cwd 的路徑重新算雜湊，不同就是 `MISMATCH`。
  6. 跑完再讀一次 `--repo`：HEAD、tree、狀態或旗標有變，就是 `MISMATCH`、exit 1。
  結論行最後加 `check=AC-1 source=order candidate=<12 位>`。
- 暫存資料夾只有已 commit 的檔，沒有 `.git`、未追蹤檔和被忽略的檔，跑完就刪。這證明「跑的是總監核准的檢查、在候選 commit 的 tree 上」，但檢查仍會執行候選 commit 裡 worker 寫的測試碼，不是沙箱。`--repo` 仍要乾淨，建議用 `git worktree add --detach <目錄> <候選 commit>` 新開（只新增 worktree，不刪別的）。
- `--rerun-recorded` 是 v0.12 的 `--rerun`：在紀錄的 cwd 跑紀錄寫的指令。能改紀錄的人就能決定跑什麼，所以結論是 `test=recorded-command-passed source=record`，永遠不印 `test=passed`。v0.12 只寫 `--rerun` 的指令現在會 exit 2，改成上面的完整寫法。

## selftest.py

```text
python -I -X utf8 selftest.py
```

改過任何工具、`vocabulary.json`、`docs/02`、範本或每輪必讀的文件就跑一次。也會檢查：文件和範本裡的固定用詞和 `vocabulary.json` 一致；README 標「每輪必讀」的文件合計不超過上限（`MUST_READ_LIMIT`，2026-11-04 為 13,428 bytes）。要提高上限，commit 訊息寫明原因。GitHub Actions 在每次 push 和 PR 跑同一支（`.github/workflows/selftest.yml`）。

## 建議另外寫的（依專案）

- **guard_check**：逐項檢查續航機制（計時器、排程、監看、壓縮設定、記憶大小）並印重建指令，見 `docs/06b`。各專案機制不同，所以沒有通用版。
- **排程看板工具**：有總管時，看板的讀寫（go / wait / ack / quiet / hold）用一支小工具統一，名稱檢查和 ACK 逾時警示寫在工具裡，見 `docs/02`。
