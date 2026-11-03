"""Run gate_check, scope_check and evidence_record against good and bad cases in a temporary folder.
Prints one line per failed case and a summary; exit 1 when anything fails. Writes only to the temporary folder.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent
TEMPLATES = TOOLS.parent / "templates"

RESUME = """PROGRESS: tests pass at abc123
DOING: AC-2 of WO-001
NEXT_STEP: run the parser test
COMMS: NONE

# RESUME_STATE
UPDATED: 2026-01-02 10:00 +08:00
"""
ORDER = """# WO-001
```text
ISSUED_BY      = director 2026-01-02 10:00
PRIMARY_WORKER = session a
MODEL / EFFORT = sonnet / medium
FALLBACK       = same session
GOVERNANCE     = Standard
BASE_REF       = main @ {base}
```
```text
SCOPE:
- src/**
- .config/app.json  # the one config file
FORBIDDEN:
- src/frozen/**
```
| ID | req | how | expected | actual | evidence | status |
|---|---|---|---|---|---|---|
| AC-1 | parser accepts empty input | run test_parser | exit 0 | | | |

- DELIVERABLES: commit on the branch
- STOP_RULES: stop after 2 rounds without progress
"""
REPORT = """done
```text
TASK_ID / WORKER / MODEL / BRANCH / BASE / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d / yes
RESULT: {result}
  ENGINEERING: builds
  PRODUCT（成品）: not applicable
DONE: parser fix, evidence e.json
TESTS: {tests}
SCOPE_CHECK: {scope}
EVIDENCE: {evidence}
UNVERIFIED: NONE
KNOWN_ISSUES: NONE
NEXT: NONE
```
"""
VERDICT = """# GATE VERDICT
## A. 判定
{verdict}
分面向：工程 PASS / 成品 未看 / PO 驗收：未做
下一步：{step}

## F. 停止狀態
NO MERGE / NO PUSH
"""

failures, total = [], 0


def run(tool, *args, cwd=None):
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / tool), *map(str, args)], cwd=cwd,
                          capture_output=True, encoding="utf-8")
    return done.returncode, done.stdout


def expect(name, tool, code, *args, cwd=None, says=None):
    global total
    total += 1
    got, out = run(tool, *args, cwd=cwd)
    if got != code or (says and says not in out):
        failures.append(f"{name}: expected exit {code}{f' with {says!r}' if says else ''}, got {got}: {out.strip()[-300:]}")


def gate(tmp, name, kind, text, code, says=None):
    file = tmp / f"{name}.md"
    file.write_text(text, encoding="utf-8")
    expect(name, "gate_check.py", code, f"--{kind}", file, says=says)


def test_gate(tmp):
    for kind, template in (("resume", "RESUME_STATE"), ("order", "WORK_ORDER"), ("report", "TASK_REPORT"), ("verdict", "GATE_VERDICT")):
        expect(f"blank template {template} is refused", "gate_check.py", 1, f"--{kind}", TEMPLATES / f"{template}.md")
    good_report = dict(result="PASS", tests="unit 12/12", scope="PASS base=abc changed=2 forbidden=0 outside=0", evidence="e.json")
    gate(tmp, "resume_ok", "resume", RESUME, 0)
    gate(tmp, "resume_order", "resume", RESUME.replace("PROGRESS", "X", 1).replace("DOING", "PROGRESS", 1).replace("X:", "DOING:", 1), 1)
    gate(tmp, "resume_empty", "resume", RESUME.replace("COMMS: NONE", "COMMS:"), 1, "COMMS: empty")
    gate(tmp, "resume_date", "resume", RESUME.replace("2026-01-02", "today"), 1, "UPDATED")
    gate(tmp, "order_ok", "order", ORDER.format(base="abc123"), 0)
    gate(tmp, "order_vague", "order", ORDER.format(base="abc123").replace("- src/**", "- 相關檔案"), 1, "vague")
    gate(tmp, "order_broad", "order", ORDER.format(base="abc123").replace("- src/**", "- **"), 1, "too broad")
    gate(tmp, "order_absolute", "order", ORDER.format(base="abc123").replace("- src/**", "- C:/src"), 1, "relative")
    gate(tmp, "order_noscope", "order", ORDER.format(base="abc123").replace("SCOPE:", "NOTES:"), 1, "SCOPE: missing")
    gate(tmp, "order_ac", "order", ORDER.format(base="abc123").replace("run test_parser", ""), 1, "how verified")
    gate(tmp, "order_gov", "order", ORDER.format(base="abc123").replace("Standard", "Loose"), 1, "GOVERNANCE")
    gate(tmp, "report_ok", "report", REPORT.format(**good_report), 0)
    gate(tmp, "report_word", "report", REPORT.format(**{**good_report, "result": "DONE"}), 1, "RESULT")
    gate(tmp, "report_notrun", "report", REPORT.format(**{**good_report, "tests": "unit NOT_RUN"}), 1, "NOT_RUN")
    gate(tmp, "report_partial_notrun", "report", REPORT.format(**{**good_report, "result": "PARTIAL", "tests": "unit NOT_RUN"}), 0)
    gate(tmp, "report_scope", "report", REPORT.format(**{**good_report, "scope": "VIOLATION base=abc"}), 1, "scope violation")
    gate(tmp, "report_scope_notrun", "report", REPORT.format(**{**good_report, "scope": "NOT_RUN no git"}), 1, "not checked")
    gate(tmp, "report_partial_scope_notrun", "report", REPORT.format(**{**good_report, "result": "PARTIAL", "scope": "NOT_RUN no git"}), 0)
    gate(tmp, "report_noevidence", "report", REPORT.format(**{**good_report, "evidence": "NONE"}), 1, "reason")
    gate(tmp, "report_reason", "report", REPORT.format(**{**good_report, "evidence": "NONE: docs only"}), 0)
    gate(tmp, "verdict_ok", "verdict", VERDICT.format(verdict="PASS_WITH_WARNINGS", step="ACCEPT_AND_CLOSE"), 0)
    gate(tmp, "verdict_word", "verdict", VERDICT.format(verdict="GOOD", step="ACCEPT_AND_CLOSE"), 1, "verdict")
    gate(tmp, "verdict_step", "verdict", VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE / CONTINUE_SAME_WORKER"), 1, "下一步")
    gate(tmp, "verdict_aspects", "verdict", VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE").replace("成品 未看 / ", ""), 1, "aspect")
    expect("missing file", "gate_check.py", 1, "--resume", tmp / "nope.md", says="file not found")
    expect("no arguments", "gate_check.py", 2)


def test_scope(tmp):
    repo = tmp / "repo"
    (repo / "src" / "frozen").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / ".config").mkdir()

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True, capture_output=True)

    def base_head():
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    for path in ("src/a.py", "src/frozen/b.py", "docs/old.md", ".config/app.json", ".config/other.json"):
        (repo / path).write_text("1\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = base_head()
    order = tmp / "WO.md"
    order.write_text(ORDER.format(base=base), encoding="utf-8")
    check = ("--order", order, "--repo", repo)

    expect("no change passes", "scope_check.py", 0, *check, says="changed=0")
    (repo / "src" / "a.py").write_text("2\n", encoding="utf-8")
    expect("change in scope passes", "scope_check.py", 0, *check, says="changed=1")
    (repo / ".config" / "app.json").write_text("2\n", encoding="utf-8")
    expect("dot folder entry matches", "scope_check.py", 0, *check, says="changed=2")
    (repo / "ignored").mkdir()
    (repo / "ignored" / "x.txt").write_text("x", encoding="utf-8")
    expect("ignored file is not counted", "scope_check.py", 0, *check, says="changed=2")
    git("add", "src/a.py")
    git("commit", "-q", "-m", "work")
    expect("committed change is still seen", "scope_check.py", 0, *check, says="changed=2")
    expect("run from a subfolder", "scope_check.py", 0, "--order", order, "--repo", repo / "src", says="changed=2")

    (repo / "docs" / "new.md").write_text("x", encoding="utf-8")
    expect("untracked outside scope", "scope_check.py", 1, *check, says="outside=1")
    (repo / "docs" / "new.md").unlink()
    (repo / ".config" / "other.json").write_text("2\n", encoding="utf-8")
    expect("sibling of an allowed file is outside", "scope_check.py", 1, *check, says="other.json")
    git("checkout", "-q", "--", ".config/other.json")
    (repo / "src" / "frozen" / "b.py").write_text("2\n", encoding="utf-8")
    expect("forbidden wins over scope", "scope_check.py", 1, *check, says="forbidden=1")
    git("checkout", "-q", "--", "src/frozen/b.py")
    git("mv", "docs/old.md", "src/old.md")
    expect("rename out of an outside path is seen", "scope_check.py", 1, *check, says="docs/old.md")
    git("mv", "src/old.md", "docs/old.md")
    expect("back to clean", "scope_check.py", 0, *check)
    expect("--base overrides", "scope_check.py", 0, *check, "--base", base)
    expect("unknown base", "scope_check.py", 2, *check, "--base", "no-such-ref", says="NOT_RUN")
    expect("order not found", "scope_check.py", 2, "--order", tmp / "nope.md", "--repo", repo, says="NOT_RUN")
    gate_less = tmp / "bare.md"
    gate_less.write_text("BASE_REF = main\n", encoding="utf-8")
    expect("order without lists", "scope_check.py", 2, "--order", gate_less, "--repo", repo, says="NOT_RUN")
    for name, old, new in (("blank line after SCOPE", "SCOPE:\n", "SCOPE:\n\n"), ("star bullets", "- src/**", "* src/**")):
        bad = tmp / f"{name}.md"
        bad.write_text(ORDER.format(base=base).replace(old, new, 1), encoding="utf-8")
        expect(name, "scope_check.py", 2, "--order", bad, "--repo", repo, says="NOT_RUN")
    slash = tmp / "slash.md"
    slash.write_text(ORDER.format(base=base).replace("- src/**", "- /src/**"), encoding="utf-8")
    (repo / "src" / "a.py").write_text("3\n", encoding="utf-8")
    expect("leading slash in a glob", "scope_check.py", 0, "--order", slash, "--repo", repo, says="changed=2")
    git("checkout", "-q", "--", "src/a.py")


def test_shared_code():
    global total
    total += 1
    blocks = [re.search(r"^def parse_list.*?(?=^\S)", (TOOLS / tool).read_text(encoding="utf-8"), re.M | re.S)
              for tool in ("gate_check.py", "scope_check.py")]
    if not all(blocks) or blocks[0].group() != blocks[1].group():
        failures.append("parse_list differs between gate_check.py and scope_check.py; keep the two copies identical")


def test_hook(tmp):
    global total
    blocked = ["git push origin main", "git -C . push", "git --no-pager -c a=b push --force", "cd x && git push",
               'bash -c "git push"', "git reset --hard HEAD~1", "git clean -fdx", "git stash", "git stash pop",
               "git stash push -u", "git worktree remove ../wt", "git branch -D old", "taskkill /F /IM python.exe",
               "pkill node", "Stop-Process -Name node", "& 'C:/Program Files/Git/bin/git.exe' push",
               r"C:\Git\bin\git.exe push origin main", "sh -c 'git reset --hard'", 'powershell -Command "git push"',
               'cmd /c "git push"', 'echo "$(git push)"', 'taskkill /F /FI "IMAGENAME eq app.exe"',
               ("Get-Process app | Stop-Process -Force", "PowerShell"),
               (r'& "C:\Program Files\Git\bin\git.exe" push', "PowerShell"), ('iex "git push"', "PowerShell"),
               (r'cd "C:\dir\"; git push', "PowerShell")]
    allowed = ["git status", 'git commit -m "docs: explain the git push rule"', "git stash push -u -m wip-1",
               "git stash apply abc123", "git clean -n", "git reset --soft HEAD~1", "taskkill /PID 1234", "echo push",
               'grep -n "git stash" rules.md', 'git commit -m "note; git reset --hard is forbidden"', "kill -9 1234",
               r'echo "a \" ; git push"', "rm -rf build",  # deleting files is out of scope (tools/README.md)
               ("Stop-Process -Id 1234", "PowerShell"), ("Remove-Item -Recurse build", "PowerShell")]
    for command, code in [(c, 2) for c in blocked] + [(c, 0) for c in allowed]:
        command, tool = command if isinstance(command, tuple) else (command, "Bash")
        total += 1
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py")], capture_output=True,
                              encoding="utf-8", input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}))
        if done.returncode != code:
            failures.append(f"hook_guard {command!r}: expected exit {code}, got {done.returncode}: {done.stderr.strip()}")
        elif re.search(r"<[^>]*>", done.stderr):  # a worker quoting it in KNOWN_ISSUES would fail gate_check
            failures.append(f"hook_guard {command!r}: message has a <...> placeholder: {done.stderr.strip()}")
    repo = tmp / "hooked"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    setup = ("setup_project_settings.py", "--repo", repo, "--only-this", "--hooks")
    expect("hooks missing", *setup[:1], 1, *setup[1:], says="hooks.PreToolUse")
    expect("hooks written", *setup[:1], 0, *setup[1:], "--apply", says="SET")
    expect("hooks kept on rerun", *setup[:1], 0, *setup[1:], "--apply", says="OK")
    data = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    total += 1
    if len(data["hooks"]["PreToolUse"]) != 1:
        failures.append("setup_project_settings --hooks added the hook twice")


def test_evidence(tmp):
    out = tmp / "evidence"
    work = tmp / "work"
    work.mkdir()
    art = work / "built.txt"
    py = sys.executable
    make = f"open('built.txt','w').write('same');print('hello')"
    common = ("evidence_record.py", )

    expect("recording a passing command", *common, 0, "run", "--out-dir", out, "--label", "AC-1", "--cwd", work,
           "--artifact", "built.txt", "--", py, "-c", make, says="exit=0")
    records = sorted(out.glob("*.json"))
    record = records[-1]
    data = json.loads(record.read_text(encoding="utf-8"))
    global total
    total += 1
    if data["output_tail"] != ["hello"] or len(data["artifacts"]) != 1 or data["artifacts"][0]["sha256"] is None:
        failures.append(f"record content: {data}")
    expect("verify same", *common, 0, "verify", record, says="OK")
    expect("verify with rerun", *common, 0, "verify", record, "--rerun", says="OK")
    art.write_text("changed", encoding="utf-8")
    expect("verify sees a changed artifact", *common, 1, "verify", record, says="MISMATCH")
    expect("rerun rebuilds it", *common, 0, "verify", record, "--rerun", says="OK")

    expect("exit code passes through", *common, 7, "run", "--out-dir", out, "--label", "AC-2", "--", py, "-c", "raise SystemExit(7)")
    expect("missing artifact fails", *common, 3, "run", "--out-dir", out, "--label", "AC-3", "--artifact", tmp / "nope", "--", py, "-c", "0", says="missing=1")
    expect("unknown command", *common, 127, "run", "--out-dir", out, "--label", "AC-4", "--", "no-such-command-xyz")
    expect("timeout", *common, 124, "run", "--out-dir", out, "--label", "AC-5", "--timeout", "1", "--", py, "-c", "import time;time.sleep(30)")
    expect("no command", *common, 2, "run", "--out-dir", out, "--label", "AC-6")
    expect("bad record", *common, 2, "verify", tmp / "nope.json", says="NOT_RUN")

    expect("two runs do not overwrite", *common, 0, "run", "--out-dir", out, "--label", "same", "--", py, "-c", "0")
    expect("two runs do not overwrite (2)", *common, 0, "run", "--out-dir", out, "--label", "same", "--", py, "-c", "0")
    total += 1
    if len(list(out.glob("*-same*.json"))) != 2:
        failures.append("two runs in a row should leave two records")

    expect("long output", *common, 0, "run", "--out-dir", out, "--label", "long", "--", py, "-c", "for i in range(200000): print('x'*1000)")
    big = next(out.glob("*-long.json"))
    total += 1
    if big.stat().st_size > 32 * 1024:
        failures.append(f"record too big: {big.stat().st_size} bytes")

    folder = work / "folder"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "a.txt").write_text("a", encoding="utf-8")
    expect("folder artifact", *common, 0, "run", "--out-dir", out, "--label", "dir", "--artifact", folder, "--", py, "-c", "0")
    rec = next(out.glob("*-dir.json"))
    expect("folder verify", *common, 0, "verify", rec, says="OK")
    (folder / "sub" / "b.txt").write_text("b", encoding="utf-8")
    expect("folder sees a new file", *common, 1, "verify", rec, says="MISMATCH")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="director_work_selftest_")).resolve()
    try:
        test_gate(tmp)
        test_scope(tmp)
        test_shared_code()
        test_hook(tmp)
        test_evidence(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for failure in failures:
        print(f"FAIL {failure}")
    print(f"selftest: {total - len(failures)}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
