"""Run gate_check, trace_report, metrics_report, scope_check, evidence_record and hook_guard against good and bad cases
in a temporary folder, and check that the fixed words, the size of the must-read docs, PURPOSE.md and the CHANGELOG have
not drifted.
Prints one line per failed case and a summary; exit 1 when anything fails. Writes only to the temporary folder.
"""
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

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
TASK_ID / WORKER / MODEL / BRANCH / BASE / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d0d0d0d / yes
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
TYPED_ORDER = ORDER.replace("BASE_REF       = main @ {base}\n",
                            "BASE_REF       = main @ {base}\nREVISION       = 1\nTRACES_TO      = DD-1\n").replace(
    """| ID | req | how | expected | actual | evidence | status |
|---|---|---|---|---|---|---|
| AC-1 | parser accepts empty input | run test_parser | exit 0 | | | |
""", """| ID | 類型 | 要求 | 驗證方法 | 預期 |
|---|---|---|---|---|
| AC-1 | AUTO | parser accepts empty input | run test_parser | exit 0 |
| AC-2 | REVIEW | the output reads right | reviewer reads out.txt in full | no WRONG answer |
| AC-3 | PO | PO accepts the wording | PO reads out.txt | PO says yes |
""")
ACCEPTANCE = {"AC-1": "| AC-1 | exit 0 | e.json | PASS |", "AC-2": "| AC-2 | out.txt written | out.txt | READY_FOR_REVIEW |",
              "AC-3": "| AC-3 | wording drafted | out.txt | PENDING_PO |"}
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


def expect(name, tool, code, *args, cwd=None, says=None, lacks=None):
    """says / lacks: a string or a list of strings the output must hold / must not hold."""
    global total
    total += 1
    got, out = run(tool, *args, cwd=cwd)
    says, lacks = [says] if isinstance(says, str) else says or [], [lacks] if isinstance(lacks, str) else lacks or []
    if got != code or any(s not in out for s in says) or any(s in out for s in lacks):
        failures.append(f"{name}: expected exit {code} with {says!r} and without {lacks!r}, got {got}: {out.strip()[-300:]}")


# 2.1 (report 5 F-1): the rules pack must verify without git (ZIP download, minimal machine). A test group that builds
# git fixtures is skipped, by name, only when no git program is on PATH; with git, a fixture error still fails.
GIT = shutil.which("git")
skipped = []
# Groups that build git fixtures (found by a run with git off PATH, 2026-11-08); guarded() skips them by name
# without git, and also skips any other group that dies on a missing program, so a new git test cannot crash the run.
GIT_GROUPS = {
    "test_scope", "test_submodule_ignore", "test_hook", "test_hook_protect", "test_hook_rules", "test_session_profiles",
    "test_pause", "test_audit", "test_audit_names", "test_review", "test_guard_modes", "test_doctor",
    "test_doctor_launch", "test_worker_clone", "test_preflight", "test_trusted_rerun", "test_rerun_binding",
    "test_trusted_isolation",
}


def skip(group, why="needs git, none on PATH"):
    skipped.append(f"{group} ({why})")
    print(f"SKIP {group}: {why}")


def git_fixture(folder):
    """A fresh repo with one commit, for tests that need a real worktree (never the DW checkout itself, F-1)."""
    folder.mkdir(parents=True, exist_ok=True)
    for argv in (["init", "-q"], ["add", "-A"], ["-c", "user.name=selftest", "-c", "user.email=selftest@example.invalid",
                                                 "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "fixture"]):
        subprocess.run(["git", *argv], cwd=folder, check=True, capture_output=True)
    return folder


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
    gate(tmp, "order_file_named_todo", "order", ORDER.format(base="abc123").replace("- src/**", "- todo.py"), 0)
    gate(tmp, "order_etc", "order", ORDER.format(base="abc123").replace("- src/**", "- src/** etc."), 1, "vague")
    gate(tmp, "order_broad", "order", ORDER.format(base="abc123").replace("- src/**", "- **"), 1, "too broad")
    gate(tmp, "order_absolute", "order", ORDER.format(base="abc123").replace("- src/**", "- C:/src"), 1, "relative")
    gate(tmp, "order_noscope", "order", ORDER.format(base="abc123").replace("SCOPE:", "NOTES:"), 1, "SCOPE: missing")
    gate(tmp, "order_ac", "order", ORDER.format(base="abc123").replace("run test_parser", ""), 1, "how verified")
    gate(tmp, "order_gov", "order", ORDER.format(base="abc123").replace("Standard", "Loose"), 1, "GOVERNANCE")
    # v0.13: optional REQUIRED_CHANGES must lie inside SCOPE and outside FORBIDDEN
    required = lambda item: ORDER.format(base="abc123").replace("- src/frozen/**\n", "- src/frozen/**\nREQUIRED_CHANGES:\n- " + item + "\n")
    gate(tmp, "order_required_ok", "order", required("src/parser.py"), 0)
    gate(tmp, "order_required_forbidden", "order", required("src/frozen/b.py"), 1, "is FORBIDDEN")
    gate(tmp, "order_required_outside", "order", required("docs/x.md"), 1, "outside SCOPE")
    gate(tmp, "report_ok", "report", REPORT.format(**good_report), 0)
    done_line = "DONE: parser fix, evidence e.json"
    gate(tmp, "report_code_span", "report", REPORT.format(**good_report).replace(done_line, done_line + ", ids are `AC-<n>`, mail <a@b.example>"), 0)
    gate(tmp, "report_placeholder", "report", REPORT.format(**good_report).replace(done_line, done_line + ", <what changed>"), 1, "placeholder")
    gate(tmp, "report_scope_prefix", "report", REPORT.format(**{**good_report, "scope": "SCOPE_CHECK: " + good_report["scope"]}), 0)
    gate(tmp, "report_scope_prefix_violation", "report", REPORT.format(**{**good_report, "scope": "SCOPE_CHECK: VIOLATION base=abc"}), 1, "scope violation")
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

    old = tmp / "order_old.md"
    old.write_text(ORDER.format(base="abc123").replace("2026-01-02", "2025-12-31").replace("- src/**", "- 相關檔案"), encoding="utf-8")
    new = tmp / "order_new.md"
    new.write_text(ORDER.format(base="abc123").replace("- src/**", "- 相關檔案"), encoding="utf-8")
    undated = tmp / "report_undated.md"
    undated.write_text(REPORT.format(**{**good_report, "result": "DONE"}), encoding="utf-8")
    expect("an old file still fails without flags", "gate_check.py", 1, "--order", old, says="FAIL")
    expect("--warn reports and does not block", "gate_check.py", 0, "--warn", "--order", old, new, says="warned 2")
    expect("--since skips an old order", "gate_check.py", 0, "--since", "2026-01-01", "--order", old, says="SKIP")
    expect("--since still checks a new order", "gate_check.py", 1, "--since", "2026-01-01", "--order", old, new, says="skipped 1")
    expect("an undated file is checked without --since", "gate_check.py", 1, "--report", undated, says="FAIL")
    expect("--since skips an undated file and counts it", "gate_check.py", 1, "--since", "2026-01-01", "--report", undated,
           "--order", old, new, says=["SKIP report", "UNDATED: no date", "checked 1, failed 1, skipped 1, UNDATED 1 (not checked)"])
    expect("--since without undated files prints no UNDATED count", "gate_check.py", 0, "--since", "2026-01-01", "--order", old,
           lacks="UNDATED")
    expect("--since skips an old RESUME_STATE", "gate_check.py", 0, "--since", "2026-02-01", "--resume", tmp / "resume_empty.md", says="SKIP")
    expect("--since needs a date", "gate_check.py", 2, "--since", "yesterday", "--order", new)


def match_report(rows, result="PASS", sha=None):
    """A report whose ACCEPTANCE table holds rows, pointing at WO-001-parser.md."""
    head = "ORDER: WO-001-parser.md REVISION 1\n" + (f"ORDER_SHA256: {sha}\n" if sha else "")
    table = "ACCEPTANCE:\n| ID | 實際 | 證據 | 狀態 |\n|---|---|---|---|\n" + "\n".join(rows) + "\n"
    text = REPORT.format(result=result, tests="unit 12/12", scope="PASS base=abc changed=2 forbidden=0 outside=0", evidence="e.json")
    return text.replace("RESULT:", head + "RESULT:", 1).replace("UNVERIFIED: NONE", table + "UNVERIFIED: NONE")


def test_acceptance(tmp):
    """v0.10: typed acceptance criteria in the order, results in the report, --match and --hash. Old files only get notes."""
    global total
    total += 1
    if "| AC-3 | PO |" not in TYPED_ORDER or "TRACES_TO" not in TYPED_ORDER:
        failures.append("TYPED_ORDER did not build from ORDER; update the replace() in selftest.py")
    typed = TYPED_ORDER.format(base="abc123")
    gate(tmp, "typed_ok", "order", typed, 0)
    expect("a typed order gets no notes", "gate_check.py", 0, "--order", tmp / "typed_ok.md", lacks="  ~ ")
    expect("an old order passes with notes", "gate_check.py", 0, "--order", tmp / "order_ok.md",
           says=["OK", "~ acceptance: no 類型 column", "~ REVISION: missing", "~ TRACES_TO: missing", "~ acceptance: 實際"])
    gate(tmp, "typed_kind", "order", typed.replace("| AUTO |", "| AUTOMATIC |"), 1, "類型: must be one of")
    gate(tmp, "typed_rev_word", "order", typed.replace("REVISION       = 1", "REVISION       = two"), 1, "must be a number")
    gate(tmp, "typed_rev_nolog", "order", typed.replace("REVISION       = 1", "REVISION       = 2"), 1, "no row for revision 2")
    gate(tmp, "typed_rev_log", "order", typed.replace("REVISION       = 1", "REVISION       = 2")
         + "\n| 版本 | 時間 | 誰改 | 原因 | 影響的 AC |\n|---|---|---|---|---|\n| 2 | 2026-01-03 | director | split AC-1 | AC-1 |\n", 0)
    expect("a report without ACCEPTANCE still passes", "gate_check.py", 0, "--report", tmp / "report_ok.md", says="~ ACCEPTANCE: no table")

    order = tmp / "WO-001-parser.md"
    order.write_bytes(typed.encode("utf-8"))
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    crlf = tmp / "WO-001-crlf.md"
    crlf.write_bytes(typed.replace("\n", "\r\n").encode("utf-8"))
    expect("--hash prints the order hash", "gate_check.py", 0, "--hash", order, says=f"{sha}  ")
    expect("--hash counts CRLF as LF", "gate_check.py", 0, "--hash", crlf, says=f"{sha}  ")
    expect("--hash of a missing file", "gate_check.py", 1, "--hash", tmp / "nope.md", says="file not found")

    def match(name, code, rows, says=None, result="PASS", digest=sha, against=order, lacks=None):
        report = tmp / f"{name}.md"
        report.write_text(match_report(rows, result, digest), encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", report, against, says=says, lacks=lacks)
        return report

    good = list(ACCEPTANCE.values())
    match("match_ok", 0, good, says="OK   match", lacks="  ~ ")
    match("match_crlf_order", 0, good, against=crlf)
    match("match_missing_ac", 1, good[:2], "AC-3: in the order but not in the report")
    match("match_extra_ac", 1, good + ["| AC-4 | x | y.json | PASS |"], "AC-4: in the report but not in the order")
    match("match_review_pass", 1, [good[0], "| AC-2 | looks fine | out.txt | PASS |", good[2]],
          ["AC-2 (REVIEW): status must be one of", "a reviewer, then the Director, judges it"])
    match("match_po_pass", 1, good[:2] + ["| AC-3 | drafted | out.txt | PASS |"], ["AC-3 (PO)", "only the PO judges it"])
    match("match_no_evidence", 1, ["| AC-1 | exit 0 | | PASS |"] + good[1:], "AC-1: PASS without evidence")
    match("match_none_evidence", 1, ["| AC-1 | exit 0 | NONE | PASS |"] + good[1:], "AC-1: PASS without evidence")
    match("match_no_actual", 1, ["| AC-1 | | e.json | PASS |"] + good[1:], "AC-1: PASS with 實際 empty")
    match("match_pass_blocked", 1, ["| AC-1 | crashed | log.txt | BLOCKED |"] + good[1:], "RESULT PASS with")
    match("match_partial_blocked", 0, ["| AC-1 | crashed | log.txt | BLOCKED |"] + good[1:], result="PARTIAL")
    match("match_no_hash", 1, good, "ORDER_SHA256: missing", digest=None)
    changed = tmp / "WO-001-changed.md"
    changed.write_text(typed.replace("exit 0 |", "exit 0 or 1 |"), encoding="utf-8")
    match("match_changed_order", 1, good, "the order is not the one the worker hashed", against=changed)
    old = tmp / "WO-old.md"
    old.write_text(ORDER.format(base="abc123"), encoding="utf-8")
    old_sha = hashlib.sha256(ORDER.format(base="abc123").encode("utf-8")).hexdigest()  # write_text may add CR
    match("match_untyped_as_auto", 0, [good[0]], "~ AC-1: the order gives no 類型; checked as AUTO", digest=old_sha, against=old)
    match("match_untyped_review", 1, ["| AC-1 | x | y.json | READY_FOR_REVIEW |"], "AC-1 (AUTO)", digest=old_sha, against=old)
    expect("--order with --report does not cross-check", "gate_check.py", 0, "--order", order, "--report",
           tmp / "match_missing_ac.md", lacks="in the order but not")
    expect("--match missing file", "gate_check.py", 1, "--match", tmp / "nope.md", order, says="file not found")


def test_table(tmp):
    r"""v0.12: the ACCEPTANCE table parser rejects a duplicate AC row, a duplicate column name and a row whose cell count
    differs from the header's; `|` inside backticks or escaped as `\|` does not split a cell."""
    global total
    total += 1
    typed = TYPED_ORDER.format(base="abc123")
    order = tmp / "WO-010-table.md"
    order.write_text(typed, encoding="utf-8")
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    good = list(ACCEPTANCE.values())

    def match(name, code, rows, says=None, lacks=None, against=order, digest=sha, header=None):
        report = tmp / f"{name}.md"
        text = match_report(rows, "PASS", digest)
        if header:
            text = text.replace("| ID | 實際 | 證據 | 狀態 |", header)
        report.write_text(text, encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", report, against, says=says, lacks=lacks)

    match("table_dup_ac_fail_then_pass", 1, ["| AC-1 | exit 1 | e.json | FAIL |"] + good,
          ["AC-1: listed twice; one row per AC", "RESULT PASS with FAIL"])
    match("table_dup_ac_pass_then_pass", 1, good + [good[0]], "AC-1: listed twice")
    match("table_short_row", 1, ["| AC-1 | PASS |"] + good[1:], "AC-1: 2 cells, the header has 4")
    match("table_long_row", 1, ["| AC-1 | exit 0 | e.json | PASS | extra |"] + good[1:], "AC-1: 5 cells, the header has 4")
    match("table_dup_column", 1, good, "column actual appears twice in the header", header="| ID | 實際 | 實際 | 狀態 |")
    gate(tmp, "table_dup_ac_order", "order", typed.replace("| AC-2 |", "| AC-1 |", 1), 1, "AC-1: listed twice")
    gate(tmp, "table_short_row_order", "order", typed.replace("| run test_parser | exit 0 |", "| run test_parser |"), 1,
         "AC-1: 4 cells, the header has 5")
    gate(tmp, "table_dup_column_order", "order", typed.replace("| ID | 類型 | 要求 | 驗證方法 | 預期 |", "| ID | 類型 | 要求 | 要求 | 預期 |"), 1,
         "column requirement appears twice")
    piped = typed.replace("| run test_parser |", "| run `cat a.txt \\| grep -E \"x\\|y\"` and `a | b`, then `c` |")
    if piped == typed:
        failures.append("test_table: TYPED_ORDER has no `run test_parser` cell; update the replace()")
    pipe_order = tmp / "WO-001-pipe.md"
    pipe_order.write_text(piped, encoding="utf-8")
    pipe_sha = hashlib.sha256(piped.encode("utf-8")).hexdigest()
    expect("a `|` inside backticks does not split the order's cell", "gate_check.py", 0, "--order", pipe_order, lacks=["cells", "  ~ "])
    match("table_pipe_in_report_cell", 0, ["| AC-1 | `a | b` and `x\\|y` ran, exit 0 | e.json | PASS |"] + good[1:],
          "OK   match", against=pipe_order, digest=pipe_sha)
    match("table_escaped_pipe_in_cell", 0, ["| AC-1 | saw a \\| b | e.json | PASS |"] + good[1:], "OK   match",
          against=pipe_order, digest=pipe_sha)
    match("table_unclosed_backtick_is_short", 1, ["| AC-1 | `a | e.json | PASS |"] + good[1:], "cells, the header has 4",
          against=pipe_order, digest=pipe_sha)


def test_dispatch(tmp):
    """v0.12: --match --dispatch-log compares the order's hash with the DISPATCH line the Director logged, so an order
    rewritten and re-hashed by the worker is caught. Without the flag only the order as it is now is compared."""
    typed = TYPED_ORDER.format(base="abc123")
    order = tmp / "WO-001-parser.md"
    order.write_bytes(typed.encode("utf-8"))
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    good = list(ACCEPTANCE.values())

    def log(name, *lines):
        file = tmp / f"{name}.md"
        file.write_text("# DIRECTOR_LOG\n" + "".join(f"2026-01-02 10:00 +08:00 | {line}\n" for line in lines), encoding="utf-8")
        return file

    def match(name, code, against=order, rows=good, says=None, lacks=None, dispatch_log=None):
        report = tmp / f"{name}.md"
        digest = hashlib.sha256(against.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # write_text may add CR
        report.write_text(match_report(rows, "PASS", digest), encoding="utf-8")
        extra = ("--dispatch-log", dispatch_log) if dispatch_log else ()
        expect(name, "gate_check.py", code, "--match", report, against, *extra, says=says, lacks=lacks)
        return report

    logged = log("log_ok", f"DISPATCH WO-001 rev=1 sha={sha}")
    match("dispatch_ok", 0, says="OK   match", lacks="  ~ ", dispatch_log=logged)
    match("dispatch_by_file_name", 0, says="OK   match", lacks="  ~ ", dispatch_log=log("log_stem", f"DISPATCH WO-001-parser.md rev=1 sha={sha}"))
    match("dispatch_latest_line_wins", 0, says="OK   match", dispatch_log=log("log_two", f"DISPATCH WO-001 rev=1 sha={'0' * 64}",
                                                                              f"DISPATCH WO-001 rev=1 sha={sha}"))
    match("dispatch_stale_line_fails", 1, says="not the one logged at dispatch", dispatch_log=log("log_stale", f"DISPATCH WO-001 rev=1 sha={sha}",
                                                                                                 f"DISPATCH WO-001 rev=2 sha={'0' * 64}"))
    # the worker weakens AC-1, drops the REVIEW / PO rows, or turns REVIEW into AUTO, then re-hashes: the report agrees
    # with the order as it is now, only the dispatch record disagrees
    weakened = tmp / "WO-001-weak.md"
    weakened.write_text(typed.replace("| AC-1 | AUTO | parser accepts empty input | run test_parser | exit 0 |",
                                      "| AC-1 | AUTO | parser exists | ls | file listed |"), encoding="utf-8")
    match("dispatch_weakened_rehashed", 1, against=weakened, says="the order changed after dispatch", dispatch_log=logged)
    expect("the same rewrite passes without --dispatch-log", "gate_check.py", 0, "--match", tmp / "dispatch_weakened_rehashed.md", weakened)
    dropped = tmp / "WO-001-dropped.md"
    dropped.write_text("\n".join(line for line in typed.splitlines() if "| AC-2 |" not in line and "| AC-3 |" not in line) + "\n", encoding="utf-8")
    match("dispatch_rows_dropped_rehashed", 1, against=dropped, rows=good[:1], says="the order changed after dispatch", dispatch_log=logged)
    retyped = tmp / "WO-001-retyped.md"
    retyped.write_text(typed.replace("| AC-2 | REVIEW |", "| AC-2 | AUTO |"), encoding="utf-8")
    match("dispatch_review_to_auto_rehashed", 1, against=retyped, rows=[good[0], "| AC-2 | reads right | e.json | PASS |", good[2]],
          says="the order changed after dispatch", dispatch_log=logged)
    # v0.13 (G01): given a log, an order it does not show as dispatched fails in every governance, so lowering the mode
    # in the order (Strict -> Direct) does not skip the check
    for governance, code, mark in (("Strict", 1, "  - DISPATCH: no line for WO-001 / WO-001-"), ("Standard", 1, "  - DISPATCH: no line for"),
                                   ("Direct", 1, "  - DISPATCH: no line for")):
        other = tmp / f"WO-001-{governance}.md"
        other.write_text(typed.replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}"), encoding="utf-8")
        match(f"dispatch_no_record_{governance}", code, against=other, says=mark,
              dispatch_log=log("log_other", f"DISPATCH WO-999 rev=1 sha={'1' * 64}"))
    strict = tmp / "WO-001-Strict.md"
    match("strict_without_dispatch_log_fails", 1, against=strict, says="- DISPATCH: Strict order checked without --dispatch-log")
    match("standard_without_dispatch_log_silent", 0, lacks="DISPATCH")
    expect("--dispatch-log needs --match", "gate_check.py", 2, "--order", order, "--dispatch-log", logged)
    expect("--dispatch-log file missing", "gate_check.py", 2, "--match", tmp / "dispatch_ok.md", order, "--dispatch-log", tmp / "nope.md")
    expect("--hash prints the DISPATCH line to log", "gate_check.py", 0, "--hash", order, says=f"\n  DISPATCH WO-001 rev=1 sha={sha}")


def test_revision(tmp):
    """v0.13: the DISPATCH line, the order and the report's ORDER line name the same REVISION (A03, A11); a report
    without one is a problem for a Strict order and a note otherwise."""
    typed = TYPED_ORDER.format(base="abc123")
    rev2 = typed.replace("REVISION       = 1", "REVISION       = 2") + (
        "\n| 版本 | 時間 | 誰改 | 原因 | 影響的 AC |\n|---|---|---|---|---|\n| 2 | 2026-01-03 | director | split AC-1 | AC-1 |\n")
    if rev2.startswith(typed):
        failures.append("test_revision: TYPED_ORDER has no `REVISION       = 1` line; update the replace()")

    def case(name, code, text, says=None, lacks=None, log_line=None, edit=None, governance="Standard"):
        folder = tmp / "revision" / name
        folder.mkdir(parents=True)
        text = text.replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        order = folder / "WO-001-parser.md"
        order.write_bytes(text.encode("utf-8"))
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        report = folder / "report.md"
        report_text = match_report(list(ACCEPTANCE.values()), "PASS", sha)
        report.write_text(edit(report_text) if edit else report_text, encoding="utf-8")
        extra = ()
        if log_line:
            (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | {log_line.format(sha=sha)}\n", encoding="utf-8")
            extra = ("--dispatch-log", folder / "log.md")
        expect(name, "gate_check.py", code, "--match", report, order, *extra, says=says, lacks=lacks)

    case("rev_dispatch_same", 0, typed, "OK   match", "  ~ ", log_line="DISPATCH WO-001 rev=1 sha={sha}")
    case("rev_dispatch_other_rev", 1, typed, "- DISPATCH: the latest line for WO-001 logs rev=99, the order is at REVISION 1",
         log_line="DISPATCH WO-001 rev=99 sha={sha}")
    case("rev_report_older", 1, rev2, "- ORDER: the report is for REVISION 1, the order is at REVISION 2")
    case("rev_report_matches_rev2", 0, rev2, "OK   match", "  - ", log_line="DISPATCH WO-001 rev=2 sha={sha}",
         edit=lambda r: r.replace("REVISION 1", "REVISION 2"))
    no_rev = lambda r: r.replace("ORDER: WO-001-parser.md REVISION 1", "ORDER: WO-001-parser.md")
    case("rev_report_none_standard", 0, typed, "~ ORDER: the report names no order revision; write `ORDER: WO-001-parser.md REVISION 1`",
         edit=no_rev)
    case("rev_report_none_strict", 1, typed, "- ORDER: the report names no order revision", edit=no_rev, governance="Strict",
         log_line="DISPATCH WO-001 rev=1 sha={sha}")


def test_verdict_binding(tmp):
    """v0.13 (G04): with --match the verdict's ORDER line names a matched order at its REVISION; with --candidate its
    CANDIDATE_HEAD is the commit under review. A missing line fails Strict and is a note otherwise."""
    typed = TYPED_ORDER.format(base="abc123")
    candidate = "d0d0d0d" + "0" * 33

    def case(name, code, verdict_head, says=None, lacks=None, candidate_flag=True, match=True, governance="Standard"):
        folder = tmp / "verdict_binding" / name
        folder.mkdir(parents=True)
        text = typed.replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        order = folder / "WO-001-parser.md"
        order.write_bytes(text.encode("utf-8"))
        report = folder / "report.md"
        report.write_text(match_report(list(ACCEPTANCE.values()), "PASS", hashlib.sha256(text.encode("utf-8")).hexdigest()),
                          encoding="utf-8")
        verdict = folder / "verdict.md"
        verdict.write_text(VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE").replace(
            "# GATE VERDICT", "# GATE VERDICT WO-001\n" + verdict_head), encoding="utf-8")
        args = ["--verdict", verdict] + (["--match", report, order] if match else [])
        args += ["--candidate", candidate] if candidate_flag else []
        expect(name, "gate_check.py", code, *args, says=says, lacks=lacks)

    case("verdict_bound", 0, f"ORDER: WO-001-parser.md REVISION 1\nCANDIDATE_HEAD: {candidate}\n", "OK   verdict", "  - ")
    case("verdict_wrong_commit", 1, f"ORDER: WO-001-parser.md REVISION 1\nCANDIDATE_HEAD: {'d' * 40}\n",
         "- CANDIDATE_HEAD: the verdict is for dddddddddddd, the candidate is d0d0d0d00000; the verdict judged another commit")
    case("verdict_wrong_commit_without_match", 1, f"CANDIDATE_HEAD: {'d' * 40}\n", "- CANDIDATE_HEAD: the verdict is for",
         match=False)
    case("verdict_old_revision", 1, f"ORDER: WO-001-parser.md REVISION 2\nCANDIDATE_HEAD: {candidate}\n",
         "- ORDER: the verdict is for REVISION 2, the order is at REVISION 1")
    case("verdict_other_order", 1, f"ORDER: WO-777-other.md REVISION 1\nCANDIDATE_HEAD: {candidate}\n",
         "- ORDER: the verdict names WO-777-other.md, which is none of the --match orders")
    case("verdict_no_lines_standard", 0, "", ["~ ORDER: the verdict names no order", "~ CANDIDATE_HEAD: the verdict names no commit"])
    case("verdict_no_head_strict", 1, "ORDER: WO-001-parser.md REVISION 1\n",
         "- CANDIDATE_HEAD: the verdict names no commit", governance="Strict")
    case("verdict_short_head_strict", 1, f"ORDER: WO-001-parser.md REVISION 1\nCANDIDATE_HEAD: {candidate[:12]}\n",
         "- CANDIDATE_HEAD: the verdict is for d0d0d0d00000", governance="Strict")
    case("verdict_alone_unchanged", 0, "", "OK   verdict", "  ~ ", candidate_flag=False, match=False)


def test_dispatch_events(tmp):
    """v0.13 (R01 G01 G02): only a whole DISPATCH line is a dispatch event; the same words in a NOTE, backticks, a quote,
    an indented line or a fence are data. The order's title, file name and the report's ORDER line name one order."""
    typed = TYPED_ORDER.format(base="abc123")
    if "# WO-001" not in typed:
        failures.append("test_dispatch_events: TYPED_ORDER has no `# WO-001` title; update the replace()")
    root = tmp / "events"
    root.mkdir()
    sha, other = hashlib.sha256(typed.encode("utf-8")).hexdigest(), "1" * 64

    def case(name, code, lines, says=None, lacks=None, text=typed, edit=None):
        folder = root / name
        folder.mkdir()
        order = folder / "WO-001-parser.md"
        order.write_bytes(text.encode("utf-8"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        report = match_report(list(ACCEPTANCE.values()), "PASS", digest)
        (folder / "report.md").write_text(edit(report) if edit else report, encoding="utf-8")
        (folder / "log.md").write_text("# DIRECTOR_LOG\n" + "".join(line.format(sha=sha, digest=digest, other=other) + "\n"
                                                                   for line in lines), encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", folder / "report.md", order, "--dispatch-log", folder / "log.md",
               says=says, lacks=lacks)
        return order

    stale = "not the one logged at dispatch"
    case("event_bare_line", 0, ["DISPATCH WO-001 rev=1 sha={digest}"], says="OK   match", lacks="  ~ ")
    case("event_date_and_basis_columns", 0, ["2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={digest} | DD-1 PO said 開"],
         says="OK   match")
    case("event_quoted_in_note_ignored", 1, ["2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={other}",
                                             "2026-01-03 10:00 +08:00 | NOTE: rejected proposal `DISPATCH WO-001 rev=1 sha={digest}`"],
         says=stale)
    case("event_in_note_column_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}",
                                             "2026-01-03 10:00 +08:00 | NOTE: rejected | DISPATCH WO-001 rev=1 sha={digest}"], says=stale)
    case("event_in_backtick_fence_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "```text", "DISPATCH WO-001 rev=1 sha={digest}", "```"],
         says=stale)
    case("event_in_tilde_fence_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "~~~", "DISPATCH WO-001 rev=1 sha={digest}", "~~~"],
         says=stale)
    case("event_in_quote_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "> DISPATCH WO-001 rev=1 sha={digest}"], says=stale)
    case("event_indented_ignored", 1, ["DISPATCH WO-001 rev=1 sha={other}", "    DISPATCH WO-001 rev=1 sha={digest}"], says=stale)
    case("event_after_closed_fence_counts", 0, ["```", "DISPATCH WO-001 rev=1 sha={other}", "```", "DISPATCH WO-001 rev=1 sha={digest}"],
         says="OK   match")
    case("event_only_quoted_is_no_line", 1, ["2026-01-03 10:00 +08:00 | NOTE: `DISPATCH WO-001 rev=1 sha={digest}`"],
         says="- DISPATCH: no line for WO-001")
    case("event_latest_across_names", 1, ["DISPATCH WO-001-parser rev=1 sha={digest}", "DISPATCH WO-001 rev=1 sha={other}"], says=stale)
    # G01: the worker renames the order in its title and lowers Strict to Direct; the log still has the real dispatch
    renamed = typed.replace("# WO-001", "# WO-999").replace("GOVERNANCE     = Standard", "GOVERNANCE     = Direct")
    order = case("order_title_renamed_and_direct", 1, ["DISPATCH WO-001 rev=1 sha={sha}"], text=renamed,
                 says=["- order: the title names WO-999, the file name WO-001-parser.md names WO-001", stale])
    expect("--hash shows a title / file name mismatch", "gate_check.py", 0, "--hash", order,
           says=["DISPATCH WO-999 rev=1", "- order: the title names WO-999"])
    # G02: the report answers another order
    case("report_names_another_order", 1, ["DISPATCH WO-001 rev=1 sha={digest}"],
         edit=lambda r: r.replace("ORDER: WO-001-parser.md", "ORDER: WO-999-other.md"),
         says="- ORDER: the report names WO-999-other.md, the order is WO-001")


def evidence_file(folder, name, head, exit_code=0, timed_out=False, dirty=False, label="AC-1", sha256="written", drop=(), **override):
    """An evidence_record.py file with every field `run` writes, written directly so the case does not depend on git.
    With sha256="written" its artifact out.txt is written next to it and hashed. drop: field names to leave out; override: field
    values to replace."""
    if sha256 == "written":
        (folder / "out.txt").write_bytes(b"x")
        sha256 = hashlib.sha256(b"x").hexdigest()
    record = {"schema": 1, "label": label, "command": ["python", "-c", "0"], "cwd": str(folder), "started": "2026-01-02T10:00:00+08:00",
              "finished": "2026-01-02T10:00:01+08:00", "seconds": 1.0, "exit_code": exit_code, "timed_out": timed_out,
              "git": {"head": head, "dirty": dirty}, "output_lines": 1, "output_tail": ["ok"], "log": None,
              "artifacts": [{"path": "out.txt", "kind": "file", "size": 1, "sha256": sha256}]}
    record.update(override)
    for key in drop:
        record.pop(key, None)
    (folder / name).write_text(json.dumps(record), encoding="utf-8")


def test_evidence_match(tmp):
    """v0.11: --match --evidence-dir reads the evidence records an AUTO PASS row names. Without the flag nothing changes."""
    typed = TYPED_ORDER.format(base="abc123")
    order = tmp / "WO-001-parser.md"
    order.write_bytes(typed.encode("utf-8"))
    sha = hashlib.sha256(typed.encode("utf-8")).hexdigest()
    head = "0123456789abcdef0123456789abcdef01234567"
    folder = tmp / "records"
    folder.mkdir()
    good = list(ACCEPTANCE.values())

    strict_text = typed.replace("GOVERNANCE     = Standard", "GOVERNANCE     = Strict")
    if strict_text == typed:
        failures.append("TYPED_ORDER has no `GOVERNANCE     = Standard` line; update test_evidence_match")
    strict = tmp / "WO-001-strict.md"
    strict.write_bytes(strict_text.encode("utf-8"))
    strict_sha = hashlib.sha256(strict_text.encode("utf-8")).hexdigest()
    strict_log = tmp / "strict_log.md"
    strict_log.write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001-strict rev=1 sha={strict_sha}\n", encoding="utf-8")

    def ev(name, code, record=None, says=None, lacks=None, rows=good, title=f"/ c / {head} / yes", extra="", result="PASS",
           against=order, digest=sha):
        """A Strict order is matched with --candidate and --dispatch-log too (v0.13), so each case shows one fault."""
        if record is not None:
            evidence_file(folder, "e.json", **{"head": head, **record})
        report = tmp / f"{name}.md"
        text = match_report(rows, result, digest).replace("RESULT:", extra + "RESULT:", 1)
        if title is None:  # a title line that does not name HEAD at all
            text = text.replace(" / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d0d0d0d / yes", " / WORKTREE_CLEAN: T / a / sonnet / b / c / yes", 1)
        else:
            text = text.replace("/ c / d0d0d0d / yes", title, 1)
        report.write_text(text, encoding="utf-8")
        bind = ("--candidate", head, "--dispatch-log", strict_log) if against == strict else ()
        expect(name, "gate_check.py", code, "--match", report, against, "--evidence-dir", folder, *bind, says=says, lacks=lacks)
        return report

    bound = {"order": {"id": "WO-001", "rev": 1, "sha": sha}}  # what `run --order` writes (G03b); unbound records get a WARN
    ev("ev_ok", 0, bound, "OK   match", "  ~ ")  # AC-2 (REVIEW) names out.txt: only AUTO rows are read
    ev("ev_short_head", 0, {}, "OK   match", title=f"/ c / {head[:7]} / yes")
    ev("ev_exit", 1, {"exit_code": 3}, "AC-1: e.json: the command exited 3")
    ev("ev_timeout", 1, {"exit_code": 124, "timed_out": True}, "(timed out)")
    ev("ev_artifact", 1, {"sha256": None}, "artifact missing when recorded: out.txt")
    ev("ev_head", 1, {"head": "fedcba9876543210fedcba9876543210fedcba98"}, "record again after the last commit")
    ev("ev_notes", 0, {"dirty": True, "label": "AC-9"},
       ["~ AC-1: e.json: recorded with uncommitted changes", "~ AC-1: e.json: its label is AC-9"])
    ev("ev_no_json", 1, {}, "AC-1: PASS names no evidence_record file (.json) in 證據",
       rows=["| AC-1 | exit 0 | log.txt | PASS |"] + good[1:])
    ev("ev_missing_record", 1, {}, "AC-1: gone.json is not an evidence_record file",
       rows=["| AC-1 | exit 0 | gone.json | PASS |"] + good[1:])
    ev("ev_head_line", 0, bound, "OK   match", "  ~ ", title=None, extra=f"HEAD: {head}\n")
    ev("ev_branch_slash", 0, bound, "OK   match", "  ~ ", title=f"/ feature/x / c / {head} / yes")
    ev("ev_no_head", 0, {"head": "fedcba9876543210fedcba9876543210fedcba98"},
       ["~ HEAD: pending is not a commit hash (7 to 40 hex digits)", "~ HEAD: the report names no commit hash (see above); evidence HEAD not compared"],
       title="/ c / pending / yes")
    # v0.12: a record must have every field `run` writes; HEAD must be a commit hash; Strict fails on dirty / other label
    (folder / "e.json").write_text('{"exit_code": 0}', encoding="utf-8")
    ev("ev_shell_record", 1, None, "AC-1: e.json is not an evidence_record file: missing field command (+1 more)")
    ev("ev_wrong_type", 1, {"exit_code": "0"}, "is not an evidence_record file: field exit_code is not int")
    ev("ev_bool_exit", 1, {"exit_code": False}, "field exit_code is not int")
    ev("ev_bad_record_head", 1, {"head": "not-a-commit"}, "git.head is not a commit hash: not-a-commit")
    ev("ev_bad_artifact_entry", 1, {"artifacts": [{"kind": "file"}]}, "artifact 1 has no path or sha256")
    ev("ev_artifacts_not_list", 1, {"artifacts": 42}, "is not an evidence_record file: field artifacts is not list")
    ev("ev_legacy_record", 0, {"drop": ("schema", "cwd", "started", "finished")},
       ["OK   match", "~ AC-1: e.json: legacy record without `schema`; only command, exit_code and artifacts checked"])
    ev("ev_legacy_still_needs_core", 1, {"drop": ("schema", "artifacts")}, "is not an evidence_record file: missing field artifacts")
    ev("ev_record_without_git_head", 0, {"head": None}, "~ AC-1: e.json: recorded with no git HEAD; not compared with the report's")
    ev("ev_bad_head_standard_notes", 0, {}, ["OK   match", "~ HEAD: not-a-commit is not a commit hash (7 to 40 hex digits)"],
       title="/ c / not-a-commit / yes")
    ev("ev_bad_head_strict_fails", 1, {}, "- HEAD: not-a-commit is not a commit hash (7 to 40 hex digits)",
       title="/ c / not-a-commit / yes", against=strict, digest=strict_sha)
    ev("ev_strict_dirty_fails", 1, {"dirty": True}, "- AC-1: e.json: recorded with uncommitted changes; Strict: commit, then record again",
       against=strict, digest=strict_sha)
    ev("ev_strict_other_label_fails", 1, {"label": "AC-9"}, "- AC-1: e.json: its label is AC-9, not AC-1; Strict: record once per AC, or label both",
       against=strict, digest=strict_sha)
    ev("ev_strict_label_lists_both", 0, {"label": "AC-1 AC-2"}, "OK   match", against=strict, digest=strict_sha)
    ev("ev_strict_clean_ok", 0, {}, "OK   match", lacks="  - ", against=strict, digest=strict_sha)
    # v0.13 batch 3: one HEAD / ORDER line (G02b); Strict reads only schema 1 and git.dirty false (G03 G03a);
    # the artifacts a record lists are hashed again (G03c)
    two_heads = ev("ev_two_heads", 1, {}, "- HEAD: the report names HEAD 2 times (0123456789ab, eeeeeeeeeeee); write it once",
                   extra=f"HEAD: {'e' * 40}\n")
    expect("--report fails a report that names HEAD twice", "gate_check.py", 1, "--report", two_heads,
           says="- HEAD: the report names HEAD 2 times")
    ev("ev_two_order_lines", 1, {}, "- ORDER: the report has 2 ORDER: lines; write it once",
       extra="ORDER: WO-001-parser.md REVISION 1\n")
    ev("ev_schema_strict", 1, {"schema": 99}, "- AC-1: e.json: schema 99 is not one this tool reads (1); Strict",
       against=strict, digest=strict_sha)
    ev("ev_schema_standard", 0, {"schema": 99}, ["OK   match", "~ AC-1: e.json: schema 99 is not one this tool reads (1)"])
    ev("ev_dirty_null_strict", 1, {"dirty": None}, "- AC-1: e.json: git.dirty is null, not false",
       against=strict, digest=strict_sha)
    ev("ev_dirty_null_standard", 0, {"dirty": None}, "OK   match", lacks="git.dirty")
    ev("ev_artifact_changed_strict", 1, {"sha256": "ab" * 32},
       "- AC-1: e.json: artifact changed since it was recorded: out.txt; Strict", against=strict, digest=strict_sha)
    ev("ev_artifact_changed_standard", 0, {"sha256": "ab" * 32},
       ["OK   match", "~ AC-1: e.json: artifact changed since it was recorded: out.txt"])
    gone = str(tmp / "never-written.txt")
    ev("ev_artifact_gone_strict", 1, {"artifacts": [{"path": gone, "kind": "file", "size": 1, "sha256": "ab" * 32}]},
       f"- AC-1: e.json: artifact gone since it was recorded: {gone}", against=strict, digest=strict_sha)
    expect("--report notes a HEAD that is not a commit hash", "gate_check.py", 0, "--report", tmp / "ev_bad_head_standard_notes.md",
           says="~ HEAD: not-a-commit is not a commit hash")
    ev("ev_fail_row_unchecked", 0, {"exit_code": 3}, "OK   match", rows=["| AC-1 | exit 3 | e.json | FAIL |"] + good[1:],
       result="FAIL")
    plain = ev("ev_flag_off_base", 1, {"exit_code": 3})
    expect("without --evidence-dir a failed record is not read", "gate_check.py", 0, "--match", plain, order, says="OK   match")
    expect("--evidence-dir needs --match", "gate_check.py", 2, "--report", plain, "--evidence-dir", folder)
    expect("--evidence-dir folder missing", "gate_check.py", 2, "--match", plain, order, "--evidence-dir", tmp / "nope")


def test_candidate(tmp):
    """v0.13 (A01 A02 A04): a Strict --match is bound to the candidate commit. With --candidate, --dispatch-log and
    --evidence-dir and a full-hash report it passes; leaving out one piece is exactly one problem for Strict and nothing
    to fail for Standard. A candidate the report or record does not match fails in both."""
    global total
    head = "0123456789abcdef0123456789abcdef01234567"
    other = "f" * 40
    for governance in ("Strict", "Standard"):
        text = TYPED_ORDER.format(base="abc123").replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        def case(name, record=None, title=head, drop=(), candidate=head):
            folder = tmp / "candidate" / governance / name
            folder.mkdir(parents=True)
            order = folder / "WO-001-parser.md"
            order.write_bytes(text.encode("utf-8"))
            evidence_file(folder, "e.json", **{"head": head, **(record or {})})
            (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={digest}\n",
                                           encoding="utf-8")
            report_text = match_report(list(ACCEPTANCE.values()), "PARTIAL", digest)
            if title is None:
                report_text = report_text.replace(" / HEAD / WORKTREE_CLEAN: T / a / sonnet / b / c / d0d0d0d / yes",
                                                  " / WORKTREE_CLEAN: T / a / sonnet / b / c / yes", 1)
            else:
                report_text = report_text.replace("/ c / d0d0d0d / yes", f"/ c / {title} / yes", 1)
            (folder / "report.md").write_text(report_text, encoding="utf-8")
            flags = {"--evidence-dir": folder, "--dispatch-log": folder / "log.md", "--candidate": candidate}
            args = [part for flag, value in flags.items() if flag not in drop for part in (flag, value)]
            code, out = run("gate_check.py", "--match", folder / "report.md", order, *args)
            return code, [line for line in out.splitlines() if line.startswith("  - ")], out

        def check(name, want, **kw):
            """want: the one problem Strict must report; Standard must pass. None: both pass with no problem."""
            global total
            total += 1
            code, problems, out = case(name, **kw)
            if want is None or governance == "Standard":
                ok = code == 0 and not problems
            else:
                ok = code == 1 and len(problems) == 1 and want in problems[0]
            if not ok:
                failures.append(f"candidate {governance} {name}: exit {code}, problems {problems}: {out.strip()[-300:]}")

        check("bound", None)
        check("no_dispatch_log", "DISPATCH: Strict order checked without --dispatch-log", drop=("--dispatch-log",))
        check("no_evidence_dir", "EVIDENCE: Strict order checked without --evidence-dir; the records of AUTO PASS rows AC-1",
              drop=("--evidence-dir",))
        check("no_candidate", "CANDIDATE: a Strict match needs --candidate", drop=("--candidate",))
        check("legacy_record", "AC-1: e.json: legacy record without `schema`; Strict: record again",
              record={"drop": ("schema", "cwd", "started", "finished")})
        check("record_without_head", "AC-1: e.json: recorded with no git HEAD; Strict: record again", record={"head": None})
        check("short_report_head", "HEAD: a Strict report names the full commit (40 hex digits), got 0123456", title=head[:7])
        check("no_report_head", "HEAD: a Strict report names the full commit (40 hex digits), got none", title=None)
        for name, kw, want in (("other_candidate", {"candidate": other}, "the report names 0123456789ab, the candidate is ffffffffffff"),
                               ("record_not_at_candidate", {"record": {"head": other}},
                                "recorded at HEAD ffffffffffff, the candidate is 0123456789ab")):
            total += 1
            code, problems, out = case(name, **kw)
            if code != 1 or not any(want in p for p in problems):
                failures.append(f"candidate {governance} {name}: exit {code}, problems {problems}: {out.strip()[-300:]}")
    expect("--candidate needs the full hash", "gate_check.py", 2, "--match", tmp / "candidate" / "Strict" / "bound" / "report.md",
           tmp / "candidate" / "Strict" / "bound" / "WO-001-parser.md", "--candidate", head[:7])
    expect("--candidate needs --match", "gate_check.py", 2, "--report", tmp / "candidate" / "Strict" / "bound" / "report.md",
           "--candidate", head)


def test_one_fault(tmp):
    """v0.12: one fault at a time in an otherwise complete record, run the way an outside audit runs gate_check
    (--order, --report, --match and --evidence-dir together). The record starts as what `evidence_record.py run` wrote,
    so no case stops early at a missing field. Strict: each fault alone exits 1 with that one problem. Standard: a record
    from another commit still fails; uncommitted changes, another AC's label and a report HEAD that is not a hash are notes."""
    global total
    base = tmp / "one_fault"
    work = base / "work"
    work.mkdir(parents=True)
    expect("one fault: recording the base record", "evidence_record.py", 0, "run", "--out-dir", base / "out", "--label", "AC-1",
           "--cwd", work, "--", sys.executable, "-c", "print('ok')", says="exit=0")
    written = json.loads(next((base / "out").glob("*.json")).read_text(encoding="utf-8"))
    head = "0123456789abcdef0123456789abcdef01234567"
    written["git"] = {"head": head, "dirty": False}  # run outside git leaves both None; set them, change nothing else
    faults = {
        "clean": ({}, head, None),
        "report_head_not_hash": ({}, "not-a-commit", "HEAD: not-a-commit is not a commit hash"),
        "record_from_other_commit": ({"git": {"head": "f" * 40, "dirty": False}}, head, "recorded at HEAD ffffffffffff"),
        "dirty": ({"git": {"head": head, "dirty": True}}, head, "recorded with uncommitted changes"),
        "other_label": ({"label": "AC-OTHER"}, head, "its label is AC-OTHER, not AC-1"),
    }
    fails_in_standard = {"record_from_other_commit"}
    for governance in ("Strict", "Standard"):
        text = TYPED_ORDER.format(base="a" * 40).replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
        for case, (change, report_head, problem) in faults.items():
            folder = base / governance / case
            folder.mkdir(parents=True)
            order = folder / "WO-001-parser.md"
            order.write_bytes(text.encode("utf-8"))
            (folder / "e.json").write_text(json.dumps({**written, **change}), encoding="utf-8")
            report = folder / "report.md"
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            report.write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest)
                              .replace("/ c / d0d0d0d / yes", f"/ c / {report_head} / yes", 1), encoding="utf-8")
            (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev=1 sha={digest}\n",
                                           encoding="utf-8")
            code, out = run("gate_check.py", "--order", order, "--report", report, "--match", report, order, "--evidence-dir", folder,
                            "--dispatch-log", folder / "log.md", "--candidate", head)
            problems = [line for line in out.splitlines() if line.startswith("  - ")]
            notes = [line for line in out.splitlines() if line.startswith("  ~ ") and problem and problem in line]
            if problem is None:
                ok = code == 0 and not problems
            elif governance == "Strict" or case in fails_in_standard:
                ok = code == 1 and len(problems) == 1 and problem in problems[0]
            else:
                ok = code == 0 and not problems and notes
            total += 1
            if not ok:
                failures.append(f"one fault {governance} {case}: exit {code}, problems {problems}, notes {notes}: {out.strip()[-300:]}")


def test_metrics(tmp):
    """metrics_report.py counts PURPOSE.md's numbers from the Director's files; a missing source is UNKNOWN, not 0."""
    root = tmp / "metrics" / "DIRECTOR"
    for folder in ("orders", "reviews"):
        (root / folder).mkdir(parents=True)
    typed = TYPED_ORDER.format(base="abc123")
    (root / "orders" / "WO-001.md").write_text(typed.replace("REVISION       = 1", "REVISION       = 3"), encoding="utf-8")
    (root / "orders" / "WO-002.md").write_text(typed.replace("# WO-001", "# WO-002"), encoding="utf-8")
    (root / "reviews" / "v1.md").write_text(VERDICT.format(verdict="FAIL", step="CONTINUE_SAME_WORKER"), encoding="utf-8")
    (root / "reviews" / "v2.md").write_text(VERDICT.format(verdict="PASS", step="ACCEPT_AND_CLOSE"), encoding="utf-8")
    (root / "DECISION_REGISTER.md").write_text("# DECISION_REGISTER\n## A. 決策\n| ID | 決定 |\n|---|---|\n| DD-1 | use json |\n",
                                               encoding="utf-8")  # has ## A but no 下一步: not a verdict
    (root / "DIRECTOR_LOG.md").write_text(
        "# DIRECTOR_LOG\n"
        "2025-12-30 10:00 +08:00 | RESUMED WO-000 at x; next=y; waiting=NONE\n"
        "2026-01-02 10:00 +08:00 | RESUMED WO-001 at AC-1; next=run; waiting=NONE; redo=NONE\n"
        "2026-01-03 10:00 +08:00 | RESUMED WO-001 at AC-2; next=run; waiting=NONE; redo=capture.mp4\n"
        "2026-01-02 11:00 +08:00 | BOOTSTRAP_STUCK 第 4 步 tool missing\n"
        "2026-01-02 12:00 +08:00 | SPEC_REVIEW WO-001 tokens=1200 issues=0/1/2 adopted=2\n", encoding="utf-8")
    (root / "PO_PENDING.md").write_text("ID: OD-1\nCREATED: 2026-01-06 09:00\nSTATUS: open\n\nID: OD-2\nCREATED: 2025-12-01 09:00\n"
                                        "STATUS: closed\n\nID: ACT-1\nSTATUS: answered\n", encoding="utf-8")
    (root / "orders" / "WO-009-old.md").write_text("# WO-009 old style\nGOVERNANCE = Strict\n", encoding="utf-8")
    (root / "orders" / "WO-010.md").write_text(typed.replace("# WO-001", "# WO-010").replace("ISSUED_BY      = director 2026-01-02 10:00",
                                                                                            "ISSUED_BY      = director"), encoding="utf-8")
    expect("metrics counts", "metrics_report.py", 0, "--director", root,
           says=["| 返工次數 | 1（CONTINUE_SAME_WORKER 1、SWITCH_TO_OTHER_WORKER 0）；工單改版 2 次（1 份工單） | 裁決 2 份、工單 3 份 |",
                 "- 像工單但沒有 `ISSUED_BY =` 行，返工和改版都沒算到：1 份：" + str(pathlib.Path("orders", "WO-009-old.md")),
                 "| 中斷後遺失的工作 | 1 / 恢復 3 次；1 次沒寫 redo= |", "| PO 介入次數 | 3（ACT 1、OD 2），還在等 PO 1；UNDATED 1（沒寫 CREATED） | PO_PENDING.md |",
                 "| 新專案導入卡住 | 1 |", "1 次，tokens 合計 1200，採用的問題 2 個", "UNKNOWN：跑 `usage_report.py`"])
    expect("metrics --since drops older lines", "metrics_report.py", 0, "--director", root, "--since", "2026-01-01",
           says=["| 中斷後遺失的工作 | 1 / 恢復 2 次 |", "範圍：2026-01-01 起"])
    expect("metrics --since drops older orders", "metrics_report.py", 0, "--director", root, "--since", "2026-01-05",
           says=["工單改版 0 次（0 份工單）", "| 新專案導入卡住 | 0 |", "0 次", "| 中斷後遺失的工作 | UNKNOWN：DIRECTOR_LOG 沒有 RESUMED 行",
                 "照 --since 略過：2 份", "- 工單沒有日期，照算：1 份",
                 "| PO 介入次數 | 2（ACT 1、OD 1），還在等 PO 1；UNDATED 1（沒寫 CREATED，照算）；--since 前 1 項沒算 |"])
    elsewhere = tmp / "metrics" / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "DECISIONS_FOR_OWNER.md").write_text(
        "| ID | 問題 | 狀態 |\n|---|---|---|\n| Q-1 | a | 等待 |\n| Q-2 | b | 已決 |\n", encoding="utf-8")
    po_cfg = elsewhere / "po.json"
    po_cfg.write_text(json.dumps({"schema_version": 1, "po_pending_files": ["DECISIONS_FOR_OWNER.md"],
                                  "po_item_pattern": r"^\|\s*(Q)-\d+", "po_open_pattern": r"等待"}), encoding="utf-8")
    expect("metrics reads PO entries from the files the config names", "metrics_report.py", 0, "--director", elsewhere,
           "--config", po_cfg, says="| PO 介入次數 | 2（Q 2），還在等 PO 1；UNDATED 2（沒寫 CREATED） | DECISIONS_FOR_OWNER.md |")
    (elsewhere / "director_work.json").write_text(po_cfg.read_text(encoding="utf-8"), encoding="utf-8")
    expect("metrics finds director_work.json in DIRECTOR", "metrics_report.py", 0, "--director", elsewhere, says="2（Q 2）")
    no_po = tmp / "metrics" / "no_po"
    no_po.mkdir()
    expect("metrics without a PO file named in the config", "metrics_report.py", 0, "--director", no_po,
           "--config", po_cfg, says="UNKNOWN：沒有 DECISIONS_FOR_OWNER.md")
    po_cfg.write_text(json.dumps({"schema_version": 1, "po_item_pattern": "(unclosed"}), encoding="utf-8")
    expect("metrics refuses a broken PO pattern", "metrics_report.py", 1, "--director", elsewhere, "--config", po_cfg,
           says="FAIL config")
    po_cfg.write_text(json.dumps({"schema_version": 9}), encoding="utf-8")
    expect("metrics refuses an unknown config version", "metrics_report.py", 1, "--director", elsewhere, "--config", po_cfg,
           says="schema_version 9 is not 1")
    no_verdict = tmp / "metrics" / "no_verdict"
    shutil.copytree(root / "orders", no_verdict / "orders")
    expect("metrics with orders but no verdict says UNKNOWN, not 0", "metrics_report.py", 0, "--director", no_verdict,
           says="| 返工次數 | UNKNOWN：找不到裁決；工單改版 2 次（1 份工單） | 裁決 0 份、工單 3 份 |", lacks="| 返工次數 | 0")
    empty = tmp / "metrics" / "empty"
    empty.mkdir()
    expect("metrics with nothing recorded", "metrics_report.py", 0, "--director", empty,
           says=["UNKNOWN：找不到裁決；工單改版 UNKNOWN：找不到工單", "UNKNOWN：沒有 DIRECTOR_LOG.md", "UNKNOWN：沒有 PO_PENDING.md",
                 "沒有 `ISSUED_BY =` 行，返工和改版都沒算到：0 份"], lacks="| 0 |")
    expect("metrics bad --since", "metrics_report.py", 2, "--director", root, "--since", "Jan 1")
    expect("metrics missing folder", "metrics_report.py", 1, "--director", tmp / "metrics" / "nope", says="folder not found")


def test_trace(tmp):
    """trace_report.py joins orders, reports and verdicts; flags orders without TRACES_TO and IDs off the pattern."""
    root = tmp / "trace"
    for folder in ("orders", "reports", "reviews"):
        (root / folder).mkdir(parents=True)
    typed = TYPED_ORDER.format(base="abc123")
    (root / "orders" / "WO-001-parser.md").write_text(typed, encoding="utf-8")
    (root / "orders" / "WO-002-ui.md").write_text(ORDER.format(base="abc123").replace("# WO-001", "# WO-002"), encoding="utf-8")
    (root / "orders" / "WO-003-api.md").write_text(typed.replace("# WO-001", "# WO-003").replace("DD-1", "REQ7"), encoding="utf-8")
    (root / "reports" / "r1.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL"), encoding="utf-8")
    (root / "reports" / "stray.md").write_text(REPORT.format(result="PASS", tests="t", scope="PASS", evidence="e"), encoding="utf-8")
    (root / "reviews" / "v1.md").write_text(VERDICT.format(verdict="PASS_WITH_WARNINGS", step="ACCEPT_AND_CLOSE")
                                            .replace("# GATE VERDICT", "# GATE VERDICT WO-001"), encoding="utf-8")
    (root / "orders" / "WO-004-old.md").write_text("# WO-004 old style\nGOVERNANCE = Strict\n", encoding="utf-8")
    (root / "reports" / "notes.md").write_text("# notes\n", encoding="utf-8")
    (root / "reviews" / "draft.md").write_text("# draft verdict\n", encoding="utf-8")
    config = root / "director_work.json"
    config.write_text(json.dumps({"schema_version": 1, "trace_id_pattern": r"^(DD|OD)-\d+$"}), encoding="utf-8")
    base = ("--orders", root / "orders", "--reports", root / "reports")
    expect("trace table", "trace_report.py", 0, *base, "--verdicts", root / "reviews", "--config", config,
           says=["| DD-1 | WO-001 | AC-2 | REVIEW | READY_FOR_REVIEW | out.txt | PASS_WITH_WARNINGS（未標版次） |",
                 "| DD-1 | WO-001 | AC-1 | AUTO | PASS | e.json | PASS_WITH_WARNINGS（未標版次） |",
                 "## 裁決對不到報告版次\n- 無",
                 "| REQ7 | WO-003 | AC-1 | AUTO | 沒有報告 |", "## 沒有 TRACES_TO 的工單\n- WO-002",
                 "## 編號格式不符 trace_id_pattern\n- WO-003: REQ7", "stray.md", "沒計入的檔案 3 份，列在文末。",
                 "工單資料夾裡沒有 `ISSUED_BY =` 行的檔案（沒算成工單）：1 份\n- ", "WO-004-old.md",
                 "報告資料夾裡沒有 `TASK_ID` 行的檔案（沒算成報告）：1 份\n- ", "notes.md",
                 "裁決資料夾裡沒有 `## A` 的檔案（沒算成裁決）：1 份\n- ", "draft.md"])
    expect("trace without a pattern accepts any ID", "trace_report.py", 0, *base, says="## 編號格式不符 trace_id_pattern\n- 無")
    many = tmp / "trace_many"
    (many / "reports").mkdir(parents=True)
    shutil.copytree(root / "orders", many / "orders")
    passed = match_report(list(ACCEPTANCE.values()), "PARTIAL")
    failed = passed.replace("| AC-1 | exit 0 | e.json | PASS |", "| AC-1 | exit 1 | e.json | FAIL |")
    (many / "reports" / "report-9.md").write_text(passed, encoding="utf-8")
    (many / "reports" / "report-10.md").write_text(failed.replace("REVISION 1", "REVISION 2"), encoding="utf-8")
    trace_many = ("--orders", many / "orders", "--reports", many / "reports")
    many_order = many / "orders" / "WO-001-parser.md"
    many_order.write_text(typed.replace("REVISION       = 1", "REVISION       = 2"), encoding="utf-8")
    expect("trace picks the higher order revision, not the last file name", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json |", "報告 2 份對到工單",
                 f"- WO-001：選 {many / 'reports' / 'report-10.md'}", "REVISION 2、ATTEMPT —、日期 —、HEAD d0d0d0d ← 選這份",
                 "report-9.md：REVISION 1"], lacks="過期：")
    many_order.write_text(typed, encoding="utf-8")
    (many / "reports" / "report-10.md").write_text(failed.replace("RESULT:", "ATTEMPT: 1\nRESULT:", 1), encoding="utf-8")
    (many / "reports" / "report-9.md").write_text(passed.replace("RESULT:", "ATTEMPT: 2\nRESULT:", 1), encoding="utf-8")
    expect("trace picks the higher ATTEMPT at the same revision", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | PASS |", f"選 {many / 'reports' / 'report-9.md'}"])
    (many / "reports" / "report-10.md").write_text(failed.replace("RESULT:", "2026-01-04 09:00\nRESULT:", 1), encoding="utf-8")
    (many / "reports" / "report-9.md").write_text(passed.replace("RESULT:", "2026-01-03 18:00\nRESULT:", 1), encoding="utf-8")
    expect("trace picks the later date when revision and attempt tie", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL |", "日期 2026-01-04 09:00"])
    (many / "reports" / "report-10.md").write_text(failed, encoding="utf-8")
    (many / "reports" / "report-9.md").write_text(passed, encoding="utf-8")
    expect("trace takes neither of two reports it cannot order", "trace_report.py", 0, *trace_many,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | 多份報告分不出先後 |", "分不出先後，表內兩份都不取"], lacks="← 選這份")
    expect("trace with one report per order lists none", "trace_report.py", 0, *base,
           says="## 同一工單有多份報告（依 REVISION、ATTEMPT、日期選，不看檔名）\n- 無")
    expect("trace with a missing folder", "trace_report.py", 1, "--orders", root / "nope", "--reports", root / "reports",
           says="folder not found")

    # v0.13 (A10): --decisions checks TRACES_TO against the project's requirement files, both ways
    decisions = root / "decisions.md"
    decisions.write_text("# 決定\n\n| ID | 決定 |\n|---|---|\n| DD-1 | parser |\n| **DD-2** | 沒人做 |\n"
                         "| 說明 | DD-3 不是第一欄 |\n", encoding="utf-8")
    expect("trace --decisions lists a TRACES_TO ID found in no decision file", "trace_report.py", 0, *base,
           "--decisions", decisions, says="## TRACES_TO 找不到的編號\n- WO-003: REQ7", lacks="- WO-001: DD-1")
    expect("trace --decisions lists a requirement no order traces", "trace_report.py", 0, *base,
           "--decisions", decisions, says="## 沒有工單的需求\n- DD-2\n", lacks="- DD-3")
    expect("trace without --decisions prints neither section", "trace_report.py", 0, *base,
           lacks=["TRACES_TO 找不到的編號", "沒有工單的需求"])
    expect("trace --decisions with a missing file", "trace_report.py", 1, *base, "--decisions", root / "nope.md",
           says="FAIL file not found")

    # v0.13 (A09): a verdict is shown only next to the report of its own REVISION
    paired = tmp / "trace_verdicts"
    for folder in ("reports", "reviews"):
        (paired / folder).mkdir(parents=True)
    shutil.copytree(root / "orders", paired / "orders")
    (paired / "orders" / "WO-001-parser.md").write_text(typed.replace("REVISION       = 1", "REVISION       = 2"),
                                                        encoding="utf-8")
    (paired / "reports" / "r2.md").write_text(failed.replace("REVISION 1", "REVISION 2"), encoding="utf-8")

    def verdict(name, verdict_word, rev, extra=""):
        text = VERDICT.format(verdict=verdict_word, step="ACCEPT_AND_CLOSE").replace(
            "# GATE VERDICT", f"# GATE VERDICT WO-001\nORDER: WO-001-parser.md REVISION {rev}\n{extra}")
        (paired / "reviews" / name).write_text(text, encoding="utf-8")

    verdict("v1.md", "PASS", 1)
    trace_paired = ("--orders", paired / "orders", "--reports", paired / "reports", "--verdicts", paired / "reviews")
    expect("trace does not put a revision 1 verdict next to a revision 2 report", "trace_report.py", 0, *trace_paired,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json | 沒有 REVISION 2 的裁決 |", "## 裁決對不到報告版次\n- WO-001：",
                 "v1.md 是 REVISION 1，表內報告是 REVISION 2"], lacks="| FAIL | e.json | PASS |")
    verdict("v2a.md", "FAIL", 2, "2026-01-05 10:00\n")
    verdict("v2b.md", "REWORK", 2, "2026-01-05 10:00\n")
    expect("trace takes neither of two verdicts it cannot order", "trace_report.py", 0, *trace_paired,
           says="| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json | 多份裁決分不出先後 |")
    verdict("v2b.md", "REWORK", 2, "2026-01-06 10:00\nCANDIDATE_HEAD: abcdef0123\n")
    expect("trace never shows a verdict whose CANDIDATE_HEAD is not the report's (G04b), even when it is later",
           "trace_report.py", 0, *trace_paired,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | FAIL | e.json | FAIL |", "v2b.md 的 CANDIDATE_HEAD abcdef0123 不是報告的 HEAD d0d0d0d"],
           lacks="| REWORK |")
    (paired / "reviews" / "v2a.md").rename(paired / "v2a.md")
    expect("trace marks the cell 未配對 when the only verdict of the revision judged another commit (G04b)",
           "trace_report.py", 0, *trace_paired, says="| FAIL | e.json | 未配對：沒有 HEAD d0d0d0d 的裁決 |", lacks="| REWORK |")
    (paired / "v2a.md").rename(paired / "reviews" / "v2a.md")
    verdict("v2b.md", "REWORK", 2, "2026-01-06 10:00\nCANDIDATE_HEAD: d0d0d0d\n")
    expect("trace accepts a CANDIDATE_HEAD equal to the report's HEAD", "trace_report.py", 0, *trace_paired,
           says="| REWORK |", lacks="不是報告的 HEAD")

    # 1.3.3: a report written for an older order no longer shows its PASS as current; no TRACES_TO x AC cross-product
    stale = tmp / "trace_stale"
    (stale / "orders").mkdir(parents=True)
    (stale / "reports").mkdir()
    order_path = stale / "orders" / "WO-001-parser.md"
    order_path.write_text(typed.replace("REVISION       = 1", "REVISION       = 2"), encoding="utf-8")
    trace_stale = ("--orders", stale / "orders", "--reports", stale / "reports")
    (stale / "reports" / "r.md").write_text(passed, encoding="utf-8")
    expect("trace marks a revision 1 report against a revision 2 order as stale", "trace_report.py", 0, *trace_stale,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | 過期：報告是 REVISION 1，工單現在是 REVISION 2（報告寫 PASS） | e.json |",
                 "## 報告過期或版次不符（表內狀態是舊報告寫的，不是現在的工單）\n- WO-001：過期"], lacks="| AUTO | PASS |")
    (stale / "reports" / "r.md").write_text(passed.replace("REVISION 1", "REVISION 3"), encoding="utf-8")
    expect("trace marks a report naming a revision the order never had", "trace_report.py", 0, *trace_stale,
           says="版次不符：報告寫 REVISION 3，工單只到 REVISION 2（報告寫 PASS）", lacks="| AUTO | PASS |")
    order_path.write_text(typed, encoding="utf-8")
    (stale / "reports" / "r.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", sha="0" * 64),
                                            encoding="utf-8")
    expect("trace marks a report whose ORDER_SHA256 is not the order's", "trace_report.py", 0, *trace_stale,
           says="過期：工單在報告之後改過（ORDER_SHA256 不符）（報告寫 PASS）", lacks="| AUTO | PASS |")
    good_sha = hashlib.sha256(order_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    (stale / "reports" / "r.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", sha=good_sha),
                                            encoding="utf-8")
    expect("trace shows a report whose ORDER_SHA256 matches as current", "trace_report.py", 0, *trace_stale,
           says=["| DD-1 | WO-001 | AC-1 | AUTO | PASS | e.json |", "## 報告過期或版次不符（表內狀態是舊報告寫的，不是現在的工單）\n- 無"],
           lacks="過期：")
    order_path.write_text(typed.replace("TRACES_TO      = DD-1", "TRACES_TO      = DD-1, DD-2"), encoding="utf-8")
    expect("trace without a 追溯 column gives one row per AC, not one per TRACES_TO ID x AC", "trace_report.py", 0,
           *trace_stale, says=["| DD-1、DD-2（工單層） | WO-001 | AC-1 | AUTO |", "| DD-1、DD-2（工單層） | WO-001 | AC-3 | PO |"],
           lacks=["| DD-2 | WO-001 | AC-1 |", "| DD-1 | WO-001 |", "AC 的追溯不在工單 TRACES_TO 裡"])
    mapped = typed.replace("TRACES_TO      = DD-1", "TRACES_TO      = DD-1, DD-2").replace(
        "| ID | 類型 | 要求 | 驗證方法 | 預期 |\n|---|---|---|---|---|", "| ID | 類型 | 要求 | 驗證方法 | 預期 | 追溯 |\n|---|---|---|---|---|---|").replace(
        "| exit 0 |\n", "| exit 0 | DD-1 |\n").replace("| no WRONG answer |\n", "| no WRONG answer | DD-1、DD-9 |\n").replace(
        "| PO says yes |\n", "| PO says yes | — |\n")
    order_path.write_text(mapped, encoding="utf-8")
    expect("an order with a 追溯 column still passes gate_check", "gate_check.py", 0, "--order", order_path, lacks="FAIL")
    expect("trace with a 追溯 column gives one row per ID the AC names", "trace_report.py", 0, *trace_stale,
           says=["| DD-1 | WO-001 | AC-1 | AUTO |", "| DD-1 | WO-001 | AC-2 | REVIEW |", "| DD-9 | WO-001 | AC-2 | REVIEW |",
                 "| （未指定） | WO-001 | AC-3 | PO |", "## AC 的追溯不在工單 TRACES_TO 裡\n- WO-001 AC-2: DD-9",
                 "## TRACES_TO 裡沒有 AC 驗證的編號\n- WO-001: DD-2"],
           lacks=["| DD-2 | WO-001 |", "| DD-1 | WO-001 | AC-3 |", "（工單層）"])
    expect("trace --decisions also checks the IDs an AC traces", "trace_report.py", 0, *trace_stale,
           "--decisions", decisions, says="## TRACES_TO 找不到的編號\n- WO-001: DD-9", lacks="- WO-001: DD-1\n")


def test_purpose():
    """PURPOSE.md keeps its 8 aims and 9 cores and says only the PO edits it; every CHANGELOG version answers to it."""
    global total
    root = TOOLS.parent
    text = (root / "PURPOSE.md").read_text(encoding="utf-8")
    for heading, count in (("初衷", 8), ("不能破壞的核心", 9)):
        total += 1
        section = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        items = re.findall(r"^\d+\. \*\*", section.group(1), re.M) if section else []
        if len(items) != count:
            failures.append(f"PURPOSE.md: ## {heading} should list {count} items, found {len(items)}; only the PO changes it")
    total += 1
    if "只有 PO 能改本檔" not in text:
        failures.append("PURPOSE.md no longer says 只有 PO 能改本檔")
    for version, body in re.findall(r"^## (\d+\.\d+\.\d+|Unreleased)[^\n]*\n(.*?)(?=^## |\Z)", (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M | re.S):
        total += 1
        if "對齊初衷" not in body:
            failures.append(f"CHANGELOG {version}: no 對齊初衷 line (PURPOSE.md, 改規則前的檢查)")


def test_chat_to_product(tmp):
    """2.0.0 (PURPOSE aim 8): mode choice first, a locked BRIEF that orders trace to, and a choice page for A/B picks."""
    global total
    root = TOOLS.parent
    wanted = [("BOOTSTRAP.md", "一般模式還是小白模式"), ("BOOTSTRAP.md", "## 14. 談需求、寫專案初衷卡"),
              ("README.md", "0. 先問我要用一般模式還是小白模式"), ("README.md", "`docs/12_chat_to_product.md`"),
              ("docs/12_chat_to_product.md", "## 為什麼"), ("docs/12_chat_to_product.md", "--decisions <WS>/DIRECTOR/BRIEF.md"),
              ("templates/BRIEF.md", "只有使用者能改這張卡"), ("templates/BRIEF.md", "| B-1 |"),
              ("templates/WORK_ORDER.md", "B-2"), ("templates/choice_page.html", "<title>"),
              ("templates/choice_page.html", 'collection("decisions")'), ("templates/choice_page.html", 'collection("notes")'),
              ("templates/choice_page.html", 'doc("brief/current")'), ("templates/choice_page.html", "總監建議"),
              ("templates/choice_page.html", "sendToClaude"), ("templates/choice_page.html", "canSendToClaude"),
              ("templates/choice_page.html", "seenAt"), ("templates/choice_page.html", '"comments":{}'),
              ("templates/choice_page.html", "S.drafts[d.id]"),
              ("docs/12_chat_to_product.md", "### 六、選擇頁不漏讀"), ("docs/12_chat_to_product.md", '"comments": {}'),
              ("docs/12_chat_to_product.md", "seenAt"), ("docs/12_chat_to_product.md", "ArtifactComments"),
              ("docs/03_communication.md", "選擇頁"), ("docs/06_resume_lossless.md", "選擇頁")]
    for path, needle in wanted:
        total += 1
        if needle not in (root / path).read_text(encoding="utf-8"):
            failures.append(f"chat to product: {path} lacks {needle!r} (docs/12)")
    for needle in ("schedule/current", "Baseball"):
        total += 1
        if needle in (root / "templates/choice_page.html").read_text(encoding="utf-8"):
            failures.append(f"chat to product: templates/choice_page.html still has the project-specific {needle!r}")
    example = json.loads((root / "director_work.example.json").read_text(encoding="utf-8"))
    total += 1
    if example.get("mode") not in ("general", "beginner") or not re.match(example.get("trace_id_pattern", ""), "B-2"):
        failures.append("director_work.example.json: mode must be general or beginner and trace_id_pattern must accept B-2")
    folder = tmp / "brief"
    for name in ("orders", "reports"):
        (folder / name).mkdir(parents=True)
    (folder / "orders" / "WO-001-parser.md").write_text(TYPED_ORDER.format(base="abc123").replace("DD-1", "B-2, B-9"), encoding="utf-8")
    base = ("--orders", folder / "orders", "--reports", folder / "reports", "--config", root / "director_work.example.json",
            "--decisions", root / "templates/BRIEF.md")
    expect("trace against the BRIEF template flags an ID the brief lacks", "trace_report.py", 0, *base,
           says=["## TRACES_TO 找不到的編號\n- WO-001: B-9", "## 編號格式不符 trace_id_pattern\n- 無"], lacks="- WO-001: B-2\n")
    expect("trace against the BRIEF template lists brief rows no order serves", "trace_report.py", 0, *base,
           says="## 沒有工單的需求\n- B-1\n", lacks="- B-2\n")


def test_vocabulary():
    """vocabulary.json is the one source; the docs and templates that spell the lists out must still match it."""
    global total
    vocab = json.loads((TOOLS / "vocabulary.json").read_text(encoding="utf-8"))
    root = TOOLS.parent
    wanted = [("docs/02_work_orders_gates.md", f"`{' / '.join(vocab[key])}`") for key in ("verdicts", "next_steps", "evidence_levels")]
    wanted += [("docs/02_work_orders_gates.md", f"**{word}**") for word in vocab["governance"]]
    wanted += [("templates/TASK_REPORT.md", " | ".join(vocab["report_results"])),
               ("templates/GATE_VERDICT.md", " | ".join(vocab["verdicts"])),
               ("templates/GATE_VERDICT.md", " | ".join(vocab["next_steps"])),
               ("templates/WORK_ORDER.md", " | ".join(vocab["governance"])),
               ("docs/02_work_orders_gates.md", f"`{' / '.join(vocab['ac_worker_statuses'])}`"),
               ("templates/WORK_ORDER.md", " / ".join(vocab["ac_worker_statuses"])),
               ("templates/TASK_REPORT.md", " / ".join(vocab["ac_worker_statuses"]["AUTO"]))]
    wanted += [(path, vocab["ac_worker_statuses"][kind][0]) for kind in ("REVIEW", "PO")
               for path in ("docs/02_work_orders_gates.md", "templates/TASK_REPORT.md")]
    for path, text in wanted:
        total += 1
        if text not in (root / path).read_text(encoding="utf-8"):
            failures.append(f"vocabulary: {path} no longer contains {text!r}; change tools/vocabulary.json and the docs together")


MUST_READ_LIMIT = 9550  # bytes of the 每輪必讀 docs on 2026-11-06 (v0.13 moved pure reasons to docs/10; +33 for the IN_FLIGHT fields kept in docs/06, review D01); 2.0.1 +48: PO 2026-11-08 the choice page counts as 待決頁 for no-miss reading (docs/03, docs/06 one clause each); every round re-reads them, so growth costs quota; 2.1.0 (reports 2 and 5) 12433 -> 9532: pure reasons to docs/10, details to docs/05 and docs/06b, one dispatch-plan line added to docs/01; the limit follows the new size so growth needs a reason again; +18 for the reading-side clause naming the choice page in docs/03 (Director W4 N1: the PO said the choice page must not be missed, so the reader must not rely on docs/06 alone)


def test_must_read_size():
    """The docs README marks 每輪必讀 must stay under MUST_READ_LIMIT; raise it only with a reason in the commit."""
    global total
    total += 1
    root = TOOLS.parent
    files = re.findall(r"^\| `(docs/[^`]+)` \|.*\*\*每輪必讀\*\*", (root / "README.md").read_text(encoding="utf-8"), re.M)
    size = sum(len((root / f).read_bytes().replace(b"\r\n", b"\n")) for f in files)
    if not files or size > MUST_READ_LIMIT:
        failures.append(f"must-read docs {files}: {size} bytes, limit {MUST_READ_LIMIT}; trim them or explain the new limit")


def test_must_read_reasons():
    """v0.13 moved the pure reasons of the must-read docs to docs/10; keep the pointer, the section and the template fields."""
    global total
    root = TOOLS.parent
    ten = (root / "docs/10_lessons_learned.md").read_text(encoding="utf-8")
    wanted = [("docs/10_lessons_learned.md", ten, "## 每輪必讀規則的理由")]
    wanted += [("docs/10_lessons_learned.md", ten, f"### {title}") for title in ("01 角色與權限", "03 溝通", "06 無損續航", "08 安全規則")]
    for doc in ("01_roles_authority", "03_communication", "06_resume_lossless", "08_safety_rules"):
        text = (root / f"docs/{doc}.md").read_text(encoding="utf-8")
        wanted.append((f"docs/{doc}.md", text.split("## 為什麼")[-1], "- 其他理由見 docs/10。"))
    template = (root / "templates/RESUME_STATE.md").read_text(encoding="utf-8")
    for field in ("ORDER:", "SESSION:", "WORKTREE / BRANCH / BASE / HEAD:", "LAST_VERIFIED_CHECKPOINT:", "COMPLETED_STEPS:", "（證據：",
                  "背景程序 PID", "啟動時間", "輸出路徑", "完成判定方式", "自己設的計時器", "等待程序",
                  "PARTIAL_OUTPUTS_TO_DISCARD:", "OPEN_DECISIONS:", "DO_NOT_REPEAT:"):
        wanted.append(("templates/RESUME_STATE.md", template, field))
    for path, text, needle in wanted:
        total += 1
        if needle not in text:
            failures.append(f"must-read reasons: {path} lacks {needle!r}; the must-read docs point to docs/10 and the template for it")


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

    # v0.13 (A05): a FORBIDDEN change that is committed or staged, then undone in the worktree, is still seen
    frozen = repo / "src" / "frozen" / "b.py"
    frozen.write_text("2\n", encoding="utf-8")
    git("add", "src/frozen/b.py")
    expect("staged change with the same worktree change", "scope_check.py", 1, *check, says=["forbidden=1", "staged=1"])
    frozen.write_text("1\n", encoding="utf-8")
    expect("staged change undone in the worktree", "scope_check.py", 1, *check, says=["src/frozen/b.py", "staged=1", "forbidden=1"])
    git("reset", "-q", "--", "src/frozen/b.py")
    frozen.write_text("2\n", encoding="utf-8")
    git("add", "src/frozen/b.py")
    git("commit", "-q", "-m", "frozen")
    frozen.write_text("1\n", encoding="utf-8")
    expect("committed change undone in the worktree", "scope_check.py", 1, *check, says=["src/frozen/b.py", "committed=2", "forbidden=1"])
    git("reset", "-q", "HEAD~1")  # back to the work commit; the worktree already holds the old content
    expect("unstaged-only change", "scope_check.py", 0, *check, says=["STATES: committed=1 staged=0", "untracked=0", "changed=2"])
    (repo / "src" / "frozen" / "new.py").write_text("x", encoding="utf-8")
    expect("untracked-only forbidden file", "scope_check.py", 1, *check, says=["untracked=1", "forbidden=1"])
    (repo / "src" / "frozen" / "new.py").unlink()

    # v0.13 batch 3 (S01): three diffs, base..HEAD, HEAD..index, index..worktree: a staged rename is not unstaged too
    git("mv", "docs/old.md", "docs/older.md")
    expect("a staged rename counts as staged only (S01)", "scope_check.py", 1, *check,
           says=["STATES: committed=1 staged=2 unstaged=1 untracked=0", "outside=2"])
    git("mv", "docs/older.md", "docs/old.md")
    # S03: a file marked skip-worktree or assume-unchanged is hashed against the index
    git("update-index", "--skip-worktree", "src/frozen/b.py")
    frozen.write_text("2\n", encoding="utf-8")
    expect("a skip-worktree file does not hide a forbidden change (S03)", "scope_check.py", 1, *check,
           says=["FORBIDDEN src/frozen/b.py", "FLAGGED: 1 file(s) marked assume-unchanged or skip-worktree; 1 differ", "forbidden=1"])
    frozen.write_text("1\n", encoding="utf-8")
    expect("a marked file that matches the index passes", "scope_check.py", 0, *check, says=["; 0 differ", "changed=2"])
    git("update-index", "--no-skip-worktree", "src/frozen/b.py")
    git("update-index", "--assume-unchanged", "src/frozen/b.py")
    frozen.unlink()
    expect("an assume-unchanged file deleted from the worktree", "scope_check.py", 1, *check, says=["FORBIDDEN src/frozen/b.py", "forbidden=1"])
    git("update-index", "--no-assume-unchanged", "src/frozen/b.py")
    git("checkout", "-q", "--", "src/frozen/b.py")
    # S02: an item in backticks keeps ` #`; without them ` #` starts a comment, and gate_check --order says so
    hashed = repo / "src" / "x #draft.txt"
    hashed.write_text("x", encoding="utf-8")
    for name, item, code, says in (("a backticked FORBIDDEN item keeps ` #` (S02)", "`src/x #draft.txt`  # the draft", 1,
                                    ["FORBIDDEN src/x #draft.txt", "forbidden=1"]),
                                   ("without backticks ` #` starts a comment", "src/x #draft.txt", 0, "forbidden=0")):
        listed = tmp / f"{name[:12]}.md"
        listed.write_text(ORDER.format(base=base).replace("- src/frozen/**\n", "- src/frozen/**\n- " + item + "\n"), encoding="utf-8")
        expect(name, "scope_check.py", code, "--order", listed, "--repo", repo, says=says)
    expect("--order notes an item cut at ` #`", "gate_check.py", 0, "--order", listed,
           says="~ FORBIDDEN: `src/x #draft.txt` is read as `src/x` (` #` starts a comment); if ` #` is part of the name")
    listed.write_text(ORDER.format(base=base).replace("- src/frozen/**\n", "- src/frozen/**  # tests only\n"), encoding="utf-8")
    expect("--order reads `# text` as a plain comment", "gate_check.py", 0, "--order", listed, lacks="is read as")
    hashed.unlink()

    # v0.13: optional REQUIRED_CHANGES; the changes now are src/a.py and .config/app.json
    expect("no REQUIRED_CHANGES keeps the old last line", "scope_check.py", 0, *check, says="outside=0", lacks="missing=")
    for name, item, code, says in (("required file not changed", "src/parser.py", 1, ["MISSING   src/parser.py", "VIOLATION", "outside=0 missing=1"]),
                                   ("required file changed", "src/a.py", 0, ["PASS", "missing=0"])):
        wanted = tmp / f"{name}.md"
        wanted.write_text(ORDER.format(base=base).replace("- src/frozen/**\n", "- src/frozen/**\nREQUIRED_CHANGES:\n- " + item + "\n"), encoding="utf-8")
        expect(name, "scope_check.py", code, "--order", wanted, "--repo", repo, says=says)


def test_submodule_ignore(tmp):
    """v0.13 batch 3 (S04): `submodule.<name>.ignore=all` does not hide a staged change of a FORBIDDEN submodule."""
    root = tmp / "submodule"
    source, outer = root / "source", root / "outer"
    source.mkdir(parents=True)
    outer.mkdir()

    def git(where, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "protocol.file.allow=always", *args], cwd=where, check=True, capture_output=True,
                              text=True).stdout.strip()

    git(source, "init", "-q", "-b", "main")
    (source / "f.txt").write_text("a", encoding="utf-8")
    git(source, "add", "-A")
    git(source, "commit", "-q", "-m", "a")
    first = git(source, "rev-parse", "HEAD")
    (source / "f.txt").write_text("b", encoding="utf-8")
    git(source, "commit", "-q", "-am", "b")
    git(outer, "init", "-q", "-b", "main")
    git(outer, "submodule", "add", "-q", str(source), "vendor/lib")
    git(outer / "vendor" / "lib", "checkout", "-q", "--detach", first)
    git(outer, "add", "-A")
    git(outer, "commit", "-q", "-m", "base")
    base = git(outer, "rev-parse", "HEAD")
    order = root / "WO.md"
    order.write_text(f"BASE_REF = {base}\nSCOPE:\n- src/**\nFORBIDDEN:\n- vendor/lib\n", encoding="utf-8")
    git(outer / "vendor" / "lib", "checkout", "-q", "main")
    git(outer, "add", "vendor/lib")
    git(outer, "config", "submodule.vendor/lib.ignore", "all")
    git(outer, "config", "diff.ignoreSubmodules", "all")
    expect("submodule ignore=all does not hide a staged forbidden gitlink (S04)", "scope_check.py", 1, "--order", order,
           "--repo", outer, says=["FORBIDDEN vendor/lib", "staged=1", "forbidden=1"])


def test_shared_code():
    global total
    total += 1
    blocks = [re.search(r"^def parse_list.*?(?=^\S)", (TOOLS / tool).read_text(encoding="utf-8"), re.M | re.S)
              for tool in ("gate_check.py", "scope_check.py")]
    if not all(blocks) or blocks[0].group() != blocks[1].group():
        failures.append("parse_list differs between gate_check.py and scope_check.py; keep the two copies identical")


def newline_kw_calls(source):
    """Lines of Path.write_text(newline=) (3.10+) and Path.read_text(newline=) (3.13+) calls, also split over lines."""
    import ast
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("write_text", "read_text") and any(k.arg == "newline" for k in node.keywords)]


def test_py39_newline():
    """1.1.0 fix: the tools run on Python 3.9, where Path.write_text has no newline= (CI 3.9 crash in auto-pause)."""
    global total
    total += 1
    sample = 'p.write_text(\n    "x",\n    encoding="utf-8",\n    newline="\\n",\n)\nq.read_text(encoding="utf-8")\n'
    if newline_kw_calls(sample) != [1]:
        failures.append(f"py39 newline scan: detector missed the multi-line sample: {newline_kw_calls(sample)}")
    for tool in sorted(TOOLS.glob("*.py")):
        total += 1
        hits = newline_kw_calls(tool.read_text(encoding="utf-8"))
        if hits:
            failures.append(f"py39 newline scan: {tool.name} line(s) {hits} pass newline= to Path.write_text/read_text;"
                            " use open(path, 'w', encoding='utf-8', newline='\\n')")


def test_hook_protect(tmp):
    """v0.13: --protect blocks Write / Edit on DIRECTOR/orders/** and DIRECTOR_LOG.md; setup migrates old entries."""
    global total
    director = tmp / "protect" / "DIRECTOR"
    (director / "orders").mkdir(parents=True)
    (director / "orders" / "WO-001-a.md").write_text("x\n", encoding="utf-8")
    (director / "DIRECTOR_LOG.md").write_text("x\n", encoding="utf-8")
    worker = tmp / "protect" / "worker"
    worker.mkdir()

    def guard(name, code, tool, file_path, protect=True, cwd=None):
        global total
        total += 1
        call = {"tool_name": tool, "tool_input": {"file_path": str(file_path), "content": "y"}}
        if cwd:
            call["cwd"] = str(cwd)
        args = ["--protect", str(director)] if protect else []
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", *args], capture_output=True,
                              encoding="utf-8", input=json.dumps(call))
        if done.returncode != code:
            failures.append(f"hook_guard protect {name}: expected exit {code}, got {done.returncode}: {done.stderr.strip()}")
        elif code == 2 and ("BLOCKED" not in done.stderr or re.search(r"<[^>]*>", done.stderr)):
            failures.append(f"hook_guard protect {name}: message {done.stderr.strip()!r}")

    guard("Write to orders", 2, "Write", director / "orders" / "WO-002-new.md")
    guard("Edit of DIRECTOR_LOG", 2, "Edit", director / "DIRECTOR_LOG.md")
    guard("relative path from the hook cwd", 2, "Write", "../DIRECTOR/orders/WO-001-a.md", cwd=worker)
    guard(".. detour", 2, "Write", director / "orders" / ".." / "orders" / "sub" / "x.md")
    if os.name == "nt":  # elsewhere a backslash is part of a file name, and that file is not under orders/
        guard("backslashes", 2, "Edit", str(director / "orders" / "WO-001-a.md").replace("/", "\\"))
        guard("other case on Windows", 2, "Edit", str(director / "ORDERS" / "wo-001-a.md").upper())
    guard("other file in DIRECTOR", 0, "Write", director / "notes.md")
    guard("folder named like orders", 0, "Write", director / "orders-old" / "x.md")
    guard("worker file", 0, "Edit", worker / "src.py")
    guard("without --protect", 0, "Write", director / "orders" / "WO-001-a.md", protect=False)
    guard("Bash is still checked", 0, "Bash", director / "orders" / "WO-001-a.md")
    total += 1
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--protect", str(director)],
                          capture_output=True, encoding="utf-8", input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push"}}))
    if done.returncode != 2:
        failures.append(f"hook_guard --protect stopped checking Bash: exit {done.returncode}")
    if os.name != "nt":
        print("SKIP hook_guard junction and 8.3 cases: not Windows")
    else:
        link = tmp / "protect" / "dirlink"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(director)], capture_output=True,
                              encoding="utf-8", errors="replace")
        if made.returncode != 0:
            print(f"SKIP hook_guard junction case: mklink /J failed: {(made.stdout + made.stderr).strip()}")
        else:
            guard("junction to DIRECTOR", 2, "Write", link / "orders" / "WO-009.md")
            os.rmdir(link)  # removes the junction only, not its target
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        longdir = tmp / "protect" / "Long Folder Name For Short"
        longdir.mkdir()
        (longdir / "orders").mkdir()
        n = ctypes.windll.kernel32.GetShortPathNameW(str(longdir), buf, len(buf))
        short = buf.value if n else str(longdir)
        if os.path.normcase(short) == os.path.normcase(str(longdir)):
            print("SKIP hook_guard 8.3 case: no short name on this volume (8.3 names are off)")
        else:
            total += 1
            done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--protect", str(longdir)],
                                  capture_output=True, encoding="utf-8",
                                  input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": short + "\\orders\\x.md"}}))
            if done.returncode != 2:
                failures.append(f"hook_guard protect 8.3 name {short}: expected exit 2, got {done.returncode}")
        # v0.13 batch 3 (H01 H02): extended-length and device prefixes, NTFS stream names, file identity
        log = str(director / "DIRECTOR_LOG.md")
        guard("extended-length prefix (H01)", 2, "Write", "\\\\?\\" + log)
        guard("extended-length prefix and ::$DATA (H01)", 2, "Write", "\\\\?\\" + log + "::$DATA")
        guard("named stream of an order", 2, "Edit", str(director / "orders" / "WO-001-a.md") + ":note")
        guard("dot-device prefix of a drive path", 2, "Write", "\\\\.\\" + log)
        guard("GLOBALROOT device path (H02)", 2, "Write", "\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1\\x.md")
        guard("extended-length prefix elsewhere", 0, "Write", "\\\\?\\" + str(worker / "src.py"))
        hard = tmp / "protect" / "log-hardlink.md"
        try:
            os.link(director / "DIRECTOR_LOG.md", hard)
        except OSError as error:
            print(f"SKIP hook_guard hardlink case: {error}")
        else:
            guard("hardlink of DIRECTOR_LOG.md (same file id)", 2, "Write", hard)
            hard.unlink()
        drive = os.path.splitdrive(str(director))[0]
        unc = f"\\\\localhost\\{drive[0]}$" + str(director)[len(drive):] if drive.endswith(":") else None
        if unc and os.path.isdir(unc):
            guard("administrative UNC share of an existing order", 2, "Edit", unc + "\\orders\\WO-001-a.md")
            guard("new file in orders through the UNC share", 2, "Write", unc + "\\orders\\WO-003.md")
        else:
            print(f"SKIP hook_guard UNC case: {unc} is not reachable")

    repo = tmp / "protect" / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    setup = ("--repo", repo, "--only-this", "--guard-mode", "block")
    expect("plain hook installed", "setup_project_settings.py", 0, *setup, "--hooks", "--apply", says="SET")
    expect("old entry is not enough once protected", "setup_project_settings.py", 1, *setup, "--protect-director", director,
           says=["MISSING", "hooks.PreToolUse matcher"])
    expect("protected entry replaces the old one", "setup_project_settings.py", 0, *setup, "--protect-director", director,
           "--apply", says="SET")
    expect("protected entry kept on rerun", "setup_project_settings.py", 0, *setup, "--protect-director", director, says="OK")
    expect("plain --hooks accepts a protected entry (v0.12 rule)", "setup_project_settings.py", 0, *setup, "--hooks", says="OK")
    entries = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    total += 1
    if len(entries) != 1 or entries[0]["matcher"] != "Bash|PowerShell|Write|Edit" or "--protect" not in entries[0]["hooks"][0]["command"]:
        failures.append(f"setup --protect-director: PreToolUse is {entries}")
    expect("the Director's worktree wants the plain hook", "setup_project_settings.py", 1, *setup, "--protect-director", director,
           "--director-worktree", repo, says="hooks.PreToolUse matcher")
    expect("the Director's worktree gets the plain hook back", "setup_project_settings.py", 0, *setup, "--protect-director", director,
           "--director-worktree", repo, "--apply", says="SET")
    entries = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    total += 1
    if len(entries) != 1 or entries[0]["matcher"] != "Bash|PowerShell" or "--protect" in entries[0]["hooks"][0]["command"]:
        failures.append(f"setup --director-worktree: PreToolUse is {entries}")

    # v0.13 batch 3 (H04): the whole command is compared, and the installed hook is run once to allow, once to block
    settings = repo / ".claude" / "settings.local.json"
    expect("a protected install tests the hook", "setup_project_settings.py", 0, *setup, "--protect-director", director,
           "--apply", says="(hook test: allow=0 block=2 block-write=2)")
    data = json.loads(settings.read_text(encoding="utf-8"))
    good = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    dead = (tmp / "protect" / "gone" / "hook_guard.py").as_posix()
    data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = good.replace((TOOLS / "hook_guard.py").as_posix(), dead)
    settings.write_text(json.dumps(data), encoding="utf-8")
    expect("a hook_guard.py that is gone is not OK (H04)", "setup_project_settings.py", 1, *setup, "--protect-director",
           director, says=["MISSING", "hooks.PreToolUse command"])
    expect("plain --hooks does not accept it either", "setup_project_settings.py", 1, *setup, "--hooks",
           says="hooks.PreToolUse command")
    expect("--apply writes the working command back", "setup_project_settings.py", 0, *setup, "--hooks", "--apply",
           says=["SET", "block-write=2"])
    total += 1
    command = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    if command != good:
        failures.append(f"setup --hooks --apply kept {command!r}, wanted {good!r} (with its --protect)")


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
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block"], capture_output=True,
                              encoding="utf-8", input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}))
        if done.returncode != code:
            failures.append(f"hook_guard {command!r}: expected exit {code}, got {done.returncode}: {done.stderr.strip()}")
        elif re.search(r"<[^>]*>", done.stderr):  # a worker quoting it in KNOWN_ISSUES would fail gate_check
            failures.append(f"hook_guard {command!r}: message has a <...> placeholder: {done.stderr.strip()}")
    repo = tmp / "hooked"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    setup = ("setup_project_settings.py", "--repo", repo, "--only-this", "--hooks", "--guard-mode", "block")
    expect("hooks missing", *setup[:1], 1, *setup[1:], says="hooks.PreToolUse")
    expect("hooks written", *setup[:1], 0, *setup[1:], "--apply", says="SET")
    expect("hooks kept on rerun", *setup[:1], 0, *setup[1:], "--apply", says="OK")
    data = json.loads((repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    total += 1
    if len(data["hooks"]["PreToolUse"]) != 1:
        failures.append("setup_project_settings --hooks added the hook twice")
    future = tmp / "future.json"
    future.write_text('{"schema_version": 2, "window": 250000}', encoding="utf-8")
    expect("unknown config version is refused", *setup[:1], 1, "--repo", repo, "--only-this", "--config", future)
    future.write_text('{"window": 250000}', encoding="utf-8")
    expect("config without a version counts as 1", *setup[:1], 0, "--repo", repo, "--only-this", "--config", future, says="OK")


def test_hook_rules(tmp):
    """1.1.0 item 1: hook_guard --rules / --profile. Every rule's examples under both profiles, bypass forms, MCP read-only
    and internal-report exemptions, config paths, self-protection, determinism, bad rules files, setup --guard-profile."""
    global total
    rules_path = TOOLS / "guard_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    home = pathlib.Path.home().as_posix()

    def hook(call, profile, rules_file=rules_path):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--rules", str(rules_file),
                               "--profile", profile], capture_output=True, encoding="utf-8", input=json.dumps(call))

    def outcome(done):
        """deny:ID / ask:ID / legacy / silent / bad / other(...), from exit code, stdout and stderr."""
        if done.returncode == 1 and done.stderr.startswith("hook_guard: bad rules file: ") and not done.stdout:
            return "bad"
        if done.returncode == 2 and not done.stdout:
            found = re.match(r"BLOCKED by hook_guard \[(G\d+)\]: \S", done.stderr)
            if found:
                return f"deny:{found.group(1)}"
            if done.stderr.startswith("BLOCKED by hook_guard: "):
                return "legacy"
        if done.returncode == 0 and not done.stderr:
            if not done.stdout:
                return "silent"
            try:
                out = json.loads(done.stdout)["hookSpecificOutput"]
                found = re.match(r"\[(G\d+)\] \S", out["permissionDecisionReason"])
                if out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "ask" and found and len(out) == 3:
                    return f"ask:{found.group(1)}"
            except (ValueError, KeyError, TypeError):
                pass
        return f"other(exit {done.returncode}: {(done.stdout + done.stderr).strip()[:160]!r})"

    def check(name, call, profile, want, rules_file=rules_path):
        global total
        total += 1
        done = hook(call, profile, rules_file)
        got = outcome(done)
        if got != want:
            failures.append(f"hook_guard rules {name} [{profile}]: expected {want}, got {got}")
        elif re.search(r"<[^>]*>", done.stdout + done.stderr):
            failures.append(f"hook_guard rules {name} [{profile}]: message has a <...> placeholder")
        return done

    bash = lambda command: {"tool_name": "Bash", "tool_input": {"command": command}}
    shell = lambda command: {"tool_name": "PowerShell", "tool_input": {"command": command}}
    tool = lambda name, **kw: {"tool_name": name, "tool_input": kw}
    write = lambda path, **kw: {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": "x"}, **kw}

    # every rule: its example_block gives that rule's decision and id, its example_allow is silent, in both profiles
    for rule in rules["rules"]:
        for profile in ("worker", "director"):
            decision = rule["decision"][profile]
            for n, call in enumerate(rule["example_block"] if isinstance(rule["example_block"], list) else [rule["example_block"]]):
                check(f"{rule['id']} example_block {n}", call, profile, "silent" if decision == "none" else f"{decision}:{rule['id']}")
            for n, call in enumerate(rule["example_allow"] if isinstance(rule["example_allow"], list) else [rule["example_allow"]]):
                check(f"{rule['id']} example_allow {n}", call, profile, "silent")

    # push written to slip past a text match is still push (F6)
    for command in ("git -C . push", "git 'push'", "/usr/bin/git push", 'bash -c "git push"', 'powershell -c "git push"',
                    "cmd /c git push", "cd x && git push", "echo $(git push)", r'"C:\Program Files\Git\bin\git.exe" push'):
        for profile in ("worker", "director"):
            check(f"push bypass {command!r}", bash(command), profile, "deny:G02")
    check("force push wins over push (lowest id)", bash("git push -f origin main"), "worker", "deny:G01")
    check("delete of a remote branch is G01", bash("git push origin :old"), "director", "deny:G01")
    # deleting, every way of writing it
    for call in (bash("bash -c 'rm -rf x'"), bash("/bin/rm -rf x"), bash("find . -name '*.tmp' -delete"), bash("ls | xargs rm"),
                 bash("cmd /c rd /s /q build"), bash("del /s x"), shell("Get-ChildItem x | Remove-Item"), shell("ri build"),
                 shell("Remove-Item -Recurse -Force build")):
        check(f"delete {call['tool_input']['command']!r}", call, "worker", "deny:G10")
        check(f"delete {call['tool_input']['command']!r}", call, "director", "ask:G10")
    done = check("worker delete message names the next step", bash("rm -rf build"), "worker", "deny:G10")
    total += 1
    if "deletable list" not in done.stderr or "cleaner" not in done.stderr:
        failures.append(f"G10 deny message lacks the next step: {done.stderr.strip()}")
    # MCP: only the action part counts; read-only prefixes never match (D3 b)
    for name in ("mcp__vendor__get_order", "mcp__vendor__get_domain_order", "mcp__vendor__list_billing_charges",
                 "mcp__vendor__get_purchase_quote", "mcp__vendor__read_payment_status", "mcp__vendor__search_orders",
                 "mcp__vendor__query_subscriptions", "mcp__vendor__status_of_transfer", "mcp__buy_tools__get_status",
                 "mcp__ccd_session_mgmt__get_session", "mcp__ccd_settings__get_settings"):
        for profile in ("worker", "director"):
            check(f"read-only MCP {name}", tool(name), profile, "silent")
    for name, worker, director in (("mcp__vendor__buy_domain", "deny:G30", "deny:G30"),
                                   ("mcp__shop__checkoutCart", "deny:G30", "deny:G30"),
                                   ("mcp__drive__trash_file", "deny:G11", "ask:G11"),
                                   ("mcp__drive__share_file", "deny:G21", "ask:G21"),
                                   ("mcp__github__createPullRequest", "deny:G21", "ask:G21"),
                                   ("mcp__chat__send_message", "deny:G21", "ask:G21"),
                                   ("mcp__ccd_session_mgmt__set_session_permission_mode", "deny:G42", "ask:G42")):
        check(f"MCP {name}", tool(name), "worker", worker)
        check(f"MCP {name}", tool(name), "director", director)
    # the internal report channel is not "sending" (D3 c)
    for name in ("SendMessage", "mcp__ccd_session_mgmt__send_message"):
        for profile in ("worker", "director"):
            check(f"internal report {name}", tool(name, to="x", message="done"), profile, "silent")
    # config files, not all of ~/.claude (D3 a)
    for path, want in ((f"{home}/.claude/settings.json", "G40"), (f"{home}/.claude/.credentials.json", "G40"),
                       (f"{home}/.claude/CLAUDE.md", "G40"), (f"{home}/.claude.json", "G40"),
                       ("D:/proj/.claude/settings.local.json", "G40"), ("D:/proj/.mcp.json", "G40"),
                       ("C:/ProgramData/ClaudeCode/managed-settings.json", "G40"),
                       (f"{home}/.claude/projects/p/memory/MEMORY.md", None), (f"{home}/.claude/plans/plan.md", None),
                       ("D:/proj/docs/settings.md", None), ("D:/proj/CLAUDE.md.bak", None)):
        check(f"Write {path}", write(path), "worker", f"deny:{want}" if want else "silent")
        check(f"Write {path}", write(path), "director", f"ask:{want}" if want else "silent")
    check("relative path read against the hook cwd", write(".claude/settings.local.json", cwd=str(tmp)), "worker", "deny:G40")
    check("~ in the path", write("~/.claude/settings.json"), "worker", "deny:G40")
    if os.name == "nt":
        check("other case on Windows", write("D:/PROJ/.CLAUDE/Settings.Local.JSON"), "worker", "deny:G40")
        check("backslashes", write(r"D:\proj\.claude\settings.json"), "worker", "deny:G40")
    check("reading a settings file is not a change", tool("Read", file_path=f"{home}/.claude/settings.json"), "worker", "silent")
    for path in (rules_path, TOOLS / "hook_guard.py"):
        check(f"self-protection {path.name}", write(path), "worker", "deny:G00")
        check(f"self-protection {path.name}", write(path), "director", "ask:G00")
    # batch 1 acceptance (11-07) 1: push through a git alias or the push plumbing is still push, in both profiles
    for command in ("git -c alias.p=push p", "git -c alias.p='!git push' p", "git config alias.p push && git p",
                    "git config --local alias.p push", "git -C . config set alias.p push", "git --config-env=alias.p=X p",
                    "git send-pack origin HEAD", "git http-push https://example.invalid/r.git main",
                    '"C:/Program Files/Git/mingw64/libexec/git-core/git-send-pack.exe" origin HEAD', "git-push origin"):
        for profile in ("worker", "director"):
            check(f"push bypass {command!r}", bash(command), profile, "deny:G02")
    for command in ("git config --get alias.p", "git config -l", "git config --unset alias.p", "git -c core.autocrlf=false status",
                    "git log --grep=alias.p=x"):
        check(f"not a push {command!r}", bash(command), "worker", "silent")
    # 2: a shell command that writes the rules file or hook_guard.py is G00; reading them is not
    for call in (bash(f"sed -i s/deny/none/ {rules_path.as_posix()}"), bash("sed -i.bak s/x/y/ tools/hook_guard.py"),
                 bash("sed --in-place s/x/y/ tools/guard_rules.json"), bash("echo x > tools/hook_guard.py"),
                 bash("cat x >> tools/guard_rules.json"), bash("cat x>tools/guard_rules.json"), bash("> tools/guard_rules.json cat x"),
                 bash("cat x 2> tools/guard_rules.json"), bash("cat x &> tools/guard_rules.json"), bash("cat x >| tools/guard_rules.json"),
                 bash("tee tools/guard_rules.json < x"), bash("cp /tmp/r.json tools/guard_rules.json"), bash("mv tools/hook_guard.py x.py"),
                 bash("git checkout HEAD -- tools/hook_guard.py"), bash("git restore tools/guard_rules.json"),
                 bash("perl -pi -e s/deny/none/ tools/guard_rules.json"), bash('bash -c "sed -i s/a/b/ tools/guard_rules.json"'),
                 bash('echo "$(cat x > tools/guard_rules.json)"'), shell(r"Set-Content tools\guard_rules.json x"),
                 shell(r"Get-Content x | Out-File tools\GUARD_RULES.json"), shell(r"Copy-Item x -Destination tools\hook_guard.py"),
                 shell(r"[IO.File]::WriteAllText('tools\guard_rules.json', 'x')")):
        check(f"G00 shell write {call['tool_input']['command']!r}", call, "worker", "deny:G00")
        check(f"G00 shell write {call['tool_input']['command']!r}", call, "director", "ask:G00")
    for call in (bash("cat tools/guard_rules.json"), bash("sed -n 1p tools/guard_rules.json"), bash("git diff tools/hook_guard.py"),
                 bash("git log -p tools/hook_guard.py > /tmp/hook.patch"), bash("sed -n '/a>b/p' tools/guard_rules.json"),
                 bash("python -I tools/hook_guard.py --rules tools/guard_rules.json < call.json 2>&1"),
                 shell(r"Get-Content tools\guard_rules.json | Select-Object -First 5"), bash("sed -i s/a/b/ notes.md")):
        for profile in ("worker", "director"):
            check(f"G00 shell read {call['tool_input']['command']!r}", call, profile, "silent")
    # batch 2 commit 1: a { } next to the > no longer hides the redirect (probe miss on e6a9959)
    for call in (bash("echo {}>tools/guard_rules.json"), bash("echo {} >tools/guard_rules.json"), bash("echo a{}>tools/guard_rules.json"),
                 bash("{ echo x; }>tools/hook_guard.py"), bash("echo }>>tools/hook_guard.py"), bash("(echo x)>tools/guard_rules.json"),
                 bash("echo x >&tools/guard_rules.json"), shell("@{}>tools/guard_rules.json")):
        check(f"G00 brace redirect {call['tool_input']['command']!r}", call, "worker", "deny:G00")
        check(f"G00 brace redirect {call['tool_input']['command']!r}", call, "director", "ask:G00")
    # (a quoted "{}>tools/guard_rules.json" stays G00 as on e6a9959: the parsed word holds > and names the file)
    for call in (bash("echo {}>/tmp/x.json"), bash("jq '{}' tools/guard_rules.json > /tmp/out.json")):
        for profile in ("worker", "director"):
            check(f"G00 brace not a write {call['tool_input']['command']!r}", call, profile, "silent")
    # G40 shell_write: writing a settings or CLAUDE.md file from the shell is G40 like Write / Edit
    for call in (bash("sed -i s/a/b/ .claude/settings.local.json"), bash("echo x > CLAUDE.md"), bash("echo x>>CLAUDE.local.md"),
                 bash("cp a.json ~/.claude/settings.json"), bash("tee .mcp.json < x"), bash("echo {}>.claude/settings.json"),
                 bash("touch .claude/settings.json"), bash("cp new/settings.json ~/.claude/"), bash("echo x > ~/.claude.json"),
                 shell("Set-Content ~/.claude.json x"), shell(r"Copy-Item a -Destination .claude\settings.json"),
                 shell(r"[IO.File]::WriteAllText('.claude\settings.json', 'x')"), shell(r"'x' | Out-File D:\proj\CLAUDE.md")):
        check(f"G40 shell write {call['tool_input']['command']!r}", call, "worker", "deny:G40")
        check(f"G40 shell write {call['tool_input']['command']!r}", call, "director", "ask:G40")
    for call in (bash("cat CLAUDE.md"), bash("grep x .claude/settings.json"), bash("cp CLAUDE.md /tmp/backup.md"),
                 bash("echo x > ~/.claude/projects/p/memory/note.md"), bash("echo x > ~/.claude/plans/plan.md"),
                 bash("echo x > docs/settings.md"), bash("sed -n 1p CLAUDE.md > /tmp/c.txt"), bash("echo CLAUDE.md > list.txt"),
                 shell(r"Copy-Item .claude\settings.json -Destination backup\settings.json")):
        for profile in ("worker", "director"):
            check(f"G40 shell not a write {call['tool_input']['command']!r}", call, profile, "silent")
    # Monitor runs a shell command (hooks see it since Claude Code 2.1.314): checked as Bash; no string command is silent
    monitor = lambda **kw: tool("Monitor", description="watch", **kw)
    for call, worker, director in ((monitor(command="git push"), "deny:G02", "deny:G02"),
                                   (monitor(command="cat .env"), "deny:G50", "deny:G50"),
                                   (monitor(command="echo x > CLAUDE.md"), "deny:G40", "ask:G40"),
                                   (monitor(command="echo {}>tools/guard_rules.json"), "deny:G00", "ask:G00"),
                                   (monitor(command="tail -f log.txt"), "silent", "silent"),
                                   (monitor(), "silent", "silent"), (monitor(command=["git", "push"]), "silent", "silent"),
                                   (monitor(command=None), "silent", "silent"), (monitor(command=42), "silent", "silent"),
                                   ({"tool_name": "Monitor", "tool_input": "git push"}, "silent", "silent"),
                                   (tool("OtherTool", command="rm -rf x"), "silent", "silent")):
        check(f"Monitor {json.dumps(call['tool_input'])}", call, "worker", worker)
        check(f"Monitor {json.dumps(call['tool_input'])}", call, "director", director)
    # 3: the gh token file on Windows (%APPDATA%/GitHub CLI) is a credential file like ~/.config/gh/hosts.yml
    gh_win = f"{home}/AppData/Roaming/GitHub CLI"
    gh_calls = [tool("Read", file_path=f"{gh_win}/hosts.yml"), tool("Grep", pattern="oauth", path=gh_win),
                tool("Grep", pattern="oauth", path=f"{home}/.config/gh"), bash(f'cat "{gh_win}/hosts.yml"'),
                shell(r'Get-Content "$env:APPDATA\GitHub CLI\hosts.yml"'), bash(r'type "%APPDATA%\GitHub CLI\hosts.yml"')]
    if os.name == "nt":
        gh_calls.append(tool("Read", file_path=f"{gh_win}/HOSTS.yml".replace("/", "\\")))
    for call in gh_calls:
        for profile in ("worker", "director"):
            check(f"gh hosts.yml {json.dumps(call['tool_input'])}", call, profile, "deny:G50")
    check("another file under AppData/Roaming is not G50", tool("Read", file_path=f"{home}/AppData/Roaming/Code/settings.json"),
          "worker", "silent")
    # legacy checks still run with --rules, and plain commands stay silent with nothing on stdout (F2)
    check("legacy stash is still blocked", bash("git stash"), "director", "legacy")
    check("legacy reset --hard is still blocked", bash("git reset --hard HEAD~1"), "director", "legacy")
    for profile in ("worker", "director"):
        check("git status is silent", bash("git status"), profile, "silent")
        check("a build is silent", bash("python -m unittest"), profile, "silent")
        check("Read is silent", tool("Read", file_path="README.md"), profile, "silent")
    # 1.1.0 item 4: reading credential files, printing the environment or a token is denied in both profiles
    grep = lambda **kw: tool("Grep", pattern="KEY", **kw)
    blocked = {
        "G50": [tool("Read", file_path=".env"), tool("Read", file_path="~/.ssh/id_ed25519"),
                grep(path=f"{home}/.aws/credentials"), grep(glob=".env"), grep(path=".", glob="*.pem"),
                tool("Glob", pattern="**/.env"), bash("cat .env"), shell(r"Get-Content .\.env"), bash("type .env"),
                bash("copy .env x"), bash("base64 id_rsa"), bash("cat $HOME/.ssh/id_rsa"), bash("bash -c 'cat .env'"),
                bash("sed -n 1p .env.local"), shell("Select-String -Path .env -Pattern KEY"),
                tool("Read", file_path="D:/proj/sub/../.env"), bash("cp ./sub/../.env x"),
                tool("Read", file_path="D:/proj/.claude/.credentials.json"), tool("Read", file_path="D:/proj/config/secrets.yaml")]
               + ([tool("Read", file_path=r"D:\proj\.ENV"), bash("cat .ENV")] if os.name == "nt" else []),
        "G51": [bash("printenv"), bash("env"), bash("env -0"), shell("gci env:"), shell("Get-ChildItem Env:\\"),
                bash("echo $GITHUB_TOKEN"), bash('echo "token is ${GITHUB_TOKEN}"'), shell("Write-Output $env:API_KEY"),
                bash("echo %OPENAI_API_KEY%"), shell("$env:GITHUB_TOKEN"), bash("set"), bash("cmd /c set"), bash("export -p"),
                bash("printenv AWS_SECRET_ACCESS_KEY"), shell("[Environment]::GetEnvironmentVariables()")],
        "G52": [bash("gh auth token"), bash("gh auth status --show-token"), bash("git credential fill"),
                bash("git credential-manager get"), bash("aws --profile x configure get aws_secret_access_key"),
                bash("az account get-access-token"), bash("gcloud auth print-access-token"), bash("kubectl config view --raw")],
    }
    for rid, calls in blocked.items():
        for call in calls:
            for profile in ("worker", "director"):
                check(f"secret {rid} {json.dumps(call['tool_input'])}", call, profile, f"deny:{rid}")
    for call in (tool("Read", file_path=".env.example"), bash("cat README.md"), bash("echo $HOME"), bash("echo $AUTHOR"),
                 bash("grep TODO src/"), bash("grep -r password ."), bash("set -e"), bash("export FOO=1"), bash("printenv PATH"),
                 shell("Get-ChildItem"), shell("Get-ChildItem src"), shell("Write-Output $env:PATH"), bash("cat ~/.ssh/id_rsa.pub"),
                 bash("cat ~/.ssh/config"), bash("env FOO=1 python x.py"), bash("gh auth status"), bash("aws configure list"),
                 bash("gcloud auth application-default login"), grep(path="src"), tool("Glob", pattern="**/*.py"),
                 bash("kubectl config view")):
        for profile in ("worker", "director"):
            check(f"not a secret {json.dumps(call['tool_input'])}", call, profile, "silent")
    done = check("secret deny message names the next step", bash("cat .env"), "worker", "deny:G50")
    total += 1
    if "report which one and why to the Director" not in done.stderr:
        failures.append(f"G50 deny message lacks the next step: {done.stderr.strip()}")
    g50 = next(r for r in rules["rules"] if r["id"] == "G50")
    paths, shells = (next(m for m in g50["match"] if m["kind"] == k) for k in ("path", "shell"))
    total += 1
    if (paths["globs"], paths["except"]) != (shells["path_args"], shells["path_except"]):
        failures.append("G50: the path globs and the shell path_args differ; keep one list")
    # secret_mask: every kind is masked with nothing of the secret left; SHAs, counts and names stay
    spec = importlib.util.spec_from_file_location("secret_mask_under_test", TOOLS / "secret_mask.py")
    masker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(masker)
    fake = {  # built at run time so that the source holds no token-shaped string
        "private_key": ("-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH " + "PRIVATE KEY-----", "b3BlbnNzaC1rZXktdjEAAAAA"),
        "aws_access_key": ("AKIA" + "IOSFODNN7EXAMPLE", "IOSFODNN7EXAMPLE"),
        "github_token": ("gh" + "p_" + "a1B2" * 9, "a1B2" * 9),
        "github_pat": ("github" + "_pat_11ABCDEFG0123456789_abcdefghijKLMNOP", "11ABCDEFG0123456789"),
        "anthropic_key": ("sk-" + "ant-api03-" + "x7" * 15, "x7" * 15),
        "openai_key": ("sk-" + "proj-" + "Ab1" * 10, "Ab1" * 10),
        "slack_token": ("xo" + "xb-1234567890-abcdefghij", "1234567890-abcdefghij"),
        "google_api_key": ("AI" + "za" + "B9" * 17 + "C", "B9" * 17),
        "npm_token": ("np" + "m_" + "c4" * 18, "c4" * 18),
        "jwt": ("ey" + "JhbGciOiJIUzI1NiJ9.ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "dozjgNryP4J3jVmNHl0w5N"),
        "bearer": ("Authorization: Bearer abc.def-ghi", "abc.def-ghi"),
        "url_password": ("https://user:hunter2pass@example.com/r.git", "hunter2pass"),
        "assignment": ("GITHUB_TOKEN=s3cr3tvalue; password: 'p@ss w'", "s3cr3tvalue"),
    }
    for kind, (text, secret) in fake.items():
        total += 1
        masked, kinds = masker.mask(f"before {text} after")
        if f"[MASKED:{kind}]" not in masked or secret in masked or kind not in kinds or not masked.startswith("before "):
            failures.append(f"secret_mask {kind}: got {masked!r} {kinds}")
    for text in ("commit 4b825dc642cb6eb9a060e54bf8d69288fbee4904", "sha256 " + hashlib.sha256(b"").hexdigest(),
                 "max_tokens=4096 author=Bob PWD=/home/x", "Authorization: Bearer [MASKED:jwt]"):
        total += 1
        if masker.mask(text) != (text, []):
            failures.append(f"secret_mask changed text with no new secret: {text!r} -> {masker.mask(text)}")
    for text, want_exit, want_out in (("id " + fake["aws_access_key"][0], 1, "FOUND aws_access_key\nSECRETS: 1 kind(s)\n"),
                                      ("plain text", 0, "SECRETS: 0 kind(s)\n")):
        total += 1
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "secret_mask.py"), "--check"], input=text,
                              capture_output=True, encoding="utf-8")
        if (done.returncode, done.stdout) != (want_exit, want_out):
            failures.append(f"secret_mask --check {text!r}: exit {done.returncode} {done.stdout!r}")
    total += 1
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "secret_mask.py")], input="k: " + fake["github_token"][0] + "\n",
                          capture_output=True, encoding="utf-8")
    if (done.returncode, done.stdout) != (0, "k: [MASKED:github_token]\n"):
        failures.append(f"secret_mask stdin: exit {done.returncode} {done.stdout!r}")
    # determinism: the same input twice gives the same bytes; the rules in reverse order give the same result
    reverse = tmp / "rules_reversed.json"
    reverse.write_text(json.dumps({**rules, "rules": rules["rules"][::-1]}), encoding="utf-8")
    for call, profile in ((bash("git push --force"), "worker"), (bash("rm x && gh pr create"), "director"),
                          (bash("gh pr create && rm x"), "director"), (tool("mcp__shop__buy_and_send"), "director"),
                          (write(rules_path), "director")):
        runs = [hook(call, profile), hook(call, profile), hook(call, profile, reverse)]
        total += 1
        if len({(d.returncode, d.stdout, d.stderr) for d in runs}) != 1:
            failures.append(f"hook_guard rules not deterministic for {call} [{profile}]: "
                            f"{[(d.returncode, d.stdout + d.stderr) for d in runs]}")
    check("two ask rules: the lowest id wins", bash("gh pr create && rm x"), "director", "ask:G10")
    check("deny beats ask whatever the order", tool("mcp__shop__buy_and_send"), "director", "deny:G30")
    # a broken rules file stops the hook with exit 1, which "onFailure": "block" turns into a block
    broken = {"not json": "{", "no rules": json.dumps({"schema_version": 1, "rules": []}),
              "bad decision": json.dumps({**rules, "rules": [{**rules["rules"][0], "decision": {"worker": "maybe", "director": "deny"}}]}),
              "angle brackets": json.dumps({**rules, "rules": [{**rules["rules"][0], "reason": "ask <someone>"}]}),
              "duplicate id": json.dumps({**rules, "rules": [rules["rules"][0], rules["rules"][0]]}),
              "reserved id": json.dumps({**rules, "rules": [{**rules["rules"][0], "id": "G00"}]}),
              "bad regex": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "shell", "cmd": ["git"], "flags": ["("]}}]}),
              "unknown kind": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "url", "cmd": ["x"]}}]}),
              "bad cmd regex": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "shell", "cmd": ["git("]}}]}),
              "bare not a bool": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "shell", "cmd": ["env"], "bare": "yes"}}]}),
              "shell_write not a bool": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "path", "tools": ["Write"], "globs": ["**/x"], "shell_write": 1}}]}),
              "path_args not globs": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "shell", "cmd": ["cat"], "path_args": ".env"}}]}),
              "bad arg_search": json.dumps({**rules, "rules": [{**rules["rules"][0], "match": {"kind": "shell", "cmd": ["echo"], "arg_search": ["[$"]}}]})}
    for name, text in broken.items():
        bad = tmp / f"rules_{name.replace(' ', '_')}.json"
        bad.write_text(text, encoding="utf-8")
        check(f"bad rules file: {name}", bash("git status"), "worker", "bad", rules_file=bad)
    check("bad rules file: missing", bash("git status"), "worker", "bad", rules_file=tmp / "no_such_rules.json")

    # setup --guard-profile: report, apply, rerun, permissions, switching profile, the Director's worktree
    repo = tmp / "guarded"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"permissions": {"deny": ["Read(./private/**)"], "allow": ["Bash(git status)"]}}), encoding="utf-8")
    setup = ("--repo", repo, "--only-this", "--guard-mode", "block")
    expect("guard profile missing", "setup_project_settings.py", 1, *setup, "--guard-profile", "worker",
           says=["MISSING", "hooks.PreToolUse", "permissions.deny"])
    expect("guard profile written and tested", "setup_project_settings.py", 0, *setup, "--guard-profile", "worker", "--apply",
           says=["SET", "guard_profile=worker", "(hook test: allow=0 block=2 block-rule=2)"])
    expect("guard profile kept on rerun", "setup_project_settings.py", 0, *setup, "--guard-profile", "worker", says="OK")
    expect("plain --hooks keeps the installed profile", "setup_project_settings.py", 0, *setup, "--hooks", says=["OK", "block-rule=2"])
    data = json.loads(settings.read_text(encoding="utf-8"))
    entry = data["hooks"]["PreToolUse"]
    wanted_deny = [p for r in rules["rules"] if r["decision"]["worker"] == "deny" for p in r.get("permissions", [])]
    total += 1
    if (len(entry) != 1 or entry[0]["matcher"] != "*" or entry[0]["hooks"][0].get("onFailure") != "block"
            or "--profile worker" not in entry[0]["hooks"][0]["command"] or "--rules" not in entry[0]["hooks"][0]["command"]):
        failures.append(f"setup --guard-profile worker: PreToolUse is {entry}")
    total += 1
    if (data["permissions"]["deny"][0] != "Read(./private/**)" or data["permissions"]["allow"] != ["Bash(git status)"]
            or any(p not in data["permissions"]["deny"] for p in wanted_deny) or data["permissions"].get("ask")):
        failures.append(f"setup --guard-profile worker: permissions are {data['permissions']}")
    expect("another profile is not OK", "setup_project_settings.py", 1, *setup, "--guard-profile", "director",
           says=["hooks.PreToolUse matcher", "permissions.deny", "permissions.ask"])
    expect("switching to director", "setup_project_settings.py", 0, *setup, "--guard-profile", "director", "--apply", says="SET")
    data = json.loads(settings.read_text(encoding="utf-8"))
    total += 1
    if ("Bash(rm *)" in data["permissions"]["deny"] or "Bash(rm *)" not in data["permissions"]["ask"]
            or "Bash(git push *)" not in data["permissions"]["deny"] or "Read(./private/**)" not in data["permissions"]["deny"]
            or len(data["hooks"]["PreToolUse"]) != 1 or "--profile director" not in data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]):
        failures.append(f"setup --guard-profile director after worker: {data['permissions']} {data['hooks']}")
    expect("the Director's worktree keeps the director profile", "setup_project_settings.py", 0, *setup, "--guard-profile",
           "worker", "--director-worktree", repo, says="OK")
    director = tmp / "guarded_DIRECTOR"
    (director / "orders").mkdir(parents=True)
    expect("guard profile with --protect-director", "setup_project_settings.py", 0, *setup, "--guard-profile", "worker",
           "--protect-director", director, "--apply", says=["SET", "block-write=2", "block-rule=2"])
    command = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    total += 1
    if "--protect" not in command or "--profile worker" not in command:
        failures.append(f"setup --guard-profile --protect-director: command is {command!r}")
    expect("an unknown profile is refused", "setup_project_settings.py", 2, *setup, "--guard-profile", "admin")


def test_session_profiles(tmp):
    """1.3.0 item 8: hook_guard --sessions picks director / worker / cleaner per session_id from one sessions file;
    cleaner may delete, nobody may delete or move the protected list; setup_project_settings --session-map."""
    global total
    rules_path = TOOLS / "guard_rules.json"
    keep = (tmp / "sess_keep").resolve()
    (keep / "sub").mkdir(parents=True)
    pause = tmp / "sess_PAUSE"
    smap = tmp / "sessions.json"
    smap.write_text(json.dumps({"schema_version": 1, "default": "worker",
                                "sessions": {"S-DIR": "director", "S-CLEAN": {"profile": "cleaner", "name": "cleaner"},
                                             "S-WORK": "worker"},
                                "protected": [keep.as_posix() + "/**", "**/RESUME_STATE*.md"]}), encoding="utf-8")

    def hook(sid, tool, command, sessions=smap, extra=()):
        call = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(tmp)}
        if sid:
            call["session_id"] = sid
        argv = [sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--rules", str(rules_path), "--profile",
                "worker", *extra] + (["--sessions", str(sessions)] if sessions else [])
        return subprocess.run(argv, capture_output=True, encoding="utf-8", input=json.dumps(call))

    def case(name, sid, command, code, says="", tool="Bash", **kw):
        global total
        total += 1
        done = hook(sid, tool, command, **kw)
        out = done.stdout + done.stderr
        if done.returncode != code or (says and says not in out):
            failures.append(f"sessions {name}: expected exit {code} with {says!r}, got {done.returncode}: {out.strip()[:200]!r}")

    k = keep.as_posix()
    up = keep.parent.as_posix()
    case("cleaner deletes a build folder", "S-CLEAN", "rm -rf build", 0)
    case("a listed worker may not", "S-WORK", "rm -rf build", 2, "[G10]")
    case("an unlisted session gets the default", "S-OTHER", "rm -rf build", 2, "[G10]")
    case("no session_id gets the default", "", "rm -rf build", 2, "[G10]")
    case("the director is asked", "S-DIR", "rm -rf build", 0, '"ask"')
    case("cleaner: a protected file", "S-CLEAN", f"rm -f {k}/sub/a.txt", 2, "protected list")
    case("cleaner: the protected folder", "S-CLEAN", f"rm -rf {k}", 2, "holds protected paths")
    case("cleaner: a folder above it", "S-CLEAN", f"rm -rf {up}", 2, "holds protected paths")
    case("cleaner: a wildcard over it", "S-CLEAN", f"rm -rf {up}/*", 2, "holds protected paths")
    case("cleaner: the drive root", "S-CLEAN", "rm -rf " + keep.anchor.replace("\\", "/"), 2, "holds protected paths")
    case("cleaner: a **/ file", "S-CLEAN", "rm RESUME_STATE.md", 2, "protected list")
    case("cleaner: moving it away", "S-CLEAN", f"mv {k}/sub ../elsewhere", 2, "protected")
    case("cleaner: PowerShell Remove-Item", "S-CLEAN", f"Remove-Item -Recurse -Force {k}", 2, "holds protected paths",
         tool="PowerShell")
    case("cleaner: a file next to it", "S-CLEAN", f"rm -f {up}/other.txt", 0)
    case("the director: protected too", "S-DIR", f"rm -f {k}/sub/a.txt", 2, "protected list")
    case("cleaner: push is still blocked", "S-CLEAN", "git push origin main", 2)
    case("cleaner: worktree remove is still blocked", "S-CLEAN", "git worktree remove ../wt", 2)
    case("cleaner: a read is silent", "S-CLEAN", "ls -la", 0)
    case("without --sessions the cleaner rule is not there", "S-CLEAN", "rm -rf build", 2, "[G10]", sessions=None)
    pause.write_text("PAUSED by director at 2026-11-07 10:00 +08:00: test\n", encoding="utf-8")
    case("pause holds a worker", "S-WORK", "touch a.txt", 2, "PAUSED", extra=("--pause-flag", str(pause)))
    case("pause holds the cleaner", "S-CLEAN", "touch a.txt", 2, "PAUSED", extra=("--pause-flag", str(pause)))
    case("pause never holds the director", "S-DIR", "touch a.txt", 0, extra=("--pause-flag", str(pause)))
    pause.unlink()
    log = tmp / "sess_audit.jsonl"
    case("audit says protected", "S-CLEAN", f"rm -rf {k}", 2, extra=("--audit", str(log)))
    total += 1
    logged = log.read_text(encoding="utf-8") if log.exists() else ""
    if "protected" not in logged:
        failures.append(f"sessions audit: no protected label in {logged!r}")
    bad = tmp / "sessions_bad.json"
    for name, text in [("not json", "{"), ("wrong version", '{"schema_version": 2}'),
                       ("unknown key", '{"schema_version": 1, "extra": 1}'),
                       ("unknown profile", '{"schema_version": 1, "sessions": {"S": "admin"}}'),
                       ("bad default", '{"schema_version": 1, "default": "root"}'),
                       ("relative protected", '{"schema_version": 1, "protected": ["DIRECTOR/**"]}')]:
        bad.write_text(text, encoding="utf-8")
        case(f"bad sessions file: {name}", "S-CLEAN", "ls", 1, "bad sessions file", sessions=bad)
    total += 1
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--sessions", str(smap)],
                          capture_output=True, encoding="utf-8",
                          input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
    if done.returncode != 1 or "--sessions needs --rules" not in done.stderr:
        failures.append(f"sessions without --rules: {done.returncode} {done.stderr!r}")
    total += 1
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", "import importlib.util, sys; "
                           "s = importlib.util.spec_from_file_location('g', sys.argv[1]); g = importlib.util.module_from_spec(s); "
                           "s.loader.exec_module(g); g.load_sessions(sys.argv[2])",
                           str(TOOLS / "hook_guard.py"), str(TOOLS.parent / "templates" / "guard_sessions.json")],
                          capture_output=True, encoding="utf-8")
    if done.returncode != 0:
        failures.append(f"templates/guard_sessions.json does not load: {done.stderr.strip()[-200:]!r}")

    # setup --session-map: one settings file for every session of a folder
    repo = tmp / "sess_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    settings = repo / ".claude" / "settings.local.json"
    setup = ("--repo", repo, "--only-this", "--guard-mode", "block")
    expect("session map missing", "setup_project_settings.py", 1, *setup, "--session-map", smap,
           says=["MISSING", "hooks.PreToolUse", "session_map="])
    expect("session map written and tested", "setup_project_settings.py", 0, *setup, "--session-map", smap, "--apply",
           says=["SET", "(cleaner,director,worker)", "block-rule=2"])
    expect("session map kept on rerun", "setup_project_settings.py", 0, *setup, "--session-map", smap, says="OK")
    data = json.loads(settings.read_text(encoding="utf-8"))
    command = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    total += 1
    if f'--sessions "{smap.resolve().as_posix()}"' not in command or "--profile worker" not in command:
        failures.append(f"setup --session-map: command is {command!r}")
    total += 1
    perms = data.get("permissions", {})
    if ("Bash(rm *)" in perms.get("deny", []) + perms.get("ask", []) or "Bash(git push *)" not in perms.get("deny", [])
            or "Bash(gh pr create *)" not in perms.get("ask", []) or "Bash(gh pr create *)" in perms.get("deny", [])):
        failures.append(f"setup --session-map: permissions are not the mildest of the mapped profiles: {perms}")
    expect("without the map the entry is not OK", "setup_project_settings.py", 1, *setup, "--guard-profile", "worker",
           says="hooks.PreToolUse matcher")
    other = tmp / "sessions_other.json"
    other.write_text(smap.read_text(encoding="utf-8"), encoding="utf-8")
    expect("another map file is not OK", "setup_project_settings.py", 1, *setup, "--session-map", other,
           says="hooks.PreToolUse matcher")
    bad.write_text('{"schema_version": 1, "sessions": {"S": "admin"}}', encoding="utf-8")
    expect("a bad map is refused", "setup_project_settings.py", 1, *setup, "--session-map", bad, lacks="MISSING")
    expect("cleaner is a guard profile", "setup_project_settings.py", 1, *setup, "--guard-profile", "cleaner",
           says="MISSING")


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
    expect("verify same", *common, 0, "verify", record, says="EVIDENCE_VERIFY: OK integrity=same test=not-rerun artifacts=1 missing=0 rerun=no")
    expect("verify with the recorded command", *common, 0, "verify", record, "--rerun-recorded",
           says="EVIDENCE_VERIFY: OK integrity=same test=recorded-command-passed artifacts=1 missing=0 rerun=yes source=record",
           lacks="test=passed")
    art.write_text("changed", encoding="utf-8")
    expect("verify sees a changed artifact", *common, 1, "verify", record, says=["artifact changed: ", "MISMATCH integrity=changed"])
    expect("rerun rebuilds it", *common, 0, "verify", record, "--rerun-recorded", says="OK")
    art.unlink()
    expect("verify sees a gone artifact", *common, 1, "verify", record, says=["artifact gone: ", "MISMATCH integrity=same test=not-rerun artifacts=1 missing=1"])
    expect("rerun rebuilds a gone artifact", *common, 0, "verify", record, "--rerun-recorded", says="OK")
    shell = out / "shell.json"
    shell.write_text('{"exit_code": 0}', encoding="utf-8")
    expect("verify refuses a record without the fields", *common, 2, "verify", shell, says=["- missing field command", "- missing field artifacts", "NOT_RUN not an evidence record (2 problems)"])
    legacy = json.loads(record.read_text(encoding="utf-8"))
    for key in ("schema", "cwd", "started", "finished"):
        legacy.pop(key)
    (out / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    expect("verify reads a legacy record with a note", *common, 0, "verify", out / "legacy.json", says=["~ legacy record without `schema`", "OK"])
    # v0.13 (A08): a field of the wrong type is a clean NOT_RUN, never a traceback
    whole = json.loads(record.read_text(encoding="utf-8"))
    for name, change, problem in (("artifacts_int", {"artifacts": 42}, "- field artifacts is not list"),
                                  ("command_int_part", {"command": [1]}, "- command: every part must be a string"),
                                  ("legacy_git_str", {"git": "abc", "schema": None}, "- field git is not dict")):
        broken = {**whole, **change}
        broken = {key: value for key, value in broken.items() if not (key == "schema" and value is None)}
        (out / f"{name}.json").write_text(json.dumps(broken), encoding="utf-8")
        expect(f"verify refuses {name} cleanly", *common, 2, "verify", out / f"{name}.json",
               says=[problem, "EVIDENCE_VERIFY: NOT_RUN not an evidence record"])

    expect("exit code passes through", *common, 7, "run", "--out-dir", out, "--label", "AC-2", "--", py, "-c", "raise SystemExit(7)")
    expect("missing artifact fails", *common, 3, "run", "--out-dir", out, "--label", "AC-3", "--artifact", tmp / "nope", "--", py, "-c", "0", says="missing=1")
    expect("verify never passes a record whose artifact was missing", *common, 1, "verify", next(out.glob("*-AC-3.json")),
           says=["artifact missing when recorded: ", "MISMATCH integrity=same test=not-rerun artifacts=1 missing=1"])
    expect("verify never passes a record whose artifact was missing, even rerun", *common, 1, "verify", next(out.glob("*-AC-3.json")),
           "--rerun-recorded", says=["artifact missing when recorded: ",
                                     "MISMATCH integrity=same test=recorded-command-passed artifacts=1 missing=1 rerun=yes"])
    expect("verify reports a failing command as test=failed", *common, 1, "verify", next(out.glob("*-AC-2.json")),
           says="MISMATCH integrity=same test=failed(recorded exit 7) artifacts=0 missing=0")
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


def with_checks(order, *lines):
    """The order with a `CHECKS:` list of lines placed after its acceptance table."""
    return order.replace("\n- DELIVERABLES", "\nCHECKS:\n" + "".join(f"- {line}\n" for line in lines) + "\n- DELIVERABLES", 1)


def test_order_checks(tmp):
    """v0.13 (A06 A07): the order's CHECKS list. --order checks its form; --match --evidence-dir compares each record's
    command with the approved one (Strict fails, Standard notes); orders without CHECKS give the same result as before."""
    global total
    order = TYPED_ORDER.format(base="abc123")
    good = '"python", "-c", "0"'
    gate(tmp, "checks_good", "order", with_checks(order, f"AC-1: [{good}]"), 0)
    for name, line, says in (("checks_not_json", "AC-1: python -c 0", "CHECKS: `AC-1: python -c 0` is not `AC-n:"),
                             ("checks_empty_array", "AC-1: []", "CHECKS: `AC-1: []` is not"),
                             ("checks_review_ac", f"AC-2: [{good}]", "CHECKS: AC-2 is REVIEW; only an AUTO criterion"),
                             ("checks_unknown_ac", f"AC-9: [{good}]", "CHECKS: AC-9 is not an acceptance criterion")):
        gate(tmp, name, "order", with_checks(order, line), 1, says=says)
    strict = order.replace("GOVERNANCE     = Standard", "GOVERNANCE     = Strict")
    gate(tmp, "checks_strict_missing_noted", "order", strict, 0, says="~ CHECKS: Strict order without an approved check for AUTO AC-1")
    head = "0123456789abcdef0123456789abcdef01234567"
    for governance, text in (("Strict", strict), ("Standard", order)):
        for name, command, code in (("same", ["python", "-c", "0"], 0), ("other", ["python", "-c", "1"], None)):
            folder = tmp / "order_checks" / governance / name
            folder.mkdir(parents=True)
            body = with_checks(text, f"AC-1: [{good}]")
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            (folder / "WO-001-parser.md").write_text(body, encoding="utf-8")
            (folder / "log.md").write_text(f"DISPATCH WO-001 rev=1 sha={digest}\n", encoding="utf-8")
            evidence_file(folder, "e.json", head, command=command)
            (folder / "report.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest).replace(
                "/ c / d0d0d0d / yes", f"/ c / {head} / yes", 1), encoding="utf-8")
            want = "AC-1: e.json: its command is not the order's approved check (CHECKS AC-1)"
            if code is None:
                code, says = (1, f"- {want}; Strict") if governance == "Strict" else (0, f"~ {want}")
            else:
                says = None
            expect(f"match CHECKS {governance} {name}", "gate_check.py", code, "--match", folder / "report.md",
                   folder / "WO-001-parser.md", "--evidence-dir", folder, "--dispatch-log", folder / "log.md",
                   "--candidate", head, says=says, lacks=None if says else "approved check")


def test_preflight(tmp):
    """v0.13 batch 3 (M01 M02 M03): --preflight lists what an older Strict review lacks, one LACKS line each, and
    resolves a short HEAD in --repo. Once each item is supplied it lists nothing and the Strict --match passes."""
    global total
    repo = tmp / "preflight" / "repo"
    repo.mkdir(parents=True)

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo,
                              check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    (repo / "a.txt").write_text("a", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    head = git("rev-parse", "HEAD")
    strict = TYPED_ORDER.format(base="abc123").replace("GOVERNANCE     = Standard", "GOVERNANCE     = Strict")
    old = tmp / "preflight" / "old"
    old.mkdir()
    order = old / "WO-001-parser.md"
    order.write_text(strict, encoding="utf-8")
    digest = hashlib.sha256(strict.encode("utf-8")).hexdigest()
    (old / "log.md").write_text("# DIRECTOR_LOG\n", encoding="utf-8")
    evidence_file(old, "e.json", head[:9], drop=("schema",))
    (old / "report.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest).replace(
        "/ c / d0d0d0d / yes", f"/ c / {head[:9]} / yes", 1).replace(" REVISION 1", "", 1), encoding="utf-8")
    flags = ("--evidence-dir", old, "--dispatch-log", old / "log.md")
    expect("preflight lists what an old Strict review lacks (M01-M03)", "gate_check.py", 1, "--preflight", old / "report.md",
           order, *flags, "--repo", repo,
           says=["(GOVERNANCE Strict): 5 item(s) to migrate; only read",
                 f"LACKS HEAD: the report names {head[:9]}; in {repo} that is {head}",
                 "LACKS ORDER: the report names no revision; write `ORDER: WO-001-parser.md REVISION 1`",
                 "LACKS DISPATCH: ", "LACKS CHECKS: no approved check for AUTO AC-1",
                 "LACKS EVIDENCE e.json: no `schema` (legacy record); git.head is " + head[:9] + ", not 40 hex digits"])
    expect("preflight without --repo, --evidence-dir or --dispatch-log", "gate_check.py", 1, "--preflight", old / "report.md",
           order, says=["resolve it with `git rev-parse <short>` in a trusted checkout (--repo)",
                        "NOT_CHECKED DISPATCH: no --dispatch-log", "NOT_CHECKED EVIDENCE: no --evidence-dir (1 record(s)"])
    expect("--repo needs --preflight", "gate_check.py", 2, "--report", old / "report.md", "--repo", repo)

    new = tmp / "preflight" / "new"
    new.mkdir()
    body = with_checks(strict, 'AC-1: ["python", "-c", "0"]').replace("REVISION       = 1", "REVISION       = 2")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    (new / "WO-001-parser.md").write_text(body, encoding="utf-8")
    (new / "log.md").write_text(f"# DIRECTOR_LOG\nDISPATCH WO-001 rev=2 sha={digest}\n", encoding="utf-8")
    evidence_file(new, "e.json", head)
    flags = ("--evidence-dir", new, "--dispatch-log", new / "log.md")
    (new / "report.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest).replace(
        "/ c / d0d0d0d / yes", f"/ c / {head} / yes", 1).replace("REVISION 1", "REVISION 2", 1), encoding="utf-8")
    expect("preflight lists a REVISION 2 record without an order binding (G03b)", "gate_check.py", 1, "--preflight",
           new / "report.md", new / "WO-001-parser.md", *flags,
           says="LACKS EVIDENCE e.json: no `order` binding and the order is at REVISION 2 (run --order)")
    evidence_file(new, "e.json", head, order={"id": "WO-001", "rev": 2, "sha": digest})
    (new / "report.md").write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest).replace(
        "/ c / d0d0d0d / yes", f"/ c / {head} / yes", 1).replace("REVISION 1", "REVISION 2", 1), encoding="utf-8")
    flags = ("--evidence-dir", new, "--dispatch-log", new / "log.md")
    expect("preflight after the migration lists nothing", "gate_check.py", 0, "--preflight", new / "report.md",
           new / "WO-001-parser.md", *flags, says="(GOVERNANCE Strict): nothing lacking; only read", lacks=["LACKS", "NOT_CHECKED"])
    expect("the migrated review passes the Strict --match", "gate_check.py", 0, "--match", new / "report.md",
           new / "WO-001-parser.md", *flags, "--candidate", head)


def test_order_binding(tmp):
    """v0.13 batch 4 (G03b): a record names the order it answers (`evidence_record.py run --order`): ID, REVISION and the
    hash `--hash` prints for the DISPATCH line. --match --evidence-dir accepts a bound record for this order at this
    revision and hash, or one an EVIDENCE_EQUIVALENT whole line in the log carries over; the line is read like DISPATCH,
    so a quoted, fenced, indented or NOTE copy does not count. An unbound record: REVISION 1 is a WARN; from REVISION 2
    Strict fails and Standard notes it."""
    global total
    head = "0123456789abcdef0123456789abcdef01234567"

    def text_of(governance, rev):
        return (TYPED_ORDER.format(base="abc123").replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
                .replace("REVISION       = 1", f"REVISION       = {rev}"))

    def digest_of(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    if text_of("Strict", 2) == text_of("Strict", 1):
        failures.append("test_order_binding: TYPED_ORDER has no `REVISION       = 1` line; update text_of()")

    def case(name, code, says=None, lacks=None, governance="Strict", rev=2, order="unbound", log_extra=""):
        """order: "unbound", "current" (this order now), "old" (REVISION 1 of the same order) or a dict to write."""
        folder = tmp / "binding" / governance / name
        folder.mkdir(parents=True)
        text = text_of(governance, rev)
        digest, old = digest_of(text), digest_of(text_of(governance, 1))
        path = folder / "WO-001-parser.md"
        path.write_bytes(text.encode("utf-8"))
        field = {"unbound": None, "current": {"id": "WO-001", "rev": rev, "sha": digest},
                 "old": {"id": "WO-001", "rev": 1, "sha": old}}.get(order, order) if isinstance(order, str) else order
        evidence_file(folder, "e.json", head, **({} if field is None else {"order": field}))
        (folder / "log.md").write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev={rev} sha={digest}\n"
                                       + log_extra.format(old=old), encoding="utf-8")
        report = folder / "report.md"
        report.write_text(match_report(list(ACCEPTANCE.values()), "PARTIAL", digest).replace(
            "/ c / d0d0d0d / yes", f"/ c / {head} / yes", 1).replace("REVISION 1", f"REVISION {rev}", 1), encoding="utf-8")
        expect(f"binding {governance} {name}", "gate_check.py", code, "--match", report, path, "--evidence-dir", folder,
               "--dispatch-log", folder / "log.md", "--candidate", head, says=says, lacks=lacks)

    equivalent = "EVIDENCE_EQUIVALENT WO-001 rev=1 sha={old} to rev=2"
    case("unbound_rev2", 1, "- AC-1: e.json: not bound to an order revision and the order is at REVISION 2, so it may "
         "answer an earlier one; Strict: record again with `evidence_record.py run --order")
    case("bound_current", 0, "OK   match", ["  - ", "WARN"], order="current")
    case("bound_old_revision", 1, ["- AC-1: e.json: recorded for WO-001 REVISION 1 (sha ", "the order is REVISION 2",
                                   "EVIDENCE_EQUIVALENT WO-001 rev=1 sha="], order="old")
    case("equivalent_dated_line", 0, "OK   match", "  - ", order="old",
         log_extra="2026-01-03 09:00 +08:00 | " + equivalent + " | AC-1 unchanged by rev 2\n")
    case("equivalent_bare_line", 0, "OK   match", "  - ", order="old", log_extra=equivalent + "\n")
    for name, extra in (("equivalent_quoted", "> " + equivalent + "\n"),
                        ("equivalent_in_code_fence", "```text\n" + equivalent + "\n```\n"),
                        ("equivalent_in_tilde_fence", "~~~\n" + equivalent + "\n~~~\n"),
                        ("equivalent_indented", "    " + equivalent + "\n"),
                        ("equivalent_in_note", "NOTE: " + equivalent + "\n"),
                        ("equivalent_mid_sentence", "the Director may write " + equivalent + " later\n"),
                        ("equivalent_other_target", equivalent.replace("to rev=2", "to rev=3") + "\n"),
                        ("equivalent_other_sha", "EVIDENCE_EQUIVALENT WO-001 rev=1 sha=" + "e" * 64 + " to rev=2\n"),
                        ("equivalent_other_order", equivalent.replace("WO-001", "WO-002") + "\n")):
        case(name, 1, "recorded for WO-001 REVISION 1 (sha ", order="old", log_extra=extra)
    case("bound_other_order", 1, "- AC-1: e.json: recorded for order WO-002, this order is WO-001",
         order={"id": "WO-002", "rev": 2, "sha": "a" * 64})
    case("unbound_rev1_warns", 0, ["OK   match", "~ AC-1: e.json: WARN evidence not bound to the order (recorded without "
                                   "--order); from the next MAJOR version `evidence_record.py run --order` is required"],
         "  - ", rev=1)
    case("unbound_rev2", 0, ["OK   match", "~ AC-1: e.json: not bound to an order revision and the order is at REVISION 2"],
         "Strict:", governance="Standard")
    case("bound_old_revision", 0, ["OK   match", "~ AC-1: e.json: recorded for WO-001 REVISION 1 (sha "],
         governance="Standard", order="old")
    case("malformed_order_field", 1, "order: needs id (text), rev (a whole number from 1) and sha (64 lower-case hex digits)",
         governance="Standard", order={"id": "WO-001", "rev": "2", "sha": "not-a-hash"})

    # run --order writes the same hash --hash prints for the DISPATCH line, also for a CRLF order (condition 4)
    base = tmp / "binding" / "run"
    work = base / "work"
    work.mkdir(parents=True)
    crlf = text_of("Strict", 2).replace("\n", "\r\n").encode("utf-8")
    order = base / "WO-001-parser.md"
    order.write_bytes(crlf)
    expect("run --order names the order in the EVIDENCE line", "evidence_record.py", 0, "run", "--out-dir", base / "out",
           "--label", "AC-1", "--order", order, "--cwd", work, "--", sys.executable, "-c", "print('ok')",
           says="order=WO-001@rev2 file=")
    total += 1
    records = list((base / "out").glob("*.json"))
    written = json.loads(records[0].read_text(encoding="utf-8")).get("order") if records else None
    _, hashed = run("gate_check.py", "--hash", order)
    logged = re.search(r"DISPATCH WO-001 rev=2 sha=([0-9a-f]{64})", hashed)
    if not (written and logged and written.get("id") == "WO-001" and written.get("rev") == 2
            and written.get("sha") == logged.group(1) == digest_of(text_of("Strict", 2))):
        failures.append(f"run --order: the record's order {written} is not the DISPATCH hash {logged and logged.group(1)}")
    expect("verify reads a record bound to an order", "evidence_record.py", 0, "verify", records[0] if records else base / "none")
    mixed = base / "WO-002-other.md"
    mixed.write_bytes(crlf)
    expect("run --order refuses an order whose title and file name differ", "evidence_record.py", 2, "run", "--out-dir",
           base / "out2", "--label", "AC-1", "--order", mixed, "--cwd", work, "--", sys.executable, "-c", "print('ok')",
           says="EVIDENCE: NOT_RUN order: the title names WO-001, the file name WO-002-other.md names WO-002")
    expect("run --order needs a readable order", "evidence_record.py", 2, "run", "--out-dir", base / "out3", "--label", "AC-1",
           "--order", base / "gone.md", "--cwd", work, "--", sys.executable, "-c", "print('ok')",
           says="EVIDENCE: NOT_RUN cannot read --order")
    total += 1
    if (base / "out2").exists() or (base / "out3").exists():
        failures.append("run --order: a refused run still wrote a record")


def test_trusted_rerun(tmp):
    """v0.13 (A06 A07): `verify --rerun` runs the order's approved check at the candidate commit, in a clean checkout,
    and only after the order matches its DISPATCH line. The record's command is compared, never run."""
    global total
    root = tmp / "trusted"
    repo, out = root / "repo", root / "records"
    repo.mkdir(parents=True)
    py = sys.executable

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    (repo / "check.py").write_text("print('checked')\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    first = git("rev-parse", "HEAD")
    order = root / "WO-001-parser.md"
    body = with_checks(TYPED_ORDER.format(base=first), f"AC-1: {json.dumps([py, 'check.py'])}")
    order.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    log = root / "log.md"
    log.write_text(f"DISPATCH WO-001 rev=1 sha={digest}\n", encoding="utf-8")
    expect("trusted: record the approved check", "evidence_record.py", 0, "run", "--out-dir", out, "--label", "AC-1",
           "--cwd", repo, "--", py, "check.py", says="exit=0")
    record = next(out.glob("*-AC-1.json"))
    data = json.loads(record.read_text(encoding="utf-8"))

    def variant(name, **change):
        path = root / f"{name}.json"
        path.write_text(json.dumps({**data, **change}), encoding="utf-8")
        return path

    def verify(name, code, path, says=None, lacks=None, candidate=None, dispatch=log, **flags):
        args = ["--order", order, "--dispatch-log", dispatch, "--repo", repo, "--candidate", candidate or first]
        expect(f"trusted: {name}", "evidence_record.py", code, "verify", path, "--rerun", *args, says=says, lacks=lacks)

    verify("approved check at the candidate", 0, record,
           says=f"EVIDENCE_VERIFY: OK integrity=same test=passed artifacts=0 missing=0 rerun=yes check=AC-1 source=order candidate={first[:12]}")
    expect("trusted: --rerun alone is refused", "evidence_record.py", 2, "verify", record, "--rerun",
           says="NOT_RUN --rerun runs the order's approved check and needs --order --dispatch-log --repo --candidate")
    expect("trusted: --rerun-recorded never says passed", "evidence_record.py", 0, "verify", record, "--rerun-recorded",
           says="test=recorded-command-passed", lacks="test=passed")
    expect("trusted: --order needs --rerun", "evidence_record.py", 2, "verify", record, "--order", order)
    expect("trusted: --candidate needs 40 hex digits", "evidence_record.py", 2, "verify", record, "--rerun", "--order", order,
           "--dispatch-log", log, "--repo", repo, "--candidate", first[:7])
    marker = root / "tampered.txt"
    tampered = variant("tampered", command=[py, "-c", f"open({str(marker)!r}, 'w').write('ran')"])
    verify("a tampered command is compared, not run", 1, tampered,
           says=["- record command differs from the approved check", "MISMATCH", "test=passed"])
    total += 1
    if marker.exists():
        failures.append("trusted: the tampered command in the record ran")
    verify("a label without an approved check", 2, variant("other_label", label="AC-2"),
           says="NOT_RUN the record's label 'AC-2' names no AC with an approved check")
    for name, line, says in (("another hash", f"DISPATCH WO-001 rev=1 sha={'0' * 64}", "is not the one logged at dispatch"),
                             ("another revision", f"DISPATCH WO-001 rev=2 sha={digest}", "logs rev=2, the order is at REVISION 1"),
                             ("no line", "nothing here", "NOT_RUN no DISPATCH line for WO-001 / WO-001-parser"),
                             # R01b: a quoted DISPATCH with the new hash is data, not a newer dispatch
                             ("quoted line", f"DISPATCH WO-001 rev=1 sha={'0' * 64}\n2026-01-03 10:00 +08:00 | NOTE: rejected "
                              f"proposal `DISPATCH WO-001 rev=1 sha={digest}`", "is not the one logged at dispatch"),
                             ("fenced line", f"DISPATCH WO-001 rev=1 sha={'0' * 64}\n```\nDISPATCH WO-001 rev=1 sha={digest}\n```",
                              "is not the one logged at dispatch")):
        other_log = root / f"log_{name.replace(' ', '_')}.md"
        other_log.write_text(line + "\n", encoding="utf-8")
        verify(f"DISPATCH {name}", 2, record, says=says, dispatch=other_log)
    (repo / "stray.txt").write_text("x\n", encoding="utf-8")
    verify("an untracked file refuses", 2, record, says="has changed or untracked files")
    (repo / "stray.txt").unlink()
    (repo / "notes.md").write_text("b\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "b")
    second = git("rev-parse", "HEAD")
    verify("the repo is not at the candidate", 2, record, says=f"is at {second[:12]}, not the candidate {first[:12]}")
    verify("a record from another commit", 1, record, candidate=second,
           says=[f"- recorded at HEAD {first[:12]}, the candidate is {second[:12]}", "MISMATCH"])


def test_rerun_binding(tmp):
    """v0.13 batch 5 (G03b): `verify --rerun` judges the record's `order` binding by gate_check's rules
    (check_binding): Strict fails a record bound to another order, or to another REVISION or hash without an
    EVIDENCE_EQUIVALENT whole line, and an unbound record from REVISION 2; Standard notes them; REVISION 1 unbound
    is a WARN."""
    root = tmp / "rerun_binding"
    repo, out = root / "repo", root / "records"
    repo.mkdir(parents=True)
    py = sys.executable

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    (repo / "check.py").write_text("print('checked')\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    head = git("rev-parse", "HEAD")
    expect("rerun binding: record the approved check", "evidence_record.py", 0, "run", "--out-dir", out, "--label", "AC-1",
           "--cwd", repo, "--", py, "check.py", says="exit=0")
    data = json.loads(next(out.glob("*-AC-1.json")).read_text(encoding="utf-8"))
    data.pop("order", None)

    def text_of(governance, rev):
        return (with_checks(TYPED_ORDER.format(base=head), f"AC-1: {json.dumps([py, 'check.py'])}")
                .replace("GOVERNANCE     = Standard", f"GOVERNANCE     = {governance}")
                .replace("REVISION       = 1", f"REVISION       = {rev}"))

    def digest_of(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def case(name, code, says=None, lacks=None, governance="Strict", rev=2, order="unbound", log_extra=""):
        """order: "unbound", "current" (this order now), "old" (REVISION 1 of the same order) or a dict to write."""
        folder = root / governance / name
        folder.mkdir(parents=True)
        text = text_of(governance, rev)
        digest, old = digest_of(text), digest_of(text_of(governance, 1))
        path = folder / "WO-001-parser.md"
        path.write_bytes(text.encode("utf-8"))
        field = {"unbound": None, "current": {"id": "WO-001", "rev": rev, "sha": digest},
                 "old": {"id": "WO-001", "rev": 1, "sha": old}}.get(order) if isinstance(order, str) else order
        record = folder / "e.json"
        record.write_text(json.dumps({**data, **({} if field is None else {"order": field})}), encoding="utf-8")
        log = folder / "log.md"
        log.write_text(f"# DIRECTOR_LOG\n2026-01-02 10:00 +08:00 | DISPATCH WO-001 rev={rev} sha={digest}\n"
                       + log_extra.format(old=old), encoding="utf-8")
        expect(f"rerun binding {governance} {name}", "evidence_record.py", code, "verify", record, "--rerun", "--order", path,
               "--dispatch-log", log, "--repo", repo, "--candidate", head, says=says, lacks=lacks)

    ok = "EVIDENCE_VERIFY: OK integrity=same test=passed"
    equivalent = "EVIDENCE_EQUIVALENT WO-001 rev=1 sha={old} to rev=2"
    case("bound_current", 0, ok, ["  - ", "  ~ "], order="current")
    case("unbound_rev2", 1, ["- AC-1: e.json: not bound to an order revision and the order is at REVISION 2",
                             "EVIDENCE_VERIFY: MISMATCH", "test=passed"])
    case("bound_old_revision", 1, ["- AC-1: e.json: recorded for WO-001 REVISION 1 (sha ", "EVIDENCE_VERIFY: MISMATCH"],
         order="old")
    case("equivalent_line", 0, ok, "  - ", order="old",
         log_extra="2026-01-03 09:00 +08:00 | " + equivalent + " | AC-1 unchanged by rev 2\n")
    for name, extra in (("equivalent_quoted", "> " + equivalent + "\n"),
                        ("equivalent_in_code_fence", "```\n" + equivalent + "\n```\n"),
                        ("equivalent_in_note", "NOTE: " + equivalent + "\n"),
                        ("equivalent_other_target", equivalent.replace("to rev=2", "to rev=3") + "\n")):
        case(name, 1, ["recorded for WO-001 REVISION 1 (sha ", "EVIDENCE_VERIFY: MISMATCH"], order="old", log_extra=extra)
    case("bound_other_order", 1, ["- AC-1: e.json: recorded for order WO-002, this order is WO-001",
                                  "EVIDENCE_VERIFY: MISMATCH"], order={"id": "WO-002", "rev": 2, "sha": "a" * 64})
    case("unbound_rev1_warns", 0, [ok, "~ AC-1: e.json: WARN evidence not bound to the order"], "  - ", rev=1)
    case("unbound_rev2", 0, [ok, "~ AC-1: e.json: not bound to an order revision and the order is at REVISION 2"],
         ["  - ", "Strict:"], governance="Standard")
    case("bound_old_revision", 0, [ok, "~ AC-1: e.json: recorded for WO-001 REVISION 1 (sha "], "  - ",
         governance="Standard", order="old")


def test_trusted_isolation(tmp):
    """v0.13 (R02-R06): the trusted rerun refuses hidden index flags, replace refs and PATH-chosen programs, runs the
    check in a copy of the candidate's tree, hashes artifacts there, and reads REPO again after the check."""
    global total
    root = tmp / "isolation"
    repo = root / "repo"
    repo.mkdir(parents=True)
    py = sys.executable

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    (repo / "check.py").write_text("from pathlib import Path\nPath('build.txt').write_bytes(b'new\\n')\n"
                                   "raise SystemExit(0 if Path('payload.txt').read_text() == 'A\\n' else 3)\n", encoding="utf-8")
    (repo / "payload.txt").write_text("A\n", encoding="utf-8")
    (repo / ".gitignore").write_text("build.txt\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "a")
    first = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "other")
    (repo / "payload.txt").write_text("B\n", encoding="utf-8")
    git("commit", "-q", "-am", "b")
    second = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    (repo / "build.txt").write_text("stale\n", encoding="utf-8")
    out = root / "records"
    expect("isolation: record the check", "evidence_record.py", 0, "run", "--out-dir", out, "--label", "AC-1", "--cwd", repo,
           "--", py, "check.py", says="exit=0")
    data = json.loads(next(out.glob("*-AC-1.json")).read_text(encoding="utf-8"))
    (repo / "build.txt").write_text("stale\n", encoding="utf-8")

    def sha(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def case(name, code, says, command=None, artifacts=(), lacks=None):
        command = command or [py, "check.py"]
        folder = root / name
        folder.mkdir()
        body = with_checks(TYPED_ORDER.format(base=first), f"AC-1: {json.dumps(command)}")
        order = folder / "WO-001-parser.md"
        order.write_text(body, encoding="utf-8")
        log = folder / "log.md"
        log.write_text(f"DISPATCH WO-001 rev=1 sha={sha(body)}\n", encoding="utf-8")
        record = folder / "record.json"
        record.write_text(json.dumps({**data, "command": command, "artifacts": list(artifacts)}), encoding="utf-8")
        expect(f"isolation: {name}", "evidence_record.py", code, "verify", record, "--rerun", "--order", order,
               "--dispatch-log", log, "--repo", repo, "--candidate", first, says=says, lacks=lacks)

    def artifact(path, text):
        return {"path": str(path), "kind": "file", "size": len(text), "sha256": sha(text)}

    case("the check runs in a copy of the tree", 0, ["in a new folder holding the 3 committed files", "test=passed"])
    (repo / "payload.txt").write_text("changed\n", encoding="utf-8")
    git("update-index", "--assume-unchanged", "payload.txt")
    case("an assume-unchanged file refuses (R02)", 2, "marks 1 file(s) assume-unchanged or skip-worktree (first: payload.txt)")
    git("update-index", "--no-assume-unchanged", "payload.txt")
    git("update-index", "--skip-worktree", "payload.txt")
    case("a skip-worktree file refuses", 2, "assume-unchanged or skip-worktree")
    git("update-index", "--no-skip-worktree", "payload.txt")
    git("checkout", "-q", "--", "payload.txt")
    git("replace", first, second)
    case("a replace ref refuses (R03)", 2, "has refs/replace/ refs")
    git("replace", "-d", first)
    case("a bare program name refuses (R04)", 2, "a bare name the PATH would resolve", command=["git", "--version"])
    case("a relative program outside the tree refuses", 2, "which is not a file inside the candidate",
         command=["./missing.exe"])
    case("the artifact is hashed in the rerun folder (R05)", 0, "artifacts=1 missing=0",
         artifacts=[artifact(repo / "build.txt", "new\n")])
    case("the artifact made by the rerun differs (R05)", 1,
         ["- artifact changed:", "(in the rerun folder: build.txt)", "MISMATCH integrity=changed"],
         artifacts=[artifact(repo / "build.txt", "stale\n")])
    case("an artifact outside the record's cwd", 1, "- artifact outside the record's cwd, so the rerun cannot make it",
         artifacts=[artifact(root / "elsewhere.txt", "x")])
    late = repo / "late.txt"
    case("a file written into the repo during the check (R06)", 1,
         ["- the repo changed while the check ran:", "has changed or untracked files", "MISMATCH"],
         command=[py, "-c", f"open({str(late)!r}, 'w').write('x')"])
    late.unlink()
    case("HEAD moved during the check (R06)", 1, [f"- the repo changed while the check ran: {repo} is at {second[:12]}", "MISMATCH"],
         command=[py, "-c", f"import subprocess; subprocess.run(['git', '-C', {str(repo)!r}, 'checkout', '-q', 'other'])"])
    git("checkout", "-q", "main")
    total += 1
    if (repo / "build.txt").read_text(encoding="utf-8") != "stale\n":
        failures.append("isolation: the rerun wrote build.txt in REPO instead of the copy")


def test_pause(tmp):
    """1.1.0 item 2: pause_ctl on/off/status/procs and hook_guard --pause-flag. While paused only reading, reporting,
    progress files and the pause status run; a call the pause lets through still meets the rules; setup gives workers
    the flag and the Director's worktree none."""
    global total
    rules_path = TOOLS / "guard_rules.json"
    director = tmp / "pause_DIRECTOR"
    (director / "orders").mkdir(parents=True)
    flag, log = director / "PAUSE", director / "DIRECTOR_LOG.md"
    log.write_text("# DIRECTOR_LOG\n", encoding="utf-8")

    def hook(call, profile="worker", rules_file=rules_path):
        args = ["--rules", str(rules_file)] if rules_file else []
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", *args, "--profile", profile,
                               "--pause-flag", str(flag)], capture_output=True, encoding="utf-8", input=json.dumps(call))

    def check(name, call, want, profile="worker"):
        global total
        total += 1
        done = hook(call, profile)
        rule = re.match(r"BLOCKED by hook_guard \[(G\d+)\]", done.stderr)
        if done.returncode == 0 and not done.stdout and not done.stderr:
            got = "silent"
        elif done.returncode == 2 and re.match(r"PAUSED by Director at \S+: CPU \(full\) for the batch; \S", done.stderr):
            got = "paused"
        elif done.returncode == 2 and rule:
            got = "deny:" + rule.group(1)
        else:
            got = f"other({done.returncode} {done.stdout.strip()[:80]} {done.stderr.strip()[:120]})"
        if got != want:
            failures.append(f"pause {name} [{profile}]: expected {want}, got {got}")
        elif re.search(r"<[^>]*>", done.stderr):
            failures.append(f"pause {name} [{profile}]: the message has a <...> placeholder")

    bash = lambda command, **kw: {"tool_name": "Bash", "tool_input": {"command": command, **kw}}
    shell = lambda command: {"tool_name": "PowerShell", "tool_input": {"command": command}}
    tool = lambda name, **kw: {"tool_name": name, "tool_input": kw}
    script = (TOOLS / "pause_ctl.py").as_posix()
    ctl = f"python -I -X utf8 {script}"
    check("flag off: a build runs", bash("python -m build"), "silent")
    expect("pause on", "pause_ctl.py", 0, "on", "--director", director, "--reason", "CPU <full> for the batch",
           says="PAUSE: on by Director at ")
    total += 1
    if not re.fullmatch(r"# DIRECTOR_LOG\nPAUSE on by=Director at=\S+ reason=CPU \(full\) for the batch\n", log.read_text(encoding="utf-8")):
        failures.append(f"pause on: DIRECTOR_LOG is {log.read_text(encoding='utf-8')!r}")
    expect("pause status shows the reason", "pause_ctl.py", 0, "status", "--director", director,
           says=["PAUSE: on by Director at ", ": CPU (full) for the batch"], lacks="<")
    for name, call in [("a build", bash("python -m build")), ("git status in the background", bash("git status", run_in_background=True)),
                       ("Agent", tool("Agent", prompt="x")), ("Monitor", tool("Monitor", command="x")),
                       ("Write", tool("Write", file_path=str(tmp / "a.py"))), ("NotebookEdit", tool("NotebookEdit", notebook_path=str(tmp / "a.ipynb"))),
                       ("worker pause_ctl off", bash(f"{ctl} off --director {director.as_posix()}")),
                       ("python -c before pause_ctl", bash(f'python -c "import os" {script} status')),
                       ("an allowed command and another", bash("git status && make")), ("git log --output", bash("git log --output=x.txt")),
                       ("git -c", bash("git -c core.pager=x log")), ("Stop-Process after Get-Process", shell("Get-Process python | Stop-Process")),
                       ("an MCP write", tool("mcp__shop__create_item")), ("start_session", tool("mcp__ccd_session__start_session")),
                       ("cat of a credential file", bash("cat .env")),
                       # batch 1 acceptance (11-07) 4: an allowed command that writes a file through a redirect
                       ("git log > a.py", bash("git log > a.py")), ("git log >> a.py", bash("git log >> a.py")),
                       ("git status 2> a.txt", bash("git status 2> a.txt")), ("git log &> a.txt", bash("git log &> a.txt")),
                       ("git log >& a.txt", bash("git log >& a.txt")), ("git log >| a.py", bash("git log >| a.py")),
                       ("git log >a.py", bash("git log >a.py")), ("> a.py git log", bash("> a.py git log")),
                       ("redirect inside $() in quotes", bash('git log "$(git status > a.py)"')),
                       ("process substitution", bash("git diff >(cat > a.py)")),
                       ("PowerShell *> a.txt", shell("git status *> a.txt")), ("PowerShell 2> a.txt", shell("git status 2> a.txt")),
                       ("Get-Process > a.txt", shell("Get-Process > a.txt")), ("pause_ctl status > a.txt", bash(f"{ctl} status > a.txt"))]:
        check(f"{name} is paused", call, "paused")
    for name, call in [("Read", tool("Read", file_path="README.md")), ("Grep", tool("Grep", pattern="x")), ("git status", bash("git status")),
                       ("git -C dir log", bash("git -C D:/x log --oneline -3")),
                       ("pause_ctl status", bash(f"{ctl} status --director {director.as_posix()}")),
                       ("pause_ctl procs", bash(f"{ctl} procs --root 4242")),
                       ("Get-Process sorted", shell("Get-Process | Sort-Object CPU -Descending | Select-Object -First 5")),
                       ("tasklist", bash('tasklist /FI "IMAGENAME eq python.exe"')), ("SendMessage", tool("SendMessage", to="x", message="stopped")),
                       ("an MCP read", tool("mcp__shop__list_items")), ("Write RESUME_STATE.md", tool("Write", file_path=str(tmp / "RESUME_STATE.md"))),
                       ("Edit a TASK REPORT", tool("Edit", file_path=str(tmp / "TASK_REPORT_item2.md"))),
                       ("git status 2>&1", bash("git status 2>&1")), ("git log >&2", bash("git log --oneline -3 >&2")),
                       ("PowerShell git status 2>&1", shell("git status 2>&1")), ("a quoted >", bash('git log --format="%h -> %s"')),
                       ("tasklist 2>&1 | findstr", bash("tasklist 2>&1 | findstr python"))]:
        check(f"{name} runs while paused", call, "silent")
    check("the Director's pause_ctl off runs", bash(f"{ctl} off --director {director.as_posix()}"), "silent", "director")
    check("a read the pause lets through still meets G50", tool("Read", file_path=".env"), "deny:G50")
    expect("pause off", "pause_ctl.py", 0, "off", "--director", director, says="PAUSE: off by Director at ")
    total += 1
    if flag.exists() or not re.search(r"\nPAUSE off by=Director at=\S+\n$", log.read_text(encoding="utf-8")):
        failures.append(f"pause off: flag {flag.exists()}, DIRECTOR_LOG {log.read_text(encoding='utf-8')!r}")
    check("flag off again: the build runs", bash("python -m build"), "silent")
    expect("pause status off", "pause_ctl.py", 0, "status", "--director", director, says="PAUSE: off")
    expect("pause off when it was not on", "pause_ctl.py", 0, "off", "--director", director, says="PAUSE: off (it was not on)")
    expect("pause on needs a reason", "pause_ctl.py", 2, "on", "--director", director)
    # --pause-flag with no rules file, rules with no pause section, or a bad pause section stop the hook (exit 1)
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    no_pause = tmp / "rules_no_pause.json"
    no_pause.write_text(json.dumps({k: v for k, v in data.items() if k != "pause"}), encoding="utf-8")
    bad_pause = tmp / "rules_bad_pause.json"
    bad_pause.write_text(json.dumps({**data, "pause": {**data["pause"], "allow_shell": {"worker": ["("], "director": []}}}), encoding="utf-8")
    for name, rules_file in (("no rules file", None), ("no pause section", no_pause), ("bad pause regex", bad_pause)):
        total += 1
        done = hook(bash("git status"), rules_file=rules_file)
        if done.returncode != 1 or not done.stderr.startswith("hook_guard: "):
            failures.append(f"pause {name}: expected exit 1, got {done.returncode} {done.stderr.strip()[:120]}")
    # procs: a busy root with an idle child, and an idle root that has already ended; only test-owned PIDs are ended
    busy = subprocess.Popen([sys.executable, "-I", "-c", "import subprocess, sys\n"
                             "c = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])\n"
                             "print(c.pid, flush=True)\nwhile True: pass"], stdout=subprocess.PIPE, encoding="utf-8")
    idle = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(300)"])
    child = None
    try:
        child = int(busy.stdout.readline())
        idle.kill()
        idle.wait()
        roots = ("--root", busy.pid, "--root", idle.pid)
        total += 1
        code, out = run("pause_ctl.py", "procs", *roots, "--sample", "1")
        rows = re.findall(r"^ +(\d+) +\d+ +[\d.]+  ", out, re.M)
        if (code != 1 or not re.search(rf"^STOPPED\n  {idle.pid}\nREMAINING", out, re.M) or rows != [str(busy.pid), str(child)]
                or "PROCS: stopped=1 remaining=2 busy=1" not in out):
            failures.append(f"pause_ctl procs with a live tree: exit {code}: {out.strip()[-400:]}")
        busy.kill()
        busy.wait()
        os.kill(child, signal.SIGTERM)
        expect("pause_ctl procs after the stop", "pause_ctl.py", 0, "procs", *roots, "--sample", "0.2",
               says="PROCS: stopped=2 remaining=0 busy=0")
    finally:
        for proc in (busy, idle):
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if child:
            try:
                os.kill(child, signal.SIGTERM)
            except OSError:
                pass
    pids = tmp / "pids.txt"
    pids.write_text("# none of these\nabc\n", encoding="utf-8")
    expect("pause_ctl procs refuses a bad PID file", "pause_ctl.py", 1, "procs", "--pids-file", pids)
    # setup: the worker hook gets --pause-flag DIR/PAUSE; the Director's worktree gets none
    repo = tmp / "paused_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    settings = repo / ".claude" / "settings.local.json"
    setup = ("--repo", repo, "--only-this", "--protect-director", director, "--guard-mode", "block")
    expect("setup: the worker hook gets the pause flag", "setup_project_settings.py", 0, *setup, "--guard-profile", "worker", "--apply",
           says=["SET", "block-rule=2"])
    command = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    total += 1
    if f'--pause-flag "{(director / "PAUSE").as_posix()}"' not in command:
        failures.append(f"setup worker: no --pause-flag DIR/PAUSE in {command!r}")
    expect("setup: the same rerun is OK", "setup_project_settings.py", 0, *setup, "--guard-profile", "worker", says="OK")
    expect("setup: another pause flag is not OK", "setup_project_settings.py", 1, *setup, "--guard-profile", "worker",
           "--pause-flag", tmp / "OTHER_PAUSE", says="MISSING")
    expect("setup: the Director's worktree has no pause flag", "setup_project_settings.py", 0, *setup, "--guard-profile", "worker",
           "--director-worktree", repo, "--apply", says="SET")
    command = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    total += 1
    if "--pause-flag" in command or "--profile director" not in command:
        failures.append(f"setup director worktree: command is {command!r}")


def test_auto_pause(tmp):
    """1.1.0 batch 2: the 5th worker deny within 600 s writes the pause flag; older denies, the Director and a state
    file that cannot be written never pause; bad auto_pause settings are refused."""
    global total
    rules_path = TOOLS / "guard_rules.json"
    folder = tmp / "auto_pause"
    folder.mkdir()
    flag = folder / "PAUSE"
    state = folder / "PAUSE.denies"

    def hook(call, profile="worker", rules_file=rules_path, flag_file=flag):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--rules", str(rules_file),
                               "--profile", profile, "--pause-flag", str(flag_file)],
                              capture_output=True, encoding="utf-8", input=json.dumps(call))

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"auto-pause {name}: {detail}")

    push = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    dotenv = {"tool_name": "Read", "tool_input": {"file_path": ".env"}}
    first_four = [hook(push if i % 2 == 0 else dotenv) for i in range(4)]
    check("4 denies: still denies, no flag", all(d.returncode == 2 and "AUTO-PAUSED" not in d.stderr for d in first_four)
          and not flag.exists(), " | ".join(d.stderr.strip()[:80] for d in first_four))
    fifth = hook(push)
    text = flag.read_text(encoding="utf-8") if flag.exists() else ""
    check("5th deny writes the flag with the rule IDs", fifth.returncode == 2 and "AUTO-PAUSED by hook_guard: auto: 5 denies in 600s" in fifth.stderr
          and re.match(r"PAUSE by hook_guard at \S+: auto: 5 denies in 600s \(G02 G50 G02 G50 G02\)\n$", text)
          and not re.search(r"<[^>]*>", fifth.stderr), fifth.stderr + text)
    check("state file cleared after the pause", state.exists() and state.read_text(encoding="utf-8") == "")
    expect("auto-paused flag reads as a pause", "pause_ctl.py", 0, "status", "--director", folder, says="PAUSE: on by hook_guard at")
    ctl = f"python -I -X utf8 {(TOOLS / 'pause_ctl.py').as_posix()}"
    status = hook({"tool_name": "Bash", "tool_input": {"command": f"{ctl} status --director {folder.as_posix()}"}})
    off = hook({"tool_name": "Bash", "tool_input": {"command": f"{ctl} off --director {folder.as_posix()}"}})
    check("auto-paused worker: pause_ctl status runs, off does not", status.returncode == 0 and off.returncode == 2
          and off.stderr.startswith("PAUSED by hook_guard at "), status.stderr + off.stderr)
    env = hook(dotenv)
    check("while paused a rule deny is not counted again", env.returncode == 2 and env.stderr.startswith("BLOCKED by hook_guard [G50]")
          and "AUTO-PAUSED" not in env.stderr and state.read_text(encoding="utf-8") == "", env.stderr)
    flag.unlink()
    old = time.time() - 601
    state.write_text("".join(f"{old:.3f} G02\n" for _ in range(4)), encoding="utf-8")
    once = hook(push)
    check("denies older than the window are not counted", once.returncode == 2 and not flag.exists(), once.stderr)
    state.write_text("", encoding="utf-8")
    for _ in range(6):
        boss = hook(push, profile="director")
    check("director: no auto-pause", not flag.exists() and "AUTO-PAUSED" not in boss.stderr
          and state.read_text(encoding="utf-8") == "", boss.stderr)
    blocked_dir = tmp / "auto_pause_blocked"
    blocked_dir.mkdir()
    (blocked_dir / "PAUSE.denies").mkdir()  # a folder where the state file should be: every write fails
    tries = [hook(push, flag_file=blocked_dir / "PAUSE") for _ in range(6)]
    check("state file cannot be written: plain deny, no pause, no traceback",
          all(d.returncode == 2 and d.stderr.startswith("BLOCKED by hook_guard [G02]") and "Traceback" not in d.stderr for d in tries)
          and not (blocked_dir / "PAUSE").exists(), tries[-1].stderr)
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    for name, value in (("missing director", {"worker": {"denies": 5, "window_s": 600}}),
                        ("zero denies", {"worker": {"denies": 0, "window_s": 600}, "director": None}),
                        ("text window", {"worker": {"denies": 5, "window_s": "600"}, "director": None})):
        bad = folder / f"bad_{name.replace(' ', '_')}.json"
        bad.write_text(json.dumps(dict(data, auto_pause=value)), encoding="utf-8")
        done = hook(push, rules_file=bad, flag_file=folder / "unused_PAUSE")
        check(f"bad auto_pause ({name}) is refused", done.returncode == 1 and "auto_pause" in done.stderr, done.stderr)


def test_audit(tmp):
    """audit_log.py: the chain, its breaks, anchors (also from a commit), cited ranges, Bash output masking,
    hook_guard decision lines and setup --audit-log."""
    global total
    folder = tmp / "audit"
    folder.mkdir()
    log = folder / "a.jsonl"
    script = str(TOOLS / "audit_log.py")
    spec = importlib.util.spec_from_file_location("audit_log_under_test", TOOLS / "audit_log.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    fake_key = "gh" + "p_" + "Q7w" * 12  # built at run time: nothing key-shaped in the source

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"audit {name}: {detail}")

    def feed(call, path=log):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", script, "append", "--log", str(path)],
                              input=json.dumps(call), capture_output=True, encoding="utf-8")

    def lines(path=log):
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def write(path, entries):
        with open(path, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) needs 3.10
            fh.write("".join(audit.canonical(e) + "\n" for e in entries))

    def copy(name, change=None):
        target = folder / name
        entries = lines()
        if change:
            entries = change(entries)
        write(target, entries)
        return target

    def anchor_of(path):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", script, "head", "--log", str(path)],
                              capture_output=True, encoding="utf-8").stdout.strip()

    bash = {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash", "tool_use_id": "t1",
            "tool_input": {"command": f"echo {fake_key}"}, "duration_ms": 15,
            "tool_response": {"stdout": "RAW-OUTPUT-MARKER-77 " + fake_key, "stderr": "", "interrupted": False, "isImage": False}}
    done = feed(bash)
    reply = json.loads(done.stdout) if done.stdout.strip() else {}
    out = reply.get("hookSpecificOutput", {}).get("updatedToolOutput", {})
    check("Bash output with a secret comes back masked, same fields", done.returncode == 0
          and out.get("stdout") == "RAW-OUTPUT-MARKER-77 [MASKED:github_token]"
          and sorted(out) == ["interrupted", "isImage", "stderr", "stdout"], done.stdout + done.stderr)
    done = feed(dict(bash, tool_use_id="t2", tool_response={"stdout": "plain", "stderr": "", "interrupted": False, "isImage": False}))
    check("Bash output with nothing to mask prints nothing", done.returncode == 0 and not done.stdout.strip(), done.stdout)
    done = feed({"hook_event_name": "PostToolUseFailure", "tool_name": "Read", "tool_use_id": "t3",
                 "tool_input": {"file_path": "missing.txt"}, "error": "File does not exist."})
    check("failure call appended", done.returncode == 0, done.stderr)
    text = log.read_text(encoding="utf-8")
    check("no raw output and no secret in the log", "RAW-OUTPUT-MARKER-77" not in text and fake_key not in text
          and "[MASKED:github_token]" in text, text[:300])
    entries = lines()
    check("failure input gives kind=failure", entries[2]["kind"] == "failure" and entries[2]["result"]["status"] == "error",
          json.dumps(entries[2]))
    expect("audit verify after 3 appends", "audit_log.py", 0, "verify", "--log", log, says=["entries=3", "head_seq=3", " OK"])
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--rules", str(TOOLS / "guard_rules.json"),
                           "--profile", "worker", "--audit", str(log)],
                          input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}),
                          capture_output=True, encoding="utf-8")
    last = lines()[-1]
    check("hook_guard deny is on the chain with its rule", done.returncode == 2 and last["kind"] == "decision"
          and last["result"] == {"status": "deny"} and last["rule"] == "G02", json.dumps(last))
    expect("audit verify with the decision line", "audit_log.py", 0, "verify", "--log", log, says=["entries=4", " OK"])
    head = anchor_of(log)
    anchors = folder / "DIRECTOR_LOG.md"
    anchors.write_text(f"# LOG\n- 01:00 gate {head}\n", encoding="utf-8")
    expect("audit verify with its anchor", "audit_log.py", 0, "verify", "--log", log, "--anchor-log", anchors, says=["anchors=1", " OK"])
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", script, "cite", "--log", str(log), "--from", "2", "--to", "3"],
                          capture_output=True, encoding="utf-8")
    cite = done.stdout.strip()
    check("cite prints AUDIT_RANGE", done.returncode == 0 and cite.startswith("AUDIT_RANGE file=") and " seq=2..3 " in cite, cite)
    expect("audit verify --cite", "audit_log.py", 0, "verify", "--cite", cite, says="cite=checked")

    def edit_two(entries):
        entries[1]["input"] = entries[1]["input"].replace("echo", "ECHO")
        return entries
    tampered = copy("tampered.jsonl", edit_two)
    expect("audit one changed character", "audit_log.py", 1, "verify", "--log", tampered, says="BROKEN seq=2:")
    dropped = copy("dropped.jsonl", lambda e: e[:1] + e[2:])
    expect("audit a deleted line", "audit_log.py", 1, "verify", "--log", dropped, says="BROKEN seq=3: comes after seq=1")
    swapped = copy("swapped.jsonl", lambda e: [e[0], e[2], e[1], e[3]])
    expect("audit two lines swapped", "audit_log.py", 1, "verify", "--log", swapped, says="BROKEN seq=3:")
    whole = copy("cut.jsonl")
    cut_anchor = folder / "cut_LOG.md"
    cut_anchor.write_text(anchor_of(whole) + "\n", encoding="utf-8")
    write(whole, lines(whole)[:-1])
    expect("audit a cut tail passes alone", "audit_log.py", 0, "verify", "--log", whole, says="entries=3")
    expect("audit a cut tail is caught by the anchor", "audit_log.py", 1, "verify", "--log", whole, "--anchor-log", cut_anchor,
           says="anchor seq=4: not in the log")

    def rewrite(entries):  # every hash recomputed: the chain alone cannot tell
        prev = audit.GENESIS
        for entry in edit_two(entries):
            entry["prev"] = prev
            entry["hash"] = prev = audit.digest(entry)
        return entries
    fake = copy("fake.jsonl")
    fake_anchor = folder / "fake_LOG.md"
    fake_anchor.write_text(anchor_of(fake) + "\n", encoding="utf-8")
    fake_cite = cite.replace(log.as_posix(), fake.as_posix())
    write(fake, rewrite(lines(fake)))
    expect("audit a recomputed chain passes alone", "audit_log.py", 0, "verify", "--log", fake, says=" OK")
    expect("audit a recomputed chain is caught by the anchor", "audit_log.py", 1, "verify", "--log", fake, "--anchor-log", fake_anchor,
           says="anchor seq=4: hash differs")
    expect("audit a cited range that changed", "audit_log.py", 1, "verify", "--cite", fake_cite, says="not the ones cited")
    expect("audit anchor file without a line for this log", "audit_log.py", 1, "verify", "--log", fake, "--anchor-log", anchors,
           says="no AUDIT_HEAD line for this log")
    # --anchor-rev: the anchor as committed; an edited working copy of the LOG does not help
    repo = folder / "director_repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    (repo / "DIRECTOR_LOG.md").write_text(fake_anchor.read_text(encoding="utf-8"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "anchor")
    rev = ("--anchor-rev", "HEAD", "--anchor-path", "DIRECTOR_LOG.md", "--repo", repo)
    expect("audit committed anchor vs a recomputed chain", "audit_log.py", 1, "verify", "--log", fake, *rev, says="hash differs")
    (repo / "DIRECTOR_LOG.md").write_text(anchor_of(fake) + "\n", encoding="utf-8")
    expect("audit edited working LOG fools --anchor-log", "audit_log.py", 0, "verify", "--log", fake, "--anchor-log", repo / "DIRECTOR_LOG.md")
    expect("audit edited working LOG does not fool --anchor-rev", "audit_log.py", 1, "verify", "--log", fake, *rev, says="hash differs")
    expect("audit anchor commit that does not exist", "audit_log.py", 2, "verify", "--log", fake, "--anchor-rev", "0" * 40,
           "--anchor-path", "DIRECTOR_LOG.md", "--repo", repo, says="NOT_RUN anchor commit")
    expect("audit missing log", "audit_log.py", 2, "verify", "--log", folder / "nope.jsonl", says="NOT_RUN")
    empty = folder / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    expect("audit empty log", "audit_log.py", 0, "verify", "--log", empty, says=["entries=0", " OK"])
    broken = folder / "broken.jsonl"
    broken.write_text(log.read_text(encoding="utf-8").splitlines()[0] + "\n{not json\n", encoding="utf-8")
    expect("audit a line that is not JSON", "audit_log.py", 1, "verify", "--log", broken, says="BROKEN line=2: not JSON")
    # 8 processes x 20 lines at once: 160 lines, one chain
    busy = folder / "busy.jsonl"
    code = ("import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location('a', sys.argv[1]); a = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(a)\n"
            "for i in range(20): a.append_entry(sys.argv[2], a.hook_entry({'tool_name': 'Bash', 'tool_input': {'n': i}}))\n")
    procs = [subprocess.Popen([sys.executable, "-I", "-X", "utf8", "-c", code, script, str(busy)]) for _ in range(8)]
    codes = [p.wait(timeout=120) for p in procs]
    check("8 writers at once all finish", codes == [0] * 8, str(codes))
    expect("audit 160 lines from 8 writers", "audit_log.py", 0, "verify", "--log", busy, says=["entries=160", " OK"])
    # setup --audit-log: Post hooks, hook_guard --audit, and the hook test leaves the log alone
    wt = folder / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    (wt / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    per = folder / "logs" / "{worktree}.jsonl"
    setup = ("--repo", wt, "--only-this", "--audit-log", per, "--guard-mode", "block")
    expect("setup audit hooks missing", "setup_project_settings.py", 1, *setup, says=["MISSING", "hooks.PostToolUse", "hooks.PostToolUseFailure"])
    expect("setup audit hooks written", "setup_project_settings.py", 0, *setup, "--apply", says=["SET", "block=2"])
    data = json.loads((wt / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    wanted = (folder / "logs" / "wt.jsonl").as_posix()
    posts = [data["hooks"][e][0]["hooks"][0]["command"] for e in ("PostToolUse", "PostToolUseFailure")]
    check("setup Post hooks run audit_log append on the worktree's log",
          all("audit_log.py" in c and f'append --log "{wanted}"' in c for c in posts)
          and f'--audit "{wanted}"' in data["hooks"]["PreToolUse"][0]["hooks"][0]["command"], json.dumps(data["hooks"]))
    check("setup hook test wrote nothing into the log", not (folder / "logs" / "wt.jsonl").exists())
    expect("setup audit hooks kept on rerun", "setup_project_settings.py", 0, *setup, says="OK")
    expect("setup plain --hooks keeps --audit", "setup_project_settings.py", 0, "--repo", wt, "--only-this", "--hooks", says="OK")


def test_report_vs_audit(tmp):
    """1.3.0 item 10: report_vs_audit.py checks the runs a TASK REPORT claims (selftest, Unity, Blender, hash) against
    the action log of the same session: run or not, exit (ok / error), time; a broken chain is a FAIL. Synthetic logs."""
    global total
    folder = tmp / "rva"
    folder.mkdir()
    spec = importlib.util.spec_from_file_location("audit_log_for_rva", TOOLS / "audit_log.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    def chain(path, rows):
        prev, out = audit.GENESIS, []
        for seq, (ts, session, tool, tool_input, kind, status) in enumerate(rows, 1):
            entry = {"seq": seq, "ts": ts, "session_id": session, "agent_id": None, "tool": tool, "tool_use_id": f"t{seq}",
                     "input": audit.summary(tool_input), "kind": kind, "result": {"status": status},
                     "duration_ms": None, "prev": prev}
            if kind == "decision":
                entry["rule"] = "push"
            entry["hash"] = audit.digest(entry)
            prev = entry["hash"]
            out.append(entry)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(audit.canonical(e) + "\n" for e in out))
        return out

    log = folder / "a.jsonl"
    long_cmd = "python -I -X utf8 tools/build_all.py " + "--flag " * 90 + "--end"
    chain(log, [
        ("2026-11-07T11:40:00.000+00:00", "S1", "Bash", {"command": "python -I -X utf8 tools/selftest.py",
                                                         "description": "selftest"}, "result", "ok"),
        ("2026-11-07T11:45:00.000+00:00", "S1", "PowerShell", {"command": "Get-FileHash D:\\w\\out\\pack.zip"},
         "result", "ok"),
        ("2026-11-07T11:50:00.000+00:00", "S1", "Bash", {"command": "\"C:/Unity/Unity.exe\" -batchmode -runTests"},
         "failure", "error"),
        ("2026-11-07T11:52:00.000+00:00", "S1", "mcp__blender__execute_blender_code", {"code": "x"}, "result", "ok"),
        ("2026-11-07T11:55:00.000+00:00", "S1", "Bash", {"command": "git push"}, "decision", "deny"),
        ("2026-11-07T11:56:00.000+00:00", "S2", "Bash", {"command": "sha256sum other.bin"}, "result", "ok"),
        ("2026-11-07T11:57:00.000+00:00", "S1", "Bash", {"command": long_cmd}, "result", "ok"),
    ])

    def run(name, report, code, says=(), lacks=(), extra=(), logs=(log,)):
        global total
        total += 1
        path = folder / f"{re.sub(r'[^A-Za-z0-9]+', '_', name)}.md"
        path.write_text(report, encoding="utf-8")
        args = [sys.executable, "-I", "-X", "utf8", str(TOOLS / "report_vs_audit.py"), "--report", str(path),
                "--utc-offset", "+08:00"]
        for item in logs:
            args += ["--log", str(item)]
        done = subprocess.run(args + [str(x) for x in extra], capture_output=True, encoding="utf-8")
        out = done.stdout + done.stderr
        wrong = [s for s in ([says] if isinstance(says, str) else says) if s not in out]
        wrong += [f"not {s}" for s in ([lacks] if isinstance(lacks, str) else lacks) if s in out]
        if done.returncode != code or wrong:
            failures.append(f"report_vs_audit {name}: expected exit {code}, got {done.returncode}; {wrong}: {out[-700:]}")

    good = ("SESSION_ID: S1\n"
            "TESTS: `python -I -X utf8 tools/selftest.py` 300/300 passed\n"
            "EVIDENCE: `Get-FileHash D:/w/out/pack.zip` OK\n"
            "RAN:\n"
            "- `\"C:/Unity/Unity.exe\" -batchmode -runTests` exit=1 at=19:50\n"
            "- `mcp__blender__execute_blender_code` exit=0 at=2026-11-07T19:53+08:00\n")
    run("all claims check out", good, 0, ("REPORT_VS_AUDIT: PASS claims=4 ok=4 failed=0 session=S1 logs=1",
                                          "OK   selftest:", "OK   hash:", "OK   unity:", "OK   blender:"))
    run("claimed exit 0 but the run failed", good.replace("-runTests` exit=1", "-runTests` exit=0"), 1,
        ("FAIL unity:", "but the log says error", "REPORT_VS_AUDIT: FAIL"))
    run("claimed failure but the run was ok", "SESSION_ID: S1\nRAN: `tools/selftest.py` exit=2\n", 1,
        "but the log says ok")
    run("not run at all", "SESSION_ID: S1\nTESTS: `blender -b scene.blend -P render.py` PASS\n", 1,
        ("FAIL blender:", "not run in session S1"))
    run("run by another session only", "SESSION_ID: S1\nEVIDENCE: `sha256sum other.bin` OK\n", 1, "not run in session S1")
    run("same claim is fine for that session", "EVIDENCE: `sha256sum other.bin` OK\n", 0, "session=S2",
        extra=("--session", "S2"))
    run("time too far off", "SESSION_ID: S1\nRAN: `tools/selftest.py` exit=0 at=21:00\n", 1, "at=21:00, but the runs")
    run("time within tolerance", "SESSION_ID: S1\nRAN: `tools/selftest.py` exit=0 at=19:50\n", 0, "PASS",
        extra=("--tolerance-min", "10"))
    run("full ISO time off", "SESSION_ID: S1\nRAN: `tools/selftest.py` at=2026-11-06T19:40+08:00\n", 1, "but the runs")
    run("denied by the hook", "SESSION_ID: S1\nRAN: `git push` exit=0\n", 1, "the hook denied it")
    run("a cut log line matches on its first part", f"SESSION_ID: S1\nRAN: `{long_cmd}` exit=0\n", 0, "PASS")
    run("slashes, quotes and case aside", "SESSION_ID: S1\nEVIDENCE: `get-filehash D:\\w\\out\\pack.zip` 通過\n", 0,
        "PASS")
    run("plain code in TESTS is not a claim", "SESSION_ID: S1\nTESTS: `git status` clean\nDONE: `docs/x.md`\n", 0,
        "REPORT_VS_AUDIT: NONE claims=0")
    run("session from the only one in the logs", "TESTS: `tools/selftest.py` PASS\n", 2, "2 sessions")
    run("a session with no lines", "SESSION_ID: S9\nTESTS: `tools/selftest.py` PASS\n", 1, "no line of session S9")
    broken = folder / "broken.jsonl"
    text = log.read_text(encoding="utf-8").replace('"status":"error"', '"status":"ok"')
    broken.write_text(text, encoding="utf-8")
    run("an edited log is a FAIL", good, 1, ("FAIL log: hash chain", "REPORT_VS_AUDIT: FAIL"), logs=(broken,))
    run("a missing log cannot run", good, 2, "no such log", logs=(folder / "none.jsonl",))
    run("a bad at= is a FAIL", "SESSION_ID: S1\nRAN: `tools/selftest.py` at=yesterday\n", 1, "not an ISO time")
    second = folder / "b.jsonl"
    chain(second, [("2026-11-07T12:10:00.000+00:00", "S1", "mcp__UnityMCP__run_tests", {"mode": "EditMode"}, "result",
                    "ok")])
    run("two logs are read together", "SESSION_ID: S1\nTESTS: `mcp__UnityMCP__run_tests` PASS\n"
        "RAN: `tools/selftest.py` exit=0\n", 0, "PASS claims=2 ok=2 failed=0 session=S1 logs=2", logs=(log, second))
    template = (TOOLS.parent / "templates" / "TASK_REPORT.md").read_text(encoding="utf-8")
    total += 1
    if "SESSION_ID:" not in template or "RAN:" not in template or "report_vs_audit.py" not in template:
        failures.append("report_vs_audit: templates/TASK_REPORT.md has no SESSION_ID: / RAN: lines")


def test_audit_names(tmp):
    """K6: {worktree} and {container} in the log path, filled in when the command runs; one chain per file."""
    global total
    folder = tmp / "audit_names"
    folder.mkdir()
    spec = importlib.util.spec_from_file_location("audit_log_names", TOOLS / "audit_log.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    script = str(TOOLS / "audit_log.py")
    ids = ["a1b2c3d4e5f6" + "0" * 52, "0f9e8d7c6b5a" + "1" * 52]
    infos = []
    for n, cid in enumerate(ids):
        info = folder / f"mountinfo{n}"
        info.write_text(f"1 0 0:1 / / rw - overlay overlay rw\n2 1 8:1 /var/lib/docker/containers/{cid}/hostname "
                        f"/etc/hostname rw - ext4 /dev/sda1 rw\n", encoding="utf-8")
        infos.append(info)
    nothing = folder / "absent"

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"audit names {name}: {detail}")

    def env(**extra):
        out = {k: v for k, v in os.environ.items() if k not in ("DW_WORKER_NAME", "CLAUDE_PROJECT_DIR")}
        out.update(extra)
        return out

    def tool(*args, cwd=None, stdin="", **extra):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", *map(str, args)], env=env(**extra), cwd=cwd,
                              input=stdin, capture_output=True, encoding="utf-8")

    check("container ID from mountinfo is its first 12 characters", audit.container_id(infos[0], nothing) == "a1b2c3d4e5f6")
    check("no mountinfo and no /.dockerenv gives host", audit.container_id(nothing, nothing) == "host")
    marker = folder / "dockerenv"
    marker.write_text("", encoding="utf-8")
    got = audit.container_id(nothing, marker)
    check("/.dockerenv without an ID in mountinfo gives the host name", got not in ("", "host")
          and all(c.isalnum() or c in "._-" for c in got), got)
    saved = os.environ.get("DW_WORKER_NAME")
    made = set()
    try:
        os.environ["DW_WORKER_NAME"] = "w/1 x"
        check("DW_WORKER_NAME wins and is made safe", audit.worker_name(folder) == "w_1_x", audit.worker_name(folder))
        os.environ.pop("DW_WORKER_NAME")
        check("without DW_WORKER_NAME the folder name is used", audit.worker_name(folder) == "audit_names")
        # the same name in two containers, and two names in one container: four files, four chains
        for name in ("w1", "w2"):
            os.environ["DW_WORKER_NAME"] = name
            for info in infos:
                path = audit.expand(folder / "logs" / "{worktree}-{container}.jsonl", mountinfo=info, dockerenv=nothing)
                for i in range(3):
                    audit.append_entry(path, audit.hook_entry({"tool_name": "Bash", "tool_input": {"n": i}}))
                made.add(path)
    finally:
        if saved is None:
            os.environ.pop("DW_WORKER_NAME", None)
        else:
            os.environ["DW_WORKER_NAME"] = saved
    names = sorted(pathlib.Path(p).name for p in made)
    check("two names x two containers give four files", names == ["w1-0f9e8d7c6b5a.jsonl", "w1-a1b2c3d4e5f6.jsonl",
          "w2-0f9e8d7c6b5a.jsonl", "w2-a1b2c3d4e5f6.jsonl"], str(names))
    for path in sorted(made):
        expect(f"audit names {pathlib.Path(path).name} is its own chain", "audit_log.py", 0, "verify", "--log", path,
               says=["entries=3", "head_seq=3", " OK"])
    try:
        audit.expand(folder / "{user}.jsonl")
        check("an unknown placeholder is refused", False, "no error")
    except ValueError as error:
        check("an unknown placeholder is refused", "{user}" in str(error), str(error))
    check("a path without placeholders is left as it is", audit.expand("x/a.jsonl") == "x/a.jsonl")
    check("only= fills in just the named ones",
          audit.expand("{worktree}-{container}", folder, only=("worktree",)) == "audit_names-{container}")

    # the command line fills them in as it runs
    here = audit.container_id()
    call = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "a"}, "tool_response": "x"})
    pattern = folder / "cli" / "{worktree}-{container}.jsonl"
    want = folder / "cli" / f"cli1-{here}.jsonl"
    done = tool(script, "append", "--log", pattern, stdin=call, DW_WORKER_NAME="cli1")
    check("append writes the filled-in file", done.returncode == 0 and want.is_file(), done.stderr + str(want))
    done = tool(script, "verify", "--log", pattern, DW_WORKER_NAME="cli1")
    check("verify reads the same filled-in file", done.returncode == 0 and f"file={want.resolve().as_posix()}" in done.stdout,
          done.stdout)
    done = tool(script, "append", "--log", pattern, cwd=folder, stdin=call)
    check("without DW_WORKER_NAME append uses the current folder name",
          done.returncode == 0 and (folder / "cli" / f"audit_names-{here}.jsonl").is_file(), done.stderr)
    bad = folder / "cli" / "{user}.jsonl"
    done = tool(script, "append", "--log", bad, stdin=call)
    check("append with an unknown placeholder exits 1 and names it", done.returncode == 1 and "{user}" in done.stderr
          and not list((folder / "cli").glob("*user*")), done.stderr)
    fake_key = "gh" + "p_" + "Z4k" * 12  # built at run time: nothing key-shaped in the source
    bash = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "x"},
                       "tool_response": {"stdout": "out " + fake_key, "stderr": "", "interrupted": False, "isImage": False}})
    done = tool(script, "append", "--log", bad, stdin=bash)
    check("append with an unknown placeholder still returns the masked output", done.returncode == 0
          and "[MASKED:github_token]" in done.stdout and fake_key not in done.stdout, done.stdout + done.stderr)
    for cmd in ("verify", "head"):
        expect(f"audit names {cmd} with an unknown placeholder", "audit_log.py", 2, cmd, "--log", bad, says=["NOT_RUN", "{user}"])
    expect("audit names cite with an unknown placeholder", "audit_log.py", 2, "cite", "--log", bad, "--from", 1, "--to", 1,
           says=["NOT_RUN", "{user}"])

    # hook_guard --audit fills them in too
    push = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
    done = tool(TOOLS / "hook_guard.py", "--mode", "block", "--rules", TOOLS / "guard_rules.json", "--profile", "worker",
                "--audit", folder / "guard" / "{worktree}-{container}.jsonl", stdin=push, DW_WORKER_NAME="g1")
    written = folder / "guard" / f"g1-{here}.jsonl"
    rows = [json.loads(x) for x in written.read_text(encoding="utf-8").splitlines()] if written.is_file() else []
    check("hook_guard --audit writes its decision to the filled-in file", done.returncode == 2 and len(rows) == 1
          and rows[0]["kind"] == "decision" and not list((folder / "guard").glob("*{*")), str(rows))

    # setup fills in {worktree}, keeps {container} for the hook, and refuses an unknown placeholder
    wt = folder / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    (wt / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    per = (folder / "logs2" / "{worktree}-{container}.jsonl").as_posix()
    done = tool(TOOLS / "setup_project_settings.py", "--repo", wt, "--only-this", "--audit-log", per, "--apply")
    check("setup writes the {container} path", done.returncode == 0 and "SET" in done.stdout, done.stdout[-300:] + done.stderr)
    data = json.loads((wt / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    wanted = (folder / "logs2").resolve().as_posix() + "/wt-{container}.jsonl"
    command = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    check("setup fills in {worktree} and leaves {container} for the hook", f'append --log "{wanted}"' in command, command)
    done = tool(TOOLS / "setup_project_settings.py", "--repo", wt, "--only-this", "--audit-log", (folder / "{user}.jsonl").as_posix())
    check("setup refuses an unknown placeholder", done.returncode == 1 and "{user}" in done.stderr, done.stdout[-200:] + done.stderr)

    # doctor fills them in the same way before it looks for the file
    done = tool(TOOLS / "doctor.py", "--repo", wt)
    line = next((x for x in done.stdout.splitlines() if " audit_log: " in x), "")
    check("doctor: the filled-in file has no entries yet", line.startswith("CONFIGURED_NOT_VERIFIED")
          and line.endswith(f"wt-{here}.jsonl has no entries yet"), done.stdout[-600:])
    target = pathlib.Path(wanted.replace("{container}", here))
    audit.append_entry(target, audit.hook_entry({"tool_name": "Read", "tool_input": {}}))
    done = tool(TOOLS / "doctor.py", "--repo", wt)
    line = next((x for x in done.stdout.splitlines() if " audit_log: " in x), "")
    check("doctor verifies the filled-in file", line.startswith("ENFORCED") and f"file={target.resolve().as_posix()}" in line,
          done.stdout[-600:])


FAKE_CLAUDE = '''import json, os, sys, time
mode = os.environ.get("FAKE_REVIEW_MODE", "block")
with open(os.environ["FAKE_REVIEW_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps({"argv": sys.argv[1:], "guard": os.environ.get("DW_HOOK_REVIEW")}) + "\\n")
if mode == "sleep":
    time.sleep(8)
if mode == "exit1":
    sys.exit(1)
if mode == "garbage":
    print("I think this is fine")
    sys.exit(0)
answer = {"verdict": "no_objection" if mode == "ok" else "block", "reason": "looks <risky>\\n   to me"}
if mode == "extra":
    answer["also"] = 1
print(json.dumps({"type": "result", "result": json.dumps(answer)}))
'''


def test_review(tmp):
    """1.1.0 batch 2: hook_guard --review shows asks of the review categories to a second model (a fake claude here,
    never the real one); it can only turn an ask into a deny, and setup --guard-review installs the switch."""
    global total
    rules_path = TOOLS / "guard_rules.json"
    folder = tmp / "review"
    folder.mkdir()
    fake = folder / "fake_claude.py"
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    calls_log = folder / "calls.jsonl"
    empty_path = folder / "no_programs"
    empty_path.mkdir()
    fake_key = "gh" + "p_" + "R8t" * 12  # built at run time: nothing key-shaped in the source
    data = json.loads(rules_path.read_text(encoding="utf-8"))

    def rules_copy(name, **change):
        path = folder / f"{name}.json"
        changed = dict(data, **change)
        for key in [k for k, v in change.items() if v is None]:
            del changed[key]
        path.write_text(json.dumps(changed), encoding="utf-8")
        return path

    def calls():
        return [json.loads(line) for line in calls_log.read_text(encoding="utf-8").splitlines()] if calls_log.exists() else []

    def hook(call, mode="block", profile="director", review=True, rules_file=rules_path, extra=(), **env_change):
        env = {k: v for k, v in os.environ.items() if k not in ("DW_HOOK_REVIEW", "CLAUDE_CODE_EXECPATH")}
        env.update(CLAUDE_CODE_EXECPATH=str(fake), FAKE_REVIEW_MODE=mode, FAKE_REVIEW_LOG=str(calls_log))
        env.update(env_change)
        argv = [sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--rules", str(rules_file),
                "--profile", profile] + (["--review"] if review else []) + [str(x) for x in extra]
        return subprocess.run(argv, capture_output=True, encoding="utf-8", input=json.dumps(call), env=env)

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"review {name}: {detail}")

    def asked(done):
        try:
            out = json.loads(done.stdout)["hookSpecificOutput"]
        except (ValueError, KeyError, TypeError):
            return ""
        return out["permissionDecisionReason"] if out.get("permissionDecision") == "ask" else ""

    remove = {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}}
    done = hook(remove)
    check("block turns the director's G10 ask into a deny", done.returncode == 2 and done.stdout == ""
          and done.stderr.startswith("BLOCKED by hook_guard [G10]: second-model review: looks (risky) to me")
          and not re.search(r"<[^>]*>", done.stderr), done.stderr)
    seen = calls()
    argv = seen[-1]["argv"] if seen else []
    check("the review runs claude -p with no hooks and no tools, marked against recursion", len(seen) == 1
          and argv[:3] == ["-p", "--model", "haiku"] and argv[argv.index("--settings") + 1] == '{"disableAllHooks":true}'
          and argv[argv.index("--tools") + 1] == "" and "--no-session-persistence" in argv
          and argv[argv.index("--output-format") + 1] == "json" and seen[-1]["guard"] == "1"
          and "rm -rf build" in argv[-1] and "Rule G10" in argv[-1], json.dumps(seen))
    hook({"tool_name": "Bash", "tool_input": {"command": f"gh pr comment 3 --body {fake_key}"}})
    prompt = calls()[-1]["argv"][-1] if len(calls()) == 2 else ""
    check("the prompt has the tool input masked", "[MASKED:" in prompt and fake_key not in prompt and "Rule G20" in prompt, prompt)
    done = hook(remove, mode="ok")
    check("no_objection keeps the ask and says so", done.returncode == 0
          and asked(done).startswith("[G10] ") and "(second-model review: no objection: looks (risky) to me)" in asked(done), done.stdout)
    for mode, says in (("garbage", "reply is not the agreed JSON"), ("exit1", "exit 1"), ("extra", "reply is not the agreed JSON")):
        done = hook(remove, mode=mode)
        check(f"{mode} reply keeps the ask as unavailable", done.returncode == 0
              and f"(second-model review unavailable: {says})" in asked(done), done.stdout + done.stderr)
    quick = rules_copy("quick", review=dict(data["review"], timeout_s=1))
    started = time.time()
    done = hook(remove, mode="sleep", rules_file=quick)
    check("a review past timeout_s keeps the ask", done.returncode == 0 and "unavailable: timed out" in asked(done)
          and time.time() - started < 7, f"{time.time() - started:.1f}s {done.stdout}")
    done = hook(remove, CLAUDE_CODE_EXECPATH="", PATH=str(empty_path))
    check("no claude at all keeps the ask", done.returncode == 0 and "unavailable: no claude executable" in asked(done),
          done.stdout + done.stderr)
    before = len(calls())
    worker = hook(remove, profile="worker")
    allowed = hook({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    plain = hook(remove, review=False)
    narrow = hook(remove, rules_file=rules_copy("narrow", review=dict(data["review"], categories=["push"])))
    inner = hook(remove, DW_HOOK_REVIEW="1")
    check("never reviewed: a deny, a silent pass, no --review, another category, a review's own calls",
          len(calls()) == before and worker.returncode == 2 and worker.stderr.startswith("BLOCKED by hook_guard [G10]: ")
          and "second-model" not in worker.stderr and allowed.returncode == 0 and allowed.stdout == ""
          and all(asked(d).startswith("[G10] ") and "second-model" not in asked(d) for d in (plain, narrow, inner)),
          " | ".join(d.stdout + d.stderr for d in (worker, allowed, plain, narrow, inner)))
    done = hook(remove, rules_file=rules_copy("no_review", review=None))
    check("--review without a review section is refused", done.returncode == 1 and "review section" in done.stderr, done.stderr)
    for name, value in (("zero timeout", dict(data["review"], timeout_s=0)), ("no categories", dict(data["review"], categories=[])),
                        ("odd model", dict(data["review"], model="haiku; rm -rf /"))):
        done = hook(remove, rules_file=rules_copy(name.replace(" ", "_"), review=value))
        check(f"bad review section ({name}) is refused", done.returncode == 1 and "bad rules file" in done.stderr
              and "review" in done.stderr, done.stderr)
    log = folder / "audit.jsonl"
    hook(remove, extra=("--audit", log))
    hook(remove, mode="ok", extra=("--audit", log))
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    check("--audit says what the review did and which claude ran it",
          [(e["result"]["status"], e["rule"]) for e in lines] == [("deny", "G10 review=block via=CLAUDE_CODE_EXECPATH"),
                                                                  ("ask", "G10 review=no_objection via=CLAUDE_CODE_EXECPATH")],
          json.dumps(lines))
    expect("review audit chain verifies", "audit_log.py", 0, "verify", "--log", log, says=["entries=2", " OK"])
    # setup --guard-review: the switch goes on the guarded entry; the hook test never starts a review
    wt = folder / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    (wt / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    setup = ("--repo", wt, "--only-this", "--guard-profile", "director", "--guard-mode", "block")
    expect("setup without review", "setup_project_settings.py", 0, *setup, "--apply", says="SET")
    expect("setup review missing", "setup_project_settings.py", 1, *setup, "--guard-review", says="MISSING")
    expect("setup review written and tested", "setup_project_settings.py", 0, *setup, "--guard-review", "--apply",
           says=["SET", "guard_review=on", "block-rule=2"])
    command = json.loads((wt / ".claude" / "settings.local.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    check("setup puts --review on the guarded command", command.endswith(" --review") and "--profile director" in command, command)
    expect("setup review kept on rerun without the option", "setup_project_settings.py", 0, *setup, says="OK")


def test_guard_modes(tmp):
    """1.3.1: a flagged call is a reminder by default (it runs), ask on --mode ask, a deny only on --mode block; the
    pause flag denies in every mode. A here-document body and quoted text are not commands. setup installs remind
    unless --guard-mode says otherwise, and writes rule permissions only as the mode wants them."""
    global total
    folder = tmp / "modes"
    folder.mkdir()

    def hook(cmd, *args, tool="Bash", inp=None):
        call = {"tool_name": tool, "tool_input": inp if inp is not None else
                {"command": cmd} if tool in ("Bash", "Monitor", "PowerShell") else {}}
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), *map(str, args)],
                              input=json.dumps(call), capture_output=True, encoding="utf-8")

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"guard modes {name}: {str(detail)[-500:]}")

    def out(done):
        try:
            return json.loads(done.stdout)
        except ValueError:
            return {}

    # the three modes on git push
    done = hook("git push origin main")
    got = out(done)
    hso = got.get("hookSpecificOutput") or {}
    check("default remind: exit 0, the reminder to the user and the model, no decision", done.returncode == 0
          and got.get("systemMessage", "").startswith("hook_guard reminder [builtin]: git push")
          and hso.get("additionalContext", "").startswith(got.get("systemMessage", "-"))
          and "do not ask again" in hso.get("additionalContext", "") and "permissionDecision" not in hso
          and done.stderr == "", done.stdout + done.stderr)
    done = hook("git push origin main", "--mode", "ask")
    hso = out(done).get("hookSpecificOutput") or {}
    check("ask: exit 0 and permissionDecision ask with the rule", done.returncode == 0 and hso.get("permissionDecision") == "ask"
          and hso.get("permissionDecisionReason", "").startswith("[builtin] git push"), done.stdout + done.stderr)
    done = hook("git push origin main", "--mode", "block")
    check("block: exit 2 and BLOCKED on stderr", done.returncode == 2 and "BLOCKED by hook_guard" in done.stderr
          and done.stdout == "", done.stdout + done.stderr)
    for mode in ("remind", "ask", "block"):
        done = hook("git status", "--mode", mode)
        check(f"{mode}: an unflagged call is silent", done.returncode == 0 and done.stdout == "" and done.stderr == "",
              done.stdout + done.stderr)
    rules = ("--rules", TOOLS / "guard_rules.json", "--profile", "worker")
    for cmd in ("gh pr merge 3", "rm -rf build", "git reset --hard HEAD~1"):
        done = hook(cmd, *rules)
        check(f"remind does not stop {cmd!r}", done.returncode == 0 and "hook_guard reminder" in done.stdout, done.stdout + done.stderr)
    done = hook("", *rules, tool="mcp__shop__buy_item")
    check("rules in remind mode: a rule hit is a reminder", done.returncode == 0 and "hook_guard reminder [G" in done.stdout,
          done.stdout + done.stderr)
    done = hook("", *rules, "--mode", "block", tool="mcp__shop__buy_item")
    check("rules in block mode: the same call is denied", done.returncode == 2, done.stdout + done.stderr)
    log = folder / "audit.jsonl"
    hook("git push", "--audit", log)
    check("remind is on the action log", '"remind"' in log.read_text(encoding="utf-8") if log.exists() else False,
          log.read_text(encoding="utf-8") if log.exists() else "no log")
    pause = folder / "PAUSE"
    pause.write_text("stop\n", encoding="utf-8")
    done = hook("git push", *rules, "--pause-flag", pause)
    check("the pause flag denies in remind mode", done.returncode == 2 and "PAUSED" in done.stderr, done.stdout + done.stderr)
    pause.unlink()

    # 1.3.1 (Director): reading a secret is denied in every mode, an approval does not cover it; git push still runs
    for mode in ("remind", "ask"):
        done = hook("", *rules, "--mode", mode, tool="Read", inp={"file_path": ".env"})
        check(f"{mode}: Read .env is denied [G50]", done.returncode == 2 and done.stdout == ""
              and done.stderr.startswith("BLOCKED by hook_guard [G50]"), done.stdout + done.stderr)
    for cmd, rid in (("cat .env", "G50"), ("cat ~/.ssh/id_ed25519", "G50"), ("printenv GITHUB_TOKEN", "G51"),
                     ("gh auth token", "G52")):
        done = hook(cmd, *rules)
        check(f"remind: {cmd!r} is denied [{rid}]", done.returncode == 2 and done.stdout == ""
              and done.stderr.startswith(f"BLOCKED by hook_guard [{rid}]"), done.stdout + done.stderr)
    done = hook("git push origin main", *rules)
    check("remind with rules: git push still runs with a reminder", done.returncode == 0
          and "hook_guard reminder" in done.stdout and done.stderr == "", done.stdout + done.stderr)
    done = hook("cat README.md", *rules)
    check("remind with rules: an ordinary read is silent", done.returncode == 0 and done.stdout == "" and done.stderr == "",
          done.stdout + done.stderr)
    hook("cat .env", *rules, "--audit", log)
    check("a secret deny in remind mode is on the action log as a deny", '"deny"' in log.read_text(encoding="utf-8"),
          log.read_text(encoding="utf-8"))

    # here-documents and quoted text are not commands (block mode, so a miss is an exit 2)
    cases = [
        ("a log heredoc that names git push origin", "cat >> notes.md <<'EOF'\n- next: git push origin main\nEOF", 0),
        ("an unquoted heredoc body", "cat > a.txt <<EOF\ngit push --force\nEOF", 0),
        ("a <<- heredoc with tabs", "cat <<-END\n\tgit push\n\tEND", 0),
        ('a double-quoted delimiter', 'cat <<"X"\ngit push\nX', 0),
        ("two heredocs on one line", "cat <<A <<B\ngit push\nA\ngit tag v1\nB", 0),
        ("python reading a heredoc", "python - <<'PY'\nimport os\nos.system('git push')\nPY", 0),
        ("echo of quoted text", 'echo "git push origin"', 0),
        ("a commit message that names git push", 'git commit -m "docs: say when to git push"', 0),
        ("a here-string", 'cat <<< "git push"', 0),
        ("$(...) in an unquoted heredoc still runs", "cat <<EOF\n$(git push)\nEOF", 2),
        ("backticks in an unquoted heredoc still run", "cat <<EOF\n`git push`\nEOF", 2),
        ("$(...) in a quoted heredoc is text", "cat <<'EOF'\n$(git push)\nEOF", 0),
        ("a command after the heredoc is checked", "cat <<'EOF'\ntext\nEOF\ngit push", 2),
        ("a command on the heredoc line is checked", "cat <<'EOF' && git push\ntext\nEOF", 2),
        ("no closing line: checked as it is", "cat <<'EOF'\ngit push", 2),
        ("arithmetic << is not a heredoc", "echo $((1<<2))\ngit push", 2),
    ]
    for name, cmd, code in cases:
        done = hook(cmd, "--mode", "block")
        check(f"heredoc/quote: {name}", done.returncode == code, f"exit {done.returncode}: {done.stderr}")
    done = hook("cat <<'EOF'\ngit push\nEOF", "--mode", "block", tool="Monitor")
    check("heredoc/quote: a Monitor heredoc body is text too", done.returncode == 0, done.stderr)

    # setup: remind by default, --guard-mode ask / block on request; rule permissions follow the mode
    repo = folder / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    settings = repo / ".claude" / "settings.local.json"
    base = ("--repo", repo, "--only-this")

    def command():
        return json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

    def perms():
        return json.loads(settings.read_text(encoding="utf-8")).get("permissions") or {}

    expect("setup --hooks installs remind and tests it", "setup_project_settings.py", 0, *base, "--hooks", "--apply",
           says=["SET", "allow=0 block=remind"])
    check("the remind command has no --mode", "--mode" not in command(), command())
    expect("remind rerun is OK", "setup_project_settings.py", 0, *base, "--hooks", says="OK")
    expect("--guard-mode ask differs from the remind entry", "setup_project_settings.py", 1, *base, "--hooks", "--guard-mode",
           "ask", says="hooks.PreToolUse")
    expect("--guard-mode ask written and tested", "setup_project_settings.py", 0, *base, "--hooks", "--guard-mode", "ask",
           "--apply", says=["SET", "block=ask"])
    check("the ask command has --mode ask", " --mode ask" in command(), command())
    expect("--guard-mode block written and tested", "setup_project_settings.py", 0, *base, "--hooks", "--guard-mode", "block",
           "--apply", says=["SET", "block=2"])
    expect("a rerun without --guard-mode keeps block", "setup_project_settings.py", 0, *base, "--hooks", says=["OK", "block=2"])
    expect("an unknown mode is refused", "setup_project_settings.py", 2, *base, "--hooks", "--guard-mode", "brake")
    expect("guard profile in block mode", "setup_project_settings.py", 0, *base, "--guard-profile", "worker", "--apply",
           says=["SET", "block-rule=2"])
    check("block mode writes the deny rules", "Bash(git push *)" in perms().get("deny", []), perms())
    data = json.loads(settings.read_text(encoding="utf-8"))
    data["permissions"]["deny"].append("Bash(my-own-rule *)")
    settings.write_text(json.dumps(data), encoding="utf-8")
    expect("remind mode wants the rule permissions out", "setup_project_settings.py", 1, *base, "--guard-profile", "worker",
           "--guard-mode", "remind", says="permissions.deny")
    expect("remind mode with a profile written and tested", "setup_project_settings.py", 0, *base, "--guard-profile", "worker",
           "--guard-mode", "remind", "--apply", says=["SET", "block-rule=remind"])
    g50 = next(r for r in json.loads((TOOLS / "guard_rules.json").read_text(encoding="utf-8"))["rules"]
               if r["id"] == "G50")["permissions"]
    check("remind takes the rule permissions out, keeps the secret deny and the user's own",
          sorted(perms().get("deny", [])) == sorted(g50 + ["Bash(my-own-rule *)"]) and not perms().get("ask"), perms())
    expect("ask mode with a profile written", "setup_project_settings.py", 0, *base, "--guard-profile", "worker",
           "--guard-mode", "ask", "--apply", says=["SET", "block-rule=ask"])
    check("ask mode puts every rule permission under ask but the secret deny", "Bash(git push *)" in perms().get("ask", [])
          and sorted(perms().get("deny", [])) == sorted(g50 + ["Bash(my-own-rule *)"])
          and not set(g50) & set(perms().get("ask", [])), perms())

    # the template is what the default --runtime-guard writes
    wt = folder / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    (wt / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    pause, log = folder / "PAUSE2", folder / "audit" / "wt.jsonl"
    expect("setup --runtime-guard in remind mode", "setup_project_settings.py", 0, "--repo", wt, "--only-this",
           "--runtime-guard", "--pause-flag", pause, "--audit-log", (folder / "audit" / "{worktree}.jsonl").as_posix(), "--apply",
           says=["SET", "block-rule=remind"])
    written = json.loads((wt / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    template = (TEMPLATES / "settings.runtime-guard.json").read_text(encoding="utf-8")
    template = template.replace("<PYTHON>", pathlib.Path(sys.executable).as_posix()).replace("<DW>/tools", TOOLS.as_posix())
    template = json.loads(template.replace("<PAUSE_FLAG>", pause.resolve().as_posix()).replace("<AUDIT_LOG>", log.resolve().as_posix()))
    check("the template is what setup --runtime-guard writes (remind: only the secret deny)",
          written.get("permissions", {}).get("deny") == g50 and not written["permissions"].get("ask")
          and template == {"hooks": written["hooks"], "permissions": {"deny": written["permissions"]["deny"]},
                           "env": {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB":
                                                               written["env"].get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB")}},
          json.dumps(template)[:300] + " | " + json.dumps(written)[:300])


def test_doctor(tmp):
    """1.1.0 batch 2: setup --runtime-guard writes what templates/settings.runtime-guard.json shows; doctor.py reports
    what is in force (fake claude executables, settings layers in temp folders, never the real claude)."""
    global total
    folder = tmp / "doctor"
    folder.mkdir()
    main_repo, wt, home, empty_root = folder / "main", folder / "wt", folder / "home", folder / "root"
    for path in (main_repo, home / ".claude", empty_root, folder / "audit"):
        path.mkdir(parents=True)

    def git_in(repo, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                       capture_output=True)

    git_in(main_repo, "init", "-q")
    git_in(main_repo, "commit", "-q", "--allow-empty", "-m", "init")
    git_in(main_repo, "worktree", "add", "-q", "--detach", str(wt))
    (main_repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")

    def fake(name, version):
        path = folder / f"{name}.py"
        path.write_text("import sys\nprint('" + version + " (Claude Code)' if sys.argv[1:] == ['--version'] else 'no')\n",
                        encoding="utf-8")
        return path

    new, old, mid = fake("claude_new", "2.1.317"), fake("claude_old", "2.1.291"), fake("claude_mid", "2.1.300")
    fake_token = "".join(["dw", "fake", "Q7x" * 10])  # built at run time: a value that must never be printed
    spec = importlib.util.spec_from_file_location("doctor_for_test", TOOLS / "doctor.py")
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    clean_env = {k: v for k, v in os.environ.items() if not doctor.CREDENTIAL_NAME.search(k) and not doctor.PROXY_NAME.match(k)
                 and k not in ("CLAUDE_CODE_EXECPATH", "CLAUDE_PID", "CLAUDE_CODE_GIT_BASH_PATH", "DW_GIT_MODE")}
    outputs = []

    def doc(*args, repo=wt, path_claude=(new,), env_change=None, fs_root=empty_root):
        env = dict(clean_env, CLAUDE_CODE_EXECPATH=str(new))
        env.update(env_change or {})
        env = {k: v for k, v in env.items() if v is not None}
        argv = [sys.executable, "-I", "-X", "utf8", str(TOOLS / "doctor.py"), "--repo", str(repo), "--home", str(home),
                "--managed", str(folder / "managed.json"), "--fs-root", str(fs_root)]
        argv += [x for p in path_claude for x in ("--path-claude", str(p))] + [str(x) for x in args]
        done = subprocess.run(argv, capture_output=True, encoding="utf-8", env=env)
        outputs.append(done.stdout + done.stderr)
        return done

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"doctor {name}: {detail[-600:]}")

    def line(done, name):
        found = [x for x in done.stdout.splitlines() if re.match(r"\w+ +" + re.escape(name) + ":", x)]
        return found[0] if found else ""

    # setup --runtime-guard
    log = folder / "audit" / "wt.jsonl"
    pause = folder / "PAUSE"
    setup = ("--repo", wt, "--only-this", "--pause-flag", pause, "--guard-mode", "block")
    expect("setup plain first", "setup_project_settings.py", 0, *setup, "--apply", says="SET")
    expect("setup --runtime-guard default log is in the git common dir", "setup_project_settings.py", 1, *setup,
           "--runtime-guard", says=["runtime_guard=on", "guard_profile=worker", "director-audit/{worktree}-{container}.jsonl",
                                    "env.CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"])
    guard = setup + ("--runtime-guard", "--audit-log", (folder / "audit" / "{worktree}.jsonl").as_posix())
    expect("setup --runtime-guard written and tested", "setup_project_settings.py", 0, *guard, "--apply",
           says=["SET", "block-rule=2"])
    expect("setup --runtime-guard rerun is OK", "setup_project_settings.py", 0, *guard, says="OK")
    settings_file = wt / ".claude" / "settings.local.json"
    written = json.loads(settings_file.read_text(encoding="utf-8"))
    backups = list((main_repo / ".git" / "director-settings-backup").glob("*.settings.local.json"))
    check("one entry per hook event and a backup of the file before", [len(written["hooks"][e]) for e in
          ("PreToolUse", "PostToolUse", "PostToolUseFailure")] == [1, 1, 1] and len(backups) == 1, json.dumps(written["hooks"]))
    good = settings_file.read_text(encoding="utf-8")

    # the full set
    done = doc()
    check("full set: hook, Monitor and worktree ENFORCED, log not yet written, isolation NOT_ENFORCED", done.returncode == 1
          and line(done, "hook_guard").startswith("ENFORCED") and "onFailure block, claude 2.1.317" in line(done, "hook_guard")
          and line(done, "Monitor commands").startswith("ENFORCED") and line(done, "audit_log").startswith("CONFIGURED_NOT_VERIFIED")
          and line(done, "permissions").startswith("CONFIGURED_NOT_VERIFIED") and line(done, "env_scrub").startswith("CONFIGURED_NOT_VERIFIED")
          and line(done, "isolation").startswith("NOT_ENFORCED") and line(done, "worktree").startswith("ENFORCED")
          and "INFO                     pause: off" in done.stdout and "review:" not in done.stdout
          and "DOCTOR: enforced=" in (done.stdout.splitlines() or [""])[-1], done.stdout + done.stderr)
    subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "hook_guard.py"), "--mode", "block", "--rules", str(TOOLS / "guard_rules.json"),
                    "--profile", "worker", "--audit", str(log)], input=json.dumps({"tool_name": "Bash", "tool_input":
                    {"command": "git push"}}), capture_output=True, encoding="utf-8")
    done = doc()
    check("a log that verifies is ENFORCED", line(done, "audit_log").startswith("ENFORCED") and "entries=1" in line(done, "audit_log"), done.stdout)
    log.write_text(log.read_text(encoding="utf-8").replace("git push", "git pull"), encoding="utf-8")
    done = doc()
    check("a broken log chain is NOT_ENFORCED", line(done, "audit_log").startswith("NOT_ENFORCED"), done.stdout)
    log.unlink()

    # versions
    done = doc(path_claude=(new, old))
    check("versions: effective via CLAUDE_CODE_EXECPATH, every PATH claude listed, an old one is a WARN",
          "effective 2.1.317 via CLAUDE_CODE_EXECPATH" in done.stdout and "PATH 2.1.291" in done.stdout
          and line(done, "old claude on PATH").startswith("WARN") and "warn=1" in done.stdout, done.stdout)
    done = doc(path_claude=(old, new), env_change={"CLAUDE_CODE_EXECPATH": None})
    check("without CLAUDE_CODE_EXECPATH the first PATH claude is the effective one", "effective 2.1.291 via PATH" in done.stdout
          and line(done, "hook_guard").startswith("NOT_ENFORCED") and "< 2.1.295" in line(done, "hook_guard")
          and line(done, "Monitor commands").startswith("NOT_ENFORCED"), done.stdout)
    done = doc(path_claude=(old,), env_change={"CLAUDE_CODE_EXECPATH": None, "CLAUDE_PID": str(os.getpid())})
    check("CLAUDE_PID names the effective executable", "via CLAUDE_PID" in done.stdout
          and pathlib.Path(sys.executable).name.lower() in done.stdout.lower(), done.stdout)
    done = doc(env_change={"CLAUDE_CODE_EXECPATH": str(mid), "CLAUDE_CODE_GIT_BASH_PATH": ""})
    check("2.1.300: Monitor NOT_ENFORCED; on Windows without Git Bash the hook item too",
          line(done, "Monitor commands").startswith("NOT_ENFORCED") and line(done, "hook_guard").startswith("ENFORCED")
          and (os.name != "nt" or line(done, "hook without Git Bash").startswith("NOT_ENFORCED")), done.stdout)
    if os.name == "nt":
        done = doc(env_change={"CLAUDE_CODE_EXECPATH": str(mid), "CLAUDE_CODE_GIT_BASH_PATH": str(new)})
        check("2.1.300 with Git Bash found", line(done, "hook without Git Bash").startswith("ENFORCED"), done.stdout)

    # settings layers
    user_settings = home / ".claude" / "settings.json"
    for layer, path in (("user", user_settings), ("managed", folder / "managed.json")):
        path.write_text('{"disableAllHooks": true}', encoding="utf-8")
        done = doc()
        check(f"disableAllHooks in the {layer} layer turns the hooks off", line(done, "hook_guard").startswith("NOT_ENFORCED")
              and f"in the {layer} settings" in line(done, "hook_guard") and line(done, "audit_log").startswith("NOT_ENFORCED"), done.stdout)
        path.unlink()
    user_settings.write_text(json.dumps({"hooks": written["hooks"]}), encoding="utf-8")
    settings_file.write_text(json.dumps({k: v for k, v in written.items() if k != "hooks"}), encoding="utf-8")
    done = doc()
    check("hooks in the user layer count for the worktree", line(done, "hook_guard").startswith("ENFORCED"), done.stdout)
    user_settings.unlink()
    (wt / ".claude" / "settings.json").write_text('{"env": {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1"}}', encoding="utf-8")
    settings_file.write_text(json.dumps(dict(written, env={"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "0"})), encoding="utf-8")
    done = doc()
    check("an env key in the local layer wins over the project layer", line(done, "env_scrub").startswith("MISSING"), done.stdout)
    (wt / ".claude" / "settings.json").unlink()

    # broken or partial hooks
    def variant(name, change, status, says):
        data = json.loads(good)
        change(data)
        settings_file.write_text(json.dumps(data), encoding="utf-8")
        done = doc()
        check(name, done.returncode == 1 and line(done, says[0]).startswith(status) and all(s in done.stdout for s in says[1:]), done.stdout)

    def pre(data):
        return data["hooks"]["PreToolUse"][0]

    variant("a matcher that is not * is MISSING", lambda d: pre(d).update(matcher="Bash"), "MISSING", ["hook_guard", "matcher 'Bash'"])
    variant("no onFailure is MISSING", lambda d: pre(d)["hooks"][0].pop("onFailure"), "MISSING", ["hook_guard", "onFailure None"])
    variant("a hook_guard.py that is not there is NOT_ENFORCED", lambda d: pre(d)["hooks"][0].update(
        command=pre(d)["hooks"][0]["command"].replace("tools/hook_guard.py", "gone/hook_guard.py")), "NOT_ENFORCED",
        ["hook_guard", "did not answer"])
    variant("no PostToolUse is MISSING", lambda d: d["hooks"].pop("PostToolUse"), "MISSING", ["audit_log", "PostToolUse"])
    variant("a missing deny rule is MISSING", lambda d: d["permissions"]["deny"].pop(), "MISSING", ["permissions", "1 of permissions.deny"])
    variant("defaultMode bypassPermissions is a WARN", lambda d: d["permissions"].update(defaultMode="bypassPermissions"),
            "WARN", ["permission mode"])
    settings_file.write_text(good, encoding="utf-8")

    # names only, never values
    fake_name = "DW_FAKE_TOKEN"
    fake_env = {fake_name: fake_token, "HTTPS_PROXY": "http://u" + ":" + fake_token + "@proxy.invalid:8080"}
    done = doc("--probe", env_change=fake_env)
    check("--probe lists credential-like names and a proxy with a password, not their values",
          line(done, "env_scrub").startswith("NOT_ENFORCED") and "DW_FAKE_TOKEN" in done.stdout and "HTTPS_PROXY" in done.stdout, done.stdout)
    done = doc("--probe")
    check("--probe with no credential-like names is ENFORCED", line(done, "env_scrub").startswith("ENFORCED"), done.stdout)

    # isolation, worktree, pause, review
    container = folder / "container"
    (container / "proc" / "1").mkdir(parents=True)
    (container / "proc" / "1" / "cgroup").write_text("0::/docker/0123abcd\n", encoding="utf-8")
    done = doc(repo=main_repo, fs_root=container)
    check("a container cgroup without --probe is CONFIGURED_NOT_VERIFIED", line(done, "isolation").startswith("CONFIGURED_NOT_VERIFIED"), done.stdout)
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    done = doc("--probe", "--director", folder, "--egress", f"127.0.0.1:{port}", "--dns-name", "localhost", fs_root=container,
               env_change={fake_name: fake_token})
    check("container --probe: a writable root and DIRECTOR and a credential name fail, a refused connection passes",
          line(done, "isolation").startswith("NOT_ENFORCED") and "root read-only FAIL" in done.stdout
          and "DIRECTOR read-only FAIL" in done.stdout and f"no connection to 127.0.0.1:{port} ok" in done.stdout
          and "no credential names FAIL" in done.stdout, done.stdout)
    check("container --probe: a name that resolves fails the DNS check (localhost); a linked worktree is the shared .git",
          "localhost does not resolve FAIL" in done.stdout and "own .git (K1) FAIL" in done.stdout, done.stdout)
    done = doc("--probe", "--egress", f"127.0.0.1:{port}", "--dns-name", "dw-doctor-probe.invalid", repo=main_repo, fs_root=container)
    check("container --probe: a name that does not resolve passes the DNS check",
          "dw-doctor-probe.invalid does not resolve ok" in done.stdout, done.stdout)
    done = doc(repo=main_repo, fs_root=container, env_change={"DW_GIT_MODE": "shared"})
    check("container, DW_GIT_MODE=shared, no --probe: isolation NOT_ENFORCED (K1 shared .git)",
          line(done, "isolation").startswith("NOT_ENFORCED") and "K1 shared .git" in done.stdout and done.returncode == 1,
          done.stdout)
    done = doc("--probe", "--egress", f"127.0.0.1:{port}", "--dns-name", "dw-doctor-probe.invalid", fs_root=container,
               repo=main_repo, env_change={"DW_GIT_MODE": "shared"})
    check("container --probe, DW_GIT_MODE=shared: own .git (K1) FAIL", line(done, "isolation").startswith("NOT_ENFORCED")
          and "own .git (K1) FAIL" in done.stdout, done.stdout)
    done = doc(fs_root=container, env_change={"DW_GIT_MODE": "clone"})
    check("container, a linked worktree with DW_GIT_MODE=clone is still the shared .git (K1)",
          "K1 shared .git" in line(done, "isolation"), done.stdout)
    done = doc(repo=main_repo, fs_root=container, env_change={"DW_GIT_MODE": "clone"})
    check("container, DW_GIT_MODE=clone in a clone: worktree ENFORCED (its own clone), isolation not yet verified",
          line(done, "worktree").startswith("ENFORCED") and "own clone" in line(done, "worktree")
          and line(done, "isolation").startswith("CONFIGURED_NOT_VERIFIED"), done.stdout)
    done = doc(repo=main_repo, env_change={"DW_GIT_MODE": "clone"})
    check("outside a container DW_GIT_MODE is ignored: the main checkout is still NOT_ENFORCED",
          line(done, "worktree").startswith("NOT_ENFORCED"), done.stdout)
    (empty_root / ".dockerenv").write_text("", encoding="utf-8")
    done = doc(repo=main_repo)
    check("/.dockerenv means a container", line(done, "isolation").startswith("CONFIGURED_NOT_VERIFIED"), done.stdout)
    (empty_root / ".dockerenv").unlink()
    done = doc(repo=main_repo)
    check("the main checkout is not a worker's worktree", line(done, "worktree").startswith("NOT_ENFORCED")
          and line(done, "hook_guard").startswith("MISSING"), done.stdout)
    pause.write_text("paused by the selftest\n", encoding="utf-8")
    done = doc()
    check("the pause flag is shown", "pause: on: paused by the selftest" in done.stdout, done.stdout)
    pause.unlink()
    expect("setup --runtime-guard --guard-review", "setup_project_settings.py", 0, *guard, "--guard-review", "--apply", says="SET")
    done = doc()
    check("review on is shown with its quota use", "review: on" in done.stdout and "quota" in done.stdout
          and line(done, "hook_guard").startswith("ENFORCED"), done.stdout)
    expect("setup --runtime-guard back to remind", "setup_project_settings.py", 0, *guard, "--guard-mode", "remind", "--apply",
           says=["SET", "block-rule=remind"])
    done = doc()
    check("remind mode: hook_guard ENFORCED with its mode, no permission rule wanted", line(done, "hook_guard").startswith("ENFORCED")
          and "mode remind" in line(done, "hook_guard") and "remind mode" in line(done, "permissions"), done.stdout)
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    data.setdefault("permissions", {}).setdefault("deny", []).append("Bash(git push *)")
    settings_file.write_text(json.dumps(data), encoding="utf-8")
    done = doc()
    check("remind mode: a rule permission left in deny is MISSING (it would still stop the call)",
          line(done, "permissions").startswith("MISSING") and "remind mode does not want" in line(done, "permissions"), done.stdout)
    done = doc(repo=folder)
    check("outside a git repo exit 2", done.returncode == 2 and "not inside a git repo" in done.stderr, done.stderr)
    check("no doctor run printed the fake credential value", all(fake_token not in out for out in outputs), "value leaked")


def test_doctor_launch(tmp):
    """1.3.0 item 9: doctor lists each worktree's hook_guard settings against the sessions that started there (from the
    transcripts' cwd) and WARNs on settings no session reads; with a --sessions file the permission check is the mildest."""
    global total
    folder = tmp / "launch"
    main_repo, wt, home = folder / "main", folder / "wt", folder / "home"
    for path in (main_repo, home / ".claude" / "projects"):
        path.mkdir(parents=True)

    def git_in(repo, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                       capture_output=True)

    git_in(main_repo, "init", "-q")
    git_in(main_repo, "commit", "-q", "--allow-empty", "-m", "init")
    git_in(main_repo, "worktree", "add", "-q", "--detach", str(wt))
    (main_repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n", encoding="utf-8")
    main_repo, wt = main_repo.resolve(), wt.resolve()
    (main_repo / "sub").mkdir()

    def transcript(cwd, name, age_days=0):
        project = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
        project.mkdir(parents=True, exist_ok=True)
        path = project / f"{name}.jsonl"
        path.write_text(json.dumps({"type": "queue-operation"}) + "\n" + json.dumps(
            {"type": "user", "cwd": str(cwd), "timestamp": "2026-11-07T01:00:00.000Z", "sessionId": name}) + "\n",
            encoding="utf-8")
        if age_days:
            old = time.time() - age_days * 86400
            os.utime(path, (old, old))

    def doc(*args):
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "doctor.py"), "--repo", str(main_repo),
                               "--home", str(home), "--managed", str(folder / "managed.json"), "--path-claude",
                               str(folder / "none.py"), *[str(x) for x in args]], capture_output=True, encoding="utf-8")
        return done.stdout + done.stderr

    def check(name, ok, detail):
        global total
        total += 1
        if not ok:
            failures.append(f"doctor launch {name}: {detail[-700:]}")

    expect("guard the worktree only", "setup_project_settings.py", 0, "--repo", wt, "--only-this", "--guard-mode", "block", "--guard-profile", "worker",
           "--apply", says="SET")
    transcript(main_repo, "s-main")
    transcript(main_repo / "sub", "s-sub")
    transcript(wt, "s-old", age_days=90)
    out = doc()
    check("counts the main checkout's sessions, a subfolder too", f"launch: {main_repo.as_posix()} sessions=2 last=2026-11-07 "
          "hook_guard=no" in out, out)
    check("an old transcript does not count", f"launch: {wt.as_posix()} sessions=0 hook_guard=yes" in out, out)
    check("settings no session reads are a WARN", re.search(r"WARN +settings unread: " + re.escape(wt.as_posix()), out)
          is not None and "sessions start in: " + main_repo.as_posix() in out, out)
    check("the unguarded launch folder is a WARN", re.search(r"WARN +launch folder unguarded: 2 session\(s\) started in "
          + re.escape(main_repo.as_posix()), out) is not None, out)
    out = doc("--launch-days", 120)
    check("--launch-days takes the old one in", f"launch: {wt.as_posix()} sessions=1" in out and "settings unread" not in out, out)
    transcript(wt, "s-wt")
    out = doc()
    check("a session in the guarded worktree clears that WARN", "settings unread" not in out
          and f"launch: {wt.as_posix()} sessions=1" in out, out)
    shutil.rmtree(home / ".claude" / "projects")
    out = doc()
    check("no transcripts folder: not checked, no WARN", "launch folders: no " in out and "settings unread" not in out
          and "launch folder unguarded" not in out, out)

    # a sessions file: the permission check takes the mildest decision, as setup wrote it
    smap = folder / "sessions.json"
    smap.write_text(json.dumps({"schema_version": 1, "default": "worker", "sessions": {"S-C": "cleaner", "S-D": "director"}}),
                    encoding="utf-8")
    expect("setup the map in the main checkout", "setup_project_settings.py", 0, "--repo", main_repo, "--only-this", "--guard-mode", "block",
           "--session-map", smap, "--apply", says="SET")
    out = doc()
    check("doctor reads the sessions file", "sessions: " in out and "cleaner, director, worker" in out
          and not re.search(r"MISSING +permissions", out), out)
    smap.write_text("{", encoding="utf-8")
    out = doc()
    check("a broken sessions file is MISSING", re.search(r"MISSING +sessions file: bad sessions file", out) is not None, out)


def test_container(tmp):
    """1.1.0 batch 2: tools/container files without Docker. run_worker.sh --dry-run prints the docker command; the
    Dockerfile pins the base image and Claude Code; init_firewall.sh allows only the listed hosts. Docker itself is
    tested by hand (TASK REPORT), not here."""
    global total
    box = TOOLS / "container"
    folder = tmp / "container"
    wt, director, linked = folder / "wt", folder / "DIRECTOR", folder / "wt-w1"
    gitc = wt / ".git"
    for path in (director, gitc / "worktrees" / "w1", gitc / "hooks", linked):
        path.mkdir(parents=True)
    (gitc / "config").write_text("[core]\n", encoding="utf-8")
    (linked / ".git").write_text(f"gitdir: {gitc.as_posix()}/worktrees/w1\n", encoding="utf-8")

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"container {name}: {detail[-600:]}")

    texts = {p.name: p.read_bytes() for p in box.iterdir() if p.is_file()}
    check("container files have no CR (they run in Linux)", all(b"\r" not in t for t in texts.values()), str(list(texts)))
    attrs = (TOOLS.parent / ".gitattributes").read_text(encoding="utf-8")
    check(".gitattributes keeps *.sh and the Dockerfile LF", "*.sh text eol=lf" in attrs and "tools/container/Dockerfile text eol=lf" in attrs, attrs)
    docker_file = texts["Dockerfile"].decode("utf-8")
    check("Dockerfile pins the base image by digest",
          re.search(r"^FROM python:3\.12-slim-bookworm@sha256:[0-9a-f]{64}$", docker_file, re.M) is not None, docker_file[:300])
    check("Dockerfile pins the Claude Code version and turns off the updater",
          re.search(r"^ARG CLAUDE_VERSION=\d+\.\d+\.\d+$", docker_file, re.M) is not None and "DISABLE_AUTOUPDATER=1" in docker_file, docker_file)
    firewall = texts["init_firewall.sh"].decode("utf-8")
    check("init_firewall.sh: default allowlist is api.anthropic.com only, then REJECT, policy DROP",
          'ALLOW="${DW_ALLOW_DOMAINS:-api.anthropic.com}"' in firewall and "iptables -P OUTPUT DROP" in firewall
          and firewall.rstrip().count("-j REJECT") == 1, firewall)
    check("init_firewall.sh puts /usr/sbin on PATH (iptables is there on Debian; the image PATH has no sbin)",
          re.search(r'^export PATH="/usr/sbin:/sbin:\$PATH"', firewall, re.M) is not None, firewall[:400])
    entry = texts["entrypoint.sh"].decode("utf-8")
    check("entrypoint drops to dw with no capabilities", "--reuid=dw" in entry and "--bounding-set=-all" in entry and "--no-new-privs" in entry, entry)

    spec = importlib.util.spec_from_file_location("doctor_for_container_test", TOOLS / "doctor.py")
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    bash = doctor.git_bash() if os.name == "nt" else shutil.which("bash")
    if not bash:
        print("SKIP run_worker.sh --dry-run cases: no bash (Git Bash on Windows)")
        return

    def run(*args):
        argv = [bash, (box / "run_worker.sh").as_posix(), "--dry-run", *[str(a) for a in args]]
        return subprocess.run(argv, capture_output=True, encoding="utf-8", env={**os.environ, "DW_DNS_UPSTREAM": "192.0.2.53"})

    base = ("--worktree", wt.as_posix(), "--director", director.as_posix(), "--git-common", gitc.as_posix())
    done = run(*base)
    words = shlex.split(done.stdout) if done.returncode == 0 else []
    check("--dry-run prints a docker run command", done.returncode == 0 and words[:2] == ["docker", "run"], done.stdout + done.stderr)
    for flag in ("--rm", "--init", "--read-only", "no-new-privileges"):
        check(f"docker command has {flag}", flag in words, done.stdout)
    check("--cap-drop ALL, and only NET_ADMIN NET_RAW SETUID SETGID SETPCAP added (root firewall step; setpriv drops all)",
          "ALL" in words and words[words.index("--cap-drop") + 1] == "ALL"
          and sorted(words[i + 1] for i, w in enumerate(words) if w == "--cap-add") == ["NET_ADMIN", "NET_RAW", "SETGID", "SETPCAP", "SETUID"], done.stdout)
    mounts = [words[i + 1] for i, w in enumerate(words) if w == "-v"]
    check("main checkout: worktree rw, DIRECTOR ro, its .git/hooks, .git/config and .git/worktrees ro, the Claude volume",
          mounts == [f"{wt.as_posix()}:/work", f"{director.as_posix()}:/director:ro",
                     f"{gitc.as_posix()}/hooks:/work/.git/hooks:ro", f"{gitc.as_posix()}/config:/work/.git/config:ro",
                     f"{gitc.as_posix()}/worktrees:/work/.git/worktrees:ro", "dw-claude-home:/home/dw/.claude"], str(mounts))
    home_dir = pathlib.Path.home().as_posix()
    check("no host home, .ssh or gh config is mounted",
          not any(m.startswith(home_dir + ":") or "/.ssh" in m or "/.config/gh" in m for m in mounts), str(mounts))
    names = sorted(words[i + 1].split("=")[0] for i, w in enumerate(words) if w == "-e")
    check("only the listed environment variables, and no GIT_DIR / GIT_WORK_TREE (they would send every git to this repo)",
          names == ["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "DW_ALLOW_DOMAINS",
                    "DW_DNS_UPSTREAM", "DW_GIT_MODE", "DW_WORKER_NAME", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_KEY_1", "GIT_CONFIG_VALUE_0",
                    "GIT_CONFIG_VALUE_1", "XDG_CACHE_HOME"] and "--env-file" not in words, str(names))
    check("default allowlist is api.anthropic.com; git never auto-gcs or prunes worktrees",
          "DW_ALLOW_DOMAINS=api.anthropic.com" in words and "GIT_CONFIG_KEY_0=gc.auto" in words and "GIT_CONFIG_VALUE_0=0" in words
          and "GIT_CONFIG_KEY_1=gc.worktreePruneExpire" in words and "GIT_CONFIG_VALUE_1=never" in words, done.stdout)
    linked_base = ("--worktree", linked.as_posix(), "--director", director.as_posix(), "--git-common", gitc.as_posix())
    done = run(*linked_base, "--login", "--worktree-name", "w1", "--", "claude", "-p", "hi")
    words = shlex.split(done.stdout) if done.returncode == 0 else []
    mounts = [words[i + 1] for i, w in enumerate(words) if w == "-v"]
    def generated(target):  # the text of the generated file run_worker mounts read-only at target
        source = next((m[:-len(target)] for m in mounts if m.endswith(target)), "")
        if source and os.name == "nt":
            source = subprocess.run([bash, "-c", 'cygpath -w "$1"', "-", source], capture_output=True, encoding="utf-8").stdout.strip()
        return pathlib.Path(source).read_text(encoding="utf-8") if source and pathlib.Path(source).is_file() else None
    check("linked worktree: .git at /repo-git with hooks/, config and worktrees/ ro, its own record rw",
          mounts[2:7] == [f"{gitc.as_posix()}:/repo-git", f"{gitc.as_posix()}/hooks:/repo-git/hooks:ro",
                          f"{gitc.as_posix()}/config:/repo-git/config:ro", f"{gitc.as_posix()}/worktrees:/repo-git/worktrees:ro",
                          f"{gitc.as_posix()}/worktrees/w1:/repo-git/worktrees/w1"] and len(mounts) == 10, str(mounts))
    check("linked worktree: a ro /work/.git file points at worktrees/w1, whose ro gitdir points back at /work/.git",
          generated(":/work/.git:ro") == "gitdir: /repo-git/worktrees/w1\n"
          and generated(":/repo-git/worktrees/w1/gitdir:ro") == "/work/.git\n", str(mounts))
    check("--login adds the sign-in hosts; the command comes last",
          "DW_ALLOW_DOMAINS=api.anthropic.com claude.ai platform.claude.com console.anthropic.com" in words
          and words[-4:] == ["dw-worker:1.2.0", "claude", "-p", "hi"], done.stdout + done.stderr)
    done = run(*base, "--worktree-name", "w1")
    check("--worktree-name on a main checkout exits 2", done.returncode == 2 and "linked worktree" in done.stderr, done.stderr)
    done = run("--worktree", linked.as_posix(), "--director", director.as_posix(), "--git-common", gitc.as_posix())
    check("a linked worktree without --worktree-name exits 2", done.returncode == 2 and "<worktree>/.git" in done.stderr, done.stderr)
    done = run(*base, "--offline")
    check("--offline: --network none and no allowlist", "--network none" in done.stdout and "DW_ALLOW_DOMAINS" not in done.stdout, done.stdout)
    done = run(*linked_base, "--worktree-name", "nope")
    check("an unknown --worktree-name exits 2", done.returncode == 2 and "no worktree named nope" in done.stderr, done.stderr)
    done = run("--worktree", wt.as_posix(), "--git-common", gitc.as_posix())
    check("no --director exits 2", done.returncode == 2 and "--director" in done.stderr, done.stderr)
    bare = folder / "bare.git"
    bare.mkdir()
    done = run("--worktree", wt.as_posix(), "--director", director.as_posix(), "--git-common", bare.as_posix())
    check("a .git without hooks/ and config exits 2 (docker would create them as root)",
          done.returncode == 2 and "hooks/ and config" in done.stderr, done.stderr)


def test_worker_clone(tmp):
    """K1 (1.2.0): worker_clone.sh create gives a clone with nothing pointing back; import takes exactly one branch from
    a bundle into refs/dw-workers/NAME/ and refuses every other bundle without touching the repository. collect (the
    docker part) is tested by hand; run_worker.sh --clone is checked with --dry-run."""
    global total
    box = TOOLS / "container"
    folder = tmp / "worker_clone"
    folder.mkdir()

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"worker_clone {name}: {detail[-600:]}")

    spec = importlib.util.spec_from_file_location("doctor_for_clone_test", TOOLS / "doctor.py")
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    bash = doctor.git_bash() if os.name == "nt" else shutil.which("bash")
    if not bash:
        print("SKIP worker_clone.sh cases: no bash (Git Bash on Windows)")
        return

    def git(where, *args, check_rc=True):
        done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                               "-C", str(where), *map(str, args)], capture_output=True, encoding="utf-8")
        if check_rc and done.returncode:
            raise RuntimeError(f"git {args}: {done.stderr}")
        return done.stdout.strip()

    def tool(*args):
        return subprocess.run([bash, (box / "worker_clone.sh").as_posix(), *[str(a) for a in args]],
                              capture_output=True, encoding="utf-8")

    repo = folder / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "one")
    git(repo, "tag", "v1")
    git(repo, "branch", "other")
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    git(repo, "commit", "-qam", "two")
    repo_p = repo.as_posix()

    def refs():
        return git(repo, "for-each-ref", "--format=%(refname) %(objectname)")

    before = refs()

    # create
    clone = folder / "clone"
    done = tool("create", "--repo", repo_p, "--base", "main", "--branch", "wb")
    check("create without --dir exits 2 (no default)", done.returncode == 2 and "--dir is required" in done.stderr, done.stderr)
    done = tool("create", "--repo", repo_p, "--base", "main", "--branch", "wb", "--dir", clone.as_posix())
    check("create makes the clone", done.returncode == 0 and done.stdout.startswith("CREATED ") and clone.is_dir(),
          done.stdout + done.stderr)
    if not clone.is_dir():
        return
    check("the clone has only refs/heads/wb, no remote, no tag",
          git(clone, "for-each-ref", "--format=%(refname)") == "refs/heads/wb" and git(clone, "remote") == "", git(clone, "for-each-ref"))
    config = (clone / ".git" / "config").read_text(encoding="utf-8")
    check("the clone's config names no remote and no path", "[remote" not in config and repo_p not in config
          and "url" not in config, config)
    check("the clone's hooks/ is empty and it borrows no objects",
          not list((clone / ".git" / "hooks").iterdir()) and not (clone / ".git" / "objects" / "info" / "alternates").exists())
    check("the clone is at --base", git(clone, "rev-parse", "HEAD") == git(repo, "rev-parse", "main"))
    done = tool("create", "--repo", repo_p, "--base", "main", "--branch", "wb", "--dir", clone.as_posix())
    check("create into an existing --dir exits 2", done.returncode == 2 and "must not exist" in done.stderr, done.stderr)
    done = tool("create", "--repo", repo_p, "--base", "nope", "--branch", "wb", "--dir", (folder / "c2").as_posix())
    check("create with an unknown --base exits 2", done.returncode == 2 and "--base" in done.stderr, done.stderr)
    done = tool("create", "--repo", repo_p, "--base", "main", "--branch", "a..b", "--dir", (folder / "c3").as_posix())
    check("an invalid --branch exits 2", done.returncode == 2 and "--branch" in done.stderr, done.stderr)
    check("create changed no ref of the repository", refs() == before, refs())

    # the worker's work, then bundles made from it
    (clone / "b.txt").write_text("worker\n", encoding="utf-8")
    git(clone, "add", "b.txt")
    git(clone, "commit", "-qm", "worker")
    tip = git(clone, "rev-parse", "HEAD")
    bundles = folder / "bundles"
    bundles.mkdir()

    def bundle(name, where, *revs):
        path = bundles / f"{name}.bundle"
        git(where, "bundle", "create", "-q", path, *revs)
        return path

    good = bundle("good", clone, "refs/heads/wb")
    evil = folder / "evil"
    git(folder, "clone", "-q", "--no-local", clone, evil)
    git(evil, "update-ref", "refs/heads/other", tip)
    git(evil, "update-ref", "refs/heads/wbx", tip)
    git(evil, "tag", "-a", "-m", "t", "wb-tag", tip)
    multi = bundle("multi", evil, "refs/heads/wb", "refs/heads/other")
    wrong = bundle("wrong", evil, "refs/heads/other")
    prefix = bundle("prefix", evil, "refs/heads/wbx")
    tag = bundle("tag", evil, "refs/tags/wb-tag")
    head_only = bundle("head", evil, "HEAD")
    # refs/heads/wb pointing at an annotated tag (git will not make such a branch, so the header is edited): not a commit
    raw_tag = tag.read_bytes()
    end = raw_tag.index(b"\n\n")
    not_commit = bundles / "notcommit.bundle"
    not_commit.write_bytes(raw_tag[:end].replace(b" refs/tags/wb-tag", b" refs/heads/wb") + raw_tag[end:])
    # a commit git's strict checks refuse (author line without an e-mail)
    tree = git(evil, "rev-parse", "HEAD^{tree}")
    raw = f"tree {tree}\nparent {tip}\nauthor broken\ncommitter x <x@y> 0 +0000\n\nbad\n"
    bad = subprocess.run(["git", "-C", str(evil), "hash-object", "-t", "commit", "-w", "--literally", "--stdin"],
                         input=raw.encode("utf-8"), capture_output=True).stdout.decode("ascii").strip()
    git(evil, "update-ref", "refs/heads/wb", bad)
    malformed = bundle("malformed", evil, "refs/heads/wb")
    # a thin bundle that needs a commit the repository lacks
    (evil / "c.txt").write_text("c\n", encoding="utf-8")
    git(evil, "update-ref", "refs/heads/wb", tip)
    git(evil, "checkout", "-q", "wb")
    git(evil, "add", "c.txt")
    git(evil, "commit", "-qm", "c1")
    (evil / "c.txt").write_text("cc\n", encoding="utf-8")
    git(evil, "commit", "-qam", "c2")
    thin = bundle("thin", evil, "refs/heads/wb", "^HEAD~1")
    data = good.read_bytes()
    cut = data.index(b"\n\n") + 2
    flipped = bytearray(data)
    for i in range(cut + 12, min(len(data) - 20, cut + 60)):
        flipped[i] ^= 0xFF
    corrupt = bundles / "corrupt.bundle"
    corrupt.write_bytes(bytes(flipped))
    truncated = bundles / "truncated.bundle"
    truncated.write_bytes(data[:cut + 30])
    junk = bundles / "junk.bundle"
    junk.write_text("not a bundle\n", encoding="utf-8")

    def objects():
        return git(repo, "count-objects", "-v")

    held = objects()
    cases = [
        ("a bundle with two refs", multi, "exactly one ref"),
        ("a bundle naming another branch", wrong, "expected refs/heads/wb"),
        ("a branch name that only starts with wb", prefix, "expected refs/heads/wb"),
        ("a tag ref", tag, "expected refs/heads/wb"),
        ("a HEAD-only bundle", head_only, "expected refs/heads/wb"),
        ("a tip that is a tag object, not a commit", not_commit, "not a commit"),
        ("a malformed commit (fsck)", malformed, "strict"),
        ("a bundle needing commits the repository lacks", thin, "verify failed"),
        ("corrupt pack bytes", corrupt, ""),
        ("a truncated bundle", truncated, ""),
        ("a file that is not a bundle", junk, "not a bundle"),
        ("a missing file", bundles / "none.bundle", "no bundle file"),
    ]
    for name, path, says in cases:
        done = tool("import", "--repo", repo_p, "--branch", "wb", "--bundle", path.as_posix(), "--name", "n1")
        check(f"import refuses {name}", done.returncode == 2 and says in done.stderr and "COLLECTED" not in done.stdout,
              f"rc={done.returncode} {done.stdout} {done.stderr}")
    check("after every refusal the repository's refs are unchanged", refs() == before, refs())
    check("after every refusal no object reached the repository", objects() == held
          and subprocess.run(["git", "-C", str(repo), "cat-file", "-e", bad], capture_output=True).returncode != 0, objects())
    for name in ("../x", ".x", "a b", ""):
        done = tool("import", "--repo", repo_p, "--branch", "wb", "--bundle", good.as_posix(), "--name", name)
        check(f"import refuses --name {name!r}", done.returncode == 2 and "--name" in done.stderr, done.stderr)

    done = tool("import", "--repo", repo_p, "--branch", "wb", "--bundle", good.as_posix(), "--name", "n1")
    check("import takes the one branch into refs/dw-workers/n1/wb",
          done.returncode == 0 and done.stdout.strip() == f"COLLECTED refs/dw-workers/n1/wb {tip}", done.stdout + done.stderr)
    after = refs()
    check("only refs/dw-workers/n1/wb was added; main, other and v1 are unchanged",
          sorted(after.splitlines()) == sorted(before.splitlines() + [f"refs/dw-workers/n1/wb {tip}"]), after)
    check("the collected commit is complete in the repository",
          subprocess.run(["git", "-C", str(repo), "fsck", "--strict", "--no-dangling", "--no-progress"],
                         capture_output=True).returncode == 0 and git(repo, "cat-file", "-t", tip) == "commit")
    (clone / "b.txt").write_text("worker 2\n", encoding="utf-8")
    git(clone, "commit", "-qam", "worker 2")
    again = bundle("again", clone, "refs/heads/wb")
    done = tool("import", "--repo", repo_p, "--branch", "wb", "--bundle", again.as_posix(), "--name", "n1")
    check("a second import moves the ref and names the old commit",
          done.returncode == 0 and done.stdout.strip().endswith(f"(was {tip})"), done.stdout + done.stderr)
    done = tool("import", "--repo", repo_p, "--branch", "main", "--bundle", good.as_posix(), "--name", "n1")
    check("--branch main with a bundle of refs/heads/wb exits 2", done.returncode == 2 and "expected refs/heads/main" in done.stderr,
          done.stderr)
    check("refs/heads/main never moves", git(repo, "rev-parse", "refs/heads/main")
          == next(x.split()[1] for x in before.splitlines() if x.startswith("refs/heads/main ")))
    done = tool("collect", "--repo", repo_p, "--branch", "wb", "--name", "n1")
    check("collect without --dir exits 2", done.returncode == 2 and "--dir" in done.stderr, done.stderr)
    done = tool("push", "--repo", repo_p, "--branch", "wb")
    check("an unknown command exits 2", done.returncode == 2 and "unknown command" in done.stderr, done.stderr)

    # run_worker.sh --clone
    director = folder / "DIRECTOR"
    director.mkdir()

    def run(*args):
        return subprocess.run([bash, (box / "run_worker.sh").as_posix(), "--dry-run", *[str(a) for a in args]],
                              capture_output=True, encoding="utf-8", env={**os.environ, "DW_DNS_UPSTREAM": "192.0.2.53"})

    done = run("--clone", clone.as_posix(), "--name", "w1", "--director", director.as_posix())
    words = shlex.split(done.stdout) if done.returncode == 0 else []
    mounts = [words[i + 1] for i, w in enumerate(words) if w == "-v"]
    c = clone.as_posix()
    check("--clone: the clone at /work, its config and hooks/ ro, DIRECTOR ro; the repository is not mounted",
          mounts == [f"{c}:/work", f"{director.as_posix()}:/director:ro", f"{c}/.git/config:/work/.git/config:ro",
                     f"{c}/.git/hooks:/work/.git/hooks:ro", "dw-claude-home:/home/dw/.claude"]
          and not any(repo_p in m for m in mounts), str(mounts) + done.stderr)
    names = sorted(words[i + 1].split("=")[0] for i, w in enumerate(words) if w == "-e")
    check("--clone: DW_WORKER_NAME is --name; no GIT_CONFIG_* (no shared worktrees to protect)",
          "DW_WORKER_NAME=w1" in words and names == ["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB",
                                                     "DW_ALLOW_DOMAINS", "DW_DNS_UPSTREAM", "DW_GIT_MODE", "DW_WORKER_NAME",
                                                     "XDG_CACHE_HOME"],
          str(names))
    check("--clone sets DW_GIT_MODE=clone (doctor: the worker's own .git)", "DW_GIT_MODE=clone" in words, done.stdout)
    check("--clone prints no WARN", "WARN" not in done.stderr, done.stderr)
    done = run("--clone", c, "--director", director.as_posix())
    check("--clone without --name exits 2", done.returncode == 2 and "--name" in done.stderr, done.stderr)
    done = run("--clone", c, "--name", "../w", "--director", director.as_posix())
    check("--clone with a bad --name exits 2", done.returncode == 2 and "--name" in done.stderr, done.stderr)
    done = run("--clone", c, "--name", "w1", "--git-common", (repo / ".git").as_posix(), "--director", director.as_posix())
    check("--clone with --git-common exits 2", done.returncode == 2 and "--clone goes without" in done.stderr, done.stderr)
    done = run("--clone", repo_p + "/nothing", "--name", "w1", "--director", director.as_posix())
    check("--clone of a folder without .git exits 2", done.returncode == 2 and "worker_clone.sh create" in done.stderr, done.stderr)
    (clone / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\n", encoding="utf-8")
    done = run("--clone", c, "--name", "w1", "--director", director.as_posix())
    check("--clone with a file in .git/hooks exits 2", done.returncode == 2 and "hooks must be empty" in done.stderr, done.stderr)
    (clone / ".git" / "hooks" / "post-checkout").unlink()
    done = run("--worktree", repo_p, "--git-common", (repo / ".git").as_posix(), "--director", director.as_posix())
    words = shlex.split(done.stdout) if done.returncode == 0 else []
    check("--git-common still works for one version, with a WARN on stderr (Q1)",
          done.returncode == 0 and "WARN K1" in done.stderr and "2.0 removes --git-common" in done.stderr, done.stderr)
    check("--git-common: DW_WORKER_NAME defaults to the folder name", "DW_WORKER_NAME=repo" in words, done.stdout)
    check("--git-common sets DW_GIT_MODE=shared (doctor: K1 NOT_ENFORCED)", "DW_GIT_MODE=shared" in words, done.stdout)
    done = run("--worktree", repo_p, "--git-common", (repo / ".git").as_posix(), "--name", "w9", "--director", director.as_posix())
    check("--git-common with --name uses it", "DW_WORKER_NAME=w9" in shlex.split(done.stdout or "''"), done.stdout + done.stderr)


def test_dns_allow(tmp):
    """DNS allowlist (1.2.0): dns_allow.py's pure functions, then the real UDP and TCP servers on 127.0.0.1 with a fake
    upstream on another local port (no network), then run_worker.sh's allowlist and upstream handling (--dry-run).
    The container itself (firewall, dwdns user) is tested by hand: TASK REPORT."""
    global total
    import socket
    import struct
    import threading
    box = TOOLS / "container"
    folder = tmp / "dns_allow"
    folder.mkdir()

    def check(name, ok, detail=""):
        global total
        total += 1
        if not ok:
            failures.append(f"dns_allow {name}: {str(detail)[-600:]}")

    spec = importlib.util.spec_from_file_location("dns_allow_for_test", box / "dns_allow.py")
    dns = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dns)

    def query(name, qtype=1, qid=0x1234, flags=0x0100, qd=1, extra=b"", qclass=1, ar=0):
        wire = b"".join(bytes([len(p)]) + p for p in name.encode("latin-1").split(b".") if p) + b"\0"
        return struct.pack("!6H", qid, flags, qd, 0, 0, ar) + wire + struct.pack("!2H", qtype, qclass) + extra

    def rcode(packet):
        return packet[3] & 0xF if packet else None

    names = dns.parse_list("# comment\nAPI.Anthropic.com.  claude.ai # tail\n\n*.Example.org\nclaude.ai\n")
    check("parse_list: comments, case, trailing dot, duplicates", names == ["*.example.org", "api.anthropic.com", "claude.ai"], names)
    for bad in ("exa!mple.com", "a..b", "-a.com", "a*.com", "*.*.com", "http://x.com", "x" * 64 + ".com", "a_b.com"):
        try:
            dns.parse_list("ok.com\n" + bad)
            check(f"parse_list refuses {bad[:20]!r}", False, "no error")
        except ValueError as err:
            check(f"parse_list refuses {bad[:20]!r} and names line 2", "line 2" in str(err), err)
    shipped = dns.parse_list((box / "dns_allow.txt").read_text(encoding="utf-8"))
    check("dns_allow.txt parses and is api.anthropic.com only", shipped == ["api.anthropic.com"], shipped)
    allow = set(names)
    check("allowed: exact name", dns.allowed("api.anthropic.com", allow) and dns.allowed("claude.ai", allow))
    check("allowed: an exact entry does not allow its subdomains or look-alikes",
          not dns.allowed("x.api.anthropic.com", allow) and not dns.allowed("api.anthropic.com.evil.net", allow)
          and not dns.allowed("anthropic.com", allow) and not dns.allowed("xclaude.ai", allow))
    check("allowed: *.example.org takes a.example.org and a.b.example.org, not example.org or badexample.org",
          dns.allowed("a.example.org", allow) and dns.allowed("a.b.example.org", allow)
          and not dns.allowed("example.org", allow) and not dns.allowed("badexample.org", allow))

    kind, q = dns.decide(query("API.anthropic.COM"), allow)
    check("decide: IN A for a listed name (any case) is forwarded", kind == "forward" and q["name"] == "api.anthropic.com", (kind, q))
    check("decide: IN AAAA is forwarded", dns.decide(query("claude.ai", 28), allow)[0] == "forward")
    for label, packet, want in (("TXT on a listed name", query("claude.ai", 16), 5),
                                ("ANY on a listed name", query("claude.ai", 255), 5),
                                ("class CH", query("claude.ai", qclass=3), 5),
                                ("opcode 2 (status)", query("claude.ai", flags=0x1100), 5),
                                ("a name not on the list", query("example.com"), 3),
                                ("a random subdomain of a listed name", query("q8x1.api.anthropic.com"), 3),
                                ("the root name", query(""), 3),
                                ("two questions", query("claude.ai", qd=2), 1),
                                ("a compression pointer in the name", struct.pack("!6H", 1, 0x100, 1, 0, 0, 0) + b"\xc0\x0c\0\1\0\1", 1),
                                ("a 64-byte label", struct.pack("!6H", 1, 0x100, 1, 0, 0, 0) + b"\x40" + b"a" * 64 + b"\0\0\1\0\1", 1),
                                ("a name over 255 bytes", query(".".join(["a" * 63] * 5)), 1),
                                ("a cut-off question", query("claude.ai")[:-3], 1)):
        kind, out = dns.decide(packet, allow)
        check(f"decide: {label} -> rcode {want}, same ID, nothing forwarded",
              kind == "reply" and rcode(out) == want and out[:2] == packet[:2] and out[2] & 0x80, (kind, out))
    check("decide: a short packet or a response is dropped",
          dns.decide(b"\x12\x34\x01", allow) == ("drop", None) and dns.decide(query("claude.ai", flags=0x8100), allow) == ("drop", None))

    worker = query("Api.AnThRoPiC.com", qid=0xBEEF, ar=1, extra=b"\0\0\x29\x10\0\0\0\0\0\0\x08SECRETS!")
    kind, q = dns.decide(worker, allow)
    sent = dns.upstream_query(q, 0x0F0F)
    check("upstream query: new ID, lower-case name, RD, one question, no extra records (nothing the worker chose)",
          kind == "forward" and sent == query("api.anthropic.com", qid=0x0F0F) and b"SECRETS" not in sent, sent)
    upstream_answer = (sent[:2] + b"\x81\x80" + b"\0\1\0\1\0\0\0\0" + sent[12:]
                       + b"\xc0\x0c\0\1\0\1\0\0\0\x3c\0\4" + bytes([160, 79, 104, 10]))
    out = dns.answer_for_worker(upstream_answer, sent, q, worker)
    check("answer_for_worker: the worker's ID and question (its letter case) come back, the answer record is kept",
          out is not None and out[:2] == b"\xbe\xef" and out[12:12 + len(sent) - 12] == worker[12:q["end"]]
          and out.endswith(bytes([160, 79, 104, 10])), out)
    for label, bad in (("another ID", b"\0\0" + upstream_answer[2:]),
                       ("not a response", upstream_answer[:2] + b"\x01\x00" + upstream_answer[4:]),
                       ("another question", upstream_answer.replace(b"anthropic", b"anthropiq")),
                       ("cut short", upstream_answer[:14])):
        check(f"answer_for_worker refuses an upstream answer with {label}", dns.answer_for_worker(bad, sent, q, worker) is None)

    # The real servers, on free local ports, with a fake upstream that answers every A query with 192.0.2.7.
    seen = []
    up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    up.bind(("127.0.0.1", 0))
    up.settimeout(5)
    up_tcp = socket.socket()
    up_tcp.bind(("127.0.0.1", up.getsockname()[1]))
    up_tcp.listen(4)
    up_tcp.settimeout(5)

    def fake_answer(packet):
        seen.append(packet)
        return packet[:2] + b"\x81\x80\0\1\0\1\0\0\0\0" + packet[12:] + b"\xc0\x0c\0\1\0\1\0\0\0\x3c\0\4" + bytes([192, 0, 2, 7])

    def fake_udp():
        try:
            while True:
                data, peer = up.recvfrom(4096)
                up.sendto(fake_answer(data), peer)
        except OSError:
            return

    def fake_tcp():
        try:
            while True:
                conn, _ = up_tcp.accept()
                with conn:
                    data = dns.read_tcp_message(conn)
                    out = fake_answer(data)
                    conn.sendall(struct.pack("!H", len(out)) + out)
        except OSError:
            return

    for target in (fake_udp, fake_tcp):
        threading.Thread(target=target, daemon=True).start()
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    import io
    log = io.StringIO()
    resolver = dns.Resolver(["api.anthropic.com"], ["127.0.0.1"], log=log, upstream_port=up.getsockname()[1])
    servers = []
    try:
        ready = threading.Event()
        servers = dns.serve(resolver, port, ready)
        ready.wait(5)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(5)
        client.sendto(query("api.ANTHROPIC.com", qid=0x4242), ("127.0.0.1", port))
        out = client.recvfrom(4096)[0]
        check("UDP: a listed name is answered through the upstream, with the worker's ID and question",
              out[:2] == b"\x42\x42" and rcode(out) == 0 and out.endswith(bytes([192, 0, 2, 7]))
              and seen and seen[-1][12:] == query("api.anthropic.com")[12:] and seen[-1][:2] != b"\x42\x42", (out, seen))
        count = len(seen)
        client.sendto(query("leak-0123.example.com", 16), ("127.0.0.1", port))
        out = client.recvfrom(4096)[0]
        check("UDP: a name not on the list gets NXDOMAIN and nothing reaches the upstream",
              rcode(out) == 3 and len(seen) == count, (out, len(seen)))
        client.close()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
            for name, want in (("api.anthropic.com", 0), ("example.com", 3)):
                packet = query(name)
                conn.sendall(struct.pack("!H", len(packet)) + packet)
                out = dns.read_tcp_message(conn)
                check(f"TCP: {name} -> rcode {want} on one connection", rcode(out) == want, out)
        check("refused names are logged once each, printable only",
              log.getvalue().count("refused leak-0123.example.com type 16") == 1 and "refused example.com type 1" in log.getvalue(), log.getvalue())
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
        up.close()
        up_tcp.close()
    check("main: no DW_DNS_UPSTREAM exits 2", subprocess.run(
        [sys.executable, "-I", "-B", str(box / "dns_allow.py")], capture_output=True, encoding="utf-8",
        env={**{k: v for k, v in os.environ.items() if k != "DW_DNS_UPSTREAM"}, "DW_ALLOW_DOMAINS": "a.com"}).returncode == 2)

    spec = importlib.util.spec_from_file_location("doctor_for_dns_test", TOOLS / "doctor.py")
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    bash = doctor.git_bash() if os.name == "nt" else shutil.which("bash")
    if not bash:
        print("SKIP run_worker.sh allowlist cases: no bash (Git Bash on Windows)")
        return
    clone, director = folder / "c", folder / "D"
    (clone / ".git" / "hooks").mkdir(parents=True)
    (clone / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    director.mkdir()

    def run(*args, env=None):
        argv = [bash, (box / "run_worker.sh").as_posix(), "--dry-run", "--clone", clone.as_posix(), "--name", "w",
                "--director", director.as_posix(), *[str(a) for a in args]]
        full = {k: v for k, v in os.environ.items() if k not in ("DW_DNS_UPSTREAM", "DW_RESOLV_CONF")}
        full.update(env or {"DW_DNS_UPSTREAM": "192.0.2.53"})
        done = subprocess.run(argv, capture_output=True, encoding="utf-8", env=full)
        words = shlex.split(done.stdout) if done.returncode == 0 else []
        values = {w.split("=", 1)[0]: w.split("=", 1)[1] for i, w in enumerate(words) if i and words[i - 1] == "-e"}
        return done, words, values

    done, words, values = run("--login", "--allow", "Example.COM.", "--allow", "claude.ai")
    check("run_worker: --dns 127.0.0.1; the file, then --login, then --allow, each once, lower case",
          "--dns" in words and words[words.index("--dns") + 1] == "127.0.0.1"
          and values.get("DW_ALLOW_DOMAINS") == "api.anthropic.com claude.ai platform.claude.com console.anthropic.com example.com"
          and values.get("DW_DNS_UPSTREAM") == "192.0.2.53", done.stdout + done.stderr)
    resolv = folder / "resolv.conf"
    resolv.write_text("nameserver 127.0.0.53\nnameserver ::1\nnameserver 10.0.0.2 # x\nsearch lan\nnameserver 10.0.0.3\n", encoding="utf-8")
    done, words, values = run(env={"DW_RESOLV_CONF": resolv.as_posix()})
    check("run_worker: upstream from resolv.conf without 127.x and IPv6", values.get("DW_DNS_UPSTREAM") == "10.0.0.2 10.0.0.3", done.stdout + done.stderr)
    resolv.write_text("nameserver 127.0.0.53\n", encoding="utf-8")
    done, _, _ = run(env={"DW_RESOLV_CONF": resolv.as_posix()})
    check("run_worker: only 127.x in resolv.conf exits 2 (no silent fallback)", done.returncode == 2 and "DW_DNS_UPSTREAM" in done.stderr, done.stderr)
    done, _, _ = run(env={"DW_DNS_UPSTREAM": "8.8.8.8 evil"})
    check("run_worker: a bad DW_DNS_UPSTREAM exits 2", done.returncode == 2 and "evil" in done.stderr, done.stderr)
    listed = folder / "allow.txt"
    listed.write_text("*.Example.org # wild\r\n\r\nzz.test\n", encoding="utf-8")
    (folder / "zz.example.org").write_text("", encoding="utf-8")
    done, _, values = run("--allow-file", listed.as_posix())
    check("run_worker: --allow-file replaces dns_allow.txt; *. stays literal (no glob), CRLF is fine",
          values.get("DW_ALLOW_DOMAINS") == "*.example.org zz.test", done.stdout + done.stderr)
    for label, args in (("a bad name in --allow", ("--allow", "bad_name")),
                        ("a missing --allow-file", ("--allow-file", (folder / "none.txt").as_posix())),
                        ("an empty allowlist", ("--allow-file", resolv.as_posix().replace("resolv.conf", "empty.txt")))):
        if label == "an empty allowlist":
            (folder / "empty.txt").write_text("# nothing\n", encoding="utf-8")
        done, _, _ = run(*args)
        check(f"run_worker: {label} exits 2", done.returncode == 2, done.stdout + done.stderr)
    done, words, values = run("--offline", env={})
    check("run_worker --offline: no --dns, no allowlist, no upstream needed",
          done.returncode == 0 and "--dns" not in words and "DW_ALLOW_DOMAINS" not in values and "DW_DNS_UPSTREAM" not in values,
          done.stdout + done.stderr)
    entry = (box / "entrypoint.sh").read_text(encoding="utf-8")
    firewall = (box / "init_firewall.sh").read_text(encoding="utf-8")
    docker_file = (box / "Dockerfile").read_text(encoding="utf-8")
    check("entrypoint: firewall dns, dns_allow.py as dwdns with no capabilities, firewall https, then dw",
          entry.index("init_firewall.sh dns") < entry.index("--reuid=dwdns") < entry.index("init_firewall.sh https") < entry.index("--reuid=dw ")
          and entry.count("--bounding-set=-all") == 2 and entry.count("--no-new-privs") == 2, entry)
    check("init_firewall: only dwdns reaches the upstream on 53; 53 on 127.0.0.1 goes to 5353",
          firewall.count("--uid-owner dwdns -j ACCEPT") == 2 and firewall.count("-d 127.0.0.1 -p udp --dport 53 -j REDIRECT --to-ports 5353") == 1
          and firewall.count("-d 127.0.0.1 -p tcp --dport 53 -j REDIRECT --to-ports 5353") == 1
          and "/etc/resolv.conf" not in firewall, firewall)
    check("Dockerfile: dns_allow.py copied, user dwdns made after the cached layers",
          "dns_allow.py /usr/local/bin/" in docker_file and docker_file.index("useradd --system --uid 999") > docker_file.index("COPY entrypoint.sh"),
          docker_file)


def check(name, ok, detail=""):
    global total
    total += 1
    if not ok:
        failures.append(f"{name}: {detail}"[:400])


def um_call(mid, ts, tools=(), **usage):
    """One assistant transcript line: tools are (name, input) pairs; usage keys are the token counts."""
    content = [{"type": "tool_use", "name": n, "input": i} for n, i in tools]
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": mid, "content": content, "usage": usage}})


def test_usage_mix(tmp):
    """usage_mix.py: fragments of one message.id are merged (L-035), a repeated id counts once, the five shares and the
    DD-049 targets, --since / --until / --session / --patterns / --json / --check, NO_DATA, and the RESTART numbers."""
    root = tmp / "usage_mix"
    p = root / "proj"
    p.mkdir(parents=True)
    (root / "empty").mkdir()
    md, py = ("Read", {"file_path": "D:/x/notes.md"}), ("Edit", {"file_path": "D:/x/app.py"})
    (p / "aaaa1111.jsonl").write_text("\n".join([
        json.dumps({"type": "custom-title", "customTitle": "line-alpha"}),
        um_call("m1", "2026-01-02T10:00:00Z", (), input_tokens=1000),          # the usage fragment of m1
        um_call("m1", "2026-01-02T10:00:00Z", [md], input_tokens=1000),        # the tool fragment of m1: merged, not summed
        um_call("m2", "2026-01-02T10:01:00Z", [py], input_tokens=1000),
        um_call("m3", "2026-01-02T10:02:00Z", [("Bash", {"command": "git status"})], input_tokens=2000)]) + "\n",
        encoding="utf-8")
    (p / "bbbb2222.jsonl").write_text("\n".join([
        um_call("m2", "2026-01-02T10:01:00Z", [py], input_tokens=1000),        # a resumed copy: counted once
        um_call("m4", "2026-01-05T10:00:00Z", [("Bash", {"command": "sleep 5"})], input_tokens=4000),
        um_call("m5", "2026-01-05T10:01:00Z", [("Bash", {"command": "run mygame.exe --level 1"})], input_tokens=2000),
        "not json"]) + "\n", encoding="utf-8")
    pats = root / "patterns.json"
    pats.write_text(json.dumps({"schema_version": 1, "patterns": {"engine_run": r"mygame\.exe"}}), encoding="utf-8")
    bad = root / "bad.json"
    bad.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    bad_key = root / "bad_key.json"
    bad_key.write_text(json.dumps({"schema_version": 1, "patterns": {"nope": "x"}}), encoding="utf-8")
    base = ("--root", root, "--project-dir", "proj")
    expect("usage_mix shares, merge and dedupe", "usage_mix.py", 0, *base,
           says=["calls=5 eq=0.0M", "讀和查\t 50.0%", "實際動手\t 10.0%", "等待\t 40.0%", "協調\t  0.0%",
                 "target <=30% MISSED", "RESULT OFF_TARGET: 讀和查 50.0% (target <=30%); 實際動手 10.0% (target >=30%)"],
           lacks="text_reply")
    expect("usage_mix --check misses", "usage_mix.py", 1, *base, "--check", says="RESULT OFF_TARGET")
    expect("usage_mix --patterns moves a project exe to 實際動手", "usage_mix.py", 0, *base, "--patterns", pats, "--check",
           says=["讀和查\t 30.0%", "實際動手\t 30.0%  tool_calls 2  target >=30% OK", "RESULT ON_TARGET"])
    expect("usage_mix --until a date keeps that whole day", "usage_mix.py", 0, *base, "--until", "2026-01-02",
           says=["calls=3", "讀和查\t 75.0%", "實際動手\t 25.0%"])
    expect("usage_mix --since", "usage_mix.py", 0, *base, "--since", "2026-01-03",
           says=["calls=2", "等待\t 66.7%", "讀和查\t 33.3%"])
    expect("usage_mix --session by title", "usage_mix.py", 0, *base, "--session", "ALPHA", says=["calls=3", "session=ALPHA"])
    expect("usage_mix --session by id prefix", "usage_mix.py", 0, *base, "--session", "bbbb", says="calls=2")
    expect("usage_mix --top names the session", "usage_mix.py", 0, *base, "--top", "2", says="session aaaa1111 line-alpha")
    expect("usage_mix --json", "usage_mix.py", 0, *base, "--json",
           says=['"eq_total": 10000', '"result": "OFF_TARGET"', '"cache_read_input_tokens": 0.1'])
    # 1.3.1: shell_other split into git, file_ops, shell_search, build, python runs, sys_query; --by-session
    sh = root / "shell"
    sh.mkdir()
    cmds = ["git log -1", "cat a.txt", "grep -n x f.txt", "npm run build", "py -3 tools/x.py", "Get-Process",
            "foo --bar", "cat x.py"]
    (sh / "eeee5555.jsonl").write_text("\n".join(
        um_call(f"s{i}", f"2026-01-02T10:0{i}:00Z", [("Bash", {"command": c})], input_tokens=1000)
        for i, c in enumerate(cmds)) + "\n", encoding="utf-8")
    expect("usage_mix splits the shell commands", "usage_mix.py", 0, "--root", root, "--project-dir", "shell", "--json",
           says=['"file_ops": 0.25', '"git": 0.125', '"shell_search": 0.125', '"build": 0.125', '"python_other": 0.125',
                 '"sys_query": 0.125', '"shell_other": 0.125'])
    expect("usage_mix build and python runs are 實際動手", "usage_mix.py", 0, "--root", root, "--project-dir", "shell",
           says=["讀和查\t 75.0%", "實際動手\t 25.0%"])
    build_pats = root / "build_patterns.json"
    build_pats.write_text(json.dumps({"schema_version": 1, "patterns": {"build": r"\bfoo\b"}}), encoding="utf-8")
    expect("usage_mix --patterns adds a build word", "usage_mix.py", 0, "--root", root, "--project-dir", "shell",
           "--patterns", build_pats, "--json", says='"build": 0.25', lacks='"shell_other"')
    expect("usage_mix --by-session: one line per session", "usage_mix.py", 0, *base, "--by-session",
           says=["by-session bbbb2222 -: 60.0% of total, calls 2, eq 6.0K | 讀和查 33%, 等待 67% | top: wait_board 67%, "
                 "shell_other 33%",
                 "by-session aaaa1111 line-alpha: 40.0% of total, calls 3, eq 4.0K | 讀和查 75%, 實際動手 25% | top: git 50%, "
                 "read_md 25%, edit_py 25%"])
    expect("usage_mix --by-session --json", "usage_mix.py", 0, *base, "--by-session", "--json",
           says=['"by_session"', '"session": "bbbb2222"', '"eq": 6000'])
    expect("usage_mix without --by-session prints no session lines", "usage_mix.py", 0, *base, lacks="by-session")
    expect("usage_mix no transcripts is NO_DATA", "usage_mix.py", 1, "--root", root, "--project-dir", "empty", says="NO_DATA")
    expect("usage_mix a range with no calls is NO_DATA", "usage_mix.py", 1, *base, "--since", "2027-01-01", says="NO_DATA")
    expect("usage_mix patterns schema", "usage_mix.py", 2, *base, "--patterns", bad, says="FAIL patterns")
    expect("usage_mix patterns key", "usage_mix.py", 2, *base, "--patterns", bad_key, says="FAIL patterns")
    expect("usage_mix patterns missing file", "usage_mix.py", 2, *base, "--patterns", root / "none.json", says="FAIL patterns")
    # RESTART: cost per call by context, orientation after a new session and after a compaction, break-even
    r = root / "restart"
    r.mkdir()
    (r / "cccc3333.jsonl").write_text("\n".join([
        um_call("r1", "2026-01-02T10:00:00Z", [md], cache_read_input_tokens=100000),
        um_call("r2", "2026-01-02T10:01:00Z", [py], cache_read_input_tokens=110000),
        um_call("r3", "2026-01-02T10:02:00Z", [md], cache_read_input_tokens=180000),
        um_call("r4", "2026-01-02T10:03:00Z", [md], cache_read_input_tokens=190000),
        um_call("r5", "2026-01-02T10:04:00Z", [md], cache_read_input_tokens=50000),   # < 0.6 x 190K: a compaction
        um_call("r6", "2026-01-02T10:05:00Z", [py], cache_read_input_tokens=60000)]) + "\n", encoding="utf-8")
    expect("usage_mix restart numbers", "usage_mix.py", 0, "--root", root, "--project-dir", "restart",
           says=["RESTART new main sessions 1, first-call context median 100.0K; compactions 1, after it 50.0K",
                 "RESTART after a new session: 1 reached 實際動手, median 1 calls and 10.0K eq before the first one",
                 "RESTART after a compaction: 1 reached 實際動手, median 1 calls and 5.0K eq",
                 "60-120K 9.0K (3 calls)", ">=170K 18.5K (2 calls)",
                 "RESTART break-even after 1 more calls: rebuilding costs 10.0K, each call saves 9.5K"])
    n = root / "never"
    n.mkdir()
    (n / "dddd4444.jsonl").write_text("\n".join([
        um_call("n1", "2026-01-02T10:00:00Z", [md], cache_creation_input_tokens=100000),  # a new session writes its cache
        um_call("n2", "2026-01-02T10:01:00Z", [py], cache_read_input_tokens=110000),
        um_call("n3", "2026-01-02T10:02:00Z", [md], cache_read_input_tokens=180000)]) + "\n", encoding="utf-8")
    expect("usage_mix break-even NEVER", "usage_mix.py", 0, "--root", root, "--project-dir", "never",
           says="RESTART break-even NEVER: a call at >=170K costs 18.0K, no more than 68.0K at 60-120K")
    expect("usage_mix break-even UNKNOWN", "usage_mix.py", 0, *base, says="RESTART break-even UNKNOWN")


def test_status_gen(tmp):
    """status_gen.py writes a status.py that only reads, prints at most max_lines lines of at most width characters,
    and exits 1 on a missing path or a disk below the threshold (L-042)."""
    d = tmp / "status_gen"
    (d / "out" / "sub").mkdir(parents=True)
    (d / "run.log").write_text("".join(f"line {i} of the run log\n" for i in range(1, 101)) + "x" * 500 + "\n", encoding="utf-8")
    (d / "hashes.txt").write_text("abc123  build.zip\n", encoding="utf-8")
    (d / "out" / "a.png").write_bytes(b"x")
    (d / "out" / "sub" / "b.png").write_bytes(b"yy")

    def status(name, script, code, says=(), lacks=(), max_lines=60, width=160):
        done = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, encoding="utf-8")
        lines = done.stdout.splitlines()
        bad = [s for s in says if s not in done.stdout] + [f"has {s}" for s in lacks if s in done.stdout]
        check(name, done.returncode == code and not bad and len(lines) <= max_lines and all(len(x) <= width for x in lines),
              f"exit {done.returncode} (want {code}), {len(lines)} lines, missing {bad}: {done.stdout.strip()[-300:]}")

    full = d / "status_full.py"
    # the git line is checked on a fixture repo, not on the DW folder, which may be an unpacked ZIP (report 5 F-1)
    git_args = ("--git", git_fixture(tmp / "status_git")) if GIT else ()
    if not GIT:
        skip("test_status_gen git line")
    expect("status_gen writes", "status_gen.py", 0, "--out", full, "--name", "line-a", "--log", d / "run.log",
           "--hash-file", d / "hashes.txt", "--checksum", d / "hashes.txt", "--outputs", d / "out", "--disk", tmp,
           "--disk-min-gib", "0.001", *git_args, says="WROTE")
    status("status.py full", full, 0, says=["STATUS line-a", "  line 99 of the run log", "HASH sha256 ", "  abc123  build.zip",
                                            " OK", "OUT ", "2 files, newest 2", "b.png"] + (["GIT "] if GIT else []))
    small = d / "status_small.py"
    expect("status_gen small cap", "status_gen.py", 0, "--out", small, "--log", d / "run.log", "--log-lines", "100",
           "--max-lines", "10", "--width", "40")
    status("status.py line cap and width", small, 0, says=["TRUNCATED 93 more lines (max_lines 10)"], max_lines=10, width=40)
    bad = d / "status_bad.py"
    expect("status_gen missing paths are written", "status_gen.py", 0, "--out", bad, "--log", d / "none.log",
           "--outputs", d / "none", "--disk", tmp, "--disk-min-gib", "999999")
    status("status.py missing and low", bad, 1, says=["LOG MISSING", "OUT MISSING", " LOW"])
    nogit = d / "status_nogit.py"
    expect("status_gen git outside a worktree", "status_gen.py", 0, "--out", nogit, "--git", d)
    status("status.py not a git worktree", nogit, 1, says=["GIT MISSING"])
    expect("status_gen keeps an existing file", "status_gen.py", 2, "--out", full, "--log", d / "run.log", says="--force")
    expect("status_gen --force replaces it", "status_gen.py", 0, "--out", full, "--log", d / "run.log", "--force")
    expect("status_gen nothing to report", "status_gen.py", 2, "--out", d / "s_none.py", says="nothing to report")
    expect("status_gen threshold needs a disk", "status_gen.py", 2, "--out", d / "s_none.py", "--log", d / "run.log",
           "--disk-min-gib", "5", says="disk_min_gib needs disk")
    conf = d / "conf" / "status.json"
    conf.parent.mkdir()
    conf.write_text(json.dumps({"schema_version": 1, "name": "from-config", "logs": ["../run.log"], "log_lines": 2}),
                    encoding="utf-8")
    cfg = d / "status_cfg.py"
    expect("status_gen config", "status_gen.py", 0, "--out", cfg, "--config", conf)
    status("status.py config paths are the config folder's", cfg, 0, says=["STATUS from-config", "  line 100 of the run log"],
           lacks=["line 98 of"])
    conf.write_text(json.dumps({"schema_version": 1, "logs": ["a"], "extra": 1}), encoding="utf-8")
    expect("status_gen unknown config key", "status_gen.py", 2, "--out", d / "s_none.py", "--config", conf, says="unknown key")
    conf.write_text(json.dumps({"schema_version": 1, "logs": "a"}), encoding="utf-8")
    expect("status_gen wrong config type", "status_gen.py", 2, "--out", d / "s_none.py", "--config", conf, says="wrong type")
    source = full.read_text(encoding="utf-8")
    check("status.py uses only the standard library and does not write", "open(path, \"rb\")" in source
          and not re.search(r"^import (?!datetime|glob|hashlib|json|os|re|shlex|shutil|subprocess|sys)", source, re.M)
          and not re.search(r"open\([^)]*[\"'][wa]", source), "status.py imports or writes something")


def test_status_director(tmp):
    """1.3.0 §6: the Director status.py: PO page counts (regex or JSON list), open orders, unsent items, the last hour of
    each action log (lines, blocked, log reads, sessions), whether a process runs, the disk; still at most max_lines."""
    d = tmp / "status_director"
    (d / "orders").mkdir(parents=True)
    (d / "audit").mkdir()
    (d / "PO_PENDING.md").write_text("ID: OD-1\nSTATUS: answered\n\nID: OD-2\nSTATUS: open\n\nID: OD-3\nSTATUS: answered\n"
                                     "\nID: N-1\nSTATUS: new\n", encoding="utf-8")
    (d / "po.html").write_text("<html><script>window.DATA = " + json.dumps(
        {"page": {"decisions": [{"status": "answered"}, {"status": "open"}], "notes": [{"status": "new"}] * 3}})
        + ";</script></html>", encoding="utf-8")
    (d / "orders" / "WO-1.md").write_text("# WO-1\nSTATUS: CLOSED\n", encoding="utf-8")
    (d / "orders" / "WO-2.md").write_text("# WO-2\nREVISION = 1\n", encoding="utf-8")
    (d / "orders" / "WO-3.md").write_text("# WO-3\n狀態：進行中\n", encoding="utf-8")
    (d / "orders" / "notes.md").write_text("not an order\n", encoding="utf-8")
    (d / "PENDING_SENDS.md").write_text("- [x] sent one\n- [ ] to 總監: report A\n- [ ] to line-b: retry\n",
                                        encoding="utf-8")
    now = datetime.datetime.now(datetime.timezone.utc)

    def line(minutes_ago, session, tool, command, kind="result", status="ok"):
        ts = (now - datetime.timedelta(minutes=minutes_ago)).isoformat(timespec="milliseconds")
        return json.dumps({"seq": 0, "ts": ts, "session_id": session, "tool": tool, "kind": kind,
                           "input": json.dumps({"command": command}), "result": {"status": status}}) + "\n"

    old = line(180, "S0", "Bash", "tail run.log")
    with open(d / "audit" / "a.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(old * (1300000 // len(old) + 1))  # more than one 1 MiB block of old lines
        fh.write(line(30, "S1", "Bash", "tail -n 20 D:/w/run.log"))
        fh.write(line(20, "S1", "PowerShell", "Get-Content D:\\w\\run.log -Tail 5"))
        fh.write(line(10, "S2", "Bash", "python tools/selftest.py"))
        fh.write(line(5, "S2", "Bash", "git push", kind="decision", status="deny"))
        fh.write(line(4, "S2", "Bash", "rm -rf x", kind="decision", status="pause"))
        fh.write(line(3, "S2", "Bash", "gh pr create", kind="decision", status="ask"))
    (d / "audit" / "b.jsonl").write_text(old, encoding="utf-8")
    marker = "dwstatusprobe" + str(os.getpid())
    sleeper = subprocess.Popen([sys.executable, "-c", "import time, sys; time.sleep(120)", marker])
    try:
        conf = d / "director.json"
        conf.write_text(json.dumps({
            "schema_version": 1, "name": "director",
            "po_page": {"path": "PO_PENDING.md", "counts": [{"label": "answered", "regex": r"^STATUS:\s*answered\b"},
                                                            {"label": "new", "regex": r"^STATUS:\s*new\b"}]},
            "orders": {"dir": "orders", "show": 1}, "pending_sends": {"path": "PENDING_SENDS.md"},
            "audit": {"globs": ["audit/*.jsonl"]},
            "processes": [{"label": "probe", "match": marker}, {"label": "idle_watch", "match": "no_such_process_" + marker[::-1]}],
            "disk": str(tmp), "max_lines": 20}), encoding="utf-8")
        script = d / "status.py"
        expect("status_gen director config", "status_gen.py", 0, "--out", script, "--config", conf, says="WROTE")
        done = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, encoding="utf-8")
        out = done.stdout
        want = [f"PO {d / 'PO_PENDING.md'}: answered=2, new=1", "ORDERS ", ": 2 open of 3", "  ... 1 more",
                ": 2 not sent", "  - [ ] to 總監: report A",
                "AUDIT a.jsonl last 1h: lines=6 blocked=2 log_reads=2 sessions=2",
                "AUDIT b.jsonl last 1h: lines=0 blocked=0 log_reads=0 sessions=0",
                "PROC probe: running (1)", "PROC idle_watch: NOT RUNNING", "DISK "]
        bad = [w for w in want if w not in out]
        check("status.py director sections", done.returncode == 1 and not bad and len(out.splitlines()) <= 20,
              f"exit {done.returncode}, missing {bad}: {out[-900:]}")
        check("status.py director: WO-1 is closed, notes.md is no order", "WO-1.md" not in out and "notes.md" not in out
              and ("WO-2.md" in out or "WO-3.md" in out), out[-600:])
    finally:
        sleeper.kill()
        sleeper.wait()
    conf.write_text(json.dumps({"schema_version": 1, "po_page": {"path": "po.html", "extract": r"window\.DATA = (\{.*\});",
                    "counts": [{"label": "decisions answered", "list": "page.decisions", "field": "status", "value": "answered"},
                               {"label": "notes new", "list": "page.notes", "value": "new"},
                               {"label": "notes", "list": "page.notes"},
                               {"label": "bad", "list": "page.none"}]},
                    "pending_sends": {"path": "orders"}}), encoding="utf-8")
    expect("status_gen director JSON page", "status_gen.py", 0, "--out", script, "--config", conf, "--force")
    done = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, encoding="utf-8")
    check("status.py JSON page counts; a bad key is ? and exit 1", done.returncode == 1
          and "decisions answered=1, notes new=3, notes=3, bad=? (" in done.stdout
          and "SENDS " in done.stdout and ": 4 not sent" in done.stdout, done.stdout[-600:])
    for name, body, says in (
            ("regex and list together", {"po_page": {"path": "x", "counts": [{"label": "a", "regex": "x", "list": "y"}]}},
             "one of them"),
            ("a bad regex", {"orders": {"dir": "orders", "closed": "("}}, "not a regex"),
            ("an unknown section key", {"audit": {"globs": ["a"], "days": 1}}, "unknown key"),
            ("hours 0", {"audit": {"globs": ["a"], "hours": 0}}, "more than 0"),
            ("a process without match", {"processes": [{"label": "x"}]}, "processes.match")):
        conf.write_text(json.dumps(dict({"schema_version": 1}, **body)), encoding="utf-8")
        expect(f"status_gen director {name}", "status_gen.py", 2, "--out", d / "s_none.py", "--config", conf, says=says)
    conf.write_text((TOOLS.parent / "templates" / "status_director.json").read_text(encoding="utf-8"), encoding="utf-8")
    expect("status_gen the director template loads", "status_gen.py", 0, "--out", d / "s_tpl.py", "--config", conf,
           says="WROTE")
    source = (d / "s_tpl.py").read_text(encoding="utf-8")
    poll = (TOOLS / "poll_hint.py").read_text(encoding="utf-8")
    check("status.py carries poll_hint's read_targets as it is",
          re.search(r"^def read_targets.*?(?=^\S)", poll, re.M | re.S).group().rstrip() in source, "copy differs")


def test_round_check(tmp):
    """round_check.py: fix rounds go in sets of 3; from round 4 the study must hold WHERE / ALTERNATIVES / DECISION
    for every finished set (L-032)."""
    d = tmp / "round_check"
    d.mkdir()

    def resume(name, rows):
        f = d / f"RESUME_STATE_{name}.md"
        f.write_text("PROGRESS: x\n\nFIX_ROUNDS:\n" + "".join(f"- {r}\n" for r in rows) + "OPEN_DECISIONS: NONE\n",
                     encoding="utf-8")
        return f

    study = ("# ROOT CAUSE STUDY\n\n## SET 1\nWHERE: the shader, not the mesh\nALTERNATIVES: a ready asset; bake it\n"
             "DECISION: bake it\n\n## material SET 2\nWHERE: import settings\nALTERNATIVES: preset\nDECISION: preset\n")
    (d / "ROOT_CAUSE_STUDY.md").write_text(study, encoding="utf-8")
    (d / "STUDY_EMPTY.md").write_text("## SET 1\nWHERE: <where>\nALTERNATIVES:\nDECISION: ...\n", encoding="utf-8")
    ok = resume("ok", ["hair: round=4 set=2 study=ROOT_CAUSE_STUDY.md", "eyes: round=3 set=1 study=NONE"])
    expect("round_check set 1 and a studied set 2 pass", "round_check.py", 0, "--resume", ok,
           says="ROUNDS: PASS files=1 defects=2 failed=0")
    expect("round_check round 4 without a study", "round_check.py", 1, "--resume",
           resume("nostudy", ["hair: round=4 set=2 study=NONE"]), says=["needs a root-cause study after set 1", "ROUNDS: FAIL"])
    expect("round_check study file missing", "round_check.py", 1, "--resume",
           resume("gone", ["hair: round=5 set=2 study=NOPE.md"]), says="study file not found: NOPE.md")
    expect("round_check study lines empty", "round_check.py", 1, "--resume",
           resume("empty", ["hair: round=4 set=2 study=STUDY_EMPTY.md"]),
           says="STUDY_EMPTY.md SET 1: WHERE, ALTERNATIVES, DECISION empty or missing")
    expect("round_check set 3 needs a SET 2 section for this defect", "round_check.py", 1, "--resume",
           resume("set3", ["hair: round=7 set=3 study=ROOT_CAUSE_STUDY.md"]), says="no `## SET 2` section")
    expect("round_check a section named for the defect counts", "round_check.py", 0, "--resume",
           resume("named", ["material: round=7 set=3 study=ROOT_CAUSE_STUDY.md"]), says="ROUNDS: PASS")
    expect("round_check set must match the round", "round_check.py", 1, "--resume",
           resume("wrongset", ["hair: round=4 set=1 study=ROOT_CAUSE_STUDY.md"]), says="round 4 belongs to set 2")
    expect("round_check numbers", "round_check.py", 1, "--resume", resume("nan", ["hair: round=x set=1 study=NONE"]),
           says="must be numbers")
    none = d / "none"
    none.mkdir()
    (none / "RESUME_STATE.md").write_text("PROGRESS: x\nFIX_ROUNDS: NONE\n", encoding="utf-8")
    expect("round_check FIX_ROUNDS NONE", "round_check.py", 0, "--dir", none, says="ROUNDS: PASS files=1 defects=0")
    (none / "RESUME_STATE.md").write_text("PROGRESS: x\n", encoding="utf-8")
    expect("round_check without the field", "round_check.py", 0, "--dir", none, says="no FIX_ROUNDS field")
    expect("round_check --dir default glob", "round_check.py", 1, "--dir", d, says="ROUNDS: FAIL files=")
    expect("round_check no RESUME_STATE", "round_check.py", 1, "--dir", d / "round_none_here",
           says="no RESUME_STATE*.md")


TR_GOOD = """TEST REQUEST: BENCH hair pass 40
FROM: line-a worker
PURPOSE: AC-3 hair look
MIN_SCOPE: one scene, 3 sets
TIER: 1
CHANGES: hair shader (switch HAIR_V2)
SWITCHES: HAIR_V2 on / off
EXCLUSIVE_MIN: 10
NORMAL_MIN: 20
BUILD_GB: 6.5
CAPTURE: 3 x 200 x 4 MiB = 2.34
CACHE_GB: 3
WRITE_GB: 12
DURATION: 3 x 12 min = 36
TIER0_DONE: unit tests, offline render check
"""


def test_test_request(tmp):
    """gate_check --test-request: every field filled; space in GiB covering build + capture + cache (L-030, L-031);
    duration = sets x measured minutes with timeouts, within the limit (L-033)."""
    expect("blank template TEST_REQUEST is refused", "gate_check.py", 1, "--test-request", TEMPLATES / "TEST_REQUEST.md")
    gate(tmp, "tr_ok", "test-request", TR_GOOD, 0)
    gate(tmp, "tr_capture_none", "test-request", TR_GOOD.replace("3 x 200 x 4 MiB = 2.34", "NONE"), 0)
    gate(tmp, "tr_missing", "test-request", TR_GOOD.replace("DURATION: 3 x 12 min = 36\n", ""), 1, "DURATION: missing")
    gate(tmp, "tr_empty", "test-request", TR_GOOD.replace("CACHE_GB: 3", "CACHE_GB:"), 1, "CACHE_GB")
    gate(tmp, "tr_decimal_gb", "test-request", TR_GOOD.replace("BUILD_GB: 6.5", "BUILD_GB: 6.5 GB"), 1, "not decimal GB")
    gate(tmp, "tr_capture_math", "test-request", TR_GOOD.replace("= 2.34", "= 0.5"), 1, "CAPTURE: 3 x 200 x 4 MiB is 2.34")
    gate(tmp, "tr_capture_form", "test-request", TR_GOOD.replace("3 x 200 x 4 MiB = 2.34", "about 2 GiB"), 1,
         "CAPTURE: `<sets>")
    gate(tmp, "tr_write_short", "test-request", TR_GOOD.replace("WRITE_GB: 12", "WRITE_GB: 8"), 1,
         "less than BUILD_GB + CAPTURE + CACHE_GB")
    gate(tmp, "tr_duration_math", "test-request", TR_GOOD.replace("= 36", "= 20"), 1, "DURATION: 3 x 12 is 36")
    gate(tmp, "tr_duration_form", "test-request", TR_GOOD.replace("3 x 12 min = 36", "about half an hour"), 1,
         "DURATION: `<sets>")
    gate(tmp, "tr_over_limit", "test-request", TR_GOOD.replace("hair pass 40", "hair pass 30"), 1,
         "the limit 30 minutes is below DURATION 36")


def test_poll_hint(tmp):
    """poll_hint.py (PostToolUse): the third read of one log by one session within the window adds 等完成通知;
    it never blocks (L-041)."""
    state = tmp / "poll_state"

    def hook(name, command, session="s1", tool="Bash", hint=False, extra=()):
        global total
        total += 1
        event = json.dumps({"session_id": session, "tool_name": tool, "tool_input": {"command": command}})
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "poll_hint.py"), "--state-dir", str(state),
                               *extra], input=event, capture_output=True, encoding="utf-8")
        got = "等完成通知" in done.stdout
        if done.returncode != 0 or got != hint or (hint and '"hookEventName": "PostToolUse"' not in done.stdout):
            failures.append(f"{name}: expected exit 0 hint={hint}, got {done.returncode} hint={got}: {done.stdout[-200:]}")

    hook("poll_hint first read", "tail -n 20 D:/w/run.log")
    hook("poll_hint other session", "tail -n 20 D:/w/run.log", session="s2")
    hook("poll_hint second read, other verb", "Get-Content D:\\w\\run.log -Tail 20", tool="PowerShell")
    hook("poll_hint third read hints", "cat d:/w/RUN.log | grep ERROR", hint=True)
    hook("poll_hint count starts again", "tail D:/w/run.log")
    hook("poll_hint cat of source is not a log read", "cat tools/a.py && cat tools/a.py && cat tools/a.py")
    hook("poll_hint other tools are ignored", "tail D:/w/run.log", tool="Read")
    hook("poll_hint other session still at 1", "tail -f D:/w/run.log", session="s2")
    hook("poll_hint one command reading twice counts once", "tail x.log; tail x.log", session="s3")
    hook("poll_hint window", "tail y.log", session="s4", extra=("--window", "0"))
    hook("poll_hint window 0 never adds up", "tail y.log", session="s4", extra=("--window", "0"))
    hook("poll_hint --times", "tail z.log", session="s5", extra=("--times", "1"), hint=True)
    global total
    total += 1
    done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "poll_hint.py"), "--state-dir", str(state)],
                          input="not json", capture_output=True, encoding="utf-8")
    if done.returncode != 0 or done.stdout.strip():
        failures.append(f"poll_hint bad input: expected exit 0 and no output, got {done.returncode}: {done.stdout[-200:]}")


def test_poll_report(tmp):
    """1.3.0 §6: poll_hint.py report counts log reads per session from action logs, for the Director's weekly report."""
    d = tmp / "poll_report"
    d.mkdir()

    def line(ts, session, command, tool="Bash", kind="result"):
        return json.dumps({"seq": 0, "ts": ts, "session_id": session, "tool": tool, "kind": kind,
                           "input": json.dumps({"command": command}), "result": {"status": "ok"}}) + "\n"

    (d / "a.jsonl").write_text(
        line("2026-11-01T01:00:00.000+00:00", "S1", "tail run.log")
        + line("2026-11-07T01:00:00.000+00:00", "S1", "tail -n 5 D:/w/run.log")
        + line("2026-11-07T01:02:00.000+00:00", "S1", "Get-Content D:\\w\\run.log -Tail 5", tool="PowerShell")
        + line("2026-11-07T01:04:00.000+00:00", "S1", "cat d:/w/RUN.log")
        + line("2026-11-07T01:05:00.000+00:00", "S1", "tail other.log")
        + line("2026-11-07T01:06:00.000+00:00", "S1", "tail run.log", kind="decision")
        + line("2026-11-07T01:07:00.000+00:00", "S1", "x", tool="Read")
        + "not json\n", encoding="utf-8")
    (d / "b.jsonl").write_text(line("2026-11-07T02:00:00.000+00:00", "S2", "tail b.log")
                               + line("2026-11-07T02:00:30.000+00:00", "S2", "git status"), encoding="utf-8")
    smap = d / "sessions.json"
    smap.write_text(json.dumps({"schema_version": 1, "sessions": {"S1": {"profile": "worker", "name": "line-a"}}}),
                    encoding="utf-8")

    def rep(name, code, *args, says=(), lacks=()):
        global total
        total += 1
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", str(TOOLS / "poll_hint.py"), "report",
                               *[str(x) for x in args]], capture_output=True, encoding="utf-8")
        out = done.stdout + done.stderr
        bad = [s for s in says if s not in out] + [f"not {s}" for s in lacks if s in out]
        if done.returncode != code or bad:
            failures.append(f"poll_hint report {name}: expected exit {code}, got {done.returncode}; {bad}: {out[-600:]}")
        return done.stdout

    rep("per session, glob", 0, "--log", d / "*.jsonl", "--sessions", smap,
        says=["line-a", "POLL_REPORT: sessions=2 log_reads=6 hints=1 lines=9 logs=2 since=all", "d:/w/run.log x3"])
    rep("--since drops the old line", 0, "--log", d / "a.jsonl", "--since", "2026-11-06",
        says=["POLL_REPORT: sessions=1 log_reads=4 hints=1 lines=6 logs=1"])
    out = rep("--json", 0, "--log", d / "a.jsonl", "--log", d / "b.jsonl", "--json")
    global total
    total += 1
    try:
        data = json.loads(out)
        rows = {r["session"]: r for r in data["sessions"]}
        ok = rows["S1"]["log_reads"] == 5 and rows["S1"]["files"] == 3 and rows["S2"]["hints"] == 0 \
            and data["total"]["log_reads"] == 6
    except (ValueError, KeyError):
        ok = False
    if not ok:
        failures.append(f"poll_hint report --json: {out[-500:]}")
    rep("--window 0 gives no hint", 0, "--log", d / "a.jsonl", "--window", "0", says=["hints=0"])
    rep("a missing log", 2, "--log", d / "none.jsonl", says=["no log at"])
    rep("a bad --since", 2, "--log", d / "a.jsonl", "--since", "last week", says=["not an ISO"])


def nogit_env():
    """os.environ with every PATH folder that holds a git program taken out: a ZIP install on a machine without git."""
    names = ("git", "git.exe", "git.cmd", "git.bat")
    keep = [folder for folder in os.environ.get("PATH", "").split(os.pathsep)
            if folder and not any((pathlib.Path(folder) / name).is_file() for name in names)]
    return {**os.environ, "PATH": os.pathsep.join(keep)}


def test_no_git(tmp):
    """2.1.0 (report 5): with no git on PATH, `evidence_record run` still writes its record (git fields null, a note on
    stderr), the trusted rerun is refused NOT_RUN (exit 2, never a pass), and doctor says git is missing (exit 2)."""
    env = nogit_env()
    if shutil.which("git", path=env["PATH"]):
        return skip("test_no_git", "git is still found after taking its folders off PATH")
    root = tmp / "nogit"
    work, out = root / "work", root / "records"
    work.mkdir(parents=True)
    py = sys.executable
    (work / "check.py").write_text("print('checked')\n", encoding="utf-8")

    def tool(name, *args):
        done = subprocess.run([py, "-I", "-X", "utf8", str(TOOLS / name), *map(str, args)], capture_output=True,
                              encoding="utf-8", env=env)
        return done.returncode, done.stdout, done.stderr

    code, stdout, stderr = tool("evidence_record.py", "run", "--out-dir", out, "--label", "AC-1", "--cwd", work, "--", py, "check.py")
    records = sorted(out.glob("*-AC-1.json"))
    data = json.loads(records[0].read_text(encoding="utf-8")) if records else {}
    check("no git: evidence run exits 0 and says exit=0", code == 0 and "exit=0" in stdout, stdout + stderr)
    check("no git: evidence run writes the record", len(records) == 1, f"{records} {stderr}")
    check("no git: the record's git fields are null", data.get("git") == {"head": None, "dirty": None}, str(data.get("git")))
    check("no git: evidence run says why the git fields are empty", "git metadata not available (git not found" in stderr, stderr)
    if not records:
        return
    code, stdout, _ = tool("evidence_record.py", "verify", records[0])
    check("no git: verify without --rerun still works", code == 0 and "EVIDENCE_VERIFY: OK" in stdout, stdout)
    order = root / "WO-001-parser.md"
    body = with_checks(TYPED_ORDER.format(base="0" * 40), f"AC-1: {json.dumps([py, 'check.py'])}")
    order.write_text(body, encoding="utf-8")
    log = root / "log.md"
    log.write_text(f"DISPATCH WO-001 rev=1 sha={hashlib.sha256(body.encode('utf-8')).hexdigest()}\n", encoding="utf-8")
    code, stdout, stderr = tool("evidence_record.py", "verify", records[0], "--rerun", "--order", order, "--dispatch-log", log,
                                "--repo", work, "--candidate", "a" * 40)
    check("no git: the trusted rerun is NOT_RUN exit 2, not a pass", code == 2 and "EVIDENCE_VERIFY: NOT_RUN git not found" in stdout
          and "OK" not in stdout, stdout + stderr)
    code, stdout, stderr = tool("doctor.py", "--repo", work)
    check("no git: doctor exits 2 and says git is missing", code == 2 and "doctor: git not found" in stderr, stdout + stderr)


def test_dispatch_plan_rule():
    """2.1.0 (PO, L-046): docs/01 keeps the one dispatch-plan line and the Director's scope; docs/05 holds the details;
    docs/03 holds the PO-reading lines word for word; docs/06b holds the rehearsal and the merged tool call."""
    root = TOOLS.parent
    read = lambda name: (root / name).read_text(encoding="utf-8")
    one, three, five, ten, six_b = (read(f"docs/{name}.md") for name in
                                    ("01_roles_authority", "03_communication", "05_models_effort", "10_lessons_learned",
                                     "06b_on_demand_procedures"))
    check("docs/01 has the dispatch-plan line", "- 每次派工前先做派工規劃，不把事情都攬在自己身上（`docs/05`「派工規劃」）。" in one)
    check("docs/01 does not narrow the Director to dispatch only", "只派工" not in one)
    check("docs/05 has the dispatch-plan section", "### 派工規劃" in five and "Single Writer" in five.split("### 派工規劃")[-1])
    check("docs/10 has lesson L-046", "L-046" in ten)
    check("docs/03 first step of each round, word for word (the reading side names the choice page, 總監 W4 N1)",
          "1. **每輪第一步讀待決頁**（任何喚醒）：照待決頁程序（含選擇頁）讀回覆和新留言，同輪執行或派工並關閉；未能完成則寫續辦紀錄。" in three)
    check("docs/03 end-of-round check, word for word",
          "- 每輪結束前自查：待決頁已讀、本輪 PO 訊息已處理並登記、已回覆項目已關閉或留有續辦紀錄。" in three)
    check("docs/06b has the hand-over rehearsal", "### 接手演練" in six_b and "metrics_report.py --run" in six_b)
    check("docs/06b has the merged per-round tool call", "合併工具呼叫" in six_b)


def test_status_po_hint(tmp):
    """2.1.0 shadow (report 5 F-4): the PO filled ANSWER but left STATUS open; the Director status.py says so in one
    line (the exit code does not change), and says nothing for an empty ANSWER or the template's <PO 填>."""
    d = tmp / "status_po_hint"
    d.mkdir(parents=True)
    page = d / "PO_PENDING.md"
    page.write_text("ID: OD-1\nSTATUS: open\nANSWER: A\n\nID: OD-2\nSTATUS: open\nANSWER: <PO 填>\n\nID: OD-3\nSTATUS: open\n"
                    "ANSWER:\n\nID: OD-4\nSTATUS: answered\nANSWER: B\n", encoding="utf-8")
    conf = d / "status.json"
    conf.write_text(json.dumps({"schema_version": 1, "name": "director", "po_page": {"path": "PO_PENDING.md", "counts": [
        {"label": "answered", "regex": r"^STATUS:\s*answered\b"}]}}), encoding="utf-8")
    script = d / "status.py"
    expect("status_gen writes the PO hint script", "status_gen.py", 0, "--out", script, "--config", conf, says="WROTE")
    done = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, encoding="utf-8")
    check("status.py: open with an ANSWER gives one hint, exit unchanged", done.returncode == 0
          and "answered=1" in done.stdout and "PO hint: 1 item(s) still STATUS open with an ANSWER filled in (OD-1)" in done.stdout,
          done.stdout + done.stderr)
    page.write_text("ID: OD-2\nSTATUS: open\nANSWER: <PO 填>\n", encoding="utf-8")
    done = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, encoding="utf-8")
    check("status.py: no hint without a filled ANSWER", done.returncode == 0 and "PO hint" not in done.stdout, done.stdout)


def test_metrics_run(tmp):
    """2.1.0 (report 4 P-3/P-4): metrics_report --run counts one rehearsal run's events, --compare subtracts it from a
    baseline; a repeated event_id counts once, a time without its zone is left out, a missing number is UNKNOWN."""
    base, run_dir = tmp / "mrun" / "base", tmp / "mrun" / "t"
    for folder in (base, run_dir):
        (folder / "events").mkdir(parents=True)
    event = lambda eid, type_, at, **extra: {"v": 1, "event_id": eid, "type": type_, "at": at, **extra}
    ask = lambda eid, at, decision, topic, ask_id: event(eid, "asked", at, decision_id=decision, topic_id=topic, scope_id="S", ask_id=ask_id)
    (run_dir / "run.json").write_text(json.dumps({"v": 1, "started_at": "2026-11-08T10:00:00+08:00"}), encoding="utf-8")
    first = ask("e1", "2026-11-08T10:01:00+08:00", "D1", "T1", "A1")
    (run_dir / "events" / "a.json").write_text(json.dumps([
        first, first,  # the same event written twice counts once
        ask("e2", "2026-11-08T10:05:00+08:00", "D1", "T1", "A2"),  # asked again: one re-ask
        event("e3", "answer_received", "2026-11-08T10:06:00+08:00", decision_id="D1", ask_id="A2"),
        ask("e4", "2026-11-08T10:07:00+08:00", "D2", "T2", "A3"),
        event("e5", "po_action", "2026-11-08T10:08:00+08:00", kind="click", count=3),
        event("e6", "po_action", "2026-11-08T02:09:00Z", kind="type"),
        event("e7", "preview_ready", "2026-11-08T10:12:30+08:00"),
        event("e8", "preview_ready", "2026-11-08T10:11:00")]), encoding="utf-8")  # no zone: left out
    (base / "events" / "x.json").write_text(json.dumps([
        event("b1", "run_started", "2026-11-07T09:00:00+08:00"),
        event("b2", "po_action", "2026-11-07T09:10:00+08:00", kind="click", count=10),
        event("b3", "preview_ready", "2026-11-07T09:30:00+08:00"),
        ask("b4", "2026-11-07T09:01:00+08:00", "D1", "T1", "A1")]), encoding="utf-8")
    expect("metrics --run counts the run", "metrics_report.py", 0, "--run", run_dir,
           says=["事件 7 筆；重複 event_id 略過 1 筆；格式不對沒算 1 筆：a.json#9", "| 第一個可用預覽 | 12.5 分鐘 |",
                 "| 決策 | 提出 2、已回覆 1、還在等 1、撤回 0 |", "| 重問 | 1 |", "| PO 操作 | 4（click 3、type 1） |"],
           lacks="# 成效數字")
    expect("metrics --compare subtracts from the baseline", "metrics_report.py", 0, "--run", run_dir, "--compare", base,
           says=["| PO 操作 | 10 | 4 | 6（60%） |", "| 第一個可用預覽 | 30.0 分鐘 | 12.5 分鐘 | 17.5 分鐘 |", "| 重問 | 0 | 1 | -1 |"])
    expect("metrics --compare: more operations than the baseline is a negative saving", "metrics_report.py", 0,
           "--run", base, "--compare", run_dir, says="| PO 操作 | 4 | 10 | -6（-150%） |")
    empty = tmp / "mrun" / "empty"
    (empty / "events").mkdir(parents=True)
    (empty / "events" / "x.json").write_text(json.dumps([ask("z1", "2026-11-08T10:01:00+08:00", "D1", "T1", "A1")]), encoding="utf-8")
    expect("metrics --run: no start, no preview, no PO action", "metrics_report.py", 0, "--run", empty, "--compare", empty,
           says=["UNKNOWN：沒有開始時間", "| PO 操作 | 0 |", "| PO 操作 | 0 | 0 | 0（百分比 UNKNOWN：基準是 0） |"])
    director = tmp / "mrun" / "DIRECTOR"
    director.mkdir()
    expect("metrics --run with --director prints both", "metrics_report.py", 0, "--director", director,
           "--run", run_dir, says=["# 成效數字", "# 接手演練數字"])
    expect("metrics --run missing folder", "metrics_report.py", 1, "--run", tmp / "mrun" / "nope", says="FAIL run folder not found")
    expect("metrics --compare needs --run", "metrics_report.py", 2, "--director", tmp / "mrun", "--compare", base)
    expect("metrics needs --director or --run", "metrics_report.py", 2)


def guarded(test, *args):
    """Run one test group. Without git on PATH, a group that dies on a missing git program is a named skip, not a crash."""
    global total
    if GIT is None and test.__name__ in GIT_GROUPS:
        return skip(test.__name__)
    mark = (total, len(failures))
    try:
        test(*args)
    except OSError as error:
        if GIT is not None:
            raise
        total, failures[mark[1]:] = mark[0], []  # the group is git work: none of its partial results count
        skip(test.__name__, f"needs git, none on PATH ({type(error).__name__} after it started)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="director_work_selftest_")).resolve()
    try:
        guarded(test_gate, tmp)
        guarded(test_acceptance, tmp)
        guarded(test_table, tmp)
        guarded(test_dispatch, tmp)
        guarded(test_revision, tmp)
        guarded(test_dispatch_events, tmp)
        guarded(test_verdict_binding, tmp)
        guarded(test_evidence_match, tmp)
        guarded(test_candidate, tmp)
        guarded(test_one_fault, tmp)
        guarded(test_trace, tmp)
        guarded(test_metrics, tmp)
        guarded(test_purpose)
        guarded(test_chat_to_product, tmp)
        guarded(test_scope, tmp)
        guarded(test_submodule_ignore, tmp)
        guarded(test_shared_code)
        guarded(test_py39_newline)
        guarded(test_vocabulary)
        guarded(test_must_read_size)
        guarded(test_must_read_reasons)
        guarded(test_hook, tmp)
        guarded(test_hook_protect, tmp)
        guarded(test_hook_rules, tmp)
        guarded(test_session_profiles, tmp)
        guarded(test_pause, tmp)
        guarded(test_auto_pause, tmp)
        guarded(test_audit, tmp)
        guarded(test_audit_names, tmp)
        guarded(test_report_vs_audit, tmp)
        guarded(test_review, tmp)
        guarded(test_guard_modes, tmp)
        guarded(test_doctor, tmp)
        guarded(test_doctor_launch, tmp)
        guarded(test_container, tmp)
        guarded(test_worker_clone, tmp)
        guarded(test_dns_allow, tmp)
        guarded(test_evidence, tmp)
        guarded(test_order_checks, tmp)
        guarded(test_preflight, tmp)
        guarded(test_order_binding, tmp)
        guarded(test_trusted_rerun, tmp)
        guarded(test_rerun_binding, tmp)
        guarded(test_trusted_isolation, tmp)
        guarded(test_usage_mix, tmp)
        guarded(test_status_gen, tmp)
        guarded(test_status_director, tmp)
        guarded(test_round_check, tmp)
        guarded(test_test_request, tmp)
        guarded(test_poll_hint, tmp)
        guarded(test_poll_report, tmp)
        guarded(test_no_git, tmp)
        guarded(test_dispatch_plan_rule)
        guarded(test_metrics_run, tmp)
        guarded(test_status_po_hint, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for failure in failures:
        print(f"FAIL {failure}")
    note = f"; skipped {len(skipped)} git group(s), see SKIP lines" if skipped else ""
    print(f"selftest: {total - len(failures)}/{total} passed{note}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
