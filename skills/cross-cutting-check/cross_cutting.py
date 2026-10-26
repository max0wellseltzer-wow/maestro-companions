"""cross_cutting - the geologist's law of cross-cutting relationships for an ordered record (backs cross-cutting-check).

In rock, whatever cuts through a layer is younger than it. In an append-only record (DECISIONS.md, an errata list, a
numbered plan) a row may only cite ids that already exist ABOVE it. Reading top to bottom:
  INTRUSION      a row cites an id first defined in a LATER row (it was edited after the fact, or the rows were
                 reordered) - reported with both line numbers
  PHANTOM        a row cites an id that is never defined anywhere
  INVERSION      an id is defined after a higher-numbered id (the strata are overturned: rows out of numeric order)
  DUPLICATE_DEF  the same id is defined twice
Defaults fit DECISIONS.md tables (`| D12 | ...`): --def is a regex whose group 1 is the id a line DEFINES, --ref a regex
whose group 1 is an id a line CITES; the defining id on its own line is not a citation. Ids are compared by their
numeric part for INVERSION. Read-only.

    python cross_cutting.py FILE [--def REGEX] [--ref REGEX] [--ignore-before N] [--summary]
    python cross_cutting.py --selftest
Exit 0 conformable, 1 findings, 2 bad arguments.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

DEF_RE = r"^\|\s*\**(D\d+)\**\s*\|"
REF_RE = r"(?<![\w-])(D\d+)(?![\w])"


def _num(i: str) -> int:
    m = re.search(r"\d+", i)
    return int(m.group(0)) if m else -1


def scan(text: str, def_re=DEF_RE, ref_re=REF_RE, ignore_before=0) -> dict:
    drx, rrx = re.compile(def_re), re.compile(ref_re)
    lines = text.splitlines()
    defs, order, finds = {}, [], []
    for n, ln in enumerate(lines, 1):
        m = drx.search(ln)
        if m:
            i = m.group(1)
            if i in defs:
                finds.append(("DUPLICATE_DEF", n, i, f"first defined at line {defs[i]}"))
            else:
                defs[i] = n
                order.append((n, i))
    hi = None
    for n, i in order:
        if hi is not None and _num(i) < _num(hi[1]):
            finds.append(("INVERSION", n, i, f"defined after {hi[1]} (line {hi[0]})"))
        if hi is None or _num(i) > _num(hi[1]):
            hi = (n, i)
    for n, ln in enumerate(lines, 1):
        if n < ignore_before:
            continue
        own = drx.search(ln)
        own_id = own.group(1) if own else None
        seen = set()
        for m in rrx.finditer(ln):
            i = m.group(1)
            if i == own_id or i in seen:
                continue
            seen.add(i)
            if i not in defs:
                finds.append(("PHANTOM", n, i, "cited, never defined"))
            elif defs[i] > n:
                finds.append(("INTRUSION", n, i, f"cited here, first defined later at line {defs[i]}"))
    finds.sort(key=lambda f: (f[1], f[0]))
    return {"defs": len(defs), "findings": finds}


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    args, o = list(argv), {}
    try:
        for f in ("--def", "--ref", "--ignore-before"):
            if f in args:
                i = args.index(f)
                o[f] = args[i + 1]
                del args[i:i + 2]
        summary = "--summary" in args
        args = [a for a in args if a != "--summary"]
        if len(args) != 1 or not Path(args[0]).is_file():
            raise ValueError("need one FILE")
        r = scan(Path(args[0]).read_text(encoding="utf-8", errors="replace"), o.get("--def", DEF_RE),
                 o.get("--ref", REF_RE), int(o.get("--ignore-before", 0)))
    except (ValueError, OSError, re.error) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    kinds = {}
    for k, n, i, d in r["findings"]:
        kinds[k] = kinds.get(k, 0) + 1
        if not summary:
            print(f"{k:<13} L{n:<6} {i:<8} {d}")
    print(f"{r['defs']} id(s) defined, {len(r['findings'])} finding(s)" +
          ("" if not kinds else ": " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))) +
          ("" if r["findings"] else " - CONFORMABLE"))
    return 1 if r["findings"] else 0


def _selftest() -> bool:
    ok = {}
    text = ("# Decisions\nSee D1 for the root rule.\n"           # 2: cites D1 before it exists -> INTRUSION
            "| D1 | root rule | x |\n"                            # 3
            "| D2 | builds on D1 | x |\n"                          # 4 ok
            "| D4 | cites D3 and D9 | x |\n"                       # 5: D3 later -> INTRUSION, D9 never -> PHANTOM
            "| D3 | late row | x |\n"                             # 6: INVERSION (after D4)
            "| D2 | again | x |\n"                                # 7: DUPLICATE_DEF
            "| D5 | cites D4, D4 and D2 | x |\n"                   # 8 ok (repeats counted once)
            "Note on D10x and XD5 and D-5 is not a citation.\n")  # 9 not ids
    r = scan(text)
    f = {(k, n, i) for k, n, i, _ in r["findings"]}
    ok["a citation above the defining row is an INTRUSION"] = ("INTRUSION", 2, "D1") in f and ("INTRUSION", 5, "D3") in f
    ok["an id never defined is a PHANTOM"] = ("PHANTOM", 5, "D9") in f
    ok["a lower id defined after a higher one is an INVERSION"] = ("INVERSION", 6, "D3") in f
    ok["the same id defined twice is DUPLICATE_DEF"] = ("DUPLICATE_DEF", 7, "D2") in f
    ok["a row's own id and repeated citations are not findings"] = not any(n in (3, 4, 8) for _, n, _ in f)
    ok["word-glued tokens (D10x, XD5, D-5) are not ids"] = not any(n == 9 for _, n, _ in f)
    ok["exactly five findings"] = len(r["findings"]) == 5
    ok["--ignore-before skips the preamble citations"] = ("INTRUSION", 2, "D1") not in {
        (k, n, i) for k, n, i, _ in scan(text, ignore_before=3)["findings"]}
    num = scan("| D9 | a |\n| D10 | b |\n| D2 | c |\n")["findings"]
    ok["ids compare by number (D2 after D10 is inverted relative to D10, not D9)"] = (
        len(num) == 1 and num[0][0] == "INVERSION" and "D10" in num[0][3])
    custom = scan("## E1 first\n## E2 needs E1 and E3\n## E3\n", def_re=r"^##\s+(E\d+)", ref_re=r"\b(E\d+)\b")
    ok["custom --def/--ref regexes work (errata-style headings)"] = [(k, i) for k, _, i, _ in custom["findings"]] == [
        ("INTRUSION", "E3")]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "d.md"
        p.write_text("| D1 | a |\n| D2 | b, D1 |\n", encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc0 = main([str(p)])
            p.write_text(text, encoding="utf-8")
            rc1 = main([str(p), "--summary"])
        ok["exit 0 conformable, 1 with findings"] = (rc0, rc1) == (0, 1)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
