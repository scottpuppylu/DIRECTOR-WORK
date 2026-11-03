"""Check that a memory index (for example MEMORY.md) stays small. It is loaded on every call.

Prints size in bytes, a rough token estimate and the longest lines; exit 1 when over the limit.
Default limit 6144 bytes (about 3k tokens for mixed Chinese / English text; the estimate is bytes / 2).
Without --file it looks at ~/.claude/projects/<current-folder-as-project-dir>/memory/MEMORY.md.
Only reads; tidy the index by hand as described in docs/09_memory.md.
"""
import argparse
import pathlib
import re
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="memory index file")
    ap.add_argument("--max-bytes", type=int, default=6144, help="limit in bytes (default 6144)")
    ap.add_argument("--top", type=int, default=5, help="how many longest lines to show (default 5)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if a.file:
        path = pathlib.Path(a.file)
    else:
        name = re.sub(r"[^A-Za-z0-9]", "-", str(pathlib.Path.cwd().resolve()))
        path = pathlib.Path.home() / ".claude" / "projects" / name / "memory" / "MEMORY.md"
    if not path.is_file():
        print(f"NOT_FOUND {path}")
        return 1
    raw = path.read_bytes()
    lines = raw.decode("utf-8", "replace").splitlines()
    size = len(raw)
    links = [m for line in lines for m in re.findall(r"\]\(([^)]+)\)", line)]
    dup = sorted({x for x in links if links.count(x) > 1})
    ok = size <= a.max_bytes
    print(f"{'OK  ' if ok else 'OVER'} {path.name}: {size} bytes (limit {a.max_bytes}), ~{size // 2} tokens, "
          f"{len(lines)} lines, {len(links)} links")
    if dup:
        print(f"duplicate links: {', '.join(dup)}")
    if not ok:
        print("longest lines (line: bytes):")
        for n, line in sorted(enumerate(lines, 1), key=lambda t: -len(t[1].encode("utf-8")))[:a.top]:
            print(f"  {n}: {len(line.encode('utf-8'))}")
        print("tidy per docs/09_memory.md: back up first, move closed / history entries to ARCHIVE_INDEX.md, "
              "keep rule entries and open work.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
