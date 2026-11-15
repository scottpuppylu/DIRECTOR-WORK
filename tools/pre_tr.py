"""Before a test request: run every CPU check for the defect classes the change touches (DIRECTOR-WORK 2.3.0, N8).

Test runs on the shared GPU / device came back with defects a CPU check already existed for (a contact check, a hash
compare, a config lint) - the check had simply not been run for that change. A config maps each defect class to the
paths that can cause it and to the CPU check commands that catch it; this runner finds the classes the change touches
and runs all their checks. Any FAIL, or a touched class with no check, blocks the test request.

  pre_tr.py --config PRE_TR.json (--changed PATH ... | --git-diff BASE [--repo DIR] | --classes NAME ...)
            [--strict] [--timeout 600] [--dry-run]

Config (JSON, schema pre-tr-v1; example: templates/pre_tr.json):
  {"schema": "pre-tr-v1",
   "classes": {"<class>": {"paths": ["src/physics/*", "*collider*"],
                           "checks": [{"name": "contact unit test", "cmd": ["{python}", "tests/contact.py"]}]}}}
  paths   fnmatch patterns on the changed files' paths (relative to --repo, `/` separators; `*` also spans `/`)
  checks  each an argv list run without a shell, in the config's folder (or "cwd", relative to it); `{python}` is this
          Python, `{repo}` the --repo folder. Exit 0 is PASS; anything else (or a timeout) is FAIL.

Changed files: --changed PATH ... (given), or --git-diff BASE: `git diff --name-only BASE` plus untracked files in
--repo (default: the current folder). --classes names the classes directly (no path matching).
A touched class with no checks is MISSING; a changed file no class claims is `~ UNCLASSIFIED` (a WARN; with --strict it
blocks too: add it to a class, or to a class with an explicit `"checks": []` and a "why").
Prints per class the files that touched it, per check `PASS|FAIL <class>: <name> (<s>s)` and the failing output's last
lines, and a last line `PRE_TR: PASS|BLOCK classes=n checks=n failed=n missing=n unclassified=n`. --dry-run lists the
checks without running them (exit 0 only when none is missing). Exit 0 PASS, 1 BLOCK, 2 cannot read the config. DW
ships the runner and an example config only; the project owns its classes and checks.
"""
import argparse
import fnmatch
import json
import pathlib
import subprocess
import sys
import time

SCHEMA = "pre-tr-v1"


def load(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("classes"), dict):
        raise ValueError(f"{path} is not a {SCHEMA} config with a \"classes\" object")
    for name, spec in data["classes"].items():
        if not isinstance(spec, dict) or not isinstance(spec.get("paths", []), list) \
                or not isinstance(spec.get("checks", []), list):
            raise ValueError(f"class {name}: paths and checks must be lists")
        for check in spec.get("checks", []):
            if not isinstance(check, dict) or not isinstance(check.get("cmd"), list) or not check["cmd"] \
                    or not all(isinstance(x, str) for x in check["cmd"]):
                raise ValueError(f"class {name}: every check needs \"cmd\": a non-empty argv list of strings")
    return data["classes"]


def git_changed(repo, base):
    out = []
    for args in (["diff", "--name-only", base], ["ls-files", "--others", "--exclude-standard"]):
        done = subprocess.run(["git", "-C", repo, *args], capture_output=True, encoding="utf-8", errors="replace")
        if done.returncode:
            raise ValueError(f"git {' '.join(args)}: {(done.stderr or done.stdout).strip()[:200]}")
        out += [l.strip() for l in done.stdout.splitlines() if l.strip()]
    return sorted(set(out))


def touched(classes, files):
    """({class: [files]}, [unclassified files])."""
    hit, free = {}, []
    for f in files:
        path = f.replace("\\", "/")
        owners = [name for name, spec in classes.items() if any(fnmatch.fnmatch(path, p) for p in spec.get("paths", []))]
        for name in owners:
            hit.setdefault(name, []).append(path)
        if not owners:
            free.append(path)
    return hit, free


def run_check(check, base, repo, timeout):
    """(ok, seconds, last output lines)."""
    argv = [x.replace("{python}", sys.executable).replace("{repo}", repo) for x in check["cmd"]]
    cwd = base / check["cwd"] if check.get("cwd") else base
    start = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, time.monotonic() - start, [f"timeout after {timeout:g}s"]
    except OSError as error:
        return False, time.monotonic() - start, [f"cannot start {argv[0]!r}: {error}"]
    lines = ((done.stdout or "") + (done.stderr or "")).strip().splitlines()
    return done.returncode == 0, time.monotonic() - start, lines[-5:] + [f"exit {done.returncode}"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="the pre-tr-v1 JSON config")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--changed", nargs="+", metavar="PATH", help="the changed files")
    src.add_argument("--git-diff", metavar="BASE", help="changed files = git diff --name-only BASE + untracked")
    src.add_argument("--classes", nargs="+", metavar="NAME", help="run the checks of these classes")
    ap.add_argument("--repo", default=".", help="the worktree (default: current folder)")
    ap.add_argument("--strict", action="store_true", help="an unclassified changed file blocks too")
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds per check (default 600)")
    ap.add_argument("--dry-run", action="store_true", help="list the checks, run nothing")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    repo = str(pathlib.Path(a.repo).resolve())
    try:
        classes = load(a.config)
        if a.classes:
            unknown = [c for c in a.classes if c not in classes]
            if unknown:
                raise ValueError(f"unknown class(es): {', '.join(unknown)} (config has: {', '.join(sorted(classes))})")
            hit, free = {c: ["(named)"] for c in a.classes}, []
        else:
            files = a.changed if a.changed else git_changed(repo, a.git_diff)
            hit, free = touched(classes, files)
    except (OSError, ValueError) as error:
        print(f"PRE_TR: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    base = pathlib.Path(a.config).resolve().parent
    checks = failed = missing = 0
    for name in sorted(hit):
        spec = classes[name]
        print(f"CLASS {name}: {', '.join(hit[name][:6])}" + (f" (+{len(hit[name]) - 6})" if len(hit[name]) > 6 else ""))
        if not spec.get("checks"):
            if "why" in spec and str(spec.get("why")).strip():
                print(f"  ~ no CPU check by design: {spec['why']}")
                continue
            missing += 1
            print(f"  MISSING {name}: no CPU check for this class; add one (or \"checks\": [] with a \"why\") before the TR")
            continue
        for check in spec["checks"]:
            checks += 1
            label = check.get("name") or " ".join(check["cmd"])
            if a.dry_run:
                print(f"  WOULD RUN {name}: {label}")
                continue
            ok, seconds, tail = run_check(check, base, repo, a.timeout)
            print(f"  {'PASS' if ok else 'FAIL'} {name}: {label} ({seconds:.1f}s)")
            if not ok:
                failed += 1
                for line in tail:
                    print(f"    | {line[:200]}")
    for f in free:
        print(f"~ UNCLASSIFIED {f}: no defect class claims it" + (" (blocks: --strict)" if a.strict else ""))
    if not hit:
        print("~ the change touches no defect class: nothing to run")
    blocked = failed or missing or (a.strict and free)
    if blocked:
        print("BLOCK: the test request waits until every check passes and every touched class has a check")
    print(f"PRE_TR: {'BLOCK' if blocked else 'PASS'} classes={len(hit)} checks={checks} failed={failed} "
          f"missing={missing} unclassified={len(free)}" + (" (dry run)" if a.dry_run else ""))
    return 1 if blocked else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"PRE_TR: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
