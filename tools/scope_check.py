"""Compare what a branch really changed with the SCOPE / FORBIDDEN lists of its work order.

Changed = tracked files that differ from the merge base with BASE_REF (committed, staged or not; both sides of a rename)
plus untracked files that git does not ignore. FORBIDDEN wins over SCOPE. A path that matches no SCOPE entry is outside.

Globs are relative to the repo root: `*` stays inside one folder, `**` crosses folders, a name without a wildcard also
covers everything below it. A leading `/` is ignored. Case is ignored on Windows.
Not seen: ignored files, files outside the repo. Only reads.

The last line is the one to paste into the TASK REPORT. Exit 0 pass, 1 violation, 2 could not check.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys


def parse_list(text, key):
    """Items of a `KEY:` line followed by `- item` lines; None when the key is missing."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.fullmatch(rf"\s*{key}\s*[:：]\s*", line):
            items = []
            for item in lines[n + 1:]:
                m = re.match(r"\s*-\s+(.*)", item)
                if not m:
                    break
                items.append(re.split(r"\s+#", m.group(1))[0].strip())
            return items
    return None


def glob_regex(glob):
    g = glob.replace("\\", "/")
    g = g[2:] if g.startswith("./") else g.lstrip("/")
    g = g + "**" if g.endswith("/") else g
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif g.startswith("**", i):
            out, i = out + ".*", i + 2
        elif g[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif g[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(g[i]), i + 1
    if not re.search(r"[*?]", g):
        out += "(?:/.*)?"
    return re.compile(out, re.I if os.name == "nt" else 0)


def matches(path, patterns):
    return next((glob for glob, rx in patterns if rx.fullmatch(path)), None)


def git(root, *args):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if done.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order", required=True, help="work order file holding SCOPE, FORBIDDEN and BASE_REF")
    ap.add_argument("--repo", default=".", help="any folder inside the worktree to check (default: current folder)")
    ap.add_argument("--base", help="base ref (default: BASE_REF of the work order)")
    ap.add_argument("--max-lines", type=int, default=20, help="how many violating paths to print (default 20)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    def cannot(reason):
        print(f"SCOPE_CHECK: NOT_RUN {reason}")
        return 2

    order = pathlib.Path(a.order)
    if not order.is_file():
        return cannot(f"work order not found: {a.order}")
    text = order.read_text(encoding="utf-8-sig")
    scope, forbidden = parse_list(text, "SCOPE"), parse_list(text, "FORBIDDEN")
    if scope is None or forbidden is None:
        return cannot("work order has no SCOPE: / FORBIDDEN: list (run gate_check.py --order)")
    if not scope or not forbidden:
        return cannot("SCOPE: / FORBIDDEN: has no `- item` line right below it (run gate_check.py --order)")
    scope, forbidden = [s for s in scope if s != "NONE"], [f for f in forbidden if f != "NONE"]
    base = a.base
    if not base:
        m = re.search(r"^\s*BASE_REF\s*=\s*(.*)$", text, re.M)
        value = m.group(1).split("@")[-1].split() if m else []
        base = value[0] if value else ""
    if not base or base.startswith("<"):
        return cannot("no usable BASE_REF in the work order; pass --base")

    try:
        root = git(a.repo, "rev-parse", "--show-toplevel").strip()
        merge_base = git(root, "merge-base", base, "HEAD").strip()
        tracked = git(root, "diff", "--name-only", "--no-renames", "-z", merge_base).split("\0")
        untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    except (RuntimeError, OSError) as error:
        return cannot(str(error))

    changed = sorted({path for path in tracked + untracked if path})
    scope_rx = [(g, glob_regex(g)) for g in scope]
    forbidden_rx = [(g, glob_regex(g)) for g in forbidden]
    hits = []
    for path in changed:
        rule = matches(path, forbidden_rx)
        if rule:
            hits.append(("FORBIDDEN", path, rule))
        elif not matches(path, scope_rx):
            hits.append(("OUTSIDE", path, ""))
    for kind, path, rule in hits[:a.max_lines]:
        print(f"{kind:9} {path}" + (f"  ({rule})" if rule else ""))
    if len(hits) > a.max_lines:
        print(f"... {len(hits) - a.max_lines} more")
    count = sum(1 for hit in hits if hit[0] == "FORBIDDEN")
    print(f"SCOPE_CHECK: {'VIOLATION' if hits else 'PASS'} base={merge_base[:10]} changed={len(changed)} "
          f"forbidden={count} outside={len(hits) - count}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
