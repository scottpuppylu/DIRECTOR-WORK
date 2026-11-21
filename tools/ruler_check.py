"""Did the ruler see enough to judge? Zero matches, a missed real line or a truncated trace is INVALID (DIRECTOR-WORK
2.6.0, N1 + N5; docs/10 lessons 127 and 134).

A checker matched nothing and the run was called FAIL ("no data"), while the log held 103 matching lines: its pattern
`cam=(\\S+)` stopped at the space in a camera name. A counter looked for `*.png`; the captures were `.jpg`; the count was
0. A trace hit its size cap and dropped 1249 rows, and the metrics computed from it were reported as if complete. In
every case the tool, not the product, failed - so the result is INVALID (fix the ruler or the input, then judge), never
FAIL or PASS.

  ruler_check.py lines --pattern REGEX --input PATH ... [--glob GLOB ...] [--expect-min N]
                       [--real-line TEXT ...] [--cap-key NAME] [--required REGEX] [--required-min N]
  ruler_check.py files --input DIR ... --glob GLOB ... [--expect-min N]

  lines     counts the lines matching REGEX in the input files (folders are walked; --glob filters them, default all)
  files     counts the files matching --glob under the folders, and lists every extension present, so `.jpg` files
            beside a `*.png` count are visible
  --expect-min   fewer matches than N (default 1) is INVALID: `ZERO_MATCH` or `TOO_FEW n < N`
  --real-line    a line copied unchanged from the real output (spaces, case and extension as they are); the pattern
                 must match it, or the ruler is INVALID (`RULER_MISSES_REAL_LINE`). Use one for the positive and one
                 for the negative control: a hand-written clean string does not test the ruler
  --cap-key      a counter the writer prints when it drops rows (for example `skippedOverCap`): any value above 0 makes
                 the input TRUNCATED, INVALID, unless --required REGEX matches at least --required-min lines (the rows
                 the verdict needs are there; printed as a WARN)

Prints `SEARCHED files=n ext: .log=3 .jpg=1822 ...`, a line per problem, and last `RULER: OK|INVALID matches=n
files=n problems=n`. Exit 0 OK, 1 INVALID, 2 the input cannot be read. Only reads. It does not judge the product:
with RULER OK, the gate's own PASS / FAIL rule applies to the matched data.
"""
import argparse
import collections
import fnmatch
import pathlib
import re
import sys


def walk(inputs, globs):
    """The files under the inputs that match one of the globs (no glob: all), and the extension counts of all files."""
    chosen, exts = [], collections.Counter()
    for raw in inputs:
        path = pathlib.Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"input not found: {raw}")
        for item in sorted(path.rglob("*")) if path.is_dir() else [path]:
            if not item.is_file():
                continue
            exts[item.suffix.lower() or "(none)"] += 1
            if not globs or any(fnmatch.fnmatch(item.name.lower(), g.lower()) for g in globs):
                chosen.append(item)
    return chosen, exts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("lines", "files"))
    ap.add_argument("--input", nargs="+", required=True, help="files or folders")
    ap.add_argument("--glob", nargs="+", default=[], help="file-name patterns (files: required)")
    ap.add_argument("--pattern", help="lines: the ruler's regex")
    ap.add_argument("--expect-min", type=int, default=1, help="fewer matches than this is INVALID (default 1)")
    ap.add_argument("--real-line", nargs="+", default=[], help="lines copied from the real output; each must match")
    ap.add_argument("--cap-key", help="lines: the dropped-rows counter, e.g. skippedOverCap")
    ap.add_argument("--required", help="lines: with --cap-key, the rows the verdict needs")
    ap.add_argument("--required-min", type=int, default=1)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.mode == "lines" and not a.pattern:
        ap.error("lines needs --pattern")
    if a.mode == "files" and not a.glob:
        ap.error("files needs --glob")
    try:
        pattern = re.compile(a.pattern) if a.pattern else None
        required = re.compile(a.required) if a.required else None
        cap = re.compile(rf"\b{re.escape(a.cap_key)}\s*[=:]\s*(\d+)") if a.cap_key else None
        chosen, exts = walk(a.input, a.glob)
    except (OSError, re.error) as error:
        print(f"RULER: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        return 2
    print(f"SEARCHED files={len(chosen)} ext: " + (" ".join(f"{e}={n}" for e, n in exts.most_common()) or "none"))
    problems, matches = [], 0
    if a.mode == "files":
        matches = len(chosen)
        if matches < a.expect_min:
            others = [f"{e}={n}" for e, n in exts.most_common() if not any(
                fnmatch.fnmatch("x" + e, g.lower()) for g in a.glob)]
            problems.append(("ZERO_MATCH" if matches == 0 else f"TOO_FEW {matches} < {a.expect_min}")
                            + f" for {' '.join(a.glob)}" + (f"; other files present: {' '.join(others)}" if others else ""))
    else:
        dropped, needed = 0, 0
        for item in chosen:
            with open(item, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if pattern.search(line):
                        matches += 1
                    if cap:
                        for m in cap.finditer(line):
                            dropped = max(dropped, int(m.group(1)))
                    if required and required.search(line):
                        needed += 1
        if matches < a.expect_min:
            problems.append("ZERO_MATCH" if matches == 0 else f"TOO_FEW {matches} < {a.expect_min}")
        if dropped:
            if required and needed >= a.required_min:
                print(f"~ WARN TRUNCATED {a.cap_key}={dropped}: the required rows are present ({needed} >= "
                      f"{a.required_min}); every other metric from this input is INVALID")
            else:
                problems.append(f"TRUNCATED {a.cap_key}={dropped}" + (f", required rows {needed} < {a.required_min}"
                                                                     if required else ", no --required rows given"))
    for line in a.real_line:
        if pattern is not None and not pattern.search(line):
            problems.append(f"RULER_MISSES_REAL_LINE {line[:120]!r}")
        if pattern is None and not any(fnmatch.fnmatch(line.lower(), g.lower()) for g in a.glob):
            problems.append(f"RULER_MISSES_REAL_LINE {line[:120]!r} (no --glob matches this real file name)")
    for p in problems:
        print(f"INVALID {p}")
    print(f"RULER: {'INVALID' if problems else 'OK'} matches={matches} files={len(chosen)} problems={len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:  # one line, never a Traceback
        print(f"RULER: NOT_RUN {type(error).__name__}: {str(error)[:200]}")
        sys.exit(2)
