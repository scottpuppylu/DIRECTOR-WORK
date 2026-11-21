"""A test plan's switches and outputs exist in the build that runs, and the run launched with exactly them (DIRECTOR-WORK
2.6.0, N2; docs/10 lesson 128).

A test plan was copied from the request without checking the code: one run left out two switches it needed and ran
another configuration; a close-up camera the request named existed only in an editor tool, not in the player build, so
it could not be captured. The run was INVALID and the device time was lost. Here every planned switch and output names
the code that implements it (`path:line`), the reference is checked in the commit that is built, and after the run the
launch line the program printed is compared with the plan.

  run_plan_check.py --plan PLAN.json [--repo DIR --commit SHA] [--log RUN=LOG ...] [--launch-regex REGEX]

PLAN.json (schema run-plan-v1):
  {"schema": "run-plan-v1",
   "runs": {"<run>": {"args": ["--mode=on", "--bounds 1"],
                      "code": {"--mode": "src/Mode.cs:42", "--bounds": "src/Bounds.cs:10"},
                      "outputs": [{"name": "side camera", "code": "src/Capture.cs:405"}]}}}
  every switch in args (the part before `=` or the first space) needs a code entry; every output needs a code field

Before the run (--repo, --commit): each `path:line` must exist in that commit (`git show COMMIT:path`, at least `line`
lines): `NOT_IN_BUILD <run> <item> <ref>`. No reference: `NO_CODE_REF <run> <item>`. Without --repo only the presence
of the references is checked (`~ WARN NOT_VERIFIED_IN_BUILD`).
After the run (--log RUN=LOG): the first line matching --launch-regex (default: `command line:` / `argv:` / `launch
args:`, with the arguments in group `args`) must hold every planned argument; `--a=v` and `--a v` count as the same.
`PLAN_MISMATCH <run>: <arg> not in the launch line` or `NO_LAUNCH_LINE <run>` makes that run INVALID - do not judge it.

Last line `RUN_PLAN: OK|STOP runs=n problems=n`. Exit 0 OK, 1 STOP, 2 the plan cannot be read. Only reads.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

SCHEMA = "run-plan-v1"
LAUNCH = r"(?i)(?:command[ -]?line|argv|launch(?:ed)?[ -]args?)\s*[:=]\s*(?P<args>.+)"


def switch(arg):
    return re.split(r"[=\s]", arg.strip(), maxsplit=1)[0]


def norm(text):
    """`--a=v`, `--a v` and repeated spaces as one form."""
    return " " + re.sub(r"\s+", " ", re.sub(r"(--?[A-Za-z0-9_.\-]+)=", r"\1 ", text)).strip() + " "


def ref_ok(repo, commit, ref):
    m = re.fullmatch(r"(?P<path>.+?):(?P<line>\d+)", ref.strip())
    if not m:
        return False
    try:
        text = subprocess.run(["git", "-C", repo, "show", f"{commit}:{m.group('path')}"], capture_output=True,
                              timeout=60, check=True).stdout.decode("utf-8", "replace")
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return False
    return len(text.splitlines()) >= int(m.group("line"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--repo", help="the checkout holding the commit that is built")
    ap.add_argument("--commit", help="the commit that is built")
    ap.add_argument("--log", nargs="+", default=[], metavar="RUN=LOG")
    ap.add_argument("--launch-regex", default=LAUNCH)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if bool(a.repo) != bool(a.commit):
        ap.error("--repo and --commit go together")
    try:
        plan = json.loads(pathlib.Path(a.plan).read_text(encoding="utf-8-sig"))
        if not isinstance(plan, dict) or plan.get("schema") != SCHEMA or not isinstance(plan.get("runs"), dict):
            raise ValueError(f"--plan is not a {SCHEMA} file with a runs object")
        launch = re.compile(a.launch_regex)
        logs = dict(item.split("=", 1) for item in a.log)
    except (OSError, ValueError, re.error) as error:
        print(f"RUN_PLAN: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    problems = []
    if not a.repo:
        print("~ WARN NOT_VERIFIED_IN_BUILD: no --repo / --commit, references were not looked up in the build")
    for run, spec in plan["runs"].items():
        code = spec.get("code") or {}
        items = [(switch(arg), code.get(switch(arg))) for arg in spec.get("args", [])]
        items += [(f"output {o.get('name', '?')}", o.get("code")) for o in spec.get("outputs", [])]
        for name, ref in items:
            if not ref:
                problems.append(f"NO_CODE_REF {run} {name}: write where the build implements it (path:line)")
            elif a.repo and not ref_ok(a.repo, a.commit, ref):
                problems.append(f"NOT_IN_BUILD {run} {name} {ref}: not in {a.commit[:12]} - it cannot run in this build")
        if run in logs:
            text = pathlib.Path(logs[run]).read_text(encoding="utf-8-sig", errors="replace")
            m = next((launch.search(line) for line in text.splitlines() if launch.search(line)), None)
            if m is None:
                problems.append(f"NO_LAUNCH_LINE {run}: the log prints no launch line - INVALID, do not judge it")
                continue
            launched = norm(m.group("args"))
            for arg in spec.get("args", []):
                if norm(arg) not in launched:
                    problems.append(f"PLAN_MISMATCH {run}: {arg} not in the launch line - INVALID, do not judge it")
            print(f"LAUNCH {run}: {m.group('args').strip()[:200]}")
    for p in problems:
        print(f"STOP {p}")
    print(f"RUN_PLAN: {'STOP' if problems else 'OK'} runs={len(plan['runs'])} problems={len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"RUN_PLAN: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
