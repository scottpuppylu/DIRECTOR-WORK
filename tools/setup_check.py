"""Check that setup made the PO page (DIRECTOR-WORK 2.2.0, BOOTSTRAP step 6; run before the first report, step 13).

  setup_check.py <WS>/DIRECTOR [...]     each folder's DIRECTOR_STATE.md (a state file may be given instead)

DIRECTOR_STATE.md must say where the PO page is and whether it is pinned. Three states pass:

  PO_PAGE_URL: https://claude.ai/artifact/<id>      (or https://claude.ai/code/artifact/<id>)
  PO_PAGE_PINNED: yes

  PO_PAGE_URL: https://claude.ai/artifact/<id>
  PO_PAGE_PINNED: no reason=<why>                   pinning failed: also prints a note to ask the PO to pin it

  PO_PAGE_URL: NONE reason=<why>                    no page (no Artifact tool, publishing failed, the PO said no);
                                                    PO_PAGE_PINNED may be left out or be `no reason=<why>`

A missing or repeated line, a placeholder (`<...>`), an empty or missing reason, or any other value fails.
Prints `OK   setup <file>` or `FAIL setup <file>` with one `  - problem` line each and `  ~ note` lines; exit 1 when
any file fails. Standard library only, read only.
"""
import argparse
import pathlib
import re
import sys

ARTIFACT_URL = re.compile(r"https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]+/?")
PLACEHOLDER = re.compile(r"<[^<>@\n]+>")  # same rule as gate_check: <name@host> is an address, not a placeholder
CODE = re.compile(r"`[^`\n]*`")


def filled(name, value, problems):
    if value.strip() in ("", "...", "…"):
        problems.append(f"{name}: empty")
    elif PLACEHOLDER.search(CODE.sub("", value)):
        problems.append(f"{name}: placeholder left: {PLACEHOLDER.search(CODE.sub('', value)).group(0)}")


def setup_reason(key, value, problems):
    """`<word> reason=<why>`: the why must be written out, not left empty or as a placeholder."""
    m = re.fullmatch(r"(\S+)[ \t]+reason=(.*)", value)
    if not m:
        problems.append(f"{key}: write `{value.split()[0]} reason=<why>`; the reason is missing")
    else:
        filled(f"{key} reason", m.group(2), problems)


def check_setup(text, notes):
    """Problems with the two PO page lines of a DIRECTOR_STATE.md text; notes get the hints."""
    problems, lines = [], {}
    for key in ("PO_PAGE_URL", "PO_PAGE_PINNED"):
        found = re.findall(rf"^{key}[ \t]*:(.*)$", text, re.M)
        if len(found) > 1:
            problems.append(f"{key}: {len(found)} lines; keep one")
        lines[key] = found[0].strip() if found else None
    url, pinned = lines["PO_PAGE_URL"], lines["PO_PAGE_PINNED"]
    none = url is not None and url.split()[:1] == ["NONE"]
    if url is None:
        problems.append("PO_PAGE_URL: line missing; write `PO_PAGE_URL: <claude.ai link>` or "
                        "`PO_PAGE_URL: NONE reason=<why>` (BOOTSTRAP step 6)")
    elif none:
        setup_reason("PO_PAGE_URL", url, problems)
    elif not ARTIFACT_URL.fullmatch(url):
        problems.append("PO_PAGE_URL: not a claude.ai artifact link (https://claude.ai/artifact/<id> or "
                        f"https://claude.ai/code/artifact/<id>) and not `NONE reason=<why>`: {url or 'empty'}")
    if pinned is None:
        if url is not None and not none:
            problems.append("PO_PAGE_PINNED: line missing; write `yes`, or `no reason=<why>` when pinning failed")
    elif pinned.split()[:1] == ["no"]:
        setup_reason("PO_PAGE_PINNED", pinned, problems)
        if not none:
            notes.append("PO_PAGE_PINNED no: ask the PO to pin the page in the sidebar themselves")
    elif pinned != "yes" or none:
        problems.append("PO_PAGE_PINNED: `yes` or `no reason=<why>`" + (" (with PO_PAGE_URL NONE there is no page to "
                        "pin: leave the line out or write `no reason=<why>`)" if none else "") + f", got: {pinned or 'empty'}")
    return problems


def state_file(path):
    """A DIRECTOR folder (its DIRECTOR_STATE.md is read) or the state file itself."""
    target = pathlib.Path(path)
    return target / "DIRECTOR_STATE.md" if target.is_dir() else target


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", metavar="DIR", help="<WS>/DIRECTOR, or a DIRECTOR_STATE.md")
    a = ap.parse_args(argv)
    failed = 0
    for path in a.dirs:
        target, notes = state_file(path), []
        if target.is_file():
            problems = check_setup(target.read_text(encoding="utf-8-sig"), notes)
        else:
            problems = ["file not found"]
        failed += bool(problems)
        print(f"{'FAIL' if problems else 'OK  '} setup {target}")
        for line in [f"  - {p}" for p in problems] + [f"  ~ {n}" for n in notes]:
            print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
