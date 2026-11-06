# CHANGELOG

版本號在 `VERSION`。專案導入時把版本號和 commit 一起記進 `DIRECTOR_OPERATING_RULES.md`（`BOOTSTRAP` 第 1 步），升級時讀這份，照「遷移」做。

- **MAJOR**：已經通過的舊檔案或舊設定會變成不通過，例如工具檢查的格式改了、`director_work.json` 的 `schema_version` 升級。一定附遷移步驟。
- **MINOR**：新增規則、文件、工具或選項，舊檔案照樣通過。
- **PATCH**：修正文字、修 bug，規則不變。

## Unreleased（候選 1.0.0-rc.1）

把 Strict 的證據鏈綁在一個候選 commit 上，讓重跑只執行總監核准的檢查，並讓工單版次和 Git 狀態對得上。另外把每輪必讀文件縮小 1,025 bytes。

版本：已經通過的 Strict 審查和舊指令會變成不通過（「對齊初衷」第 5 題、遷移），照本檔政策是 MAJOR。候選版號 1.0.0-rc.1；最後發 0.13.0 還是 1.0.0 由 Owner 決定，決定前 `VERSION` 寫 `Unreleased`，不打 tag。原本寫成 0.13.0 的段落沒有發行過，併進這一段。

- `evidence_record.py verify --rerun` 改成跑工單 `CHECKS:` 裡核准的指令（JSON 字串陣列，不經 shell，工單雜湊包含它，所以派工時的 `DISPATCH` 行已鎖住）。要給 `--order`、`--dispatch-log`、`--repo`、`--candidate`，少一個就 `NOT_RUN`、exit 2。工單雜湊和版次要等於最新的 `DISPATCH` 行，repo 的 HEAD 要等於候選 commit 而且工作樹乾淨。紀錄的指令不同、或不是在候選 commit 記的，都是 `MISMATCH`。舊行為改名 `--rerun-recorded`，結論寫 `test=recorded-command-passed source=record`，絕不印 `test=passed`。
- `evidence_record.py`：欄位型別不對（例如 `artifacts=42`、`command=[1]`）印 `NOT_RUN not an evidence record`、exit 2，不再丟 traceback（`gate_check.py` 也一樣）。
- `gate_check.py --order` 查 `CHECKS:` 格式；Strict 工單有 AUTO 條件卻沒有 CHECKS 只提示。`--match --evidence-dir` 時紀錄的指令要和核准的指令相同（Strict 失敗、Standard 提示）。
- `gate_check.py --match` 新增 `--candidate <40 位>`。Strict 工單少了 `--dispatch-log`、`--candidate`、有 AUTO 列填 PASS 卻沒給 `--evidence-dir`、報告 HEAD 不是完整 40 位、證據是舊紀錄或沒有 git HEAD、紀錄或報告的 HEAD 不等於候選 commit，都失敗。Standard 和 Direct 給了 `--candidate` 才比對。
- 版次：`DISPATCH` 的 `rev=` 要等於工單的 REVISION；報告 `ORDER:` 行的 REVISION 要等於工單（沒寫：Strict 失敗、Standard 提示）。`templates/GATE_VERDICT.md` 加 `ORDER:` 和 `CANDIDATE_HEAD:` 兩行。`trace_report.py` 的裁決欄只放和選中報告同版次的裁決，對不到版次或 HEAD 的列在「裁決對不到報告版次」。
- `trace_report.py --decisions 檔案`（選用，可重複）：列出 TRACES_TO 寫了卻不在需求或決定檔裡的編號，以及沒有任何工單追溯的需求。
- `scope_check.py` 看四種 Git 狀態的聯集：已 commit、已暫存、未暫存、沒被忽略的新檔。已 commit 或已暫存、之後在工作樹改回原樣的修改也看得到。結論行上面多一行 `STATES: committed=n staged=n unstaged=n untracked=n`；結論行格式不變。
- 工單可加選用的 `REQUIRED_CHANGES:` 清單：`scope_check.py` 對每條沒對到改動的 glob 印 `MISSING`、判越界，結論行多 ` missing=n`（沒有這個清單，輸出和以前一樣）。`gate_check.py --order` 查每條都在 SCOPE 裡、不在 FORBIDDEN 裡。
- 每輪必讀文件 13,417 → 12,392 bytes（LF，−1,025），分兩件事：
  - 搬理由：docs/01、03、06、08「為什麼」段裡純理由的 8 條，原文逐字搬到 `docs/10` 的「每輪必讀規則的理由」。有規範句的條目留在原處，每份留一行 `- 其他理由見 docs/10。`。
  - 欄位引用範本：docs/06 的 RESUME_STATE 欄位清單改成「照 `templates/RESUME_STATE.md` 逐欄寫齊」（範本已逐欄列出）。IN_FLIGHT 的最小欄位（背景程序的 PID、啟動時間、輸出檔、完成判定，以及計時器和等待程序）仍寫在 docs/06 本身。
  - 「## 規則」段其他部分逐位元組不變。`MUST_READ_LIMIT` 降到 12,392。
- `docs/11`：Strict 工單的規格審查（`SPEC_REVIEW`）在放上 PO 待決頁之前做完；PO 說「開」的那一輪只寫 `DISPATCH` 行和開 worker。`docs/02`、`templates/SPEC_REVIEW.md` 同步。
- `setup_project_settings.py --hooks --protect-director <DIRECTOR> [--director-worktree <總監的 worktree>]`（或 config 的 `protect_director`、`director_worktree`）：worker 的 hook matcher 改成 `Bash|PowerShell|Write|Edit`，`hook_guard.py --protect` 擋 Write / Edit 改 `orders/` 和 `DIRECTOR_LOG.md`（處理相對路徑、大小寫、`..`、junction、8.3 短檔名）。總監自己的 worktree 維持舊項目。舊的 hook_guard 項目在 `--apply` 時就地換掉，不重複追加。不加 `--protect-director` 和 v0.12 完全相同。這只是防手誤，不是安全隔離（限制見 `docs/11`、`tools/README.md`）。
- Codex 對抗式審查後的修正：
  - `DISPATCH` 只認整行的固定格式（前面可加 `<日期> |`，後面可加 `| <依據>`）。引文、縮排、`>` 開頭和 code fence 裡的都是資料，不算派工（R01、R01b）。`gate_check.py` 和 `evidence_record.py --rerun` 共用同一個 parser。給了 `--dispatch-log` 卻找不到這張工單的 DISPATCH 行，各治理模式都失敗。
  - 工單身分：標題 ID 和檔名 ID 要一致；工單改了 GOVERNANCE 或 ID，雜湊就對不上派工紀錄，不能自己降級（G01）。報告的 `ORDER:` 行要指這張工單（G02）；HEAD、ORDER、ORDER_SHA256、RESULT 各只能寫一次（G02b）。
  - 裁決綁工單和 commit：`--verdict` 搭 `--match` / `--candidate` 時，裁決的 `ORDER:` 行要指到比對的工單和版次，`CANDIDATE_HEAD:` 要等於候選 commit（G04）。`trace_report.py` 不顯示 CANDIDATE_HEAD 和報告 HEAD 不同的裁決，沒有可配的就寫「未配對」（G04b）。
  - 證據：Strict 只收本版讀得懂的 schema（Standard 提示），`git.dirty` 必須是 false（G03、G03a）。紀錄列出的產物重新算雜湊（相對路徑以紀錄的 cwd 為準；沒有 cwd 的舊紀錄只提示），不見或變了：Strict 失敗、Standard 提示（G03c）。
  - `verify --rerun` 由審查端自己物化候選：git 一律關掉 replace objects；有 `refs/replace/`、assume-unchanged 或 skip-worktree 的檔案就拒跑；從 git 物件把候選的 tree 寫進新的暫存資料夾（逐個 blob 驗雜湊），在那裡跑核准的檢查、算產物雜湊；跑完再讀一次 repo（HEAD、tree、狀態、標記）。核准指令的程式要是絕對路徑、候選裡的路徑或 `python`，不讓 PATH 決定（R02–R06）。
  - `scope_check.py`：三段 diff 分開取（base..HEAD、HEAD..index、index..worktree），已暫存或已 commit 的改名不再重複算成未暫存（S01）。一律 `--ignore-submodules=none`，設定擋不掉 FORBIDDEN 的 submodule（S04）。assume-unchanged / skip-worktree 的檔案拿去和 index 比雜湊，不同就算未暫存，另印一行 `FLAGGED:`（S03）。清單項目用反引號包起來就照字面讀，檔名裡的 ` #` 不會被切掉；`gate_check.py --order` 會提示沒包反引號、` #` 後面緊接著字而被切掉的項目（S02）。
  - `hook_guard.py --protect`（Windows）：去掉磁碟或 UNC 路徑的 `\\?\`、`\\.\` 前綴，NTFS 資料流算檔案本身，其他裝置路徑（GLOBALROOT、volume GUID）一律擋（H01、H02）。目標或它的上層資料夾已存在時，再用檔案識別（磁碟序號＋檔案編號）和 `DIRECTOR_LOG.md`、`orders/` 底下每個項目比對，UNC 別名和既有檔案的 hardlink 也擋得到。
  - `setup_project_settings.py`：已裝的 hook_guard 指令和這份工具要寫的不是逐字相同，就是 `MISSING (hooks.PreToolUse command)`，`--apply` 換掉。項目到位後實際跑一次 hook（一筆要放行、一筆要擋，有 `--protect` 時再加一筆寫進 `orders/` 的 Write），答得不對是 `HOOK_FAIL`、exit 1（H04）。
  - `gate_check.py --preflight 報告 工單`（只讀）：舊版本做的審查要照現在的 Strict 重審前，一項一行 `LACKS` 列出缺什麼，並給補法（M01–M03，見遷移第 7 步）。
  - 證據綁工單（G03b）：`evidence_record.py run --order 工單` 把工單 ID、REVISION 和雜湊寫進紀錄的 `order` 欄；雜湊就是 `gate_check.py --hash` 印給 DISPATCH 行的那一個（同一個函式、同樣讀工單檔的位元組）。`--match --evidence-dir` 時，有綁的紀錄要和工單現在的 ID、版次、雜湊相同，或 `--dispatch-log` 有總監寫的整行 `EVIDENCE_EQUIVALENT <WO-ID> rev=<舊> sha=<舊雜湊> to rev=<新>`（和 DISPATCH 用同一套整行規則：引文、縮排、code fence、寫在 NOTE 句子裡的都不算）。沒綁的紀錄：REVISION 1 照收，印 `WARN evidence not bound to the order`；REVISION 2 以上 Strict 失敗、Standard 提示。`--preflight` 對 REVISION 2 以上沒綁的紀錄印 `LACKS`。
- `selftest.py` 加上面各項的正反案例（285 → 486 項）。

對齊初衷：
1. 幫到誰：外部稽核（Codex）和 SDD 報告指出的漏洞，先在暫存 fixture 逐項重現才修：Strict 少給旗標只出提示、`--rerun` 會執行紀錄裡被竄改的指令、`artifacts=42` 丟 traceback、DISPATCH 版次不同照收、已暫存後改回的 FORBIDDEN 修改看不到、裁決配到別版的報告。重現腳本修正前 A01–A11 是 exit 0 或 traceback，修正後是 1 或 2。第二輪 Codex 對抗式審查找到的繞道（改 GOVERNANCE 自己降級、引文裡的 DISPATCH 被當授權、別的 commit 的 PASS 裁決、用 replace refs 或 assume-unchanged 騙過重跑、用裝置路徑繞過 hook）也先用審查附的重現腳本重現，修完再跑一次。
2. Desktop：在 Desktop Code 分頁的 worker session 實作，Python 3.11 跑 selftest 全過。junction 和 8.3 短檔名案在 Windows 實跑，沒有 SKIP；一般帳號沒有建立 symlink 的權限（WinError 1314），symlink 沒測。`--protect-director` 還沒在真實 worker 資料夾裝過；`CHECKS` 和 `--candidate` 還沒在真實工單上跑過，都是 NOT_VERIFIED。
3. 服務：成品要真的對（5）：重跑只跑總監核准的檢查，證據、報告、裁決指向同一個 commit。PO 不用盯細節（3）：工具查得出版次和 Git 狀態不一致。零成本（7）：只用標準函式庫。
4. 核心：每輪必讀變小（13,417 → 12,392 bytes），規則沒有刪，理由搬到 `docs/10`。Direct 不多步驟。PO 不多操作：新參數都是總監下的。
5. 舊檔案和舊指令：可能新不通過的有四種。Strict 審查少了 `--candidate`、`--dispatch-log` 或 `--evidence-dir`；單獨寫 `verify --rerun` 沒給 `--order`（exit 2）；`scope_check.py` 看到以前漏掉的已暫存或已 commit 修改（當 bug 修，Standard 也會報）；DISPATCH 或報告的版次和工單不同。審查修正後再加四種：LOG 裡引用、縮排或放在 code fence 的 DISPATCH 不再算派工；報告 header 欄位重複；Strict 證據的 `git.dirty` 沒寫或 schema 不認得；候選裡有 assume-unchanged / skip-worktree 檔案或 `refs/replace/` 時重跑拒跑；REVISION 2 以上的 Strict 工單，證據沒用 `--order` 綁版次（G03b）。沒有 `CHECKS` 和 `REQUIRED_CHANGES` 的舊工單，`--order` 結果不變。這些照本檔政策是 MAJOR；0.x 升 MAJOR 等於 1.0，由 Owner 決定，所以先寫 Unreleased（候選 1.0.0-rc.1）。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。
2. Strict 的審查指令補上三個參數：`gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md --evidence-dir 證據資料夾 --candidate <git rev-parse worker 分支>`。少一個就失敗。
3. `CHECKS:` 在 v0.13 只是建議：Strict 工單有 AUTO 條件卻沒寫，只印提示。v0.14 起會變成必要，現在就開始在工單 E 節寫。
4. `evidence_record.py verify --rerun` 改成執行工單核定的檢查：`verify 紀錄 --rerun --order 工單 --dispatch-log DIRECTOR_LOG.md --repo <候選 commit 的乾淨 worktree> --candidate <40 位>`。舊行為（跑紀錄裡寫的指令）改名 `--rerun-recorded`，不算重跑驗證。重跑會執行候選 commit 的測試碼，在 `git worktree add --detach` 開的乾淨目錄跑。
5. 報告的 `ORDER:` 行寫 REVISION；裁決加 `ORDER:` 和 `CANDIDATE_HEAD:` 兩行（`templates/GATE_VERDICT.md`）。
6. 要擋 worker 改工單：重跑 `setup_project_settings.py --hooks --protect-director <DIRECTOR> --director-worktree <總監的 worktree> --apply`，舊的 hook 項目會被換掉，裝好後印出 hook 實測結果。
7. 舊版本做的審查要照新 Strict 重審，先跑 `gate_check.py --preflight 報告 工單 --evidence-dir 證據資料夾 --dispatch-log DIRECTOR_LOG.md --repo <受信任的 checkout>`，照每行 `LACKS` 補：
   - 報告 HEAD 不是完整 40 位（M01）：在受信任的 checkout 用 `git rev-parse <短碼>` 解出完整 commit（給 `--repo` 時 preflight 直接印出），寫進新報告，舊報告留著當紀錄。解不出唯一的 commit，就請 worker 重交。
   - 只用 `--match` 比對格式不需要 `CHECKS`，舊工單照樣相容（M02）。要用核准重跑（`verify --rerun`），總監要先寫 `CHECKS:`、升 REVISION、記新的 DISPATCH 行，worker 在新版次重新收證。
   - 證據紀錄沒有 `schema`、`git.head` 不是 40 位或 `git.dirty` 不是 false（M03）：在候選 commit 用這版 `evidence_record.py` 重新收證（或 `verify --rerun`）。已結案的審查保留原檔不動。
8. `DIRECTOR_LOG.md` 的 DISPATCH 行頂格寫成一整行（`gate_check.py --hash` 印的那行）；引用、縮排、放進 code fence 的不算派工。報告和裁決的 header 欄位各寫一次。
9. 證據綁工單（G03b）：worker 收證一律加 `--order`。REVISION 2 以上的 Strict 工單，沒綁的舊證據要在候選 commit 重新收，例如：
   `python -I -X utf8 DIRECTOR/tools/evidence_record.py run --out-dir <證據資料夾> --label AC-1 --order DIRECTOR/orders/WO-001-parser.md -- python -I -m unittest tests.test_parser`
   舊版次的證據確定仍然有效時，總監改在 `DIRECTOR_LOG.md` 頂格寫一整行 `EVIDENCE_EQUIVALENT WO-001 rev=1 sha=<紀錄 order 欄的 sha> to rev=2`，不必重收。
   Codex 重現腳本的 M-C05（對照組，REVISION 2 配沒綁的紀錄）因此從 0 變 1：這是預期變更（G03b 優先），不是退步。

Deprecated：
- 證據未綁工單，下個 MAJOR 起必填 `--order`。現在 `evidence_record.py run` 不加 `--order` 仍可用；REVISION 1 的工單照收，但 `gate_check.py --match --evidence-dir` 會印 WARN。

沒做：
- 兄弟 repo 共用 `<上層>/DIRECTOR/director_work.json`（稽核 P1-5 / A12）：要設計 config 綁 repo 的欄位，延到 v0.14。
- hook 不擋 MultiEdit、NotebookEdit 和用 Bash / PowerShell 寫檔：延到 v0.14 評估。
- `CHECKS` 從提示改成失敗：v0.14。
- `REQUIRED_CHANGES` 對 SCOPE / FORBIDDEN 的檢查是把每一條當路徑比對，glob 對 glob 只是近似。
- `hook_guard.py --protect` 的已知限制（審查 H03、H05）：經由別名（網路磁碟、`subst`、UNC 共用）建立還不存在的 `DIRECTOR_LOG.md` 或 `orders/` 資料夾、hook 執行時目標還不存在的 junction、沒權限建立而沒測的 symlink、MultiEdit、NotebookEdit 都擋不到。真的要擋，請用作業系統的寫入權限保護 DIRECTOR 資料夾。
- 清單項目沒包反引號時，` #` 之後仍是註解（設計如此，S02）；檔名含 ` #` 請用反引號包起來。

## 0.12.0 — 2026-11-06

補上審查工具查不出來或會誤報的地方：worker 改工單後重算雜湊、只有 `{"exit_code": 0}` 的證據檔、檔名排序選錯報告、沒資料時印 0、檔案被悄悄略過。版本照總監派工單定為 MINOR；會讓舊檔案不通過的項目列在「對齊初衷」第 5 題和遷移。

- `gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md`：LOG 裡 `DISPATCH <WO-ID> rev=<n> sha=<雜湊>`（`--hash` 會印好）要和工單現在的雜湊相同。worker 改了工單又重算 `ORDER_SHA256`，報告和工單仍一致，只有這條查得出來。LOG 沒有紀錄：Strict 失敗、Standard 提示、Direct 不查。
- 驗收表（工單和報告）：同一個 AC 兩列、表頭兩欄同名、某列欄數和表頭不同都失敗，不再悄悄取最後一列；反引號裡的 `|` 和 `\|` 不當成欄位分隔。
- `--evidence-dir`：證據檔要有 `evidence_record.py run` 寫的每個欄位且型別正確；沒有 `schema` 的舊紀錄照讀並提示。報告的 HEAD 要是 7 到 40 位十六進位。紀錄時有未提交改動、label 沒寫這條 AC、HEAD 不是雜湊：Strict 失敗，Standard 提示。label 可以寫多條 AC，一份紀錄給多條 AC 共用。
- `evidence_record.py verify` 分三項報告：完整性（檔案雜湊）、測試（紀錄的 exit code，加 `--rerun` 才重跑）、產物（有沒有缺）。只有 `verify --rerun` 算重跑驗證；`gate_check.py` 只讀紀錄。
- `gate_check.py --since`：找不到日期的檔案也跳過，印 `UNDATED`，最後一行另計；要查它就不加 `--since`。
- `metrics_report.py`：沒有裁決時返工印 `UNKNOWN`，沒有 `RESUMED` 行時中斷重做印 `UNKNOWN`，不再印 0。像工單卻沒算進去的檔案、`--since` 略過的和沒有日期的工單，列在文末「沒計入的檔案」。PO 介入的來源可在 `director_work.json` 設 `po_pending_files`、`po_item_pattern`、`po_open_pattern`，加 `--config`；每項的 `CREATED:` 給 `--since` 用，沒寫的照算並標 `UNDATED`。設定或規則式寫壞時印 FAIL、exit 1。
- `trace_report.py`：沒算進去的檔案列在文末。同一工單多份報告時，依 `ORDER:` 行的 REVISION、`ATTEMPT: n`、報告裡第一個日期取最新的，不看檔名；全部相同就都不取並寫明。另列每份報告和選了哪份。
- `templates/PO_PENDING.md` 加 `CREATED:`；`director_work.example.json` 加三個 `po_` 欄位（選用，`schema_version` 不變）。
- `selftest.py` 加上面各項的正反案例（共 285 項）。另一組照外部稽核的跑法同時加 `--order`、`--report`、`--match`、`--evidence-dir`：紀錄由 `evidence_record.py run` 寫出、欄位完整，每案只改壞一項（報告 HEAD、紀錄 HEAD、未提交改動、label）。Strict 每項單獨 exit 1 且只有這一條問題；Standard 下紀錄 HEAD 不符仍 exit 1，其他三項只提示。

對齊初衷：
1. 幫到誰：外部深度分析報告和總監的對抗測試找到的漏洞，在隔離 fixture 逐項重現後才修。worker 放寬或刪掉驗收條件再重算雜湊會通過（對抗測試 T7–T9）。只有 `{"exit_code": 0}` 的檔案能當證據。`report-9.md` 會蓋過 `report-10.md`。真實專案 21 份工單只算 17 份，沒有說明。沒有裁決時返工印 0。
2. Desktop：在 Desktop Code 分頁的 worker session 實作。selftest 在 Python 3.11 通過；3.9 只用 `ast` 檢查語法，實跑交給 GitHub Actions。用真實 `DIRECTOR` 資料唯讀重跑三個工具；真實專案還沒有 `DISPATCH` 紀錄，`--dispatch-log` 在真實工作上 NOT_VERIFIED。
3. 服務：成品要真的對（5）：證據要完整，工單被改查得出。PO 不用盯細節（3）：總監用工具核對，不靠讀檔猜。用數字決定規則留不留：沒資料印 UNKNOWN，不印 0。零成本（7）：只用標準函式庫。
4. 核心：每輪必讀不變（13,417 / 13,428 bytes）。Direct 不多步驟（`--dispatch-log` 對 Direct 不查）。PO 不多操作：`CREATED:` 由總監寫。
5. 舊檔案：可能新不通過的有三種。驗收表有重複 AC、重複欄或欄數不符；加 `--evidence-dir` 時證據紀錄欄位不全；Strict 工單的證據有未提交改動、label 不符或 HEAD 不是雜湊。用真實 21 份工單比對 0.11.1 和本版的 `gate_check.py --warn` 輸出，完全相同。舊檔案先用 `--warn` 只警告。`PURPOSE.md` 第 5 題要「先只警告，或升 MAJOR」；本版靠 `--warn` 過渡，0.x 升 MAJOR 等於 1.0，要 PO 決定。

遷移：
1. 把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。
2. 派工時把 `gate_check.py --hash 工單` 印出的 `DISPATCH` 行記進 `DIRECTOR_LOG`；審查改跑 `gate_check.py --match 報告 工單 --dispatch-log DIRECTOR_LOG.md`。
3. 要用 `--evidence-dir` 的工單，請 worker 用新版 `evidence_record.py run` 重記證據。
4. `PO_PENDING.md` 新項目加 `CREATED:`。待決事項放在別的檔案或格式的專案，在 `director_work.json` 設 `po_pending_files`、`po_item_pattern`、`po_open_pattern`。
5. 同一工單重做時，報告的 `ORDER:` 行寫 REVISION；同一版重做加 `ATTEMPT: n`。
6. `--since` 印 `UNDATED` 的檔案，另外不加 `--since` 查一次。

沒做：
- 這次不做（留給 PO 決定）：`hook_guard` 擴到 Write／Edit 和 `python -c`、`scope_check` 檢查 repo 外的檔案、`context_probe` 固定等 20 秒、`doctor` 指令、SQLite 狀態庫、`worker_task.py`、HTML 面板、多 CLI 轉接。
- 沒有 git 時 HEAD 排不出先後，只列出。多份裁決仍取路徑排最後的。
- `--dispatch-log` 是事後偵測：沒有 `DISPATCH` 紀錄就查不出「改完重算」。

## 0.11.1 — 2026-11-04

修第一次在 Desktop 上跑完整 Strict 工單時找到的工具誤判和文件缺漏。PATCH：規則不變，原本通過的檔案照樣通過。

- `gate_check.py` 的模糊詞檢查不再把檔名裡的 `todo`（例如 `todo.py`）當成模糊詞；單獨寫 `todo`、`etc.` 照樣擋。
- `gate_check.py --report` 不再把程式碼區段裡的 `<...>`（例如 `` `AC-<n>` ``）和 `<名稱@主機>` 這種地址當成沒填的占位字；其他 `<...>` 照樣擋。
- `gate_check.py --report`：`SCOPE_CHECK` 欄照範本貼上 `scope_check.py` 最後一行時，那行本身開頭的 `SCOPE_CHECK:` 會被拿掉再判斷，不再誤判成沒跑檢查。
- `metrics_report.py` 只把 `## A` 節裡有「下一步」的檔案算成裁決；決策紀錄、工單也有 `## A`，之前會被多算。
- `BOOTSTRAP` 第 8 步：`usage_report.py` 的 `--since` 是 UTC 日期；建置 session 不是從專案資料夾開的要加 `--project-dir`。
- `docs/11`：Strict 工單的規格審查要在 PO 發話的同一輪等到結果再開 worker；直接開 worker 可以帶 `cwd`。
- `selftest.py` 加上面各項的正反案例（共 209 項）。

對齊初衷：
1. 幫到誰：拿新專案在 Desktop 上跑一張真實 Strict 工單，總監被工具誤判卡了三次（檔名 `todo.py`、報告裡的格式說明、照範本貼的 `SCOPE_CHECK` 行），成效數字也把決策紀錄算成裁決。
2. Desktop：這次的問題就是在 Desktop 上實測找到的；修完用同一批真實工單、報告、`DIRECTOR` 資料夾重跑，三項都通過，裁決數字從 3 份變成 1 份。selftest 在 Python 3.11、3.12、3.14 通過；本機沒有 3.9，交給 GitHub Actions。
3. 服務：PO 不用盯細節（3，誤判會讓總監停下來問）、用數字決定規則留不留（數字要算對）。
4. 核心：每輪必讀不變（13,417 / 13,428 bytes）；只放寬誤判，擋的範圍沒有變大；PO 不多操作。
5. 舊檔案：原本通過的照樣通過；原本被誤判的現在通過。

遷移：把 `tools/` 整個重新複製到 `DIRECTOR/tools/`。

## 0.11.0 — 2026-11-04

驗收證據可以機器核對，成效數字可以從檔案數出來。MINOR：`gate_check.py` 不帶 `--evidence-dir` 時行為不變；新的紀錄慣例只寫在需要時才讀的文件。

- `gate_check.py --match 報告 工單 --evidence-dir 資料夾`：AUTO 條件填 PASS 時，證據欄要寫 `evidence_record.py` 的 `.json` 檔名；紀錄的指令要 exit 0、沒逾時、產物沒有缺，紀錄的 git HEAD 要和報告寫的 HEAD 相同。紀錄時有未提交的改動、label 不是這條 AC，只印提示。報告沒寫 commit 雜湊時印提示、不比 HEAD。紀錄只證明指令跑過而且通過，不證明它測對了東西。
- 新增 `tools/metrics_report.py`：從 `DIRECTOR` 的裁決、工單、`DIRECTOR_LOG`、`PO_PENDING` 數出 `PURPOSE.md` 的成效數字（返工、中斷後重做、PO 介入、導入卡住）和規格審查的花費；來源檔不存在印 `UNKNOWN`。額度仍用 `usage_report.py`。
- 兩個紀錄慣例，給 `metrics_report.py` 數：`docs/06b` 恢復程序第 7 步的 `RESUMED` 行加 `redo=`，總監記進 `DIRECTOR_LOG`；`BOOTSTRAP` 卡住時在 `DIRECTOR_LOG` 記 `BOOTSTRAP_STUCK 第 n 步 原因`。
- `docs/02`、`templates/TASK_REPORT.md`、`tools/README.md` 寫明：AUTO 條件在最後一次 commit 之後記錄，證據欄寫 `.json` 檔名。
- `selftest.py` 加上面各項的正反案例（共 202 項）。

對齊初衷：
1. 幫到誰：v0.10 的 `--match` 只查證據欄有沒有寫字，worker 寫了不存在或失敗的紀錄也會通過；`PURPOSE.md` 列了五個成效指標，但沒有工具能數，改規則前後無從比較。
2. Desktop：工具只用標準函式庫、本機執行，selftest 在 Python 3.11 和 3.9 通過，也用真的 `evidence_record.py` 紀錄在暫存 git repo 跑過一次。在 Desktop 上拿真實 Strict 工單試用、量基準數字 NOT_VERIFIED。
3. 服務：成品要真的對（5，PASS 要有通過的紀錄）、PO 不用盯細節（3，總監用工具核對）、用數字決定規則留不留（PURPOSE.md 怎麼判斷有沒有效）。
4. 核心：每輪必讀不變（13,417 / 13,428 bytes）；`--evidence-dir` 是選用的，Direct 不受影響；PO 不多操作。新增的兩行紀錄由總監和 worker 寫。
5. 舊檔案：不帶新參數時照樣通過。用 `--evidence-dir` 時，舊報告的證據欄若不是 `.json` 檔名會不通過，所以只對新報告用。

遷移：把 `tools/` 整個重新複製到 `DIRECTOR/tools/`（含 `metrics_report.py`）。要核對證據時，總監審查改跑 `gate_check.py --match 報告 工單 --evidence-dir 證據資料夾`，並在派工時告訴 worker 證據欄要寫 `.json` 檔名、最後一次 commit 之後再記錄。

## 0.10.0 — 2026-11-04

驗收條件分類型、規格和結果分開放，加上 PO 定的初衷。MINOR：新檢查對舊檔案只印提示（`  ~ ` 開頭），不會讓舊檔案不通過；`gate_check.py` 不帶新參數時行為不變。

- 新增 `PURPOSE.md`：初衷、目的、不能破壞的九項核心、改規則前的五題檢查。只有 PO 能改；其他規則和它衝突時照它。`docs/01`（每輪必讀）加一行指向它，README、`BOOTSTRAP` 1.2 加進閱讀順序。
- 工單驗收條件加「類型」欄 `AUTO / REVIEW / PO`；實際、證據、狀態改寫在 TASK REPORT 的 ACCEPTANCE 表。worker 對 REVIEW 最多填 `READY_FOR_REVIEW`，對 PO 只填 `PENDING_PO`（`vocabulary.json` 的 `ac_worker_statuses`）。
- 工單加 `REVISION`、`TRACES_TO` 和 H 節變更紀錄；報告加 `ORDER`、`ORDER_SHA256`。
- `gate_check.py` 加 `--match 報告 工單`（逐條對照、狀態符合類型、PASS 附證據、工單雜湊相符）和 `--hash`。雜湊只能查出工單被改過，擋不住修改。
- 新增 `tools/trace_report.py`：從工單、報告、裁決產生追溯表；`director_work.json` 可選加 `trace_id_pattern` 檢查編號格式（不改 `schema_version`）。
- 新增 `templates/SPEC_REVIEW.md`：Strict 工單派工前用只讀 subagent 審規格；Standard 選用；記下花費和抓到的問題。
- `docs/07` 常識閘門：有成品的工單寫成 `REVIEW` 條件，開工前寫明誰看、從哪個角度、看多大範圍。
- `selftest.py` 加上面各項的正反案例，並檢查 `PURPOSE.md` 結構和每一版 CHANGELOG 有「對齊初衷」。

對齊初衷：
1. 幫到誰：使用中的專案出過「數字全對、成品動作方向相反」和「worker 自己判過要用眼睛看的條件」；規格和結果混在工單裡，規格被改也查不出來。
2. Desktop：工具只用標準函式庫、本機執行，selftest 通過；在 Desktop 上拿真實工單試用 NOT_VERIFIED。
3. 服務：成品要真的對（5）、PO 保留最終權力（6）、PO 不用盯細節（3）、中斷不丟進度（4，追溯表從檔案重建）。
4. 核心：每輪必讀維持在上限內（13,417 / 13,428 bytes）；Direct 不多步驟；規格審查只在 Strict 必做，花費要記錄，划不來就降回選用；PO 不多操作。
5. 舊檔案：照樣通過，只多提示。

遷移：把 `tools/` 整個重新複製到 `DIRECTOR/tools/`（含 `vocabulary.json`、`trace_report.py`）。新工單和報告改用新的 `templates/WORK_ORDER.md`、`TASK_REPORT.md`；舊工單不用改。要檢查編號格式時，在 `director_work.json` 加 `trace_id_pattern`。

## 0.9.0 — 2026-11-04

第一個版本號，涵蓋到這一版為止的全部內容。還不算定案：`v1.0.0` 要等完整開發循環實測過。

- 新增 `docs/11_claude_desktop.md`：在 Claude Desktop 上開 worker、傳訊息、讀額度和上下文視窗用哪個工具。不列入每輪必讀。
- `BOOTSTRAP` 第 7.5 步：Desktop 上用 `get_usage` 確認上下文視窗。
- `gate_check.py` 加 `--warn`（只警告、exit 0）和 `--since YYYY-MM-DD`（跳過較早的檔案）。不帶這兩個參數時行為不變。
- 固定用詞集中到 `tools/vocabulary.json`；`selftest.py` 檢查 `docs/02` 和範本的寫法跟它一致。
- `selftest.py` 檢查 README 標「每輪必讀」的文件合計不超過 13,428 bytes。
- `director_work.json` 加 `schema_version`（目前 1）。沒有這個欄位的設定檔視為 1；版本不認得時 `setup_project_settings.py` 會拒絕執行。
- 工單規則：worker 不改驗收條件和規格，有問題回報 `BLOCKED`，由總監裁決。
- GitHub Actions 在 Windows 上用 Python 3.9 和 3.12 跑 `selftest.py`。

對齊初衷（補記）：幫已在用的專案導入時不被舊檔案卡住（`--warn` / `--since`）、用詞不再漂移、必讀文件不再無聲變長；服務省額度（2）和中斷不丟進度（4）；舊檔案照樣通過。

遷移：不用改任何舊檔案。已建置的專案可以把 `"schema_version": 1` 加進 `director_work.json`，不加也一樣。把 `tools/` 整個重新複製到 `DIRECTOR/tools/`，`vocabulary.json` 要一起帶過去，否則 `gate_check.py` 會無法執行。
