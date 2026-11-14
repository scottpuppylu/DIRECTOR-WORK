"""Write a set of awkward input files for a worker's self-check (DIRECTOR-WORK 2.2.5, B7). Not a per-turn read.

  python -I -X utf8 weird_inputs.py OUT_DIR [--deep N] [--long N]

Writes these files into OUT_DIR (made when missing; files with these names are replaced, nothing else is touched):
  empty.txt         0 bytes
  bom.txt           a UTF-8 BOM, then two lines of text
  bom_only.txt      only the UTF-8 BOM
  control.txt       control characters: NUL, BEL, backspace, ESC [31m, form feed, a lone CR, DEL
  long_line.txt     one line of --long characters (default 1,000,000), no newline at the end
  deep.json         --deep nested JSON arrays (default 1,000)
  deep_parens.txt   --deep nested parentheses around 1
  bad_utf8.txt      bytes that are not UTF-8: Big5 / cp950 text, a lone continuation byte, a cut 3-byte sequence
  utf16.txt         UTF-16 LE text with its BOM
  mixed_newlines.txt  CRLF, LF and a lone CR in one file
  fullwidth.txt     full-width digits and operators, an emoji, a combining accent
Feed each file to the tool under test: it should give a clear message or the right result, never a Traceback, and its
messages should not echo the control characters. Prints one line per file (name, bytes, what it is).
Exit 0 written; 2 could not write (one line, never a Traceback).
"""
import argparse
import pathlib
import sys

BOM = b"\xef\xbb\xbf"


def files(deep, long):
    return [
        ("empty.txt", b"", "0 bytes"),
        ("bom.txt", BOM + "第一行 first line\nsecond line\n".encode("utf-8"), "UTF-8 BOM + text"),
        ("bom_only.txt", BOM, "only a BOM"),
        ("control.txt", b"a\x00b\x07c\x08d\x1b[31mred\x1b[0m\x0ce\rf\x7fg\n", "control characters"),
        ("long_line.txt", b"x" * long, f"one line of {long} characters, no newline"),
        ("deep.json", b"[" * deep + b"]" * deep, f"{deep} nested JSON arrays"),
        ("deep_parens.txt", b"(" * deep + b"1" + b")" * deep, f"{deep} nested parentheses"),
        ("bad_utf8.txt", "中文 Big5".encode("cp950") + b" \x80 lone \xe4\xb8 cut\n", "not UTF-8"),
        ("utf16.txt", "UTF-16 文字\r\n".encode("utf-16"), "UTF-16 with BOM"),
        ("mixed_newlines.txt", b"crlf\r\nlf\nlone cr\rend", "CRLF, LF and CR mixed"),
        ("fullwidth.txt", "１２３＋４５６＝？ 😀 é\n".encode("utf-8"), "full-width, emoji, combining accent"),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write awkward input files for a self-check (DIRECTOR-WORK 2.2.5).")
    ap.add_argument("out_dir", help="folder to write into")
    ap.add_argument("--deep", type=int, default=1000, help="nesting depth (default 1000)")
    ap.add_argument("--long", type=int, default=1_000_000, help="length of the long line (default 1000000)")
    a = ap.parse_args(argv)
    if a.deep < 1 or a.long < 1:
        print("weird_inputs: --deep and --long must be 1 or more")
        return 2
    out = pathlib.Path(a.out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name, data, what in files(a.deep, a.long):
            (out / name).write_bytes(data)
            print(f"{name}  {len(data)} bytes  {what}")
    except OSError as e:
        print(f"weird_inputs: cannot write in {out}: {e.strerror or type(e).__name__}")
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("weird_inputs: stopped")
        sys.exit(2)
