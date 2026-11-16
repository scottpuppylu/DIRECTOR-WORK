"""Before deleting: is any candidate still referenced? (2.5.0; lesson: a cleanup deleted inputs two other work lines
still needed.) Only reads; never deletes, moves or writes anything.

  delete_guard.py [PATH ...] [--list FILE] [--repo DIR ...] [--refs GLOB ...] [--no-basename]

Candidates come from the arguments and from --list (one path per line; blank lines and `#` lines skipped). Each
candidate is looked for as its full text (with / and \\ both tried) and, unless --no-basename, as its file name:

  --repo DIR    tracked files of that git repository, via `git grep -F -i -I` (repeatable)
  --refs GLOB   any other file that declares inputs: RESUME_STATE*.md, plans, work orders (repeatable; ** works)

A candidate file's own content does not count as a reference to itself. Prints `REFERENCED <candidate>` with up to
5 `file:line` places (never the line's text), or `CLEAN <candidate>`, and a last line
`DELETE_GUARD: REFERENCED|CLEAN candidates=n referenced=n`.
Exit 1 when any candidate is referenced, 0 when all are clean, 2 on an input error (no candidate, a missing --list
file, a --repo that is not a git repository, no git program).

Safe deletion order (docs/06b): list first -> this guard -> quarantine or back up with a checksum -> delete -> reconcile.
"""
import argparse
import glob
import os
import pathlib
import shutil
import subprocess
import sys

SHOW = 5


def candidates_from(args, list_file):
    out = [a for a in args if a.strip()]
    if list_file:
        for line in pathlib.Path(list_file).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                out.append(line.strip())
    return list(dict.fromkeys(out))


def terms_of(candidate, basename=True):
    text = candidate.rstrip("/\\")
    terms = {text, text.replace("\\", "/"), text.replace("/", "\\")}
    name = os.path.basename(text.replace("\\", "/"))
    if basename and name:
        terms.add(name)
    return sorted(t for t in terms if t)


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def repo_hits(git, repo, terms, candidate):
    args = [git, "-C", str(repo), "grep", "-n", "-F", "-i", "-I", "--no-color"]
    for t in terms:
        args += ["-e", t]
    done = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace")
    if done.returncode not in (0, 1):
        raise RuntimeError(f"git grep in {repo}: {done.stderr.strip()[:200]}")
    hits = []
    for line in done.stdout.splitlines():
        path, _, rest = line.partition(":")
        number = rest.partition(":")[0]
        if not same_file(pathlib.Path(repo) / path, candidate):
            hits.append(f"{repo}/{path}:{number}")
    return hits


def ref_hits(files, terms, candidate):
    low = [t.lower() for t in terms]
    hits = []
    for f in files:
        if same_file(f, candidate):
            continue
        try:
            text = pathlib.Path(f).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if any(t in line.lower() for t in low):
                hits.append(f"{f}:{n}")
    return hits


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Report delete candidates that are still referenced; never deletes.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("paths", nargs="*", help="candidate paths")
    ap.add_argument("--list", metavar="FILE", help="file with one candidate path per line")
    ap.add_argument("--repo", action="append", default=[], metavar="DIR", help="git repository to search (repeatable)")
    ap.add_argument("--refs", action="append", default=[], metavar="GLOB", help="other files to search (repeatable)")
    ap.add_argument("--no-basename", action="store_true", help="match the full path only, not the file name")
    a = ap.parse_args(argv)
    try:
        cands = candidates_from(a.paths, a.list)
    except OSError as error:
        print(f"FAIL input: --list: {type(error).__name__}: {error}")
        return 2
    if not cands:
        print("FAIL input: no candidate (give paths or --list FILE)")
        return 2
    git = shutil.which("git") if a.repo else None
    if a.repo and not git:
        print("FAIL input: --repo needs git on PATH")
        return 2
    for repo in a.repo:
        done = subprocess.run([git, "-C", repo, "rev-parse", "--git-dir"], capture_output=True, encoding="utf-8")
        if done.returncode != 0:
            print(f"FAIL input: --repo {repo}: not a git repository")
            return 2
    ref_files = sorted({f for g in a.refs for f in glob.glob(g, recursive=True) if os.path.isfile(f)})
    if not a.repo and not ref_files:
        print("~ WARN nothing searched: give --repo and/or --refs that match files")
    referenced = 0
    for cand in cands:
        terms = terms_of(cand, not a.no_basename)
        try:
            hits = [h for repo in a.repo for h in repo_hits(git, repo, terms, cand)] + ref_hits(ref_files, terms, cand)
        except RuntimeError as error:
            print(f"FAIL input: {error}")
            return 2
        if hits:
            referenced += 1
            print(f"REFERENCED {cand} ({len(hits)} places)")
            for h in hits[:SHOW]:
                print(f"  - {h}")
        else:
            print(f"CLEAN {cand}")
    print(f"DELETE_GUARD: {'REFERENCED' if referenced else 'CLEAN'} candidates={len(cands)} referenced={referenced}")
    return 1 if referenced else 0


if __name__ == "__main__":
    sys.exit(main())
