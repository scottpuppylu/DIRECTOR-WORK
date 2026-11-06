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
| `hook_guard.py` | PreToolUse hook：擋下 push、`reset --hard`、`git clean`、裸 stash、刪 worktree / 分支 / tag、依名稱結束程序；加 `--protect` 時另擋 Write / Edit 改工單和 `DIRECTOR_LOG.md`；加 `--rules` 時依 `guard_rules.json` 對每個工具呼叫回 deny / ask / 不出聲 | 不寫 | 不花；放行時不輸出 |
| `secret_mask.py` | 把文字裡的私鑰、token、API key、JWT、`password=` 這類值換成 `[MASKED:種類]`；`--check` 只列出找到的種類 | 不寫 | 不花 |
| `pause_ctl.py` | 暫停開關：`on` / `off` 寫入或移除 `<DIRECTOR>/PAUSE` 並記進 `DIRECTOR_LOG.md`，`status` 印目前狀態；`procs` 依 CPU 增量列出停機後程序樹還剩哪些 | `on` / `off` 只寫旗標檔和 LOG 一行；`procs` 不寫、不結束任何程序 | 不花 |
| `audit_log.py` | 動作紀錄：PostToolUse / PostToolUseFailure hook 把每個工具呼叫寫成一行有雜湊鏈的 JSONL；`verify` 檢查鏈和總監的錨點，`head` 印錨點，`cite` 印 TASK REPORT 引用的區段 | `append` 只寫紀錄檔和它的 `.lock`；其他不寫 | 不花 |
| `guard_rules.json` | `hook_guard.py --rules` 的規則檔：每條規則的類別、worker / director 的結論、比對方式、正反例子和要寫進 settings 的權限規則 | — | — |
| `selftest.py` | 用正反案例測 gate_check、trace_report、metrics_report、scope_check、evidence_record、hook_guard、pause_ctl、audit_log 和 `--hooks` 安裝；查用詞、必讀文件大小、`PURPOSE.md` 結構和 CHANGELOG 的「對齊初衷」 | 只寫暫存資料夾，結束刪除 | 不花 |

## setup_project_settings.py

```text
python -I -X utf8 setup_project_settings.py --repo <repo>                     # 只回報
python -I -X utf8 setup_project_settings.py --repo <repo> --apply             # 寫入
python -I -X utf8 setup_project_settings.py --config <DIRECTOR>/director_work.json --apply
python -I -X utf8 setup_project_settings.py --plugins-off a@m,b@m --apply     # PO 勾過的才放
python -I -X utf8 setup_project_settings.py --hooks --apply                   # 加裝 hook_guard
python -I -X utf8 setup_project_settings.py --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply
python -I -X utf8 setup_project_settings.py --guard-profile worker --director-worktree <總監的 worktree> --apply
python -I -X utf8 setup_project_settings.py --guard-profile worker --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply   # worker 加暫停旗標
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
- `--guard-profile worker|director`（設定檔 `guard_profile`，隱含 `--hooks`）：hook 的 matcher 改成 `*`（每個工具呼叫都檢查），指令加 `--rules "<tools>/guard_rules.json" --profile <身分>`，並設 `"onFailure": "block"`：hook 自己壞掉（例如規則檔寫壞，exit 1）時擋下，不放行。`--director-worktree` 指定的 worktree 一律用 director。
  - 每條規則的 `permissions` 依這個身分的結論寫進 `permissions.deny` 或 `permissions.ask`（第二層：這兩種規則在每個權限模式都有效，包括 bypass）。缺的報 `MISSING (permissions.deny)` / `MISSING (permissions.ask)`；`--apply` 只補上缺的，放錯清單的（換身分後）搬過去，其他權限規則不動。
  - profile 不同也算 `MISSING (hooks.PreToolUse matcher)`。沒給 `--guard-profile` 時沿用已裝項目的 `--profile`，和 `--protect` 一樣。
  - worker 的指令再加 `--pause-flag "<旗標檔>"`：`--pause-flag`（設定檔 `pause_flag`），沒給就用 `--protect-director` 的 `<DIRECTOR>/PAUSE`。總監的 worktree 不加：worker 暫停時，總監還要停程序樹。旗標檔不同也算 `MISSING (hooks.PreToolUse matcher)`；沒給 `--guard-profile` 時沿用已裝項目的 `--pause-flag`。
- `--audit-log <檔案>`（設定檔 `audit_log`，隱含 `--hooks`）：加 PostToolUse 和 PostToolUseFailure 兩個 hook（matcher `*`），執行 `audit_log.py append --log "<檔案>"`；hook_guard 的指令也加 `--audit "<檔案>"`，擋下和詢問也記進同一條鏈。路徑裡的 `{worktree}` 換成 worktree 資料夾名稱，一個 worker 一份紀錄。缺的報 `MISSING (hooks.PostToolUse)` / `MISSING (hooks.PostToolUseFailure)`，`--apply` 就地換掉舊的 audit_log 項目。沒給 `--audit-log` 時沿用已裝項目的 `--audit`。下面的 hook 測試不帶 `--audit`，測試呼叫不會寫進紀錄。
- 項目到位後，實際跑一次 hook：一個要放行的指令（exit 0）、一個要擋的指令（exit 2），有 `--protect` 時再加一個寫進 `orders/` 的 Write（exit 2）。有 `--profile` 時再加一個每個身分都擋的 MCP 呼叫（`buy_item`，exit 2，證明規則檔有讀到）。放行那次 stdout 也要是空的。結果印在 OK / SET 那行：`(hook test: allow=0 block=2 block-write=2 block-rule=2)`；不對就是 `HOOK_FAIL`，exit 1。

## hook_guard.py

- Claude Code 每次執行 Bash / PowerShell 前把指令以 JSON 傳進來；違反 `docs/08` 的指令 exit 2，理由印到 stderr，指令不執行。
- 只在引號外拆 `&&`、`;`、`|`、`$(...)`。引號裡的字串只有被執行時才檢查：`bash` / `sh -c`、`cmd /c`、`powershell -Command`、`eval`、`Invoke-Expression`，以及雙引號裡的 `$(...)`。所以 `grep "git stash"`、`git commit -m "...git push..."` 不會被擋。
- 略過 `git -C <dir>`、`-c k=v` 這類全域選項；`C:\...\git.exe` 這種反斜線路徑也認得。
- 依名稱結束程序：`Stop-Process` 沒帶 `-Id` 一律擋，包括 `Get-Process x | Stop-Process`。
- 放行：`git stash push -m <標記>`、`stash apply / list / show`、`git clean -n`、`reset --soft`、`taskkill /PID`、`Stop-Process -Id`。
- 不加 `--rules` 時**沒有涵蓋刪檔**：`rm -rf`、`Remove-Item -Recurse` 照常執行，刪檔照 `docs/08` 和 `docs/06b`「刪檔之前」。
- 清理員的 session 不裝這個 hook：它要刪 worktree，而 `worktree remove / prune` 會被擋。
- 只是安全帶，不是安全邊界：寫在腳本檔裡或執行時才組出來的指令看不到。PO 核准的 push 由 PO 自己執行，或先移除 hook。
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
- push 對總監也是 deny：沒加 `--rules` 時 `git push` 本來就對每個人擋（PO 自己執行），規則檔沿用。
- G50–G52 對總監也是 deny：讀到的機密會留在對話紀錄裡，誰讀都一樣。需要憑證時回報要哪一個、做什麼用。
- G50 只看讀取工具；寫 `.credentials.json` 仍由 G40 處理。
- G50–G52 擋不到的（寫進限制）：`grep -r` 不指定檔案時掃到 `.env`；`python -c`、`node -e` 這類直譯器讀檔；`$X` 間接展開的變數名；指令輸出本身帶出的 token（例如程式把 token 印到 log）。輸出遮罩屬於下一批。
- 仍然只是安全帶：寫進腳本再執行、變數拼出來的指令、編碼過的指令看不到（Claude Code 文件也說 Bash 權限規則不是安全邊界）。
- 間接執行看不到：`python -c "import subprocess; ..."`、`node -e`、自己寫的腳本裡呼叫 git 或寫檔。這類情況由容器路線處理（容器裡沒有 token、沒有 push 權限），hook 不再追。
- G02 擋不到的：用環境變數帶設定（`GIT_CONFIG_PARAMETERS`、`GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n`）、直接改 `.git/config` 或用 `include.path` 引入的 alias。G02 會多擋只讀的 `git config get alias.p`（新語法）和不帶值的 `git config alias.p`，寧可多擋。
- selftest 會跑每條規則的 `example_block` 和 `example_allow`（兩個身分各一次），所以規則檔加一條，案例就自動多幾個。

### `--audit`（1.1.0）

- `--audit <檔案>`：hook_guard 的每個 deny、ask 和暫停擋下都用 `audit_log.py` 加一行 `kind=decision`，`rule` 是規則 ID（G..）、`builtin`（沒有規則 ID 的內建擋法）或 `PAUSE`。放行不寫（放行的呼叫由 PostToolUse hook 記）。
- 紀錄寫不進去（鎖被占、磁碟滿、最後一行壞掉）時照樣做原本的決定，不會因此放行或多擋。

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

### audit_log.py（1.1.0）

```text
python -I -X utf8 audit_log.py append --log <檔案>                     # hook 用：stdin 是 hook 的 JSON
python -I -X utf8 audit_log.py verify --log <檔案> [--from N] [--to M] [--anchor-log <LOG>]
                               [--anchor-rev <commit> --anchor-path <DIRECTOR_LOG 在 repo 裡的路徑> [--repo <DIRECTOR repo>]]
python -I -X utf8 audit_log.py verify --cite "AUDIT_RANGE file=... seq=a..b first=... last=..."
python -I -X utf8 audit_log.py head --log <檔案>                       # 印 AUDIT_HEAD file=... seq=n sha=...
python -I -X utf8 audit_log.py cite --log <檔案> --from A --to B        # 印 AUDIT_RANGE ...，貼進 TASK REPORT
```

- 一行一個 JSON：`seq`、`ts`（UTC）、`session_id`、`agent_id`、`tool`、`tool_use_id`、`kind`（`result` / `failure` / `decision`）、`input`（工具輸入先經 `secret_mask.py` 遮罩，最多 500 字）、`result`（`ok` / `error` / `interrupted`，或 `deny` / `ask` / `pause`；有輸出時只存遮罩後輸出的 sha256 和長度，**不存輸出本身**）、`duration_ms`、`rule`、`prev`（前一行的 hash，第一行是 64 個 0）、`hash`（其他欄位排序後的精簡 JSON 的 sha256）。
- 多個 hook 同時寫：用 `<檔案>.lock`（`O_CREAT|O_EXCL`）排隊，等 5 秒還被占就 exit 1；超過 30 秒的鎖視為殘留，直接接手。最後一行沒寫完、不是 JSON 或 hash 不對時不再往後接，exit 1。
- Bash 輸出遮罩：`append` 發現 stdout 或 stderr 有機密時，印出 `updatedToolOutput`（欄位和原本相同，只把值遮掉），Claude 看到的就是遮過的輸出。紀錄寫不進去時仍回傳遮罩結果（exit 0，錯誤印到 stderr）。PowerShell 工具的輸出格式 NOT_VERIFIED，不遮。
- PostToolUseFailure 的輸入欄位（`error`、`is_interrupt`）照文件假設，NOT_VERIFIED（沒有用 `claude -p` 實際取樣）。
- `verify`：重算整條鏈，印第一個斷點（`BROKEN seq=n: ...` 或 `BROKEN line=n: not JSON`），exit 1；檔案、錨點 commit 或錨點檔不存在 exit 2（`NOT_RUN`）。最後一行是 `AUDIT_VERIFY file=... entries=n head_seq=n [anchors=k] [cite=checked] OK|BROKEN`。
- 錨點：總監過 gate 時跑 `head`，把 `AUDIT_HEAD` 那行寫進 `DIRECTOR_LOG.md` 並 commit。`--anchor-rev` 從 commit 裡的 LOG 讀（`git show <commit>:<路徑>`），所以改工作樹裡的 LOG 騙不過；`--anchor-log` 讀目前的檔案。同一份紀錄（絕對路徑相同）的每個錨點都要還在鏈上、hash 相同；一個錨點都沒有也算失敗。
- **沒有錨點就抓不到整條重寫**：把整條鏈連同每個 hash 重算一次，`verify` 單獨跑會過，只有錨點抓得到。最後一個錨點之後的行被截掉，也要等下一個錨點才抓得到。
- `--cite`：TASK REPORT 的 `AUDIT_RANGE` 那一段的第一行和最後一行 hash 要和現在的紀錄相同，整條鏈也要完整。

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
- `--evidence-dir <資料夾>`（配 `--match`）：AUTO 條件填 PASS 時，證據欄要寫 `evidence_record.py` 產生的 `.json` 檔名，檔案在這個資料夾裡；紀錄的指令 exit 0、沒逾時、產物沒有缺；紀錄的 git HEAD 要和報告的 HEAD 相同，所以最後一次 commit 之後再記。檔案要有 `run` 寫的每個欄位而且型別正確（`schema, label, command, cwd, started, finished, exit_code, timed_out, git, artifacts`），缺一個或型別不對就不算證據，例如只有 `{"exit_code": 0}` 的檔案會失敗；沒有 `schema` 的舊紀錄照舊讀。舊紀錄、沒有 git HEAD 的紀錄、紀錄時有未提交的改動、label 不是這條 AC：Strict 失敗，Standard 只印提示；一份紀錄要給兩條 AC 共用，label 寫兩個（`--label "AC-1 AC-2"`）。Strict 另外要 `schema` 是這版讀得懂的（Standard 提示），`git.dirty` 要明寫 false。紀錄列出的產物會重新算雜湊（相對路徑以紀錄的 cwd 為準），不見或變了：Strict 失敗，Standard 提示；沒有 cwd 的舊紀錄不重算，只提示。報告的 HEAD 要是 7 到 40 位十六進位：Strict 失敗，Standard 和 `--report` 只印提示。工單有 CHECKS 時，紀錄的 command 要和這條 AC 核准的指令完全相同：Strict 失敗，Standard 提示。用 `run --order <WO.md>` 記的紀錄有 `order` 欄（工單 ID、REVISION、雜湊；雜湊和 `--hash` 印給 DISPATCH 行的是同一個），要和工單現在的 ID、版次、雜湊相同；工單改版後要沿用舊證據，總監在 `--dispatch-log` 寫整行 `EVIDENCE_EQUIVALENT <WO-ID> rev=<舊> sha=<舊雜湊> to rev=<新>`（和 DISPATCH 行一樣只認整行，引文、縮排、code fence、寫在別的句子裡都不算），否則 Strict 失敗、Standard 提示。沒有 `order` 欄的紀錄：REVISION 1 照收，印 `WARN evidence not bound to the order`（下一個 MAJOR 起必填 `--order`）；REVISION 2 以上 Strict 失敗、Standard 提示。不加這個參數就和以前一樣，只查有沒有寫證據。這裡只讀紀錄、不重跑；只有 `evidence_record.py verify --rerun --order ...` 才算重跑驗證。紀錄是 worker 自己寫的 JSON，只證明指令跑過而且通過，不證明它測對了東西。
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
python -I -X utf8 evidence_record.py run --out-dir <資料夾> --label AC-1 --order <WO.md> --artifact <檔案或資料夾> -- <指令> <參數>
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
  7. 紀錄的 `order` 欄（`run --order` 寫的工單 ID、REVISION、雜湊）照 `gate_check.py --match --evidence-dir` 的規則比對，LOG 裡的整行 `EVIDENCE_EQUIVALENT` 也照算：Strict 工單不符是 `MISMATCH`、exit 1，Standard 印 `~` 提示；沒綁的紀錄 REVISION 1 印 WARN。
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
