"""Compare what a branch really changed with the SCOPE / FORBIDDEN lists of its work order.

Changed = the union of four git states, both sides of a rename: committed (merge base with BASE_REF .. HEAD), staged
(HEAD .. index), unstaged (index .. worktree) and untracked files that git does not ignore. So a change that was
committed or staged and then undone in the worktree is still seen. Submodule changes are always compared, whatever
`submodule.*.ignore` or `diff.ignoreSubmodules` says. Files marked assume-unchanged or skip-worktree, which git diff
skips, are hashed and compared with the index; one that differs counts as unstaged, and a `FLAGGED:` line says how
many are marked (a skip-worktree file missing from the worktree is a sparse checkout and counts as unchanged).
The line above the last one counts each state. FORBIDDEN wins over SCOPE. A path that matches no SCOPE entry is outside.

List items follow gate_check: ` #` starts a comment, and an item in backticks is taken as written.
Globs are relative to the repo root: `*` stays inside one folder, `**` crosses folders, a name without a wildcard also
covers everything below it. A leading `/` is ignored. Case is ignored on Windows.
Not seen: ignored files, files outside the repo. Only reads.

An optional `REQUIRED_CHANGES:` list in the order names globs the work must change: each one that no changed path
matches prints `MISSING <glob>` and makes it a VIOLATION, and the last line ends with ` missing=n`. An order without
the list gets the same output as before.
2.2 (F14): REQUIRED_CHANGES is no longer met by a change that only ever showed in one layer. The four-state union
above still catches out-of-scope work; the required globs are matched against the final result instead: the working
files as they are now (tracked files that differ from the merge base, untracked files, flagged files that differ)
or, with `--candidate SHA`, the candidate commit's tree against its merge base with BASE_REF (use it on the commit you
hand in). A `REQUIRED_BASIS:` line says which. A file staged and then put back as it was is MISSING.

The last line is the one to paste into the TASK REPORT. Exit 0 pass, 1 violation, 2 could not check.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys


def parse_list(text, key):
    """Items of a `KEY:` line followed by `- item` lines; None when the key is missing. ` #` starts a comment; an item
    written in backticks (`- `a #b.txt``) is taken as it is, so a name holding ` #` round-trips (S02)."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.fullmatch(rf"\s*{key}\s*[:：]\s*", line):
            items = []
            for item in lines[n + 1:]:
                m = re.match(r"\s*-\s+(.*)", item)
                if not m:
                    break
                quoted = re.fullmatch(r"`([^`]+)`(?:\s+#.*)?\s*", m.group(1))
                items.append(quoted.group(1) if quoted else re.split(r"\s+#", m.group(1))[0].strip())
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


def git(root, *args, stdin=None):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, input=stdin)
    if done.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout.decode("utf-8", "replace")


def hidden_changes(root):
    """(marked, changed): paths marked assume-unchanged or skip-worktree, and those whose worktree file is not the
    index blob (S03). git diff trusts the marks, so the files are hashed here with the repo's filters."""
    marked = {entry[2:]: entry[0] for entry in git(root, "ls-files", "-v", "-z").split("\0")
              if len(entry) > 2 and (entry[0].islower() or entry[0] == "S")}
    if not marked:
        return {}, set()
    index = {}
    for entry in git(root, "ls-files", "-s", "-z").split("\0"):
        meta, _, path = entry.partition("\t")
        if path in marked:
            index[path] = meta.split()[:2]
    changed, compare = set(), []
    for path, tag in marked.items():
        mode, blob = index.get(path, ("", ""))
        file = pathlib.Path(root, path)
        if mode not in ("100644", "100755"):
            continue  # a symlink or submodule entry: not hashed here
        if not file.is_file():
            if tag.islower():
                changed.add(path)  # assume-unchanged and gone: deleted
            continue  # skip-worktree and gone: a sparse checkout
        compare.append((path, blob))
    if compare:
        hashes = git(root, "hash-object", "--stdin-paths", stdin="\n".join(p for p, _ in compare).encode("utf-8")).split()
        changed |= {path for (path, blob), now in zip(compare, hashes) if now != blob}
    return marked, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order", required=True, help="work order file holding SCOPE, FORBIDDEN and BASE_REF")
    ap.add_argument("--repo", default=".", help="any folder inside the worktree to check (default: current folder)")
    ap.add_argument("--base", help="base ref (default: BASE_REF of the work order)")
    ap.add_argument("--max-lines", type=int, default=20, help="how many violating paths to print (default 20)")
    ap.add_argument("--candidate", help="2.2: the commit handed in; REQUIRED_CHANGES is matched against its tree")
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
    required = parse_list(text, "REQUIRED_CHANGES")
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
        names = ("diff", "--name-only", "--no-renames", "--ignore-submodules=none", "-z")
        states = {"committed": git(root, *names, merge_base, "HEAD"), "staged": git(root, *names, "--cached", "HEAD"),
                  "unstaged": git(root, *names),
                  "untracked": git(root, "ls-files", "--others", "--exclude-standard", "-z")}
        marked, hidden = hidden_changes(root)
        final, basis = None, None
        if required is not None:  # 2.2 (F14): the final result, not the union of layers
            if a.candidate:
                commit = git(root, "rev-parse", "--verify", a.candidate + "^{commit}").strip()
                since = git(root, "merge-base", base, commit).strip()
                final = git(root, *names, since, commit)
                basis = f"candidate={commit[:12]}"
            else:
                final = git(root, *names, merge_base) + "\0" + states["untracked"]
                basis = "worktree-final"
    except (RuntimeError, OSError) as error:
        return cannot(str(error))

    states = {state: {path for path in out.split("\0") if path} for state, out in states.items()}
    states["unstaged"] |= hidden
    changed = sorted(set().union(*states.values()))
    scope_rx = [(g, glob_regex(g)) for g in scope]
    forbidden_rx = [(g, glob_regex(g)) for g in forbidden]
    hits = []
    for path in changed:
        rule = matches(path, forbidden_rx)
        if rule:
            hits.append(("FORBIDDEN", path, rule))
        elif not matches(path, scope_rx):
            hits.append(("OUTSIDE", path, ""))
    count = sum(1 for hit in hits if hit[0] == "FORBIDDEN")
    final = {path for path in (final or "").split("\0") if path} | (hidden if basis == "worktree-final" else set())
    missing = [g for g in required or [] if g != "NONE" and not any(glob_regex(g).fullmatch(path) for path in final)]
    hits += [("MISSING", glob, "") for glob in missing]
    for kind, path, rule in hits[:a.max_lines]:
        print(f"{kind:9} {path}" + (f"  ({rule})" if rule else ""))
    if len(hits) > a.max_lines:
        print(f"... {len(hits) - a.max_lines} more")
    if marked:
        print(f"FLAGGED: {len(marked)} file(s) marked assume-unchanged or skip-worktree; {len(hidden)} differ from the index")
    print("STATES: " + " ".join(f"{state}={len(paths)}" for state, paths in states.items()))
    if basis:
        print(f"REQUIRED_BASIS: {basis} final={len(final)}")
    print(f"SCOPE_CHECK: {'VIOLATION' if hits else 'PASS'} base={merge_base[:10]} changed={len(changed)} "
          f"forbidden={count} outside={len(hits) - count - len(missing)}" + ("" if required is None else f" missing={len(missing)}"))
    return 1 if hits else 0


def not_utf8(error, argv=None):
    """2.2 (v2.1.0 known issue): one line, never a traceback, for an input file that is not UTF-8 text. It names the
    file when it is on the command line or in a folder there (text files only: .md .json .jsonl .txt .log)."""
    import itertools
    named = []
    for arg in (sys.argv[1:] if argv is None else argv):
        path = pathlib.Path(arg)
        try:
            files = [path] if path.is_file() else (list(itertools.islice(
                (p for p in path.rglob("*") if p.suffix.lower() in (".md", ".json", ".jsonl", ".txt", ".log")
                 and ".git" not in p.parts), 2000)) if path.is_dir() else [])
        except (OSError, ValueError):
            files = []
        for file in files:
            try:
                file.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                named.append(str(file))
            except OSError:
                pass
    where = f" ({', '.join(dict.fromkeys(named[:3]))})" if named else ""
    return f"a file is not UTF-8 text{where}: {error.reason} at byte {error.start}; save it as UTF-8 and run again"


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UnicodeDecodeError as error:  # 2.2: one line and NOT_RUN (exit 2), never a traceback
        print(f"SCOPE_CHECK: NOT_RUN {not_utf8(error)}")
        sys.exit(2)
