# tools

Python 3.9 以上，只用標準函式庫。一律用 `python -I -X utf8 <tool> ...` 執行（`-I` 不從目前資料夾載入模組）。
每支都有 `--help`。沒有任何寫死的本機路徑：路徑都從參數、目前資料夾或 git 推導。

| 工具 | 做什麼 | 會寫檔嗎 | 花額度嗎 |
|---|---|---|---|
| `setup_project_settings.py` | 在一個 git repo 的每個 worktree 寫入壓縮門檻（`autoCompactWindow` + 環境變數）、要關掉的使用者 plugin，以及可選的 `hook_guard` hook；`--runtime-guard` 一次寫入整組執行期防護 | 只有加 `--apply` 才寫，只寫 `<worktree>/.claude/settings.local.json` | 不花 |
| `context_probe.py` | 免費探測每輪固定成本：類別 token、`autoCompactThreshold`、記憶檔、skill | 不寫（`--json-out` 除外） | **不花**：只送 control request，不呼叫模型 |
| `usage_report.py` | 從本機對話紀錄只彙總 usage 數字：呼叫數、上下文分佈、模型、快取重建、工具輸出量、圖片數 | 不寫（`--json-out` 除外） | 不花 |
| `usage_mix.py`（1.3.0） | 額度花在哪：每次呼叫依它選的動作歸成五大類（讀和查、協調、看圖與審查、實際動手、等待），對照門檻，各 session 的比例，以及開新 session 划不划算（RESTART 行） | 不寫 | 不花；只印比例，不印訊息內容 |
| `memory_size_check.py` | 檢查記憶索引大小，超過門檻 exit 1 | 不寫 | 不花 |
| `gate_check.py` | 檢查 RESUME_STATE、工單、TASK REPORT、裁決的欄位和用詞；`--match` 逐條對照報告和工單的驗收條件，加 `--evidence-dir` 再核對證據紀錄；`--hash` 印工單雜湊 | 不寫 | 不花 |
| `setup_check.py`（2.2.0） | 建置完成的檢查：`DIRECTOR_STATE.md` 的 `PO_PAGE_URL` 和 `PO_PAGE_PINNED` 兩行是不是三種合法寫法之一；2.2.1 起另查旁邊的 `PO_PENDING.md`、`RESUME_STATE.md` 表頭、`director_work.json`（shadow，`--strict` 才失敗） | 不寫 | 不花 |
| `round_check.py`（1.3.0） | 修正輪數：RESUME_STATE 的 `FIX_ROUNDS:` 到第 4 輪（之後每組）沒有根因研究就 FAIL | 不寫 | 不花 |
| `report_vs_audit.py`（1.3.0） | 用動作紀錄核對 TASK REPORT：報告說跑過的指令（`RAN:` 和 TESTS / EVIDENCE / DONE 裡的 selftest、Unity、Blender、雜湊檢查）紀錄裡有沒有、exit 和時間對不對；2.2.1 修截斷的長指令（引號、反斜線）比不到 | 不寫 | 不花 |
| `transcript_audit.py`（2.2.1） | 沒裝 hook 時，從本機 Claude Code transcript（含 subagents）重建一份 hook 格式的動作紀錄，第 1 行標明是重建的 | 只寫 `--out`（已存在要 `--force`） | 不花 |
| `trace_report.py` | 從工單、報告、裁決產生追溯表：需求 → 工單 → AC → 證據 → 裁決 | 不寫 | 不花 |
| `metrics_report.py` | 從總監的檔案數出 `PURPOSE.md` 的成效數字：返工、中斷後重做、PO 介入、導入卡住，以及規格審查的花費；`--run` 另數接手演練的決策、重問、PO 操作和第一個可用預覽的時間 | 不寫 | 不花 |
| `vocabulary.json` | 判定、下一步、RESULT、治理模式、證據等級等固定用詞的唯一來源；`gate_check.py` 讀它 | — | — |
| `scope_check.py` | 比對實際改動和工單的 SCOPE / FORBIDDEN | 不寫 | 不花 |
| `evidence_record.py` | 跑驗收指令，留下 exit code、輸出結尾、產物 SHA-256；之後可重新比對 | `run` 寫一份小 JSON，不覆蓋舊的 | 不花 |
| `hook_guard.py` | PreToolUse hook：預設只提醒（`--mode remind`，呼叫照跑），`--mode ask` 交給使用者，`--mode block` 才擋；對象是 push、`reset --hard`、`git clean`、裸 stash、刪 worktree / 分支 / tag、依名稱結束程序；加 `--protect` 時另擋 Write / Edit 改工單和 `DIRECTOR_LOG.md`；加 `--rules` 時依 `guard_rules.json` 對每個工具呼叫回 deny / ask / 不出聲；加 `--review` 時先把部分 ask 交給第二個模型看；加 `--sessions` 時依 `session_id` 選 director / worker / cleaner | 不寫 | 不花；放行時不輸出。`--review` 每次審查用一次 `claude -p`（不花錢，但吃訂閱額度） |
| `doctor.py` | 報告一個 worktree 實際生效的防護：claude 版本（生效的那個和 PATH 上每一個）、各設定層合併後的 hook、動作紀錄、權限規則、`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`、隔離、worktree、各 worktree 最近有沒有 session 從那裡啟動；每項標 ENFORCED / CONFIGURED_NOT_VERIFIED / NOT_ENFORCED / MISSING | 不寫 | 不花：`claude --version` 只在本機印版本 |
| `status_gen.py`（1.3.0） | 產生一支工作線的 `status.py`：log 尾段、雜湊、磁碟 GiB、git、最新輸出；總監版再加待決頁計數、未結案工單、未送出訊息、最近 1 小時的動作紀錄、常駐程序 | 只寫 `--out` 那一支（已存在要 `--force`）；產生的 `status.py` 不寫 | 不花 |
| `poll_hint.py`（1.3.0） | PostToolUse hook：同一個 session 10 分鐘內讀同一份 log 第 3 次時，提示「等完成通知」，不擋；`report` 從動作紀錄算各 session 讀 log 的次數 | hook 只寫暫存資料夾的小狀態檔；`report` 不寫 | 不花 |
| `secret_mask.py` | 把文字裡的私鑰、token、API key、JWT、`password=` 這類值換成 `[MASKED:種類]`；`--check` 只列出找到的種類 | 不寫 | 不花 |
| `pause_ctl.py` | 暫停開關：`on` / `off` 寫入或移除 `<DIRECTOR>/PAUSE` 並記進 `DIRECTOR_LOG.md`，`status` 印目前狀態；`procs` 依 CPU 增量列出停機後程序樹還剩哪些 | `on` / `off` 只寫旗標檔和 LOG 一行；`procs` 不寫、不結束任何程序 | 不花 |
| `audit_log.py` | 動作紀錄：PostToolUse / PostToolUseFailure hook 把每個工具呼叫寫成一行有雜湊鏈的 JSONL；`verify` 檢查鏈和總監的錨點，`head` 印錨點，`cite` 印 TASK REPORT 引用的區段；`recover`（2.2.0）留複本後接著寫 | `append` 只寫紀錄檔和它的 `.lock`；其他不寫 | 不花 |
| `guard_rules.json` | `hook_guard.py --rules` 的規則檔：每條規則的類別、worker / director 的結論、比對方式、正反例子和要寫進 settings 的權限規則 | — | — |
| `selftest.py` | 用正反案例測 gate_check、trace_report、metrics_report、scope_check、evidence_record、hook_guard（含 `--review`，用假的 claude）、pause_ctl、audit_log、doctor（假的 claude 版本、暫存的設定層）和 `--hooks`、`--runtime-guard` 安裝；查用詞、必讀文件大小、`PURPOSE.md` 結構和 CHANGELOG 的「對齊初衷」 | 只寫暫存資料夾，結束刪除 | 不花 |

## setup_project_settings.py

```text
python -I -X utf8 setup_project_settings.py --repo <repo>                     # 只回報
python -I -X utf8 setup_project_settings.py --repo <repo> --apply             # 寫入
python -I -X utf8 setup_project_settings.py --config <DIRECTOR>/director_work.json --apply
python -I -X utf8 setup_project_settings.py --plugins-off a@m,b@m --apply     # PO 勾過的才放
python -I -X utf8 setup_project_settings.py --hooks --apply                   # 加裝 hook_guard（提醒模式）
python -I -X utf8 setup_project_settings.py --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply
python -I -X utf8 setup_project_settings.py --guard-profile worker --director-worktree <總監的 worktree> --apply
python -I -X utf8 setup_project_settings.py --guard-profile worker --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply   # worker 加暫停旗標
python -I -X utf8 setup_project_settings.py --runtime-guard --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply   # 整組執行期防護（1.1.0）
```

- 預設 `--repo` = 目前資料夾所在的 git repo，預設處理它的所有 worktree（`--only-this` 只處理一個）。
- 寫入前先確認 `.claude/settings.local.json` 已被 git 忽略；沒有就 `NOT_IGNORED`，不寫。
- 已存在的檔案先備份到 `--backup-dir`（預設 `<git common dir>/director-settings-backup/`，不會被 commit）。
- 合併寫入，保留其他設定鍵；寫完重讀確認。
- 使用者層設定（家目錄的 `.claude/`）絕不碰。
- 設定檔欄位見 `../director_work.example.json`；命令列參數優先於設定檔。
- 新開 worktree 後要再跑一次（這個檔案不跟著 git 走）。
- `--hooks`：加一個 `Bash|PowerShell` 的 PreToolUse hook，用目前的 Python 跑 `hook_guard.py`；已有就不重複加。
- `--guard-mode remind|ask|block`（設定檔 `guard_mode`，1.3.1）：hook 標出的呼叫怎麼處理。預設 `remind`：照跑，附一行提醒；`ask`：交給使用者當場決定；`block`：exit 2 擋下，是明確 opt-in 的嚴格模式。**不要預設把 block 裝到工作線**，工作線的 AI 會因此不敢動手（docs/10 L-045）。`remind` 不寫 `--mode`，其他模式在指令加 `--mode X`；沒給時沿用已裝項目的 `--mode`（沒有就是 remind）。模式不同也算 `MISSING (hooks.PreToolUse command)`。
- `--protect-director <DIRECTOR>`（設定檔 `protect_director`，隱含 `--hooks`）：hook 的 matcher 改成 `Bash|PowerShell|Write|Edit`，指令加 `--protect "<DIRECTOR>"`。`--director-worktree`（設定檔 `director_worktree`）指定的總監 worktree 維持原本的 hook，總監照常改工單。
- 已裝的 hook_guard 項目和要的不同時，`--apply` 就地換掉，不另外追加：
  - matcher 或 `--protect` 不同：`MISSING (hooks.PreToolUse matcher)`。
  - 指令不是逐字相同（換了 Python、hook_guard.py 搬走或不存在）：`MISSING (hooks.PreToolUse command)`。
  - 沒給 `--protect-director` 時，沿用已裝項目的 `--protect`（或沒有）。
- `--guard-profile worker|director`（設定檔 `guard_profile`，隱含 `--hooks`）：hook 的 matcher 改成 `*`（每個工具呼叫都檢查），指令加 `--rules "<tools>/guard_rules.json" --profile <身分>`，並設 `"onFailure": "block"`：hook 自己壞掉（例如規則檔寫壞，exit 1）時擋下，不放行。`--director-worktree` 指定的 worktree 一律用 director。
  - block 模式：每條規則的 `permissions` 依這個身分的結論寫進 `permissions.deny` 或 `permissions.ask`（第二層：這兩種規則在每個權限模式都有效，包括 bypass）。ask 模式全部寫進 `permissions.ask`。remind 模式只寫機密規則（G50）的 `permissions.deny`，其他一條都不寫，舊安裝留下的規則權限從兩個清單拿掉（否則 Claude Code 照樣擋）；ask 模式的 G50 也留在 deny，使用者自己加的權限規則不動。缺的報 `MISSING (permissions.deny)` / `MISSING (permissions.ask)`；`--apply` 只補上缺的，放錯清單的（換身分後）搬過去，其他權限規則不動。
  - profile 不同也算 `MISSING (hooks.PreToolUse matcher)`。沒給 `--guard-profile` 時沿用已裝項目的 `--profile`，和 `--protect` 一樣。
  - worker 的指令再加 `--pause-flag "<旗標檔>"`：`--pause-flag`（設定檔 `pause_flag`），沒給就用 `--protect-director` 的 `<DIRECTOR>/PAUSE`。總監的 worktree 不加：worker 暫停時，總監還要停程序樹。旗標檔不同也算 `MISSING (hooks.PreToolUse matcher)`；沒給 `--guard-profile` 時沿用已裝項目的 `--pause-flag`。
- `--audit-log <檔案>`（設定檔 `audit_log`，隱含 `--hooks`）：加 PostToolUse 和 PostToolUseFailure 兩個 hook（matcher `*`），執行 `audit_log.py append --log "<檔案>"`；hook_guard 的指令也加 `--audit "<檔案>"`，擋下和詢問也記進同一條鏈。路徑裡的 `{worktree}` 在 setup 時換成 worktree 資料夾名稱；`{container}` 留到 hook 執行時由 audit_log.py 換成容器 ID 前 12 碼（容器外是 `host`）。所以一個 worker、一個容器各一份紀錄，各自一條鏈；其他 `{名稱}` 一律報錯。缺的報 `MISSING (hooks.PostToolUse)` / `MISSING (hooks.PostToolUseFailure)`，`--apply` 就地換掉舊的 audit_log 項目。沒給 `--audit-log` 時沿用已裝項目的 `--audit`。下面的 hook 測試不帶 `--audit`，測試呼叫不會寫進紀錄。
- `--guard-review`（設定檔 `guard_review: true`）：有 `--guard-profile` 的項目加上 hook_guard `--review`。缺的報 `MISSING`。沒給時沿用已裝項目的 `--review`；要拿掉就手動刪掉指令結尾的 ` --review`。hook 測試會去掉 `--review`，測試呼叫不會啟動審查。
- `--runtime-guard`（設定檔 `runtime_guard: true`，1.1.0）：寫入 `../templates/settings.runtime-guard.json` 列出的那一組。
  - 沒給 `--guard-profile` 就用 worker；沒給 `--audit-log` 就用 `<git common dir>/director-audit/{worktree}-{container}.jsonl`（不會被 commit）。1.1.0 裝的 `{worktree}.jsonl` 照舊能用，重跑 `--apply` 才換成新檔名，舊檔留著不動。
  - 另加 `env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB = "1"`：子程序（Bash、hook 等）拿不到環境變數裡的 Anthropic 和雲端憑證。官方文件寫明它**保留** `GITHUB_TOKEN`、`GH_TOKEN`、proxy 帳密和 `GIT_CONFIG_*`。缺的報 `MISSING (env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB)`。
  - 範本裡的 `<PYTHON>`、`<DW>`、`<PAUSE_FLAG>`、`<AUDIT_LOG>` 由 setup 換成實際路徑；selftest 確認範本和 setup 寫出的內容相同。範本不含 sandbox（原生 Windows 沒有）、`blockWritesOutsideWorkingDirectories`（依使用者決定不啟用）和 WSL2 版本。
  - 寫完用 `doctor.py` 看實際生效的是哪些。
- 項目到位後，實際跑一次 hook：一個要放行的指令（exit 0）、一個要標出的指令，有 `--protect` 時再加一個寫進 `orders/` 的 Write。有 `--profile` 時再加一個每個身分都標出的 MCP 呼叫（`buy_item`，證明規則檔有讀到）。放行那次 stdout 也要是空的。標出的那幾次依模式要得到：block `2`、ask `ask`（ask JSON）、remind `remind`（exit 0 加提醒 JSON）。結果印在 OK / SET 那行，例如 `(hook test: allow=0 block=remind block-rule=remind)`、block 模式 `(hook test: allow=0 block=2 block-write=2 block-rule=2)`；不對就是 `HOOK_FAIL`，exit 1。

## hook_guard.py

- Claude Code 每次執行 Bash / PowerShell 前把指令以 JSON 傳進來。`docs/08` 列的指令依 `--mode`（1.3.1）處理：
  - `remind`（預設）：exit 0，指令照跑；stdout 一行 JSON，`systemMessage` 給使用者看、`hookSpecificOutput.additionalContext` 給模型看，都是 `hook_guard reminder [ID]: 原因`，給模型的那份另註明「只是提醒；使用者已在對話裡核准就直接做、不要再問」。使用者核准後 AI 直接執行，不必拆設定。
  - `ask`：exit 0，stdout 是 `permissionDecision: "ask"` 的 JSON，使用者當場決定。
  - `block`：明確 opt-in 的嚴格模式，exit 2，理由印到 stderr，指令不執行（1.3.0 以前的行為）。
  - 暫停旗標（`--pause-flag`）是人明確設下的停止，每個模式都擋；機密規則（G50–G52，類別 `secret`）的 deny 也是每個模式都擋，讀機密不在「核准就執行」的範圍。自動暫停和 `--review` 只在 block 模式作用。
  - 以下寫「擋」「deny」「exit 2」的地方都是 block 模式；remind / ask 模式同一批呼叫得到提醒或 ask。
- Bash 的 here-document（`cat <<'EOF' ... EOF`、`<<-`、不加引號的 `EOF`）內容是資料，不是指令，不檢查；不加引號時內容裡的 `$(...)` 和反引號照樣會執行，照樣檢查。找不到結尾那一行的 here-document 照原文檢查，藏不了指令。`<<<` 不是 here-document。
- 只在引號外拆 `&&`、`;`、`|`、`$(...)`。引號裡的字串只有被執行時才檢查：`bash` / `sh -c`、`cmd /c`、`powershell -Command`、`eval`、`Invoke-Expression`，以及雙引號裡的 `$(...)`。所以 `grep "git stash"`、`git commit -m "...git push..."`、`echo "git push origin"` 不會被擋。
- 略過 `git -C <dir>`、`-c k=v` 這類全域選項；`C:\...\git.exe` 這種反斜線路徑也認得。
- 依名稱結束程序：`Stop-Process` 沒帶 `-Id` 一律擋，包括 `Get-Process x | Stop-Process`。
- 放行：`git stash push -m <標記>`、`stash apply / list / show`、`git clean -n`、`reset --soft`、`taskkill /PID`、`Stop-Process -Id`。
- 不加 `--rules` 時**沒有涵蓋刪檔**：`rm -rf`、`Remove-Item -Recurse` 照常執行，刪檔照 `docs/08` 和 `docs/06b`「刪檔之前」。
- 清理員的 session 不裝這個 hook：它要刪 worktree，而 `worktree remove / prune` 會被擋。1.3.0 起可以改用 `--sessions`（下面）的 cleaner。
- `--sessions <檔>`（1.3.0，要配 `--rules`）：同一個資料夾啟動的 session 共用一份 settings，所以依 hook 輸入的 `session_id` 選 profile。檔案格式見 `templates/guard_sessions.json`：`sessions` 是 `session_id` → `director` / `worker` / `cleaner`（或 `{profile, name}`），`default` 給沒列到的，`protected` 是任何角色都不能刪或搬的路徑。cleaner = worker 但刪除規則不套用。總監的 session 不受暫停旗標影響。檔案讀不到或格式錯就 exit 1。安裝：`setup_project_settings.py --hooks --rules --session-map <檔> --apply`，權限清單取各角色最寬鬆的那個。hook 輸入只有 `session_id`，沒有 session 名稱，所以要先從 Desktop 或對話紀錄查到 id 再寫進檔案。
- 只是安全帶，不是安全邊界：寫在腳本檔裡或執行時才組出來的指令看不到。PO 在對話裡核准 push 之後，AI 直接執行：remind 模式照跑、ask 模式由使用者當場點頭；不必移除 hook。只有 block 模式會擋下已核准的動作，所以工作線預設不裝 block。
- `--protect <DIRECTOR>`：Write / Edit 的 `file_path` 落在 `<DIRECTOR>/orders/` 底下或就是 `<DIRECTOR>/DIRECTOR_LOG.md` 時 exit 2。相對路徑以 hook 輸入的 `cwd` 為準；兩邊都先 resolve（展開 junction、symlink、`..`），Windows 再展開 8.3 短檔名、不分大小寫比對。
- Windows 路徑先正規化：去掉 `\\?\` 和 `\\.\` 前綴（磁碟或 UNC 路徑）；NTFS 資料流（`DIRECTOR_LOG.md::$DATA`、`x.md:note`）視為檔案本身。其他裝置路徑（GLOBALROOT、volume GUID）不比對，一律擋下並請改用磁碟或 UNC 路徑。
- 目標或它的上層資料夾已存在時，再用檔案識別（磁碟序號＋檔案編號）和 `DIRECTOR_LOG.md`、`orders/` 底下的每個檔案和資料夾比對，所以同一個物件換個名字（UNC 別名、既有檔案的 hardlink）也會擋下。
- `--protect` 只防手誤，擋不到：用 Bash / PowerShell 寫檔、MultiEdit、NotebookEdit、MCP 工具寫檔、經由別名（網路磁碟、`subst` 磁碟代號、UNC 共用）建立還不存在的 `DIRECTOR_LOG.md` 或 `orders/` 資料夾，以及 hook 執行時目標還不存在的 junction。symlink 會先 resolve，但一般帳號沒有建立 symlink 的權限（WinError 1314），selftest 只測 junction。真的要擋，請用作業系統的寫入權限保護 DIRECTOR 資料夾。

### `--rules`、`--profile`（1.1.0）

```text
hook_guard.py --rules <tools>/guard_rules.json --profile worker|director [--protect <DIRECTOR>]
```

- 規則檔每條：`id`（`G` 加兩位以上數字，`G00` 保留）、`category`、`decision`（worker 和 director 各一個：`deny` / `ask` / `none`）、`reason`（不可有 `<...>`）、`match`、`example_block`、`example_allow`，選用 `permissions`。
- `match` 三種：
  - `shell`：Bash / PowerShell 指令拆成每個子指令（含 `bash -c`、`cmd /c`、`powershell -c`、`eval`、`xargs` 這類包起來的），比指令名稱（`cmd` 是完整比對的 regex，去掉路徑和 `.exe`、不分大小寫）、依序的非選項字（`args`，`git -C`、`gh -R`、`aws --profile` 這類選項的值會跳過）、選項 regex（`flags` 至少一個、`not_flags` 一個都不能有）。另有三個選用欄位：
    - `bare: true`：指令完全沒有參數才算（`env`、`set`）。
    - `arg_search`：任一參數用 regex 搜得到（`echo $GITHUB_TOKEN`）。
    - `path_args` / `path_except`：每個非選項參數以 hook 的 `cwd` 解析成路徑（展開 `~`、`$HOME`、`${VAR}`、`%VAR%`、`$env:VAR`），比 glob，規則同 `path`。
    - `env` 後面只有選項或 `X=1` 指派時，`env` 本身就是印環境變數的指令；`env X=1 python a.py` 比的是 `python`。
  - `path`：`tools` 列的工具，`file_path`（或 `notebook_path`、`path`）比 `globs`，`except` 除外。Grep 的 `glob`、Glob 的 `pattern` 接在搜尋路徑後面，也當成一個目標比。`~/` 是家目錄，`**/` 是任意層，`*` 不跨 `/`；相對路徑以 hook 輸入的 `cwd` 為準；Windows 不分大小寫、反斜線視同 `/`。
    - 選用 `shell_write: true`：Bash / PowerShell / Monitor 寫到這些路徑也算命中。看三種寫法：寫檔指令（同 G00 的清單）的非選項參數，複製類（`cp`、`copy`、`Copy-Item`、`install`、`ln`、`scp`、`xcopy`、`robocopy`、`rsync`）只看目的地（`-Destination` / `-t` 的值，否則最後一個參數；目的地是資料夾時接上來源檔名）；重新導向的目標；同一行有 `[IO.File]::Write*` 這類 .NET 寫檔時，行內任一個比得到的路徑。所以 `cp CLAUDE.md /tmp/backup.md`、`cat CLAUDE.md` 照常放行。
  - `mcp`：只看 MCP 工具名稱最後一段（`mcp__伺服器__動作`），駝峰拆成底線、轉小寫後比 `words`。開頭是 `read_only_mcp_prefixes`（get、list、read、search、query、status）的一律不比，所以 `get_order`、`list_billing_charges` 不會被「付費」擋。
- `internal_report_tools`（`SendMessage`、`mcp__ccd_session_mgmt__send_message`）是回報總監的管道，任何規則都不比。
- Monitor：Claude Code 2.1.314 起 Monitor 的 shell 指令也會經過 PreToolUse hook。hook_guard 把 `tool_input.command` 當 Bash 指令比 `shell` 規則、G00 和 G40 的 shell 寫檔。**NOT_VERIFIED**：欄位名稱 `command` 是照文件推定，還沒有實際收到 Monitor 的 hook 輸入核對過。`command` 不存在或不是字串時不比、exit 0、不出聲。
- 內建 `G00`：Write / Edit / MultiEdit / NotebookEdit 改使用中的規則檔、`hook_guard.py` 旁邊的 `guard_rules.json` 或 `hook_guard.py` 本身，worker deny、director ask。Bash / PowerShell 也算：子指令寫出這些檔名，又是寫檔指令（`sed -i`、`perl -i`、`tee`、`cp`、`mv`、`git checkout/restore`、`Set-Content`、`Out-File`、`Copy-Item` 等），或重新導向（`>`、`>>`、`2>`、`&>`、`>|`）指到這些檔（從整行原文找，所以 `echo {}>guard_rules.json`、`{ ...; }>hook_guard.py` 這類 `{ }` 緊貼 `>` 的寫法也算），或同一行有 `[IO.File]::Write*` 這類 .NET 寫檔呼叫。只讀的指令（`cat`、`sed -n`、`git diff`、把輸出導到別的檔）照常放行。檔名放在變數裡、`python -c` 或腳本裡寫檔，看不到。
- 結論：有 deny 就 exit 2，stderr 是 `BLOCKED by hook_guard [ID]: 原因`；原本的檢查（stash、`reset --hard`、`--protect` 等）擋下時用原本的訊息；有 ask 就 exit 0，stdout 只有一行 `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "[ID] 原因"}}`；其他 exit 0、什麼都不印。**永遠不回 allow**：不出聲就是照 Claude Code 自己的權限流程，hook 只會讓結果更嚴。
- 多條規則同時命中：deny 優先於 ask，同一種結論取編號最小的。結果只看輸入和規則檔，規則的先後順序不影響結果。
- 規則檔讀不到或格式錯：exit 1，stderr `hook_guard: bad rules file: ...`。配合 setup 寫的 `"onFailure": "block"`，等於擋下所有工具呼叫，直到規則檔修好。
- 預設規則（`guard_rules.json`）：

| ID | 類別 | worker | director | 擋什麼 |
|---|---|---|---|---|
| G01 | force push | deny | deny | `git push --force`、`-f`、`--force-with-lease`、`--mirror`、`--delete`、`+ref`、`:ref` |
| G02 | push | deny | deny | `git push` 各種寫法、`git send-pack`、`git http-push`（含 `git-push`、`git-send-pack` 執行檔）、`gh repo sync`；設定 alias 的 `git -c alias.*=`、`--config-env=alias.*`、`git config alias.*`（查詢的 `--get`、`-l`、`--unset` 除外），因為 alias 可以把 push 換個名字執行 |
| G10 | 刪除 | deny | ask | `rm`、`rmdir`、`rd`、`del`、`erase`、`unlink`、`shred`、`Remove-Item`、`ri`、`find -delete` |
| G11 | 刪除 | deny | ask | MCP 動作含 delete、trash、destroy、purge、wipe、erase、uninstall |
| G20 | 送出 | deny | ask | `gh pr/issue/release/gist/repo` 的寫入子指令、`gh api` 帶寫入方法或欄位、`npm/pnpm/yarn/cargo publish`、`twine upload`、`docker/podman/gem push` |
| G21 | 送出 | deny | ask | MCP 動作含 send、post、publish、share、reply、comment、merge、create_pr、deploy、upload 等 |
| G30 | 付費 | deny | deny | MCP 動作含 buy、purchase、checkout、payment、pay、order、subscribe、transfer、renew |
| G40 | 改設定 | deny | ask | Write / Edit 到 `.claude/settings*.json`、`managed-settings.json`、`.credentials.json`、`CLAUDE.md`、`CLAUDE.local.md`、`~/.claude.json`、`.mcp.json`；Bash / PowerShell 用寫檔指令、重新導向或 .NET 寫檔寫這些檔也算（`shell_write`）；`~/.claude/projects/*/memory/**` 和 `~/.claude/plans/**` 除外 |
| G41 | 改設定 | deny | ask | `git config --global/--system`、`claude config/mcp` 的寫入、`setx`、`reg add` 等、PowerShell 改 HKLM / HKCU |
| G42 | 改設定 | deny | ask | MCP 動作含 setting、settings、permission_mode |
| G50 | 機密 | deny | deny | Read / Grep / Glob / NotebookRead 和讀檔類指令（`cat`、`head`、`grep`、`sed`、`Get-Content`、`type`、`cp`、`base64`、`certutil` 等）碰到 `.env`、`.env.*`、`.envrc`、`*.pem`、`*.key`、`*.p12`、`*.pfx`、`id_rsa*` 等私鑰、`.ssh/**`、`.aws/credentials`、`gh/hosts.yml`（含 Windows 的 `%APPDATA%/GitHub CLI/hosts.yml`）、`.git-credentials`、`.npmrc`、`.pypirc`、`.netrc`、`.claude/.credentials.json`、`credentials.json`、`secrets.*`；`.env.example`、`.env.sample`、`.env.template`、`.env.dist`、`*.pub`、`known_hosts`、`.ssh/config` 除外 |
| G51 | 機密 | deny | deny | 印出環境變數：不帶參數的 `env`、`printenv`、`set`、`export`；`export -p`、`declare -x`；`gci env:`；`echo` / `Write-Output` 帶名稱含 token、secret、password、key、credential、auth 的變數；單獨一行 `$env:GITHUB_TOKEN`；`[Environment]::GetEnvironmentVariable(s)` |
| G52 | 機密 | deny | deny | 印出 token 或密碼的指令：`gh auth token`、`gh auth status --show-token`、`git credential fill`、credential helper 的 `get`、`aws configure get`、`aws configure export-credentials`、`aws sts get-session-token`、`az account get-access-token`、`gcloud auth print-*-token`、`kubectl config view --raw`、`security find-*-password -w` |

- worker 的刪除是 deny，訊息會說下一步：把可刪清單（路徑、大小、原因）送給總監或清理員。
- block 模式下 push 對總監也是 deny：沒加 `--rules` 時 `git push` 本來就對每個人標出，規則檔沿用。PO 核准的 push 要在 block 模式下執行，就改用 remind 或 ask 模式；1.3.1 起預設就是 remind。
- G50–G52 對總監也是 deny：讀到的機密會留在對話紀錄裡，誰讀都一樣。需要憑證時回報要哪一個、做什麼用。
- G50 只看讀取工具；寫 `.credentials.json` 仍由 G40 處理。
- G50–G52 擋不到的（寫進限制）：`grep -r` 不指定檔案時掃到 `.env`；`python -c`、`node -e` 這類直譯器讀檔；`$X` 間接展開的變數名；指令輸出本身帶出的 token（例如程式把 token 印到 log）。輸出遮罩屬於下一批。
- 仍然只是安全帶：寫進腳本再執行、變數拼出來的指令、編碼過的指令看不到（Claude Code 文件也說 Bash 權限規則不是安全邊界）。
- 間接執行看不到：`python -c "import subprocess; ..."`、`node -e`、自己寫的腳本裡呼叫 git 或寫檔。這類情況由容器路線處理（容器裡沒有 token、沒有 push 權限），hook 不再追。
- G02 擋不到的：用環境變數帶設定（`GIT_CONFIG_PARAMETERS`、`GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n`）、直接改 `.git/config` 或用 `include.path` 引入的 alias。G02 會多擋只讀的 `git config get alias.p`（新語法）和不帶值的 `git config alias.p`，寧可多擋。
- selftest 會跑每條規則的 `example_block` 和 `example_allow`（兩個身分各一次），所以規則檔加一條，案例就自動多幾個。

### `--audit`（1.1.0）

- `--audit <檔案>`：hook_guard 的每個 deny、ask、remind 和暫停擋下都用 `audit_log.py` 加一行 `kind=decision`（`result.status` 是 `deny` / `ask` / `remind` / `pause`），`rule` 是規則 ID（G..）、`builtin`（沒有規則 ID 的內建擋法）或 `PAUSE`。放行不寫（放行的呼叫由 PostToolUse hook 記）。
- 紀錄寫不進去（鎖被占、磁碟滿、最後一行壞掉）時照樣做原本的決定，不會因此放行或多擋。

### `--review`（1.1.0）

- 預設關。要 `--rules`，而且規則檔要有 `review` 段（`model`、`timeout_s` 1–600、`categories`），否則 exit 1。目前的設定：`haiku`、45 秒、`push` / `delete` / `send` / `config`。
- 只有「規則結論是 ask、而且這條規則的類別在 `categories` 裡」才審查。deny、內建擋法和放行都不送審，所以審查**只能把 ask 升成 deny**，不會放行任何東西。目前只有 director 有 ask（G10、G11、G20、G21、G40–G42）。
- 執行檔：先用 `CLAUDE_CODE_EXECPATH`（目前這個 session 的 claude），沒有才找 PATH 上的 `claude`。路徑結尾是 `.py` 時用同一個 Python 跑（測試用的假 claude）。執行方式：`claude -p --model <model> --settings {"disableAllHooks":true} --tools "" --no-session-persistence --output-format json <提示>`，沒有工具、不跑 hook、不留 session。子程序帶 `DW_HOOK_REVIEW=1`，有這個變數時 hook_guard 不再審查，不會遞迴。
- 提示只有工具名稱、遮罩過的工具輸入（`secret_mask.py`，最多 1000 字）、規則 ID 和理由；不送檔案內容。
- 回覆的 `result` 必須剛好是 `{"verdict": "block" | "no_objection", "reason": "..."}`：
  - `block`：改成擋下，exit 2，`BLOCKED by hook_guard [G10]: second-model review: <理由>`（理由去掉角括號、最多 300 字）。這次擋下照常算進自動暫停。
  - `no_objection`：照舊詢問，理由後面加 `(second-model review: no objection: ...)`，仍由人決定。
  - 逾時、exit 不是 0、找不到 claude、回覆格式不對：照舊詢問，加 `(second-model review unavailable: ...)`。
- `--audit` 的 `rule` 欄寫成 `G10 review=block via=CLAUDE_CODE_EXECPATH`（`via` 是 `CLAUDE_CODE_EXECPATH`、`PATH` 或 `none`）。
- NOT_VERIFIED：selftest 只用假的 claude；沒有用真的 `claude -p` 實測回覆格式、`--tools ""` 和 `disableAllHooks` 的實際效果，也沒有量真實的延遲（hook 預設逾時 60 秒，`timeout_s` 45 秒要留在它之內）。

### `--pause-flag`（1.1.0）

```text
hook_guard.py --rules <tools>/guard_rules.json --profile worker --pause-flag <DIRECTOR>/PAUSE
```

- 每個工具呼叫最先檢查：旗標檔存在時，只放行規則檔 `pause` 段列的呼叫，其他一律 exit 2，stderr 是 `PAUSED by 誰 at 時間: 原因; <pause.reason>`（原因來自 `pause_ctl.py on --reason`，不會有 `<...>`）。暫停放行的呼叫接著照一般規則檢查（例如暫停時 Read `.env` 仍是 G50）。
- `pause` 段：
  - `allow_tools`：Read、Grep、Glob、NotebookRead、TaskList、TaskGet、TaskOutput、ToolSearch、ReadNotifications、`update_plan`、`wrap_up`；`internal_report_tools`（SendMessage）也放行，才能回報停在哪裡。
  - `allow_mcp_read_only: true`：開頭是 get、list、read、search、query、status 的 MCP 工具放行。
  - `allow_write`：Write / Edit / MultiEdit / NotebookEdit 只放行進度檔 `**/RESUME_STATE.md`、`**/TASK_REPORT*.md`。
  - `allow_shell`：每個身分一組 regex。Bash / PowerShell 沒有 `run_in_background`、整行沒有把輸出寫到檔案（不在引號裡的 `>`、`>>`、`2>`、`&>`、`>|`、`>(...)`，`$(...)` 裡的也算；`2>&1`、`>&2` 只是合併串流，照常放行），而且拆出的每個子指令（`名稱 參數...`，不分大小寫）都完整比對到其中一條才放行。預設放行 `git status/log/diff/show/rev-parse`（不可帶 `--output`、`-c`）、`tasklist`、`Get-Process`、`ps`、排序和篩選輸出的指令、`pause_ctl.py status|procs`；`pause_ctl.py off` 只有 director 放行。
- 被擋的：其他 Bash / PowerShell、背景執行、Monitor、Agent、Workflow、其他寫檔、MCP 寫入動作、`start_session`。
- 自動暫停（規則檔 `auto_pause`，只在 `--mode block`）：worker 在 600 秒內被擋 5 次（規則擋下和內建擋法都算），第 5 次就由 hook 自己寫入旗標，第一行是 `PAUSE by hook_guard at 時間: auto: 5 denies in 600s (G02 G50 ...)`，擋下訊息後面多一行 `AUTO-PAUSED ...`。次數記在旗標旁的 `<旗標>.denies`，暫停後清空；已經暫停時的擋下不再計數。director 是 `null`，不開。解除照舊由總監跑 `pause_ctl.py off`，暫停中的 worker 只放行 `pause_ctl.py status`。`.denies` 讀寫失敗時照常擋下、不暫停，不會卡住。setup 的 hook 測試不帶 `--pause-flag`，測試的擋下不計數。`auto_pause` 格式錯（缺身分、次數或秒數不是正整數）：exit 1。
- 給了 `--pause-flag` 卻沒給 `--rules`，或規則檔沒有 `pause` 段、`pause` 段格式錯：exit 1（配合 `onFailure: block` 等於全部擋下）。
- 限制：旗標只擋**新的**工具呼叫，已經在跑的程式（背景批次、子程序）照跑，要依 `docs/02` 停整條程序樹，再用 `pause_ctl.py procs` 確認；含空白的路徑在 allowlist regex 裡比不到 `\S+`，會被擋（寧可多擋）。

### pause_ctl.py（1.1.0）

```text
python -I -X utf8 pause_ctl.py on --director <DIRECTOR> --reason "原因" [--by 名稱]   # 寫 <DIRECTOR>/PAUSE，LOG 記 PAUSE on
python -I -X utf8 pause_ctl.py off --director <DIRECTOR> [--by 名稱]                 # 移除旗標，LOG 記 PAUSE off
python -I -X utf8 pause_ctl.py status --director <DIRECTOR>                         # PAUSE: on by 誰 at 時間: 原因 / PAUSE: off；exit 0
python -I -X utf8 pause_ctl.py procs --root <PID> [--root <PID>...] [--sample 3] [--busy 0.05]
python -I -X utf8 pause_ctl.py procs --pids-file <檔案>                              # 一行一個 PID，# 之後是註解
```

- `--flag <檔案>` 取代 `<DIRECTOR>/PAUSE`；只給 `--flag` 時不寫 LOG。`--by` 預設 `Director`。
- `off` 只有總監能跑：worker 的 hook 在暫停時擋下它。
- `procs` 列出給定 PID 和它們所有子孫，隔至少 `--sample` 秒讀兩次 CPU 時間（Windows 經 PowerShell 讀 `Win32_Process`，Linux 讀 `/proc`），印：
  - `STOPPED`：已經不存在的給定 PID。
  - `REMAINING`：還在的程序，取樣期間 CPU 秒數最多的排最前，每行 PID、PPID、CPU 秒數、名稱、指令列。
  - `PROCS: stopped=n remaining=m busy=k`（busy：取樣期間 CPU 超過單核 `--busy` 比例）。還有程序就 exit 1。
- 間隔用實際經過的時間算（讀一次程序表本身要約一秒）。**永遠不結束程序**：停程序照 `docs/02`，用 PID。
- PID 被系統重新分配給新程式時會被算成 remaining：看指令列確認。

### secret_mask.py（1.1.0）

```text
python -I -X utf8 secret_mask.py [FILE]          # 印出遮罩後的 FILE（沒給就讀 stdin），exit 0
python -I -X utf8 secret_mask.py --check [FILE]  # 每種找到的機密印一行 FOUND kind，最後 SECRETS: n kind(s)；有找到就 exit 1
```

- 整段換成 `[MASKED:種類]`：私鑰區塊、AWS access key、GitHub token 和 fine-grained PAT、Anthropic / OpenAI key、Slack token、Google API key、npm token、JWT。
- 保留前段、只遮值：`Authorization: Bearer` / `Basic` / `token` 後面的值、URL 裡的密碼（`https://user:密碼@host`）、名稱含 password、passphrase、token、secret、api_key、access_key、private_key、client_secret、auth 的 `名稱=值` 或 `名稱: 值`。
- 不遮：40 碼 git SHA、sha256、`max_tokens=4096`、`author=...`、`PWD=...`、已經遮過的值。已知會多遮：`"token_type": "Bearer"`。
- 只認得常見格式，沒見過的 token 格式會原樣通過。也可當模組用：`mask(text)` 回傳 `(遮罩後文字, 種類清單)`。
- `mask_tree(value)`（2.2.0）：遮罩 JSON 結構，序列化之前用。每個字串（含鍵名）都過 `mask()`；鍵名像機密（password、api_key、github_token、auth…）的整個值換成 `[MASKED:field]`，值是 null、true / false 或空字串時保留。先序列化再遮會漏掉 `password="a b"`：JSON 把引號跳脫成 `\"`，遮罩只遮到第一個空白。
- 2.2.0 另外遮：指令字串裡跳脫的 JSON（`{\"password\": \"...\"}`）、單獨的 `Bearer <token>`（8 字以上）、`--password X` 這類空白分隔的旗標、`mysql` / `mysqldump` / `mysqladmin` / `mysqlsh` / `mariadb` / `sshpass` 的 `-p X` 和 `-pX`、`--user bob:X` 和 `curl -u bob:X`、`passw0rd`、`p@ssword` 這類鍵名；`mask_tree` 的 `Authorization`、`Proxy-Authorization`、`Cookie`、`Set-Cookie` 欄位整欄遮。還遮不到的寫法見 CHANGELOG 2.2.0 的已知問題。

### audit_log.py（1.1.0）

```text
python -I -X utf8 audit_log.py append --log <檔案>                     # hook 用：stdin 是 hook 的 JSON
python -I -X utf8 audit_log.py verify --log <檔案> [--from N] [--to M] [--anchor-log <LOG>]
                               [--anchor-rev <commit> --anchor-path <DIRECTOR_LOG 在 repo 裡的路徑> [--repo <DIRECTOR repo>]]
python -I -X utf8 audit_log.py verify --cite "AUDIT_RANGE file=... seq=a..b first=... last=..."
python -I -X utf8 audit_log.py head --log <檔案>                       # 印 AUDIT_HEAD file=... seq=n sha=...
python -I -X utf8 audit_log.py cite --log <檔案> --from A --to B        # 印 AUDIT_RANGE ...，貼進 TASK REPORT
python -I -X utf8 audit_log.py recover --log <檔案>                    # 2.2.0：紀錄壞了，留複本、加一行 recovery 後接著寫
```

- 一行一個 JSON：`seq`、`ts`（UTC）、`session_id`、`agent_id`、`tool`、`tool_use_id`、`kind`（`result` / `failure` / `decision` / `recovery`）、`input`（工具輸入先經 `secret_mask.py` 遮罩，最多 500 字；2.2.0 起先用 `mask_tree` 遮每個字串、名稱像機密的欄位整欄換掉，再序列化，所以沒超過 500 字時是合法 JSON；超過時截斷，結尾 `…`）、`result`（`ok` / `error` / `interrupted`，或 `deny` / `ask` / `pause`；有輸出時只存遮罩後輸出的 sha256 和長度，**不存輸出本身**）、`duration_ms`、`rule`、`prev`（前一行的 hash，第一行是 64 個 0）、`hash`（其他欄位排序後的精簡 JSON 的 sha256）。
- 多個 hook 同時寫：用 `<檔案>.lock`（`O_CREAT|O_EXCL`）排隊，等 5 秒還被占就 exit 1；超過 30 秒的鎖視為殘留，直接接手。最後一行沒寫完、不是 JSON 或 hash 不對時不再往後接，exit 1，訊息要你先 `verify` 再 `recover`。
- Bash 輸出遮罩：`append` 發現 stdout 或 stderr 有機密時，印出 `updatedToolOutput`（欄位和原本相同，只把值遮掉），Claude 看到的就是遮過的輸出。紀錄寫不進去時仍回傳遮罩結果（exit 0）。2.2.0 起「遮罩」和「寫入」是兩個結果：寫不進去時 `hookSpecificOutput` 另加 `additionalContext`（output masked, but the audit line was NOT written），stderr 印 `audit_log: masked=yes|no written=no: <原因>`。PowerShell 工具的輸出格式 NOT_VERIFIED，不遮。
- PostToolUseFailure 的輸入欄位（`error`、`is_interrupt`）照文件假設，NOT_VERIFIED（沒有用 `claude -p` 實際取樣）。
- `verify`：重算整條鏈，印第一個斷點（`BROKEN seq=n: ...` 或 `BROKEN line=n: not JSON`），exit 1；檔案、錨點 commit 或錨點檔不存在 exit 2（`NOT_RUN`）。最後一行是 `AUDIT_VERIFY file=... entries=n head_seq=n [anchors=k] [cite=checked] OK|BROKEN`。
- 錨點：總監過 gate 時跑 `head`，把 `AUDIT_HEAD` 那行寫進 `DIRECTOR_LOG.md` 並 commit。`--anchor-rev` 從 commit 裡的 LOG 讀（`git show <commit>:<路徑>`），所以改工作樹裡的 LOG 騙不過；`--anchor-log` 讀目前的檔案。同一份紀錄（絕對路徑相同）的每個錨點都要還在鏈上、hash 相同；一個錨點都沒有也算失敗。
- **沒有錨點就抓不到整條重寫**：把整條鏈連同每個 hash 重算一次，`verify` 單獨跑會過，只有錨點抓得到。最後一個錨點之後的行被截掉，也要等下一個錨點才抓得到。
- `--cite`：TASK REPORT 的 `AUDIT_RANGE` 那一段的第一行和最後一行 hash 要和現在的紀錄相同，整條鏈也要完整。
- **`recover`（2.2.0）**：`verify` 說 BROKEN（當機截斷最後一行、某行不是 JSON、某行不在鏈上）後用。在鎖內把整份原檔原封不動複製成 `<檔案>.damaged-<UTC 時間>`，保留第一個壞行之前的每一行（最後一個好 hash 和之前的 `AUDIT_HEAD` 錨點都還有效），再接一行 `kind=recovery`：`damage` 記拿掉部分的起始行、行數、位元組、sha256，以及複本的檔名和 sha256。印 `AUDIT_RECOVER ...` 和新的 `AUDIT_HEAD`，之後 `append` 照常接著寫。壞行之後的行只留在複本裡。沒壞的紀錄不動（`nothing broken`，exit 0）；檔案不存在 exit 2。
- `verify` 對每個 recovery 行印 `GAP seq=n: from line a (k lines, b bytes, sha256=...) kept in <複本>, copy checked`，結尾加 `gaps=n`。GAP 本身不算壞；複本找不到時標 `copy not found`，並多印一行 `~ warning seq=n: ...`；有給錨點（`--anchor-log` / `--anchor-rev`）時算 BROKEN（錨定的紀錄少了證據）。複本內容被改過（sha256 對不上）也是 BROKEN。整條鏈壞掉時多印一行 `~ to go on writing: audit_log.py recover --log ...`。

## doctor.py（1.1.0）

```text
python -I -X utf8 doctor.py [--repo <worktree>]                 # 讀設定、跑一次 hook，不寫任何檔
python -I -X utf8 doctor.py --probe                              # 在 Claude 的 Bash 工具裡跑：看子程序實際拿到的環境
python -I -X utf8 doctor.py --probe --director <DIRECTOR>        # 容器裡：再查隔離六項
```

- 每項一行，等級：
  - `ENFORCED`：生效，而且這次查過（hook 實際跑過、紀錄鏈驗過）。
  - `CONFIGURED_NOT_VERIFIED`：設定在，但這次證明不了它有用。
  - `NOT_ENFORCED`：沒生效（有設定把它關掉、claude 版本太舊）。
  - `MISSING`：沒設定。
  - `WARN`、`INFO`、`VERSION` 只是說明，不算失敗。
- 啟動資料夾（1.3.0）：settings 只從 session 啟動的資料夾讀。doctor 從 `~/.claude/projects` 的對話紀錄數出最近 `--launch-days` 天（預設 30）各 worktree 啟動過幾個 session，印 `INFO launch:`。有防護、卻沒有 session 從那裡啟動，印 `settings unread`；session 從沒有防護的 worktree 啟動、別的 worktree 卻有，印 `WARN launch folder unguarded`。有 `--sessions` 檔時，權限一項取各角色最寬鬆的結論，並檢查檔案權限。
- 最後一行 `DOCTOR: enforced=n not_verified=m not_enforced=k missing=j warn=w`；有 NOT_ENFORCED 或 MISSING 就 exit 1。不在 git repo 裡 exit 2。沒有 git 程式（2.1.0）也是 exit 2，印 `doctor: git not found (...)` 和裝 Git 或放上 PATH 的提示，不再當掉；git 拒絕讀別人擁有的 repo（dubious ownership）時另外說明。
- **原生 Windows 上 doctor 一定 exit 1**：`isolation: NOT_ENFORCED (native Windows, no OS-level isolation for shell)`。這是實話，不是設定錯。
- claude 版本：
  - 生效的那個依序取 `CLAUDE_CODE_EXECPATH`、`CLAUDE_PID` 那個程序的執行檔、PATH 上第一個 claude。另外列出 PATH 上每一個，以及 `~/.local/bin` 和 npm 全域資料夾裡不在 PATH 上的（標 `other`）。版本來自 `<exe> --version`，只在本機印，不呼叫模型。
  - 生效版本 < 2.1.295：沒有 `onFailure`，hook 壞掉時會放行 → `hook_guard: NOT_ENFORCED`。
  - Windows 上 < 2.1.310 而且找不到 Git Bash → `hook without Git Bash: NOT_ENFORCED`。
  - < 2.1.314：Monitor 的指令不經過 hook → `Monitor commands: NOT_ENFORCED`。
  - PATH 上任何一個 < 2.1.295 → `WARN`（PATH 順序一變就會用到它）。要不要移除或更新由 PO 決定，doctor 不動它。
- 設定層：使用者（`~/.claude/settings.json`）、專案（`.claude/settings.json`）、本機（`.claude/settings.local.json`）、managed（Windows `C:/Program Files/ClaudeCode/managed-settings.json`，其他 `/etc/claude-code/managed-settings.json`）。hook 和權限清單各層相加；`env` 的鍵和 `defaultMode` 取最高一層的值；任一層 `disableAllHooks: true` → 所有 hook 項目 NOT_ENFORCED。
- `hook_guard`：要有 matcher `*`、`onFailure: block`、`--profile` 的項目，再實際跑一次（和 setup 的 hook 測試相同，依 `--mode` 判斷，不帶 `--audit`、`--pause-flag`、`--review`）。ENFORCED 那行寫出模式（`mode remind` 等）。
- `audit_log`：PostToolUse 和 PostToolUseFailure 都要指到同一份紀錄；紀錄存在就跑 `verify`。
- `permissions`：依 hook 的 `--mode` 算要的清單。規則檔對這個 profile 產生的每一條都在 → CONFIGURED_NOT_VERIFIED（由 Claude Code 執行，doctor 無法實測）。remind 模式只要機密規則（G50）的 deny，就寫 `remind mode: only the secret rules' deny is written`；清單裡還留著這個模式不要的規則權限（例如從 block 換成 remind 卻沒重跑 setup）→ MISSING，因為那條照樣會擋。`defaultMode` 是 `bypassPermissions` → WARN。
- `env_scrub`：設定在但沒加 `--probe` → CONFIGURED_NOT_VERIFIED。`--probe` 只看**變數名稱**：名稱像憑證（token、secret、password、api key 等），或 proxy 變數的值帶 `帳號:密碼@`，就 NOT_ENFORCED 並列出名稱。**值一律不印**；selftest 用一個假的 token 值確認輸出裡沒有它。SCRUB 開著時 `GITHUB_TOKEN`、`GH_TOKEN`、proxy 帳密照樣會被列出，因為官方設計就保留它們。
- `isolation`：不在容器裡 → NOT_ENFORCED。在容器裡（`/.dockerenv`、`/run/.containerenv` 或 cgroup 顯示 docker / containerd / kubepods / libpod）→ CONFIGURED_NOT_VERIFIED；加 `--probe` 再查六項，六項都過才 ENFORCED：根目錄寫不進去、`--director` 的資料夾寫不進去、連不上 `example.com:443`、`example.com` 解析不到（DNS 白名單）、`.git` 是 worker 自己的（K1）、沒有像憑證的變數名稱。`--probe` 在容器裡會試連一次外部網路、查一次 DNS。
  - K1：`run_worker.sh` 會設 `DW_GIT_MODE`。`--git-common` 開的容器（`DW_GIT_MODE=shared`，或 linked worktree，它的 `.git` 就是 repo 的）不加 `--probe` 也直接報 NOT_ENFORCED（K1 shared .git）。`worker_clone.sh` 做的 clone（`DW_GIT_MODE=clone`、不是 linked worktree）在 `worktree` 那一項算 ENFORCED（the worker's own clone）。容器外不看 `DW_GIT_MODE`。
- `worktree`：linked worktree → ENFORCED；主 checkout → NOT_ENFORCED。director profile 不查。
- 暫停旗標的狀態、`--review` 有沒有開（開著會吃 `claude -p` 額度）印成 INFO。

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
python -I -X utf8 gate_check.py --test-request <申請.md>       # TEST REQUEST 欄位齊、單位 GiB、寫入量涵蓋 build + 擷取 + 快取（1.3.0）
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
- `--evidence-dir <資料夾>`（配 `--match`）：AUTO 條件填 PASS 時，證據欄要寫 `evidence_record.py` 產生的 `.json` 檔名，檔案在這個資料夾裡；紀錄的指令 exit 0、沒逾時、產物沒有缺；紀錄的 git HEAD 要和報告的 HEAD 相同，所以最後一次 commit 之後再記。檔案要有 `run` 寫的每個欄位而且型別正確（`schema, label, command, cwd, started, finished, exit_code, timed_out, git, artifacts`），缺一個或型別不對就不算證據，例如只有 `{"exit_code": 0}` 的檔案會失敗；沒有 `schema` 的舊紀錄照舊讀。舊紀錄、沒有 git HEAD 的紀錄、紀錄時有未提交的改動、label 不是這條 AC：Strict 失敗，Standard 只印提示；一份紀錄要給兩條 AC 共用，label 寫兩個（`--label "AC-1 AC-2"`）。Strict 另外要 `schema` 是這版讀得懂的（Standard 提示），`git.dirty` 要明寫 false。紀錄列出的產物會重新算雜湊（相對路徑以紀錄的 cwd 為準），不見或變了：Strict 失敗，Standard 提示；沒有 cwd 的舊紀錄不重算，只提示。報告的 HEAD 要是 7 到 40 位十六進位：Strict 失敗，Standard 和 `--report` 只印提示。工單有 CHECKS 時，紀錄的 command 要和這條 AC 核准的指令完全相同：Strict 失敗，Standard 提示。用 `run --order <WO.md>` 記的紀錄有 `order` 欄（工單 ID、REVISION、雜湊；雜湊和 `--hash` 印給 DISPATCH 行的是同一個），要和工單現在的 ID、版次、雜湊相同；工單改版後要沿用舊證據，總監在 `--dispatch-log` 寫整行 `EVIDENCE_EQUIVALENT <WO-ID> rev=<舊> sha=<舊雜湊> to rev=<新>`（和 DISPATCH 行一樣只認整行，引文、縮排、code fence、寫在別的句子裡都不算），否則 Strict 失敗、Standard 提示。沒有 `order` 欄的紀錄：REVISION 1 照收，印 `WARN evidence not bound to the order`（下一個 MAJOR 起必填 `--order`）；REVISION 2 以上 Strict 失敗、Standard 提示。不加這個參數就和以前一樣，只查有沒有寫證據。這裡只讀紀錄、不重跑；只有 `evidence_record.py verify --rerun --order ...` 才算重跑驗證。紀錄是 worker 自己寫的 JSON，只證明指令跑過而且通過，不證明它測對了東西。
- `--dispatch-log <DIRECTOR_LOG.md>`（配 `--match`）：LOG 裡要有 `DISPATCH <WO-ID> rev=<n> sha=<64 位雜湊>` 一行（`--hash` 會印好給你貼；WO-ID 是工單標題第一個字或檔名，同一工單以最新一行為準），工單現在的雜湊要和它相同。worker 改工單（放寬條件、刪 REVIEW / PO 列、把 REVIEW 改成 AUTO）後重算 `ORDER_SHA256`，報告和工單彼此一致，只有這條會查出來。DISPATCH 必須獨占一行（前面可有 `<日期> |` 欄、後面可有 `| <依據>` 欄）；寫在說明裡、縮排、`>` 引用或 ``` / ~~~ 圍欄裡的都不算。LOG 沒有這張工單的紀錄：各治理模式都失敗。工單標題和檔名的編號要一致，報告 ORDER 行也要指向這張工單。最新一行的 `rev=` 要等於工單的 REVISION，不同就失敗。
- 報告的 `ORDER: <檔名> REVISION <n>` 要和工單的 REVISION 相同，不同就失敗（報告回答的是另一版工單）；沒寫 REVISION：Strict 失敗，Standard 提示。
- `--candidate <40 位>`（配 `--match`）：審查的 commit，總監自己用 `git rev-parse <worker 分支>` 取得，不抄報告。報告的 HEAD 要是它（Strict 以外前綴相同即可），每份證據紀錄的 git HEAD 也要是它（Strict 要完全相同）。不是 40 位十六進位就 exit 2。
- **Strict 的審查綁在一個 commit 上**：Strict 工單做 `--match` 時，沒給 `--candidate`、沒給 `--dispatch-log`、有 AUTO 列填 PASS 卻沒給 `--evidence-dir`、報告 HEAD 不是完整 40 位，都失敗；舊紀錄和沒有 git HEAD 的紀錄也失敗。v0.12 的 Strict 審查指令要補上這三個參數。
- `--preflight 報告 工單`（可重複，只讀）：舊版本做的審查要照現在的 Strict 重審前，逐項列出缺什麼，一項一行 `LACKS`：報告 HEAD 不是 40 位（給 `--repo` 時在那個 checkout 解出完整 commit；解不出來就要 worker 重交）、報告 `ORDER:` 行沒寫 REVISION、LOG 沒有這一版的 DISPATCH 行、AUTO 條件沒有 CHECKS（要用核准重跑就要補）、證據紀錄沒有支援的 schema、git.head 不是 40 位或 `git.dirty` 不是 false（要重新收證）。沒給 `--evidence-dir` / `--dispatch-log` 的部分印 `NOT_CHECKED`。有缺就 exit 1。
- `--hash`：派工時記下，交件時比對。**這是事後偵測，不是事前防止**：任何人都還是改得動工單，只是改了會被查出來；沒有派工紀錄就查不出「改完重算」。
- 固定用詞（判定、下一步、RESULT、治理模式、證據等級）只在 `vocabulary.json` 定義；改用詞時改它，再改 selftest 點名的文件和範本。
- **初衷卡與 PO 看過的紀錄（2.1，shadow：只加 `~` 提示，exit code 不變；沒有新欄位的舊工單照樣通過）**：
  - `--brief BRIEF.md` 單獨用：印 `BRIEF_REVISION = <版次>` 和 `BRIEF_FINGERPRINTS_V1 = {"B-2": "<64 位>"}` 兩行，貼進工單表頭。指紋是 sha256(`brief-row-v1\n` + `[ID, 類別, 內容, 怎麼算做到]` 的精簡 JSON)；同一編號兩列或欄數不是 4，印 `~ BRIEF_UNCONFIRMED`（依據未確認），不給指紋。
  - `--brief` 配 `--order` / `--match` / `--preflight`：工單記的列變了，印 `~ BRIEF_STALE <WO> <B> <AC-1,AC-2>`（舊條件驗過，新條件待重驗）；工單沒有追溯欄時寫 `WHOLE_ORDER`；版次沒升卻內容變了另註「同版內容有變」；列被刪掉寫「需求已取消，待調整範圍」。工單追溯了 B 卻沒記指紋，印 `~ BRIEF_UNCONFIRMED`。
  - `--brief BRIEF.md --snapshot <資料夾>`：只收狀態 LOCKED、有版次的初衷卡，否則 exit 2。快照原子寫入：同資料夾暫存檔、fsync、改名；同內容的舊檔保留。寫完印 `BRIEF_LOCKED rev=<n> sha=<雜湊> snapshot=<路徑>`，整行寫進 DIRECTOR_LOG。再加 `--dispatch-log` 時，以最新一行 BRIEF_LOCKED 為依據：現在的初衷卡不是它（例如定版後的草稿），就改拿快照比，並印 `compared with the locked snapshot`。
  - `--hash <WO.md> --snapshot <資料夾>`：另存 `<WO-ID>-rev<n>-<雜湊>.md`。`--match ... --order-history <資料夾>`：用 EVIDENCE_EQUIVALENT 沿用的證據，拿舊工單記的指紋比；條件變了印 `BRIEF_STALE`，找不到舊工單印 `BRIEF_UNCONFIRMED`（沿用依據未確認）。2.2 起 `evidence_record.py verify --rerun` 加 `--brief` / `--order-history` 也用同一個函式做這項比對（見 evidence_record 第 10 點）。
  - `--po-acceptance PO_ACCEPTANCE.json [--candidate <40 位>]`：檢查 PO 驗收紀錄（schema `po-acceptance-v1`），必填 candidate_id、commit（40 位）、entry、manifest_sha256、offered_message_ref；outcome 是 seen / changes / accepted 時還要 reply_ref，還沒回覆寫 null。少綁一項、雜湊不是 64 位、commit 不是 `--candidate`，印 `~ UNBOUND_PO_REPLY`；綁好的印 `~ PO_ACCEPTANCE <候選 ID>: <commit 前 12 位> <入口>: 已驗收 (<訊息>)`。
  - 裁決可加 `ORDER_SHA256:`、`REPORT_SHA256:`（`--hash` 的值）。`--verdict ... --match` 時值不是現在的雜湊，印 `~ VERDICT_RECORD`。
- **PO 驗收綁到成品本身（2.2，F09，shadow：只改 `~` 提示的內容，exit code 不變）**：
  - `--po-acceptance` 另外核對成品檔：從 `--artifact-root <資料夾>`（預設：驗收紀錄檔所在的資料夾）讀 `entry`，要是這個資料夾裡的檔；紀錄有 `entry_sha256` 就要相同。選填的 `manifest` 欄寫 manifest 檔的路徑，要算得出 `manifest_sha256`。
  - 檔不見、雜湊不同、入口在資料夾外、同一個 `reply_ref` 用在兩份不同成品（候選 ID、commit、入口、兩個雜湊任一不同），都印 `~ UNBOUND_PO_REPLY`，不再印已驗收。
  - 沒有 `entry_sha256` 或沒列 `manifest` 路徑的舊紀錄照讀，印 `~ PO_ACCEPTANCE … PO 回覆 accepted，成品待核對（沒核對的項目）`，不算已驗收。要升成已驗收：補 `entry_sha256` 和 `manifest` 兩欄。
- 證據紀錄有 `log_error`（2.2，F15：`run --log` 寫到一半失敗）：Standard 印提示「its --log was not written in full」，Strict 失敗。重新記一次就好。
- 已有舊檔案的專案導入時：`--warn` 只警告、exit 0；`--since YYYY-MM-DD` 跳過較早的檔案（工單看 ISSUED_BY、RESUME_STATE 看 UPDATED、報告和裁決看第一個日期）；找不到日期的檔案無從比較，也跳過，印 `UNDATED` 並在最後一行另計，要查它就不加 `--since`。先用 `--warn` 看全貌，新工單再用 `--since` 嚴格檢查。舊檔案不追溯修改。

## setup_check.py（2.2.0）

```text
python -I -X utf8 setup_check.py <WS>/DIRECTOR [更多資料夾或檔案]   # 建置完成：待決頁網址和置頂兩行
```

- 讀資料夾裡的 `DIRECTOR_STATE.md`（也可直接給檔案）。每個對象印 `OK   setup <檔案>` 或 `FAIL setup <檔案>`，問題一行一個 `  - ...`，提示 `  ~ ...`。
- 合法的只有三種：`PO_PAGE_URL: https://claude.ai/artifact/<id>`（或 `https://claude.ai/code/artifact/<id>`）加 `PO_PAGE_PINNED: yes`；同樣的網址加 `PO_PAGE_PINNED: no reason=<原因>`（另印提示：請 PO 自己置頂）；`PO_PAGE_URL: NONE reason=<原因>`（沒有頁面，`PO_PAGE_PINNED` 可省略或寫 `no reason=...`，不能寫 yes）。
- 缺行、同一行寫兩次、不是 claude.ai 的 Artifact 網址、`<...>` 佔位、`NONE` / `no` 沒寫原因、檔案不存在，都 exit 1。全部合法 exit 0。
- 只驗格式，不驗頁面真的存在或真的置頂：偽造的 Artifact 網址、`NONE reason=x` 都會 exit 0。所以總監回報時要貼出發布工具回傳的結果原文（BOOTSTRAP 第 6 步第 7 點、第 13 步）。
- `BOOTSTRAP` 第 6、11、13 步要它 exit 0 才送第一份回報。只用在建置流程；舊專案不跑它，`status.py` 只印 shadow 提示 `PO_PAGE_MISSING`（`status_gen.py`）。
- 2.2.1（shadow）：給資料夾、或檔名是 `DIRECTOR_STATE.md` 時，連旁邊的三個檔案一起查；檔案還沒產生只印 `~ not checked, not there yet: ...`。
  - `PO_PENDING.md`：每筆 `ID: OD-xx` / `ID: ACT-xx` 的 ID、STATUS、QUESTION、OPTIONS、RECOMMENDED、SOURCE、ANSWER 各一次（缺 CREATED 只提示）；STATUS 是 open、answered 或 closed；QUESTION、OPTIONS、RECOMMENDED 有填；SOURCE 有填或寫 NONE；answered / closed 要有真的 ANSWER；同一個 ID 只用一次。
  - `RESUME_STATE.md`：前四行依序是 PROGRESS、DOING、NEXT_STEP、COMMS 而且有填，UPDATED 有日期（和 `gate_check.py --resume` 同一條規則）。
  - `director_work.json`：JSON 物件；`schema_version` 是 1（或不寫）；window 在 100000–1000000；mode 是 general / beginner；`plugins_off` 是 `名稱@marketplace`；guard_profile / guard_mode 是已知的值；`*_pattern` 是合法正規式；其他已知鍵型別要對（不認得的鍵只提示）。
  - 問題印成 `  ~ shadow: ...`，exit code 只看待決頁兩行；加 `--strict` 改成 `  - ...` 並 exit 1。從範本複製、還沒填的資料夾會看到 shadow 提示（範本的範例條目和佔位）。

## trace_report.py

```text
python -I -X utf8 trace_report.py --orders <DIRECTOR>/orders --reports <報告資料夾> [--verdicts <DIRECTOR>/reviews] [--config <DIRECTOR>/director_work.json] [--decisions <需求或決定檔.md> ...]
```

- 只讀，印 Markdown 表：需求 | 工單 | AC | 類型 | 狀態 | 證據 | 裁決。需要存檔就自己導到檔案。
- 需求取自工單的 `TRACES_TO`；報告靠 `ORDER:` 行裡的工單檔名對應，沒有就用 TASK_ID 開頭的工單編號；裁決靠標題裡的工單編號。同一工單有多份報告時不看檔名，依序比 `ORDER:` 行的 REVISION、`ATTEMPT: n` 行、報告裡第一個日期（可帶 HH:MM），取最新的；全部相同就兩份都不取，表內寫「多份報告分不出先後」。這些工單會在「同一工單有多份報告」一節列出每份報告和選了哪份。HEAD 只列出，沒有 git 排不出先後。裁決只配選中報告的版次（看裁決的 `ORDER:` 行）：同版多份取日期較晚的，分不出先後就都不取；沒標版次的舊裁決只有一份時照列，加註「未標版次」。`CANDIDATE_HEAD:` 不是報告 HEAD 的裁決一律不放進表，剩不下就寫「未配對」。
- 表後列出：沒有 TRACES_TO 的工單、不符 `trace_id_pattern` 的編號、對不到工單的報告、裁決對不到報告版次（含 `CANDIDATE_HEAD:` 不是報告 HEAD 的）、報告過期或版次不符。沒設 `trace_id_pattern` 就不檢查格式。
- 過期報告（1.3.3）：選中的報告 `ORDER:` 行的 REVISION 不是工單現在的 REVISION，或 `ORDER_SHA256` 不是工單現在的雜湊，狀態欄不再照抄它的 PASS，改寫「過期：…（報告寫 PASS）」或「版次不符：…」。只是提示，不擋；正式判定仍是 `gate_check --match`。沒寫 `ORDER:` 或 `ORDER_SHA256` 的舊報告不判斷。
- 一列一條 AC（1.3.3），不再把 TRACES_TO 的每個編號和每條 AC 交叉配對。工單的 AC 表可加選用的 `追溯`（或 `traces`）欄，寫這條 AC 驗證哪些編號：每個編號一列，空的（或 `—`）寫「（未指定）」；表後另列「AC 的追溯不在工單 TRACES_TO 裡」和「TRACES_TO 裡沒有 AC 驗證的編號」。沒有這欄、TRACES_TO 有兩個以上編號時，每條 AC 一列，需求欄寫「DD-1、DD-2（工單層）」。`--decisions` 也查 AC 追溯的編號。
- `--decisions 檔案`（可重複）：讀專案需求或決定檔裡表格列第一欄的 `XX-數字` 編號。TRACES_TO 寫了、卻不在這些檔裡的，列在「TRACES_TO 找不到的編號」；檔裡有、卻沒有任何工單追溯的，列在「沒有工單的需求」。不給這個旗標，輸出和以前相同。專案用初衷卡時，卡和決策登記表一起查（旗標給兩次）：`--decisions <WS>/DIRECTOR/BRIEF.md --decisions <WS>/DIRECTOR/DECISION_REGISTER.md`；舊專案沒有登記表才只給卡。只有 B 開頭的列算待做項目，「沒有工單的需求」裡的 DD、PO、OD 只是決策紀錄，不代表缺工單。配色這類待預覽的事不要編成 B 號，放在卡的「待預覽」段（`docs/12` 第三節）。
- 初衷卡只用清單列出 DD 編號（`- DD-1 …`，2.1）：只給 `--decisions BRIEF.md` 時，這些編號也算找得到，但不列進「沒有工單的需求」；圍欄裡的清單是例子，不算。表格裡沒有某個開頭的編號時（例如 PO），會提示再加 `--decisions DECISION_REGISTER.md`。
- `--brief BRIEF.md`（2.1，只讀、不擋）：多印「初衷卡三欄」一節，每條 B 一列：有人負責／這版有驗證紀錄／你看過這個成品嗎。
  - 驗證紀錄看選中的報告：AC 狀態，加 `--evidence-dir` 時 PASS 還要找得到證據檔。工單記的指紋和現在的列不同，寫「工單是照舊條件寫的，新條件待重驗」。
  - 你看過：`--director-log` 讀 `PO_PRODUCT_REVIEW` 行，`--acceptance PO_ACCEPTANCE.json`（可重複）讀驗收紀錄，都要綁到報告的 HEAD。看的是別的成品，寫「看過別的成品」；看的是舊條件，寫「當時是舊條件」。
  - 另列 `BRIEF_STALE` / `BRIEF_UNCONFIRMED` 提示和綁不到成品的 PO 回覆（`UNBOUND_PO_REPLY`）。`--director-log` 有 BRIEF_LOCKED 時以它為依據，和 gate_check 相同。
  - `--director-log`、`--evidence-dir` 要配 `--brief`，否則 exit 2；`--acceptance` 可以單獨用。
- **四種證明分開寫（2.2，F08，shadow：只多四欄、exit code 不變）**：初衷卡一節的表頭變成 `| 需求 | 內容 | 有人負責 | worker 自述 | 證據有效 | 綁鎖定依據 | 總監重跑 | 這版有驗證紀錄 | 你看過這個成品嗎 |`。
  - worker 自述：報告的 AC 狀態。全部 PASS 寫 `自述全過（AC-1 PASS）`，**永遠不寫「有」**。
  - 證據有效：加 `--evidence-dir` 時，每條 PASS 的證據檔都要是合格的 `evidence_record` 紀錄、HEAD 是報告的 HEAD（和 `gate_check --match --evidence-dir` 同一套檢查）；沒給寫「未知」。
  - 綁鎖定依據：讀到的初衷卡是 `--director-log` 最新一行 BRIEF_LOCKED 的那份，而且狀態是 LOCKED。
  - 總監重跑：`--director-log` 有這張工單每條 AC、這個報告 HEAD 的整行 `EVIDENCE_RERUN`（`evidence_record.py verify --rerun` 通過時印的 `LOG_LINE:`，總監貼進 LOG）。
  - 這版有驗證紀錄：四欄都齊才寫 `有（AC-1：自述、證據、鎖定依據、總監重跑都齊）`；缺的寫 `部分（缺：…）`。只有 worker 自述的舊專案會從「有」變成「部分」，這是預期的：照上面四步補齊就會回到「有」。工單只有工單層 TRACES_TO（沒逐 AC 指定）時寫 `部分（工單層 TRACES_TO，沒逐 AC 指定；…）`。
- **你看過哪一份成品（2.2，F09）**：
  - 報告可加 `CANDIDATE_ID: <id>`，指定 PO_ACCEPTANCE 裡哪一份成品。同一 commit 有兩份以上成品、報告沒寫 CANDIDATE_ID，寫「分不出是哪一份」。
  - 同一份成品有多筆紀錄時照 `replied_at` 取最新；沒有 `replied_at` 寫「分不出先後」。
  - 報告 HEAD 認不出時，寫「報告 HEAD 認不出，對不到成品」，不拿別的成品充數。
  - `PO_PRODUCT_REVIEW` 行沒寫 `manifest=` 的，寫「對該 commit 的歷史回覆：…，成品待核對」。
  - 驗收紀錄的成品檔照 gate_check 的規則核對（入口和 manifest 從驗收紀錄檔所在的資料夾讀）；同一個 reply_ref 用在兩份不同成品，兩筆都列進綁不到。
- 不悄悄略過檔案：三個資料夾裡不是該類檔案的 `.md`（工單沒有 `ISSUED_BY =`、報告沒有 `TASK_ID`、裁決沒有 `## A`）列在「沒計入的檔案」，寫數量和檔名。舊格式工單要算進來，補一行 `ISSUED_BY = <誰> <日期>`。
- 只看檔案寫了什麼，不判斷做得對不對。資料夾或 `--decisions` / `--brief` / `--director-log` / `--acceptance` 檔不存在 exit 1，其他情況 exit 0。

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

### metrics_report --run（2.1.0，shadow：只讀、只多印一節）

```text
python -I -X utf8 metrics_report.py --run <run 資料夾> [--compare <基準 run 資料夾>] [--director <DIRECTOR>]
```

接手演練（`docs/06b`「接手演練」）每一輪一個 run 資料夾，放在 `DIRECTOR/research/<run>/`：

- `run.json`：`{"v": 1, "run_id": "...", "started_at": "2026-11-08T10:00:00+08:00"}`。沒有這個檔，就用最早的 `run_started` 事件當開始時間。
- `events/*.json`：每個檔是一筆事件或一串事件。每筆都要有 `v: 1`、`event_id`、`type`、`at`（ISO 8601，**要帶時區**，`Z` 也可以）；可以另記 `recorded_at`、`source`。各 type 另外要的欄位：

| type | 另外要的欄位 | 算進哪裡 |
|---|---|---|
| `run_started` | 無 | 開始時間（沒有 `run.json` 時） |
| `asked` | `decision_id`、`topic_id`、`scope_id`、`ask_id` | 決策「提出」；重問 |
| `answer_received` | `decision_id`、`ask_id` | 決策「已回覆」 |
| `applied`、`closed` | `decision_id` | 只記錄，不另算 |
| `withdrawn` | `decision_id` | 決策「撤回」（已回覆的不算撤回） |
| `po_action` | 無；可加 `kind`（click、type、paste…）和 `count`（正整數，預設 1） | PO 操作次數 |
| `preview_ready` | 無 | 第一個可用預覽 = 最早的 `preview_ready` − 開始時間（分鐘） |

- 同一個 `event_id` 只算一次（照檔名順序取第一筆）；內容不同的會註明。缺欄位、不認得的 type、時間沒帶時區的事件不算，列出檔名和第幾筆。
- 決策依 `decision_id` 去重：提出、已回覆、還在等（提出 − 已回覆 − 撤回）、撤回。重問：同一個 `topic_id` + `scope_id` 有幾個不同的 `ask_id`，減 1 再加總；同一個 `ask_id` 重送不算重問。
- `--compare`：省下 = 基準 − 本次（正數表示本次比較少），PO 操作另印百分比，基準是 0 時百分比寫 UNKNOWN。沒有開始時間或沒有 `preview_ready` 時預覽時間寫 UNKNOWN，不寫 0。
- **採樣完整度（2.2，F16）**：`run.json` 可加 `"sampling": {"version": 1, "complete": true, "scenario": "S-1", "counted": ["po_action", "asked"], "kinds": ["click", "type"]}`。
  - `complete: true` 表示這一輪每一筆事件都記了；`counted` 寫有記的 type（省略＝全部）；`kinds` 寫認得的 po_action kind（省略＝任何短名稱）。
  - 每個數字後面標完整度：確認／部分／未知。沒有標記的舊 run 照讀，標「未知」；沒有事件時印 UNKNOWN，不印 0。
  - `--compare` 只在兩邊都「確認」、`scenario` 相同時才相減，否則寫 `UNKNOWN：採樣不完整（…）` 或 `UNKNOWN：劇本不同`。舊 run 要再比較：補上 sampling 標記。
  - `kind` 不是短名稱（例如 `[]`、數字）或不在 `kinds` 裡的 po_action 隔離：列在「隔離」一行，不算、不中斷，exit 0。
  - `answer_received` 要有同一個 `decision_id` + `ask_id`、時間更早的 `asked` 才算已回覆，否則列在「回覆對不到發問」。
- 不加 `--run` 時輸出和以前完全相同；`--director` 和 `--run` 至少給一個。run 資料夾不存在：exit 1。

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
- REQUIRED_CHANGES 看最後結果（2.2，F14）：比的是 merge base 和最後狀態（工作樹現在的檔案加未追蹤檔）的差，不是三段 diff 的聯集。暫存後又改回、或兩次 commit 改了又改回的檔，現在是 `MISSING`。加 `--candidate <commit>` 時改比 merge base 和那個 commit 的 tree，總監審查用這個。多印一行 `REQUIRED_BASIS: worktree-final|candidate=<12 位> final=<n>`。越界檢查（SCOPE / FORBIDDEN）照舊看聯集。
- 最後一行貼進 TASK REPORT。exit 0 通過、1 越界或缺必要改動、2 沒辦法檢查（`NOT_RUN`，包括 SCOPE / FORBIDDEN 下一行不是 `- 項目`）。

## evidence_record.py

```text
python -I -X utf8 evidence_record.py run --out-dir <資料夾> --label AC-1 --order <WO.md> --artifact <檔案或資料夾> -- <指令> <參數>
python -I -X utf8 evidence_record.py verify <紀錄.json>
python -I -X utf8 evidence_record.py verify <紀錄.json> --rerun --order <WO.md> --dispatch-log <DIRECTOR_LOG.md> --repo <候選 commit 的乾淨 checkout> --candidate <40 位>
python -I -X utf8 evidence_record.py verify <紀錄.json> --rerun-recorded   # 跑紀錄裡寫的指令，不算重跑驗證
```

- 紀錄放 repo 外的工作資料夾。只留最後 40 行（`--tail`）、每行最多 400 字；要完整輸出就加 `--log <檔案>`。
- `--log` 的上層資料夾不存在時自動建立（2.2，v2.1.0 已知問題）。建不出來或開不了（例如上層是一個檔案、沒有寫入權限）：印 `EVIDENCE: NOT_RUN cannot open --log …`、exit 2，指令不跑、不寫紀錄（F15；以前會照跑並寫 exit 0 的紀錄）。跑到一半寫不進 log：指令照跑完，紀錄多一個 `log_error` 欄，結論行加 ` log=incomplete(…)`，指令 exit 0 時改 exit 4。
- 沒有 git（2.1.0，例如從 ZIP 解開的規則包）：`run` 照樣跑指令、寫紀錄，`git` 欄是 `{"head": null, "dirty": null}`，stderr 印一行 `git metadata not available (git not found ...)`。這種紀錄在 `gate_check --match --evidence-dir` 算「沒有 git HEAD 的紀錄」（Strict 失敗、Standard 提示）。`verify` 不加 `--rerun` 照常可用；`--rerun` 要 git，沒有就 `NOT_RUN git not found ...`、exit 2，絕不算通過。
- 螢幕只印一行結論，指令本身的 exit code 原樣傳回。
- 讀到不是 UTF-8 的檔（2.2，v2.1.0 已知問題）：gate_check、scope_check、trace_report、metrics_report、evidence_record 都只印一行 `<工具>: NOT_RUN a file is not UTF-8 text (<檔名>) …`、exit 2，不再印 traceback。把檔案另存成 UTF-8 再跑。
- 指令和輸出結尾會照原樣存檔，不要把密鑰放進指令。
- `verify` 先查紀錄有沒有 `run` 寫的每個欄位（缺欄位或型別不對：`NOT_RUN not an evidence record`，exit 2；沒有 `schema` 的舊紀錄照讀，印提示），再比對產物雜湊。結論行把三件事分開印：`integrity=same|changed`（產物和紀錄時相同）、`test=not-rerun|passed|failed(...)`（只有 `--rerun` 跑核准的檢查而且 exit 0 才是 `passed`；不重跑就是 `not-rerun`，不算重跑過）、`artifacts=N missing=M`（紀錄時就缺的、現在不見的都算 missing）。有任何一項不對就是 `MISMATCH`，exit 1；產物缺了絕不會 OK。會變動的產物（含時間戳）重跑後一定不同，這種就只比 exit code 和人工看的部分。
- `--rerun` 跑的是總監核准的檢查，不是紀錄裡寫的指令，四個參數都要給，少一個就 `NOT_RUN`、exit 2，什麼都不跑：
  1. 工單的雜湊和 REVISION 要等於 LOG 裡這張工單最新的 DISPATCH 行，不同就 exit 2。
  2. 用紀錄的 label 找 AC，取工單 `CHECKS:` 裡那條 AC 的指令；沒有就 exit 2。
  3. `--repo` 的 HEAD 要是 `--candidate`（40 位）；不能有修改或未追蹤檔、不能有標成 assume-unchanged 或 skip-worktree 的檔（git status 看不到它們的修改）、不能有 `refs/replace/`（它能讓別的 tree 冒用候選 commit 的名字），否則 exit 2。git 一律關掉 replace 物件來讀。
  4. 指令的程式要是絕對路徑、候選 commit 裡的檔（`./tools/check`）或 `python` / `python3`（就是跑這支工具的 Python）；只寫程式名、要靠 PATH 找的一律 exit 2，避免 PATH 換掉程式。
  5. 從 git 物件把候選 commit 的 tree 寫進新的暫存資料夾，每個檔案都核對雜湊，在那裡跑核准的指令，不在 `--repo` 的工作樹裡跑。紀錄的 git HEAD 不是候選 commit、或紀錄的 command 和核准的不同，都是 `MISMATCH`、exit 1；紀錄的 command 只拿來比對，不會執行。產物在暫存資料夾裡、照它相對紀錄 cwd 的路徑重新算雜湊，不同就是 `MISMATCH`。
  6. 跑完再讀一次 `--repo`：HEAD、tree、狀態或旗標有變，就是 `MISMATCH`、exit 1。
  7. 紀錄的 `order` 欄（`run --order` 寫的工單 ID、REVISION、雜湊）照 `gate_check.py --match --evidence-dir` 的規則比對，LOG 裡的整行 `EVIDENCE_EQUIVALENT` 也照算：Strict 工單不符是 `MISMATCH`、exit 1，Standard 印 `~` 提示；沒綁的紀錄 REVISION 1 印 WARN。
  結論行最後加 `check=AC-1 source=order candidate=<12 位>`。
  8. （2.2，F10）候選 commit 的 tree 有 symlink（mode 120000）或 submodule（160000）時，重建出來的就不是候選 commit，所以 `NOT_RUN unsupported tree mode …`、exit 2，什麼都不跑。這種 AC 改用別的方式驗，或把連結拿出候選 commit。
  9. （2.2，F08）通過時多印一行 `LOG_LINE: EVIDENCE_RERUN <WO-ID> <AC> candidate=<40 位> result=ok record=<檔名>`，總監整行貼進 DIRECTOR_LOG，`trace_report --brief` 的「總監重跑」欄讀它。
  10. （2.2，v2.1.0 已知問題）加 `--brief <BRIEF.md>`（初衷卡）和 / 或 `--order-history <資料夾>`：用 `gate_check --match` 的同一組函式比初衷卡。工單釘的指紋和鎖定的初衷卡比（`brief_notes`）；紀錄是用 EVIDENCE_EQUIVALENT 從舊工單沿用的，再拿舊工單釘的指紋比（`carried_notes`）。結果印 `~ BRIEF_STALE` / `~ BRIEF_UNCONFIRMED`，`LOG_LINE` 結尾多 ` brief=ok|stale|unconfirmed`（`ok` 要有 `--brief`，而且初衷卡是 `--dispatch-log` 裡最新的 BRIEF_LOCKED；只給 `--order-history` 沒給 `--brief` 時沒東西可比，印 `brief=unconfirmed`）。只是提示，exit code 不變；不加這兩個參數時 `LOG_LINE` 和以前一樣。`brief=stale` 或 `brief=unconfirmed` 的行，`trace_report` 的「總監重跑」欄不算，顯示「沒有：重跑時鎖定依據不符」。
- 暫存資料夾只有已 commit 的檔，沒有 `.git`、未追蹤檔和被忽略的檔，跑完就刪。這證明「跑的是總監核准的檢查、在候選 commit 的 tree 上」，但檢查仍會執行候選 commit 裡 worker 寫的測試碼，不是沙箱。`--repo` 仍要乾淨，建議用 `git worktree add --detach <目錄> <候選 commit>` 新開（只新增 worktree，不刪別的）。
- `--rerun-recorded` 是 v0.12 的 `--rerun`：在紀錄的 cwd 跑紀錄寫的指令。能改紀錄的人就能決定跑什麼，所以結論是 `test=recorded-command-passed source=record`，永遠不印 `test=passed`。v0.12 只寫 `--rerun` 的指令現在會 exit 2，改成上面的完整寫法。

## container/（1.1.0 起；1.2.0 加每個 worker 自己的 clone 和 DNS 白名單）：在容器裡跑 worker

在 WSL 裡用 docker 開一個 worker，給它 OS 層的隔離和網路出口管制。原生 Windows 上這兩項 doctor 都報 NOT_ENFORCED，這是 DW 目前唯一能讓 `isolation` 變成 ENFORCED 的路。

```text
# 在 WSL 裡（docker 在那裡），一次：
docker build -t dw-worker:1.2.0 tools/container
# 每個 worker（1.2.0，K1）：先給它自己的 clone，做完再收回那一條分支
bash tools/container/worker_clone.sh create  --repo /mnt/d/.../repo --base <commit> --branch <分支> --dir ~/dw-clones/<名稱>
bash tools/container/run_worker.sh --clone ~/dw-clones/<名稱> --name <名稱> --director /mnt/d/.../DIRECTOR \
     [--offline | --login | --allow <host> | --allow-file <檔案>] [--dry-run] -- claude
bash tools/container/worker_clone.sh collect --repo /mnt/d/.../repo --branch <分支> --dir ~/dw-clones/<名稱> --name <名稱>
# 舊的寫法（1.1.0）：2.2.0 仍支援的舊模式，印 WARN K1，doctor 報 NOT_ENFORCED；只會在 major 版（最早 3.0）移除，小版本不會拿掉。要遷移就改用上面的 worker_clone.sh create + --clone：
bash tools/container/run_worker.sh --worktree /mnt/d/.../wt --director /mnt/d/.../DIRECTOR \
     --git-common /mnt/d/.../repo/.git [--worktree-name <名稱>] [...] -- claude
```

### worker_clone.sh（1.2.0，K1）

- `create`：把 REPO 在 `--base` 的內容完整複製到 `--dir`（`--no-local`：不共用 hardlink，也沒有 alternates）。clone 裡只有 `--branch` 一條分支，沒有 remote、沒有 tag，`.git/config` 由腳本重寫，`.git/hooks` 是空的。clone 裡沒有任何東西指回原 repo。
  - `--dir` 必填，沒有預設，而且不能已經存在（Q4）。建議放 WSL 的 ext4（例如 `~/dw-clones/<名稱>`），不要放 `/mnt/<磁碟>`（數字見下面 K2）。
  - 不要在主機上對 clone 跑 git：worker 可能在裡面留了 config、hook 或 attributes，會在主機上執行。
- `collect`：在一個離線、沒有 capability、clone 唯讀掛載的拋棄式容器裡，把 clone 的 `refs/heads/<分支>` 打包成 bundle（worker 留下的 git 檔案只在那個容器裡被讀到），再交給 `import`。
- `import`：bundle 從這裡起只當資料處理。它必須剛好只有一個 ref `refs/heads/<分支>`，且在 REPO 裡過 `git bundle verify`。objects 先進一個隔離 repo，過 `index-pack --strict` 和 `fsck --strict`，tip 必須是 commit；都過了才把 objects 複製進 REPO，並設 `refs/dw-workers/<名稱>/<分支>`。
  - 原 repo 的其他 ref（分支、tag、`HEAD`）一律不動：worker 碰不到，`collect` 也不改。
  - worker 不能 push（Q3）：容器裡沒有 remote、沒有 token，原 repo 沒掛進去；由總監 `collect`。
  - 成功印 `COLLECTED <ref> <sha>`，exit 0；其他情況印原因，exit 2。selftest 用 12 種 bundle 測過都拒收，拒收後原 repo 的 ref 和 objects 都沒變：兩個 ref、別的分支、名稱只是開頭相同的分支、tag、只有 HEAD、tip 是 tag 物件、fsck 不過的 commit、需要原 repo 沒有的 commit、pack 位元組損毀、截斷、不是 bundle、檔案不存在；不合法的 `--name` 也拒收。
- 代價：每個 worker 多一份完整 objects（DW repo 很小）；容器裡看不到原 repo 的其他分支，要用就在 `create` 時用 `--base` 指定。

- `Dockerfile`：基底 `python:3.12-slim-bookworm` 用 digest 釘住，Claude Code 用 `ARG CLAUDE_VERSION` 釘版本，`DISABLE_AUTOUPDATER=1`。要升級就改這兩行重 build，不會自己更新。
- `run_worker.sh` 給容器的東西只有：
  - `/work`：worker 的 worktree，唯一能寫的專案資料夾。
  - `/director`：DIRECTOR，唯讀。**2.2.0（F11）起 DIRECTOR 不可以和任何可寫掛載重疊**：`--clone`、`--worktree`、`--git-common` 的真實路徑（`pwd -P`）與 DIRECTOR 相同、在它底下、或包住它，都 exit 2、不印 docker 指令；另用 inode（`-ef`）和 `/mnt/<磁碟>` 不分大小寫比對，擋住 symlink、`..`、Windows／WSL 大小寫別名。原因：DIRECTOR 放在 clone 裡時，worker 改 `/work/DIRECTOR/...` 就等於改了唯讀的 `/director`（審查實測寫入成功）。
    - 遷移：先備份 DIRECTOR，再把它搬到 clone／repo 以外的獨立資料夾（例如 `/mnt/d/DIRECTOR-WORK-DIRECTOR`），同步改 `--director` 與專案設定裡寫死的路徑；舊專案若 DIRECTOR 在 repo 內，這是 2.1.0 → 2.2.0 唯一會從「能啟動」變成「exit 2」的行為。
    - 啟動前的重疊檢查是掛載設定檢查，不寫任何檔；doctor 的診斷若要寫入測試，只准用一次性 canary 檔，不碰正式工單。
  - repo 的 `.git`，可寫（見 K1），其中三處另外唯讀蓋上：
    - `hooks/` 和 `config`：之後在主機上執行。少了這兩個就 exit 2，免得 docker 用 root 身分在主機上建出來。
    - `worktrees/`：別的 worktree 的紀錄。它們的 `gitdir` 檔寫的是 Windows 路徑，容器裡看起來不存在，所以容器裡的 `git worktree prune` 會把它們刪掉。
  - 兩種 worktree：
    - 主 checkout（不給 `--worktree-name`）：`--git-common` 必須是 `<worktree>/.git`，`.git` 就在 `/work/.git`。
    - linked worktree（`--worktree-name <名稱>`）：`.git` 掛在 `/repo-git`。主機上 worktree 的 `.git` 檔寫的是 Windows 路徑，Linux 的 git 讀不懂，所以另外唯讀掛一個 `/work/.git` 檔指到 `/repo-git/worktrees/<名稱>`。自己那筆紀錄可寫（index、HEAD、logs），其中 `gitdir` 檔唯讀換成 `/work/.git`，prune 就不會刪它。
  - docker volume `dw-claude-home` → `/home/dw/.claude`：只放容器裡 Claude Code 自己的登入。**這是同一台主機上所有 worker 共用、可寫的同一個 volume（F18）**：clone 隔離不等於登入與使用者設定隔離，一個 worker 能讀到、改到另一個 worker 的登入狀態與設定，也和跨專案、跨帳號共用。需要隔離時，每個信任範圍用自己的 volume：啟動前設環境變數 `DW_CLAUDE_HOME_VOLUME=dw-claude-home-<範圍>`（預設仍是 `dw-claude-home`，不設就和 2.1.0 一樣；名稱只准字母、數字、`_ . -`），各 volume 第一次都要在容器裡 `/login`。舊 volume 保留到確認遷移完成再刪（刪除屬於 PO 或總監的決定）。
  - `--clone`（1.2.0）：`/work` 就是 worker 自己的 clone，`.git/config` 和 `.git/hooks` 另外唯讀蓋上；原 repo 完全不掛。上面 `.git` 的三種掛法只用在舊的 `--git-common`。
  - 環境變數只有這些：`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`、`XDG_CACHE_HOME`、`DW_ALLOW_DOMAINS`、`DW_DNS_UPSTREAM`、`DW_WORKER_NAME`（audit log 檔名用）、`DW_GIT_MODE`（`clone` 或 `shared`，doctor 用），有網路時 `--sysctl`（關 IPv6，不是環境變數），`--git-common` 時再加 `GIT_CONFIG_COUNT/KEY/VALUE` 設的 `gc.auto=0` 和 `gc.worktreePruneExpire=never`（git 不會自己 gc 或 prune）。不帶 `--env-file`，主機的變數一個都不進去。`--offline` 沒有 `DW_ALLOW_DOMAINS` 和 `DW_DNS_UPSTREAM`。
  - 沒有 `GIT_DIR` 和 `GIT_WORK_TREE`：設成全域變數，容器裡每個 git 都會指到這個 repo，連在別的資料夾跑的也是（selftest 在暫存區 `git init` 就壞了）。
  - 不掛主機的家目錄、`~/.ssh`、gh 設定、AppData，也沒有 docker socket。
- 權限：`--cap-drop ALL`，只加回 NET_ADMIN、NET_RAW、SETUID、SETGID、SETPCAP，給 entrypoint 以 root 設防火牆用。設完 `setpriv` 換成使用者 `dw`，並清空所有 capability（包括 bounding set，所以要 SETPCAP）和 `no_new_privs`。另有 `--read-only`（根目錄唯讀，`/tmp`、`/run` 是 tmpfs）、`--pids-limit 512 --memory 4g --cpus 4`。
- 網路（`init_firewall.sh`，分兩段，中間由 entrypoint 啟動 `dns_allow.py`）：OUTPUT 預設 DROP。只放行 loopback、已建立連線的回應、使用者 `dwdns`（只有 `dns_allow.py` 用）對 `DW_DNS_UPSTREAM` 的 53，以及白名單名稱在**開容器當下**解析到的 IPv4 的 TCP 443。其他一律 REJECT；IPv6 一律 DROP。
  - **這條規則的準確說法（F18）：放行的是「解析後的目的 IP:443」，不是網域名稱。** 防火牆不看 TLS SNI，也不看 HTTP Host；同一個 IP 上若還有別的網站（CDN、共用主機），443 也連得到。要做到網域層控制，得改用受控代理並禁止直接連線，目前沒有做。
  - IPv6（F18）：`init_firewall.sh` 設 `ip6tables` DROP 時失敗會被忽略，所以 2.2.0 的 `run_worker.sh` 在有網路時另外給 docker `--sysctl net.ipv6.conf.all.disable_ipv6=1` 和 `net.ipv6.conf.default.disable_ipv6=1`（映像不變，仍是 `dw-worker:1.2.0`）。docker 不接受這個 sysctl 時容器起不來（失敗即關閉）。實際有效與否用 `doctor.py --probe` 在容器裡驗證；本版沒有在真實 Docker 上跑（見 TASK_REPORT 的 UNVERIFIED）。
  - 名稱清單：`--allow-file`（預設是同資料夾的 `dns_allow.txt`，裡面只有 `api.anthropic.com`），加上 `--login` 和 `--allow`，依序合併、去重、轉小寫；有不合法的名稱就 exit 2，清單是空的也 exit 2（要沒網路就用 `--offline`）。
  - `--login` 加 `claude.ai`、`platform.claude.com`、`console.anthropic.com`，只有第一次登入要用。
  - `--allow <host>` 再加別的名稱。`*.example.com` 代表它底下的子網域（不含本身）：只解析，不開 443。
  - `--offline` 是 `--network none`，完全沒有網路，也不啟動 resolver。
- DNS（1.2.0，`dns_allow.py`，只用標準庫）：容器的 `/etc/resolv.conf` 指向 `127.0.0.1`（`--dns 127.0.0.1`），53 埠轉到 `dns_allow.py` 的 5353。
  - 它以使用者 `dwdns` 跑，沒有任何 capability、`no_new_privs`；`dw` 結束不了它，也搶不到 5353。
  - 只回答白名單名稱的 A / AAAA（class IN、一個問題、opcode 0）。不在清單的名稱回 NXDOMAIN；其他型別（TXT、MX、ANY…）回 REFUSED；格式錯回 FORMERR；上游都沒回應回 SERVFAIL。
  - 轉給上游時用新的隨機 ID、名稱轉小寫、不帶 worker 送來的其他欄位；回來的答案要對得上 ID 和問題才轉回去。
  - 被擋的名稱寫一行 `dns_allow: refused <名稱> type <n>` 到容器的 stderr（同一名稱只寫一次，最多 100 個）。
  - 上游：`DW_DNS_UPSTREAM`（以空白分隔的 IPv4），沒設就用主機 `/etc/resolv.conf` 裡不是 `127.x` 的 IPv4 nameserver（WSL 的 `127.0.0.53` 容器連不到）。都沒有就 exit 2，請設 `DW_DNS_UPSTREAM`。
  - 沒有關閉開關（Q2）。直接 `docker run` 不帶 `DW_DNS_UPSTREAM`，容器拒絕啟動。直接問 `8.8.8.8`、`1.1.1.1` 這類 DNS 伺服器會被拒（UDP EPERM、TCP 連線被拒）。
- `--dry-run` 只印出 docker 指令，什麼都不跑。selftest 用它檢查掛載、權限和環境變數。

實測（2026-11-07，WSL2 docker，repo 在 `/mnt/d`，throwaway clone）：

| 項目 | 結果 |
|---|---|
| C1 pull 基底（digest） | 7.4 秒 |
| C2 build（含 apt 和 Claude Code 2.1.317 安裝） | 73 秒；之後只改腳本重 build 3 秒；image 797 MB |
| C3 開容器到結束（`-- true`） | 有防火牆約 0.95 秒，`--offline` 約 0.59 秒 |
| C4 容器裡 `git status` | 約 0.6 秒（主機同一份 clone 約 0.09 秒） |
| C4 容器裡 selftest（`--offline`） | 1304/1304 通過，約 390–430 秒；只在 Windows 跑的案例不算（junction、8.3 短檔名、反斜線等）。主機同一份 clone 1326/1326，約 283 秒 |
| C5 防火牆和繞路探測 | 35 案全部符合預期（見下） |
| C8 容器裡 `setup_project_settings.py --runtime-guard --protect-director /director --apply`，再 `doctor.py --probe --director /director` | linked worktree：enforced=5、not_verified=2（audit_log 還沒有紀錄、permissions），not_enforced=0，exit 0。主 checkout 多一項 worktree NOT_ENFORCED（不是 worker 自己的 worktree）。這是 1.1.0 的結果；1.2.0 起 linked worktree 在容器裡是 K1 shared .git，isolation 會報 NOT_ENFORCED |

1.2.0 實測（2026-11-07，同一台機器，`dw-worker:1.2.0`，來源都是 throwaway clone）：

| 項目 | 結果 |
|---|---|
| 重 build（只改腳本，快取） | 約 3 秒，沒有下載 |
| K1 容器實測 | 9/9：worker 在容器裡 commit；clone 的 hooks/ 和 config 沒被改；`collect` 印 COLLECTED 和 worker 的 commit；原 repo 只多了 `refs/dw-workers/w1/k1`，worker 打的 tag 和移動的 main 都沒進來；原 repo 過 `fsck --strict` |
| DNS 容器實測 | 20/20：`api.anthropic.com` 解析得到（UDP、TCP），`example.com` 和 `<亂數>.api.anthropic.com` 解析不到；TXT 被拒；直接問 `8.8.8.8`、`1.1.1.1` 被拒；HTTPS 只連得到白名單；resolver 以 `dwdns` 跑，`dw` 結束不了它、改不了 iptables、搶不到 5353；`--offline` 照常；不帶 `DW_DNS_UPSTREAM` 拒絕啟動 |
| doctor 容器實測 | 8/8：`--clone` 的 isolation 六項全過（ENFORCED），worktree 報 the worker's own clone；`--git-common` 印 WARN K1，isolation 報 own .git (K1) FAIL（NOT_ENFORCED） |
| K2：`worker_clone.sh create` 和日常 git，ext4（`~`）對 `/mnt/d`（drvfs），DW repo 55 個檔，兩輪 | create 0.63–0.82 秒 對 3.10–3.49 秒；`git status` 10 次 0.07 秒 對 1.96–2.05 秒；寫 1000 個檔 0.04–0.05 秒 對 4.20–4.68 秒；`add` 加 `commit` 0.23 秒 對 11.2–13.8 秒；之後 `git status` 10 次 0.12–0.15 秒 對 5.1–6.1 秒 |

C5 探測，全部在容器裡以 `dw` 身分跑：
- 能連：`api.anthropic.com:443`。
- 連不上（REJECT 或 DROP）：
  - `curl https://example.com`（0.09 秒內被拒）、`example.com:443`、`1.1.1.1:443`（直接用 IP）、`github.com:443`、`api.anthropic.com:80`
  - `host.docker.internal:443`、gateway 的 22 和 2375（docker API）
  - 對 resolver 以外的 DNS（9.9.9.9）、IPv6
- 做不到：
  - 以 `dw` 改 iptables、`su` 成 root（沒有 sudo）
  - 寫 `/` 和 `/usr/local/bin`、寫 `/director` 和 `/director/orders`、掛 tmpfs
- 都沒有：capability（Inh、Prm、Eff、Bnd、Amb 全 0）、docker socket、`/mnt/c`、`/mnt/d`、`~/.ssh`、`~/.config/gh`、像憑證的變數名稱。
- `git status`、`git commit`（帶 `-c user.name=... -c user.email=...`）照常可用，主 checkout 和 linked worktree 都實測過；commit 後主機上的 `git worktree list` 照常。
- 在容器裡真的跑 `git worktree prune`：exit 0，但別的 worktree 的紀錄都還在（寫不進唯讀的 `worktrees/`）；linked worktree 自己的紀錄也還在，`prune -n` 什麼都不列。

已知風險：
- **K1：`.git` 整個可寫（只剩舊的 `--git-common`）。** 1.2.0 的 `--clone` 已經解決：原 repo 不掛進容器，worker 只動得到自己的 clone，總監只收那一條分支。下面是 `--git-common` 仍有的情況，實測在容器裡能做到：
  - 移動或刪除別的 branch 的 ref、打 tag、改 `packed-refs`、寫 objects。
  - `hooks/` 和 `config` 唯讀之後，放 hook、設 `core.hooksPath`、加 alias 都擋下了。這三條是「容器裡寫、主機上跑」的路。
  - `worktrees/` 唯讀之後，容器裡的 `git worktree prune` 刪不掉別的 worktree 的紀錄。代價：容器裡不能 `git worktree add`；`git gc` 有別的 worktree 時會 exit 128（它要改別的 worktree 的 reflog），要 gc 就在主機上跑。
  - 剩下的會影響 ref 的正確性，但不會在主機上執行東西。總監驗收時用 `git rev-parse <worker 分支>` 取候選 commit，不信 worker 寫的 ref。
  - worktree 本身的檔案（腳本、`.claude/settings.local.json`）容器裡照樣能改，主機上之後有人跑它就會執行。這和不用容器時一樣，靠 hook_guard 的 G40 和審查。
- **K2：drvfs 慢，filemode 不同。** `/mnt/d` 上的 git 慢很多（上表：`git status` 約 28 倍、`add` 加 `commit` 約 50 倍）。`--clone` 把 clone 放在 WSL 的 ext4 就沒有這個問題。image 設 `core.filemode false`，免得 `/mnt/d` 上每個檔都顯示權限改了。
- **K3：Desktop 開的 session 不在容器裡。** 只有用 `run_worker.sh` 開的 CLI worker 有隔離。
- **K4：容器用的是 account B 的額度。** 第一次要 PO 在容器裡 `/login`。憑證只存在 volume 裡，DW 不碰。
- **K5：容器裡的 Claude Code 版本另外釘。** 和主機分開升級；doctor 在容器裡報的是容器裡的版本。
- **K6：容器裡的設定寫的是容器路徑。** 在容器裡跑 `setup_project_settings.py`，hook 指令和 audit log 路徑都是 `/work/...`、`/repo-git/...`，這份 worktree 之後只能在容器裡用。audit log 檔名 1.2.0 起是 `{worktree}-{container}.jsonl`：`{worktree}` 是 `DW_WORKER_NAME`（`run_worker.sh --name`），`{container}` 在 hook 執行時換成容器 ID 前 12 碼。所以同一個 repo 開兩個容器 worker 各寫各的紀錄，每份各自一條鏈；`--rm` 每次開容器 ID 都不同，所以每次開容器也是新的一份。
- **DNS 剩下的路。** 1.2.0 的 `dns_allow.py` 只回答白名單名稱，資料不能再藏在任意名稱裡送出去。剩下的：
  - 白名單名稱的查詢仍會到上游，上游看得到名稱、A 或 AAAA、時間。
  - 查詢的時間點（查或不查、隔多久查）可以當成很慢的隱密通道。
  - `*.` 開頭的名稱可以查任意子網域，資料能藏在子網域名稱裡；預設清單沒有 `*.` 名稱，加之前要想清楚。
- **IP 只在開容器時解析一次。** `api.anthropic.com` 的 IP 在 session 中途換掉，連線就會失敗，要重開容器。

## usage_mix.py（1.3.0）

```text
python -I -X utf8 usage_mix.py --since 2026-11-01 [--until ...] [--session <id 前綴>] [--project-dir <資料夾名>] [--all] [--by-session] [--json] [--check]
```

- 讀 `~/.claude/projects` 的對話紀錄（含 subagent），每次呼叫算額度等價量：輸入 × 1 + 快取寫入 × 1.25 + 快取讀取 × 0.1 + 輸出 × 5（每 token），平分給它選的工具呼叫。同一個 `message.id` 拆成幾行的先合併（L-035），分叉或續接的 session 重複的只算一次。
- 印五大類的比例和門檻（讀和查 ≤ 30%、實際動手 ≥ 30%）、細類、各 session 的比例，最後一行 `RESULT ON_TARGET|OFF_TARGET`；`--check` 沒達到就 exit 1。
- shell 指令依序歸類（1.3.1 把原本的 `shell_other` 拆開）：`wait_board`、`render`、`engine_run`、`log_check`、`git`、`disk`；python 執行（`python`、`py -3`、`pytest`、`uv run`、直接跑 `.py`）是 `python_other`，帶審查工具名的是 `review_tools`；`build`（make、cmake、msbuild、dotnet、cargo、npm、node、gcc、pip 等編譯建置）；`list_files`；`shell_search`（grep、rg、findstr、Select-String）；`file_ops`（cat、sed、cp、mv、mkdir、rm、echo、Copy-Item、Set-Content 等）；`sys_query`（程序、版本、環境變數、網路）；剩下的才是 `shell_other`。`build` 和 `python_other` 算實際動手，其他算讀和查。
- `--by-session`（1.3.1）：每個 session 一行（它的 subagent 算在它身上），依花費排序：佔總量比例、呼叫數、等價量、五大類比例、花最多的五個細類。`--top N` 只列前 N 個、不含細類。
- RESTART 行：新 session 第一次呼叫的上下文、新 session 或壓縮後到第一個實際動手的呼叫數和等價量、依上下文大小的單價，和由這些算出的損益兩平點（`docs/04`「開新 session 划不划算」）。
- `--patterns <檔>` 加專案自己的字（執行檔、審查工具名、建置指令），讓 shell 指令歸到對的類別；鍵可以是 `wait_board`、`render`、`engine_run`、`log_check`、`git`、`disk`、`review_tools`、`list_files`、`review_read`、`engine_mcp`、`python`、`build`、`shell_search`、`file_ops`、`sys_query`。專案字只放在那個檔，不進工具。
- 只印比例和數字，不印訊息內容。紀錄格式不是官方介面，改版後可能讀不到；讀不到就印 UNKNOWN，不印 0。

## status_gen.py（1.3.0）

```text
python -I -X utf8 status_gen.py --out <線的資料夾>/status.py --log <log> --hash-file <檔> --outputs <資料夾> --disk D:/ --disk-min-gib 20 --git <worktree>
python -I -X utf8 status_gen.py --out <DIRECTOR>/status.py --config templates/status_director.json   # 總監版：先把路徑改成專案自己的
```

- 產生的 `status.py` 只讀、只用標準庫，總長最多 `--max-lines` 行（預設 60），每行截到 `--width`。大 log 從檔尾讀，不整份讀進來。
- 一般段：LOG（log 尾段）、HASH（雜湊檔尾段、`--checksum` 檔的 SHA-256）、DISK（GiB）、GIT（分支、領先 / 落後、改動數、最近的 commit）、OUT（最新輸出）。
- 總監段（設定檔，都選用）：`po_page`（待決頁的計數：每項一個 regex，或 JSON 頁的 `list` 加 `field` / `value`）、`orders`（沒有結案字樣的工單）、`pending_sends`（還沒勾的 `- [ ]`）、`audit`（每份動作紀錄最近 `hours` 小時的筆數、被擋次數、讀 log 次數、session 數；讀 log 的判斷照抄 `poll_hint.py`）、`processes`（命令列含某字串的程序有沒有在跑）。
- 讀不到的路徑印 MISSING；磁碟低於門檻、讀不到待決頁或程序沒在跑時 exit 1。
- 2.1.0（shadow）：待決頁是文字頁（沒有 `extract`）時，若有項目 `STATUS: open` 但 `ANSWER:` 已填（不算空白或 `<…>` 佔位），多印一行 `PO hint: N item(s) still STATUS open with an ANSWER filled in (ID…)`：PO 可能已回覆但沒改狀態，計數會漏掉，要到頁上讀。exit code 不變。
- 2.2.0（shadow）：總監版設了 `po_page` 時，待決頁旁邊的 `DIRECTOR_STATE.md`（或 `po_page.state` 指定的路徑，相對於設定檔）沒有 `PO_PAGE_URL:` 開頭的行，多印一行 `~ PO_PAGE_MISSING: <路徑> has no PO_PAGE_URL line; publish and pin the PO page (BOOTSTRAP step 6)`，exit code 不變。2.2.0 以前建置的專案會看到它：照 `docs/11`「待決頁網頁的授權與備援」取得同意後補建，或寫 `PO_PAGE_URL: NONE reason=<原因>`。舊的 `status.py` 要用新 `status_gen.py` 重新產生（`--force`）才會印。
- 已存在的 `--out` 要加 `--force` 才覆蓋。

## round_check.py（1.3.0）

```text
python -I -X utf8 round_check.py [--dir <worktree>]        # 資料夾裡每份 RESUME_STATE*.md
python -I -X utf8 round_check.py --resume <RESUME_STATE.md> ...
```

- RESUME_STATE 的 `FIX_ROUNDS:` 每個缺陷一行：`- <缺陷>: round=<n> set=<n> study=<檔名>|NONE`。`set` = (round − 1) // 3 + 1。
- 第 4 輪起，研究檔要存在，而且每個做完的組都有 `## SET n`（或 `## <缺陷> SET n`）一節，填了 `WHERE:`、`ALTERNATIVES:`、`DECISION:`（`docs/07` 第 4 節）。
- 每個缺陷印 OK / FAIL，最後一行 `ROUNDS: PASS|FAIL files= defects= failed=`；有 FAIL 或找不到 RESUME_STATE 就 exit 1。專案的 guard_check 對每個 worktree 跑它。

## poll_hint.py（1.3.0）

- PostToolUse hook（matcher `Bash|PowerShell`）。`tail`、`Get-Content`（`gc`、`cat`、`type`，以及 `head` / `less` 讀 .log .out .err .txt）算一次讀 log。同一個 session 在 `--window` 秒（預設 600）內第 3 次讀同一份檔，就回一段提示「等完成通知」，計數歸零。永遠 exit 0，不擋。
- 安裝（專案的 `.claude/settings.local.json`）：
  ```json
  "PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "\"<PYTHON>\" -I -X utf8 \"<DW>/tools/poll_hint.py\""}]}]
  ```
- 報告：`poll_hint.py report --log <動作紀錄或 glob> [--log ...] [--since 2026-11-01 | --days 7] [--sessions <sessions 檔>] [--json]`，每個 session 一列：讀幾次、幾份檔、最常讀的檔、提示會出現幾次。最後一行 `POLL_REPORT: sessions= log_reads= hints= lines= logs= since=`。只讀。

## report_vs_audit.py（1.3.0）

```text
python -I -X utf8 report_vs_audit.py --report <報告.md> --log <動作紀錄.jsonl> [--log ...] [--session <id>] [--tolerance-min 15]
```

- 報告裡的主張來自兩處：`RAN:` 行（`` RAN: `指令` exit=0 at=19:40 ``，exit 和 at 可省），以及 TESTS / EVIDENCE / DONE 欄位裡看起來是跑 selftest、Unity、Blender 或雜湊檢查的 `` `指令` ``（同一行的 `exit=N`；PASS、OK、通過 當成 exit 0）。
- session 取 `--session`，沒有就取報告的 `SESSION_ID:`，再沒有就取紀錄裡唯一的 session_id；都沒有就 exit 2。
- shell 指令比對同一個 session 的 Bash / PowerShell 紀錄（空白、引號、斜線方向不計；紀錄被截在 500 字的比前段）；`mcp__` 工具比對工具名。exit 0 要有一筆 ok，其他 exit 要有一筆 error；有 `at=` 就要在誤差內。只被 hook 擋下的會寫明。紀錄的雜湊鏈斷了印 `FAIL log: hash chain`。
- 最後一行 `REPORT_VS_AUDIT: PASS|FAIL|NONE claims= ok= failed= session= logs=`；FAIL exit 1，不能跑 exit 2。
- 只證明「有跑、結果和報告一致」，不證明跑的內容對；動作紀錄沒有 exit code，用 ok / error 判斷。
- 2.2.1：被截在 500 字的紀錄行照 JSON 規則解回（`\"`、`\\` 還原；2.2.0 沒還原，含引號或反斜線路徑的長指令比不到）。比對前去掉 `&`、`cmd /c`、啟動程式（python、py、pwsh、powershell、node、bash 等）和它的啟動旗標；`...`、`…`、`<名稱>` 當萬用字；單一檔名可以對到以它結尾的較長路徑；靠詞比對時至少要 2 個實詞（只寫啟動程式不算）。只比 Bash / PowerShell 的紀錄。紀錄有 `kind=rebuild` 行時多印 `~ note: a log was rebuilt from a transcript ...`。

## transcript_audit.py（2.2.1）

```text
python -I -X utf8 transcript_audit.py build --out <新紀錄.jsonl> [--force] --transcript <transcript.jsonl> [--transcript ...]
python -I -X utf8 transcript_audit.py build --out <新紀錄.jsonl> [--force] --session <ID> [--project-dir <專案資料夾>] [--root <~/.claude/projects>] [--no-subagents]
```

- 沒裝 hook 做完的工作，從本機 transcript 重建一份 `audit_log.py` 格式的紀錄：每個有結果的工具呼叫一行，`input` 用 `audit_log` 同一段程式遮罩、截在 500 字；`is_error` 的結果是 `kind=failure`（使用者中斷是 `interrupted`），其他是 `kind=result`；依結果的時間排序後串成雜湊鏈。`audit_log.py verify` 和 `report_vs_audit.py` 照讀。
- `--transcript` 也讀旁邊的 `<檔名>/subagents/*.jsonl`（`--no-subagents` 不讀）。`--session` 找 `<root>/<專案資料夾換成 - 的名字>/<ID>.jsonl`。
- 第 1 行是 `kind=rebuild`，`source` 記來源 transcript 的名稱、sha256、大小，和 `no_result`（還沒有結果，不寫）、`duplicates`（同一個 id 又出現，留第一筆）、`no_time`、`bad_lines` 的數目。
- 印 `TRANSCRIPT_AUDIT file= lines= sessions= no_result= duplicates= no_time=` 和新紀錄的 `AUDIT_HEAD`。exit 0 寫好；1 拒絕（`--out` 已存在）或沒寫成；2 不能跑（沒有 transcript、找不到工具呼叫、參數不對）。
- 限制：`result.sha256` 算的是 transcript 裡的結果，和 hook 紀錄的不能互比；`duration_ms` 是 null；hook_guard 的 decision 行無法重建。transcript 格式是 Claude Code 自己的、沒有文件，格式改了會找不到工具呼叫並 exit 2。重建的紀錄只表示 transcript 裡有什麼，不能證明沒做別的事；有 hook 紀錄和 AUDIT_HEAD 錨點時，以那份為準。

## browser_check.py（2.2.0）

用無頭 Chrome 和假的 Artifact SDK 檢查選擇頁的行為（F04 F05 F07 頁面端）：錯指紋或舊格式回覆不會藏起題目、回條只配給總監採用的回覆、指紋不符禁止送出、重送沿用同一個 submissionId。

```
python -I -X utf8 browser_check.py [--chrome <Chrome 路徑>] [--page <choice_page.html>]
```

找瀏覽器的順序：`--chrome`、環境變數 `DW_CHROME`、PATH 上的 google-chrome／chromium／chrome、Windows 的 Chrome 與 Edge。找不到：印 `SKIP browser_check: …` 並結束碼 0；`DW_REQUIRE_BROWSER=1`（CI 用）時結束碼 1。每項印一行 `名稱=True/False`，任一項 False 結束碼 1。selftest 不依賴它。

## choice_reconcile.py（2.2.0，shadow）

```text
python -I -X utf8 choice_reconcile.py register --db <DIRECTOR>/choice_inbox.sqlite3 --snapshot <一題一版.json>
python -I -X utf8 choice_reconcile.py publish  --db <DIRECTOR>/choice_inbox.sqlite3 --question CH-01 --revision 2 | --close
python -I -X utf8 choice_reconcile.py ingest   --db <DIRECTOR>/choice_inbox.sqlite3 --export <從選擇頁讀回來的.json> [--source <artifact id>]
python -I -X utf8 choice_reconcile.py rescan   --db <DIRECTOR>/choice_inbox.sqlite3
python -I -X utf8 choice_reconcile.py plan     --db <DIRECTOR>/choice_inbox.sqlite3 --question CH-01 --revision 2 [--wo WO-012] [--orders <DIRECTOR>/orders]
python -I -X utf8 choice_reconcile.py advance  --db <DIRECTOR>/choice_inbox.sqlite3 --question CH-01 --revision 2 --from QUEUED --to CLAIMED --session <名字> [--generation N] [--result <文字>]
python -I -X utf8 choice_reconcile.py settle   --db <DIRECTOR>/choice_inbox.sqlite3 --key <來源鍵> --to NOTED|SUPERSEDED|CLOSED [--result <文字>]
python -I -X utf8 choice_reconcile.py status   --db <DIRECTOR>/choice_inbox.sqlite3 [--now <ISO>] [--late-min 10] [--stuck-min 30] [--json]
```

- 選擇頁回覆的本機帳本（`docs/12` 第四、六節），一個 SQLite 檔：`revisions`（每題每版的快照和 hash，登記後不能改）、`questions`（頁面上現在是哪一版、題目開或關，和快照分開記）、`inbox`（每筆回覆一列，用來源鍵和冪等鍵去重）、`decisions`（每題每版最多採用一筆和它的狀態）、`effects`（固定的 WO 編號、持有者、世代、結果）、`events`（每一步誰動的）、`quarantine`（讀不懂的那幾筆）。
- 回覆身分是 `questionId + revision + snapshotHash + submissionId`；冪等鍵是 `<source>|<kind>|<submissionId>`（`docs/12` 第六節）。
- `register` 印 `snapshotHash=sha256:…`（JSON 排序鍵、UTF-8、不含 `snapshotHash` 和 `id`）；同一版內容不同就 `REFUSED`，exit 1。一題第一次登記時同時當成現行版；之後的新版只存快照，等 `publish`。
- `publish --revision N` 把現行版指到 N（要先登記過）；`--close` 記成題目已關。之後所有回覆重判一次，印 `REEVALUATED <來源> <舊> -> <新>`。匯出裡的 `decisions`、或新版的有效回覆，也會帶動現行版。
- `ingest` 的 JSON：`{"source": "<artifact>", "decisions": [...], "choiceReplies": [...], "notes": [...]}`，每筆是 db 的欄位加 `id`。匯出沒有最上層 `source` 時用 `--source` 補；兩者都沒有就當成 `artifact` 並印 `WARNING`（同一筆換一份匯出重送會多算一次）；兩者不同時以匯出的為準，也印 `WARNING`。逐筆讀：讀不懂的那筆進隔離區（`QUARANTINED <來源> reason=`），其他照記。新題的回覆用登記時存的選項重建 `choice` 指的那個選項，跟回覆的 `selectedOptionSnapshot` 比 `key`（有 `label` 也比 `label`）；不一致進隔離區（`reason=snapshot_mismatch`），不記帳、不排工。回覆沒附 `selectedOptionSnapshot`（舊頁面）或那一版還沒登記，照記並印 `WARNING`，不擋。每筆標 `ok`、`legacy`（2.0 舊題）、`note`、`duplicate`、`conflict`、`conflict-late`（題目已採用別的答案後才到）、`conflict-same-submission`、`stale`、`question-closed`、`bad-hash`、`bad-choice`、`unknown-revision`；`ok`、`legacy` 以外的只記錄，進 `RECEIPT_PENDING`，要回給使用者。`unknown-revision` 在快照登記後自動重判；重判時選項對不上的改標 `snapshot_mismatch`，留在 `RECEIPT_PENDING`，不會排工。題目已關閉的 2.0 舊答案記成 `legacy-closed`，直接 `CLOSED`。重送的留言記 `duplicate`，直接 `CLOSED`。再跑一次同一份不會多記（`already=`）。
- `rescan` 重讀隔離區和等快照的回覆。
- `plan` 在 `BEGIN IMMEDIATE` 裡採用最早一筆 `RECORDED` 回覆，先查這一版還能不能做（現行版、hash、題目開著、沒有登記了卻還沒上頁面的新版）：新版待發布印 `HOLD`，其他不符印 `REFUSED`，exit 1。可以就給固定 WO 編號（沒給 `--wo` 就取帳本和 `--orders` 裡最大號加一），印 `PLANNED <鍵> <WO> ... identity={...}`；再跑還是同一張（`already`），已經不能做時多印 `WARNING` 和下一步 `advance --from <目前狀態> --to RECONCILE`。沒有可採用的回覆 `NOTHING`，exit 1。
- `advance` 只照 `RAW → RECORDED → PLANNED → QUEUED → CLAIMED | RECONCILE → RECEIPT_PENDING → CLOSED`（`PLANNED | QUEUED | CLAIMED → RECONCILE`、`RECONCILE → CLAIMED | QUEUED`）走；不是一步 exit 2。動到 `CLAIMED` 或 `RECONCILE` 的要 `--session`，沒給 exit 2。狀態已經不是 `--from`、或 `--generation` 不對，就 `LOST`，exit 1。領取時再查一次版本，世代加 1，記下持有者；只有持有者能交成 `RECEIPT_PENDING`，別人（含 2.1 沒有持有者的領取）`REFUSED`，要先 `CLAIMED → RECONCILE` 接手。持有者以外的人接手一定要帶 `--generation <看到的世代>`，沒帶印 `REFUSED ... a takeover needs --generation N`，exit 2；接手記一筆 `takeover from <原持有者>`。
- `settle` 結案沒被採用的那幾列：留言 `NOTED`、被取代 `SUPERSEDED`、回給使用者後 `CLOSED`；`--key` 是隔離區的來源鍵時 `CLOSED` 代表確認是垃圾，之後不再提起。已被採用的要用 `advance`，exit 1。
- `status` 列出還沒結束的：只有 `ok`、`legacy` 的 `RECORDED` 回覆超過 `--late-min` 分才標「沒交出去」，留言另計 `notes=`；`PLANNED / QUEUED / CLAIMED / RECONCILE` 超過 `--stuck-min` 分標「收到但卡住」；版本已不能做、2.1 沒有持有者的領取另有提示。`receipts_pending` 算所有還在等回條的回覆（含已採用的）。最後一行 `CHOICE_RECONCILE: open= not_handed= stuck= receipts_pending= notes= reconcile= quarantined= clear=yes|no states= (shadow: hints only)`，一律 exit 0；沒有帳本也 exit 0。`status` 打開 2.1 的帳本時也會升級它（見下），不是唯讀。`--json` 只印一份 JSON（`schema: dw-choice-status/2`，摘要行在 `summary`），沒有帳本、帳本壞了也一樣。
- 帳本檔壞了、壞 `--now`、資料夾不存在：`register` 以外的指令只印 `CHOICE_RECONCILE: SHADOW_ERROR <原因>`，exit 0（`status --json` 印成一份 JSON）；`register` exit 2。`publish` 找不到快照、版本不對是 `REFUSED`，exit 1。帳本被另一個總監鎖住超過 `--busy-timeout`（預設 5 秒）：每個指令都印 `CHOICE_RECONCILE: BUSY <原因>`，exit 1（`status --json` 印一份 `"busy": true` 的 JSON），什麼都沒改，稍後重跑。只有 `MOVED`、`PLANNED`、`SETTLED`、`PUBLISHED` 代表狀態真的改了。
- 2.1 的帳本第一次被打開時自動升級（`PRAGMA user_version` 2）：先在升級的鎖內備份：複製到暫存檔，`PRAGMA quick_check` 通過、確定是 2.1 的帳本，才取名 `<帳本>.v210.bak`；這個名字已有檔案（例如上次留下的空檔或半截檔）就改用 `<帳本>.v210.bak.<UTC 時間>`，不覆寫。備份失敗就不升級，原帳本不動。之後補欄位和新表，每題最新一版記成現行版（來源 `backfill-2.1`），舊回覆補冪等鍵，已領取的世代記 1、持有者照留（2.1 沒記持有者的仍是空的，要先接手到 `RECONCILE`）。升級後 2.1 版工具不保證能讀。
- 仍是 shadow：只提示、不擋其他工具；讀 db 和寫回條仍由總監用 `ArtifactData` 做，本工具不連網。

## selftest.py

```text
python -I -X utf8 selftest.py
```

改過任何工具、`vocabulary.json`、`docs/02`、範本或每輪必讀的文件就跑一次。也會檢查：文件和範本裡的固定用詞和 `vocabulary.json` 一致；README 標「每輪必讀」的文件合計不超過上限（`MUST_READ_LIMIT`，2.1.0 起為 9,550 bytes：四份必讀從 12,433 減到 9,550）。要提高上限，commit 訊息寫明原因。GitHub Actions 在每次 push 和 PR 跑同一支（`.github/workflows/selftest.yml`），另外在 PATH 上沒有 git 時再跑一次。

- 沒有 git（2.1.0）：要建 git 測試資料的測試組整組略過，每組印一行 `SKIP <測試組>: needs git, none on PATH`，最後一行寫 `skipped N git group(s)`；其餘照跑，有失敗照樣 exit 1。有 git 時這些測試組照常跑，建資料失敗仍是失敗。`test_no_git` 自己把 git 從 PATH 拿掉，確認 `evidence_record run` 仍寫紀錄、`--rerun` 是 NOT_RUN、doctor 說沒有 git。

## 建議另外寫的（依專案）

- **guard_check**：逐項檢查續航機制（計時器、排程、監看、壓縮設定、記憶大小）並印重建指令，對每個 worktree 跑 `round_check.py`，見 `docs/06b`。各專案機制不同，所以沒有通用版。
- **排程看板工具**：有總管時，看板的讀寫（go / wait / ack / quiet / hold）用一支小工具統一，名稱檢查和 ACK 逾時警示寫在工具裡，見 `docs/02`。
