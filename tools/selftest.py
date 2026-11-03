"""Run gate_check, trace_report, metrics_report, scope_check, evidence_record and hook_guard against good and bad cases
in a temporary folder, and check that the fixed words, the size of the must-read docs, PURPOSE.md and the CHANGELOG have
not drifted.
Prints one line per failed case and a summary; exit 1 when anything fails. Writes only to the temporary folder.
"""
import hashlib
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
    expect("--since still checks an undated file", "gate_check.py", 1, "--since", "2026-01-01", "--report", undated, says="FAIL")
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


def evidence_file(folder, name, head, exit_code=0, timed_out=False, dirty=False, label="AC-1", sha256="ab" * 32):
    """An evidence_record.py file, written directly so the case does not depend on git."""
    record = {"schema": 1, "label": label, "command": ["python", "-c", "0"], "exit_code": exit_code, "timed_out": timed_out,
              "git": {"head": head, "dirty": dirty}, "artifacts": [{"path": "out.txt", "kind": "file", "size": 1, "sha256": sha256}]}
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

    def ev(name, code, record=None, says=None, lacks=None, rows=good, title=f"/ c / {head} / yes", extra="", result="PASS"):
        if record is not None:
            evidence_file(folder, "e.json", **{"head": head, **record})
        report = tmp / f"{name}.md"
        text = match_report(rows, result, sha).replace("/ c / d / yes", title, 1).replace("RESULT:", extra + "RESULT:", 1)
        report.write_text(text, encoding="utf-8")
        expect(name, "gate_check.py", code, "--match", report, order, "--evidence-dir", folder, says=says, lacks=lacks)
        return report

    ev("ev_ok", 0, {}, "OK   match", "  ~ ")  # AC-2 (REVIEW) names out.txt: only AUTO rows are read
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
    ev("ev_head_line", 0, {}, "OK   match", "  ~ ", title="/ c / d / yes", extra=f"HEAD: {head}\n")
    ev("ev_branch_slash", 0, {}, "OK   match", "  ~ ", title=f"/ feature/x / c / {head} / yes")
    ev("ev_no_head", 0, {"head": "fedcba9876543210fedcba9876543210fedcba98"},
       "~ HEAD: the report names no commit hash; evidence HEAD not compared", title="/ c / d / yes")
    ev("ev_fail_row_unchecked", 0, {"exit_code": 3}, "OK   match", rows=["| AC-1 | exit 3 | e.json | FAIL |"] + good[1:],
       result="FAIL")
    plain = ev("ev_flag_off_base", 1, {"exit_code": 3})
    expect("without --evidence-dir a failed record is not read", "gate_check.py", 0, "--match", plain, order, says="OK   match")
    expect("--evidence-dir needs --match", "gate_check.py", 2, "--report", plain, "--evidence-dir", folder)
    expect("--evidence-dir folder missing", "gate_check.py", 2, "--match", plain, order, "--evidence-dir", tmp / "nope")


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
    (root / "PO_PENDING.md").write_text("ID: OD-1\nSTATUS: open\n\nID: OD-2\nSTATUS: closed\n\nID: ACT-1\nSTATUS: answered\n",
                                        encoding="utf-8")
    expect("metrics counts", "metrics_report.py", 0, "--director", root,
           says=["| 返工次數 | 1（CONTINUE_SAME_WORKER 1、SWITCH_TO_OTHER_WORKER 0）；工單改版 2 次（1 份工單） | 裁決 2 份、工單 2 份 |",
                 "| 中斷後遺失的工作 | 1 / 恢復 3 次；1 次沒寫 redo= |", "| PO 介入次數 | 3（OD 2、ACT 1），還在等 PO 1 |",
                 "| 新專案導入卡住 | 1 |", "1 次，tokens 合計 1200，採用的問題 2 個", "UNKNOWN：跑 `usage_report.py`"])
    expect("metrics --since drops older lines", "metrics_report.py", 0, "--director", root, "--since", "2026-01-01",
           says=["| 中斷後遺失的工作 | 1 / 恢復 2 次 |", "範圍：2026-01-01 起"])
    expect("metrics --since drops older orders", "metrics_report.py", 0, "--director", root, "--since", "2026-01-05",
           says=["工單改版 0 次（0 份工單）", "| 新專案導入卡住 | 0 |", "0 次"])
    empty = tmp / "metrics" / "empty"
    empty.mkdir()
    expect("metrics with nothing recorded", "metrics_report.py", 0, "--director", empty,
           says=["UNKNOWN：找不到裁決或工單", "UNKNOWN：沒有 DIRECTOR_LOG.md", "UNKNOWN：沒有 PO_PENDING.md"], lacks="| 0 |")
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
    config = root / "director_work.json"
    config.write_text(json.dumps({"schema_version": 1, "trace_id_pattern": r"^(DD|OD)-\d+$"}), encoding="utf-8")
    base = ("--orders", root / "orders", "--reports", root / "reports")
    expect("trace table", "trace_report.py", 0, *base, "--verdicts", root / "reviews", "--config", config,
           says=["| DD-1 | WO-001 | AC-2 | REVIEW | READY_FOR_REVIEW | out.txt | PASS_WITH_WARNINGS |",
                 "| DD-1 | WO-001 | AC-1 | AUTO | PASS | e.json | PASS_WITH_WARNINGS |",
                 "| REQ7 | WO-003 | AC-1 | AUTO | 沒有報告 |", "## 沒有 TRACES_TO 的工單\n- WO-002",
                 "## 編號格式不符 trace_id_pattern\n- WO-003: REQ7", "stray.md"])
    expect("trace without a pattern accepts any ID", "trace_report.py", 0, *base, says="## 編號格式不符 trace_id_pattern\n- 無")
    expect("trace with a missing folder", "trace_report.py", 1, "--orders", root / "nope", "--reports", root / "reports",
           says="folder not found")


def test_purpose():
    """PURPOSE.md keeps its 7 aims and 9 cores and says only the PO edits it; every CHANGELOG version answers to it."""
    global total
    root = TOOLS.parent
    text = (root / "PURPOSE.md").read_text(encoding="utf-8")
    for heading, count in (("初衷", 7), ("不能破壞的核心", 9)):
        total += 1
        section = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        items = re.findall(r"^\d+\. \*\*", section.group(1), re.M) if section else []
        if len(items) != count:
            failures.append(f"PURPOSE.md: ## {heading} should list {count} items, found {len(items)}; only the PO changes it")
    total += 1
    if "只有 PO 能改本檔" not in text:
        failures.append("PURPOSE.md no longer says 只有 PO 能改本檔")
    for version, body in re.findall(r"^## (\d+\.\d+\.\d+)[^\n]*\n(.*?)(?=^## |\Z)", (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M | re.S):
        total += 1
        if "對齊初衷" not in body:
            failures.append(f"CHANGELOG {version}: no 對齊初衷 line (PURPOSE.md, 改規則前的檢查)")


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


MUST_READ_LIMIT = 13428  # bytes of the 每輪必讀 docs on 2026-11-04; every round re-reads them, so growth costs quota


def test_must_read_size():
    """The docs README marks 每輪必讀 must stay under MUST_READ_LIMIT; raise it only with a reason in the commit."""
    global total
    total += 1
    root = TOOLS.parent
    files = re.findall(r"^\| `(docs/[^`]+)` \|.*\*\*每輪必讀\*\*", (root / "README.md").read_text(encoding="utf-8"), re.M)
    size = sum(len((root / f).read_bytes().replace(b"\r\n", b"\n")) for f in files)
    if not files or size > MUST_READ_LIMIT:
        failures.append(f"must-read docs {files}: {size} bytes, limit {MUST_READ_LIMIT}; trim them or explain the new limit")


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
    future = tmp / "future.json"
    future.write_text('{"schema_version": 2, "window": 250000}', encoding="utf-8")
    expect("unknown config version is refused", *setup[:1], 1, "--repo", repo, "--only-this", "--config", future)
    future.write_text('{"window": 250000}', encoding="utf-8")
    expect("config without a version counts as 1", *setup[:1], 0, "--repo", repo, "--only-this", "--config", future, says="OK")


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
        test_acceptance(tmp)
        test_evidence_match(tmp)
        test_trace(tmp)
        test_metrics(tmp)
        test_purpose()
        test_scope(tmp)
        test_shared_code()
        test_vocabulary()
        test_must_read_size()
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
