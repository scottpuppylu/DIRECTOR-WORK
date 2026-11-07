"""Mask secrets in text: private keys, cloud and git host tokens, API keys, JWTs, bearer headers, key=value secrets
and passwords in URLs. Each one becomes [MASKED:<kind>], with no part of the secret kept, so nothing narrows a guess.

  python -I -X utf8 secret_mask.py [FILE]          print FILE (or stdin) masked; exit 0
  python -I -X utf8 secret_mask.py --check [FILE]  print only "FOUND kind" per kind and a SECRETS line; exit 1 when any

Used as a module by the action log (mask before writing). It masks common formats only: a token in a format it has
not seen goes through. A 40-character git SHA or a sha256 on its own is never masked.
"""
import argparse
import pathlib
import re
import sys

# a key name that holds a secret: the secret word, then nothing or a suffix after a separator (github_token, api_key.prod),
# so max_tokens, author and authorization (the header has its own pattern) are not key names
SECRET_NAME = (r"[\w.-]*?(?:password|passwd|passphrase|token|secret|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|auth)"
               r"(?:[_.-][\w.-]*)?")
PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S)),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
]
# these keep the part before the secret (the header name, the key name, the scheme and user) and mask the rest
KEEP_PREFIX = [
    ("bearer", re.compile(r"(?i)(\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic|token)\s+)([^\s\"']+)")),
    ("url_password", re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)([^/\s@]+)(?=@)")),
    ("assignment", re.compile(r"(?i)(\b" + SECRET_NAME + r"[\"']?\s*[:=]\s*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s\"',;]+)")),
]
MASK = re.compile(r"\[MASKED:\w+\]")


def mask(text):
    """(masked text, sorted list of the kinds found)."""
    found = set()

    def whole(kind):
        def swap(match):
            found.add(kind)
            return f"[MASKED:{kind}]"
        return swap

    def tail(kind):
        def swap(match):
            value = match.group(2)
            if MASK.fullmatch(value.strip("\"'")) or not value.strip("\"'"):
                return match.group(0)
            found.add(kind)
            return f"{match.group(1)}[MASKED:{kind}]"
        return swap

    for kind, pattern in PATTERNS:
        text = pattern.sub(whole(kind), text)
    for kind, pattern in KEEP_PREFIX:
        text = pattern.sub(tail(kind), text)
    return text, sorted(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="text file (default: stdin)")
    ap.add_argument("--check", action="store_true", help="only list the kinds found; exit 1 when any")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    text = pathlib.Path(a.file).read_text(encoding="utf-8", errors="replace") if a.file else sys.stdin.read()
    masked, kinds = mask(text)
    if a.check:
        for kind in kinds:
            print(f"FOUND {kind}")
        print(f"SECRETS: {len(kinds)} kind(s)")
        return 1 if kinds else 0
    sys.stdout.write(masked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
