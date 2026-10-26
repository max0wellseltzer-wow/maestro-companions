"""mask_text - mask key-shaped tokens, values assigned to key-like names, and e-mail addresses in any text a miner is
about to write (a reusable version of digest.py's redaction, plus e-mails; candidate #66 for transcript-miner).

    from mask_text import mask           # mask(text) -> text with <redacted> / <email>
    python mask_text.py < in.txt > out.txt               # filter
    python mask_text.py --in-place FILE [FILE ...]       # rewrite files (line endings kept)
    python mask_text.py --check FILE-or-DIR [...]        # exit 1 and list file:line:kind for anything unmasked
    python mask_text.py --selftest
Kept on purpose: 40- and 64-character lowercase hex (git shas, sha256 digests) - miners need them. --check never
prints the matched value. Stdlib only.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

PATTERNS = [
    ("PREFIXED", re.compile(r"\b(?:PK|AK|SK)[A-Z0-9]{14,}\b|\b(?:sk-(?:ant-|proj-)?|gh[pousr]_|github_pat_|"
                            r"xox[abprs]-|AI" + r"za)[A-Za-z0-9_\-]{12,}")),
    ("LONG", re.compile(r"\b(?![0-9a-f]{40}\b)(?![0-9a-f]{64}\b)[A-Za-z0-9]{32,}\b")),
]
ASSIGNED = re.compile(r"(?i)\b(\w*(?:key|secret|token|passw(?:or)?d|apikey)\w*['\"]?\s*[=:]\s*['\"]?)([^'\"\s;,)<]{4,})")
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
EMAIL_OK = re.compile(r"(?i)^(?:git@github\.com|noreply@.*|.*no-reply@.*|.*@(?:[\w-]+\.)*example\.(?:com|org|net))$")


def _secret_value(m: re.Match) -> bool:
    """An assigned value that looks like a secret: not KeyError text, not a placeholder/expression, and either has a
    digit or is 12+ characters (so 'keys: none' stays)."""
    name, v = m.group(1), m.group(2)
    if re.search(r"(?i)error\b", name) or v[0] in "{$=%<(" or "(" in v or v.startswith(("re.", "os.", "self.")):
        return False
    return "<redacted>" not in v and (bool(re.search(r"\d", v)) or len(v) >= 12)


def mask(text: str) -> str:
    text = ASSIGNED.sub(lambda m: m.group(1) + "<redacted>" if _secret_value(m) else m.group(0), text)
    for _, rx in PATTERNS:
        text = rx.sub("<redacted>", text)
    return EMAIL.sub(lambda m: m.group(0) if EMAIL_OK.match(m.group(0)) else "<email>", text)


def findings(text: str) -> list:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        kinds = [k for k, rx in PATTERNS if rx.search(line)]
        if any(_secret_value(x) for x in ASSIGNED.finditer(line)):
            kinds.append("ASSIGNED")
        if any(not EMAIL_OK.match(m.group(0)) for m in EMAIL.finditer(line)):
            kinds.append("EMAIL")
        if kinds:
            out.append((i, sorted(set(kinds))))
    return out


def _files(paths: list) -> list:
    out = []
    for s in paths:
        p = Path(s)
        out += [p] if p.is_file() else [q for q in sorted(p.rglob("*")) if q.is_file() and q.suffix.lower() in
                                         {".md", ".txt", ".tsv", ".csv", ".json", ".jsonl", ".log"}]
    return out


def _selftest() -> bool:
    ok = {}
    fake_pk = "PK" + "FAKESENTINEL0" + "9F3A1C2B"
    fake_secret = "Zq" + "FAKE0sentinel" + "9f3a1c2b7d04e5f6a7b8c9d0e1f2"
    addr = "someone" + "@" + "mailhost.io"
    sha = "4b6d947749cc1ff19aa22f8938d86d72aad341012f1a990a227c5c13920bda1e"
    src = (f"export APCA_API_KEY_ID={fake_pk}\nsecret {fake_secret} pasted\nmail {addr} please\n"
           f"commit {sha[:40]} and digest {sha}\nauthor <email>\nsecret_key = 'short1'\n"
           "KeyError: 'bar_time_2026'\nSECRET = re.compile(r'x')\nset ALPACA_KEY: {ALPACA_KEY_ID}\nthe keys: none\n")
    m = mask(src)
    ok["prefixed key masked"] = fake_pk not in m
    ok["long mixed-case secret masked"] = fake_secret not in m
    ok["e-mail masked, <email> kept"] = addr not in m and "<email>" in m and "<email>" in m
    ok["git sha and sha256 digest kept"] = sha in m and sha[:40] in m
    ok["short value assigned to a key-like name masked"] = "short1" not in m
    ok["masked text has no findings; raw text has four lines (KeyError, re.compile, {PLACEHOLDER}, prose not flagged)"] = findings(m) == [] and len(findings(src)) == 4 and "KeyError: 'bar_time_2026'" in m and "{ALPACA_KEY_ID}" in m
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "digest.tsv"
        f.write_bytes(("row\t" + fake_secret + "\r\nok\r\n").encode("utf-8"))
        ok["--check flags the file (exit 1)"] = main(["--check", td]) == 1
        main(["--in-place", str(f)])
        b = f.read_bytes()
        ok["--in-place masks and keeps CRLF"] = fake_secret.encode() not in b and b.count(b"\r\n") == 2
        ok["--check passes after masking (exit 0)"] = main(["--check", td]) == 0
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv: list) -> int:
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv and argv[0] == "--check":
        bad = 0
        for f in _files(argv[1:]):
            for line, kinds in findings(f.read_text(encoding="utf-8", errors="replace")):
                print(f"{f}:{line}: {', '.join(kinds)}")
                bad += 1
        print(f"{bad} line(s) with unmasked secrets or e-mails")
        return 1 if bad else 0
    if argv and argv[0] == "--in-place":
        for s in argv[1:]:
            p = Path(s)
            with p.open("r", encoding="utf-8", errors="replace", newline="") as fh:
                text = fh.read()
            with p.open("w", encoding="utf-8", newline="") as fh:
                fh.write(mask(text))
        return 0
    if argv:
        print(f"unknown argument {argv[0]}", file=sys.stderr)
        return 2
    sys.stdout.write(mask(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
