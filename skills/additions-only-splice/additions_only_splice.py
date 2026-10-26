"""additions_only_splice - add to a big file without changing one existing line (backs additions-only-splice).

splice: insert the text of INSERT before (default) or after the line holding MARKER, which must occur exactly once
        (counted over the whole file; 0 or 2+ is refused, with the line numbers). The inserted text takes the file's
        own newline style (CRLF or LF) and gets a trailing newline. The result must pass `check` before anything is
        written; it goes to --out, or back over FILE only with --in-place (FILE.bak keeps the old bytes).
check:  OLD -> NEW is additions only when
          - every old line is still there, in the same order (old is a subsequence of new: one greedy walk);
          - the file grew;
          - no paragraph longer than 80 characters appears more often in NEW than in OLD (accidental double paste);
          - the newline style did not change (CRLF vs LF), and no old line changed only by trailing whitespace.
        Prints ADDITIONS_ONLY (+N lines) or VIOLATION with the first missing old line and its number.

    python additions_only_splice.py splice FILE --marker TEXT --insert INSERT.md [--after] (--out NEW | --in-place)
    python additions_only_splice.py check OLD NEW
    python additions_only_splice.py --selftest
Exit 0 ok, 1 violation / marker refused, 2 bad arguments.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path


def _style(b: bytes) -> str:
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    return "CRLF" if crlf > lf else "LF" if lf else "NONE"


def _lines(b: bytes) -> list:
    return b.decode("utf-8", errors="surrogateescape").replace("\r\n", "\n").split("\n")


def _paras(lines) -> Counter:
    out, cur = Counter(), []
    for ln in lines + [""]:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            p = " ".join(cur)
            if len(p) > 80:
                out[p] += 1
            cur = []
    return out


def check(old: bytes, new: bytes) -> dict:
    a, b = _lines(old), _lines(new)
    j, missing = 0, None
    for i, ln in enumerate(a):
        while j < len(b) and b[j] != ln:
            j += 1
        if j == len(b):
            missing = (i + 1, ln)
            break
        j += 1
    problems = []
    if missing:
        near = [k + 1 for k, x in enumerate(b) if x.rstrip() == missing[1].rstrip()]
        how = " (only trailing whitespace differs)" if near else ""
        problems.append(f"old line {missing[0]} missing or out of order{how}: {missing[1][:80]!r}")
    if len(new) <= len(old):
        problems.append(f"file did not grow ({len(old)} -> {len(new)} bytes)")
    po, pn = _paras(a), _paras(b)
    dups = [p for p, n in pn.items() if n > 1 and n > po.get(p, 0)]
    if dups:
        problems.append(f"{len(dups)} paragraph(s) over 80 chars now appear twice, first: {dups[0][:60]!r}")
    so, sn = _style(old), _style(new)
    if so != "NONE" and sn != so:
        problems.append(f"newline style changed {so} -> {sn}")
    return {"ok": not problems, "added": max(0, len(b) - len(a)), "problems": problems}


def splice(text: bytes, marker: str, insert: str, after: bool = False) -> bytes:
    lines = text.decode("utf-8", errors="surrogateescape").split("\n")
    hits = [i for i, ln in enumerate(lines) if marker in ln]
    total = text.decode("utf-8", errors="surrogateescape").count(marker)
    if total != 1 or len(hits) != 1:
        raise ValueError(f"marker occurs {total} time(s) (lines {[h + 1 for h in hits][:10]}); it must occur exactly once")
    nl = "\r\n" if _style(text) == "CRLF" else "\n"
    block = insert.replace("\r\n", "\n").rstrip("\n").split("\n")
    if nl == "\r\n":
        block = [ln + "\r" for ln in block]
    at = hits[0] + (1 if after else 0)
    if after and at == len(lines) and lines[-1] == "":
        at -= 1
    return "\n".join(lines[:at] + block + lines[at:]).encode("utf-8", errors="surrogateescape")


def apply_edits(text: bytes, edits: list) -> tuple:
    """The explicit in-place row edits allowed besides additions (a §0 phase row, a Block C order line).
    Each edit is [OLD, NEW]: OLD must occur exactly once and NEW must be OLD with one inserted run of text (the row
    only grows, nothing is reworded). Returns (edited bytes, report lines); raises ValueError on a refused edit."""
    s = text.decode("utf-8", errors="surrogateescape")
    report = []
    for old, new in edits:
        n = s.count(old)
        if n != 1:
            raise ValueError(f"edit OLD occurs {n} time(s), must be once: {old[:60]!r}")
        ins = len(new) - len(old)
        if "\n" in new or ins <= 0 or not any(new.startswith(old[:k]) and new.endswith(old[k:])
                                               for k in range(len(old) + 1)):
            raise ValueError(f"edit NEW must be OLD with one insertion (no rewording, no newline): {old[:60]!r}")
        line = s[:s.index(old)].count("\n") + 1
        s = s.replace(old, new)
        report.append(f"allowed in-place edit at old line {line}: {old[:50]!r} -> +{len(new) - len(old)} chars")
    return s.encode("utf-8", errors="surrogateescape"), report


def _load_edits(path: str) -> list:
    import json
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not all(isinstance(e, list) and len(e) == 2 for e in data):
        raise ValueError("--edits file must be a JSON list of [OLD, NEW] pairs")
    return data


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    edits = []
    if "--edits" in argv:
        i = argv.index("--edits")
        try:
            edits = _load_edits(argv[i + 1])
        except (IndexError, OSError, ValueError) as e:
            print(f"REFUSED: --edits: {e}", file=sys.stderr)
            return 2
        argv = argv[:i] + argv[i + 2:]
    if argv[:1] == ["check"] and len(argv) == 3:
        old_b = Path(argv[1]).read_bytes()
        try:
            old_b, notes = apply_edits(old_b, edits)
        except ValueError as e:
            print(f"VIOLATION\n  - {e}")
            return 1
        r = check(old_b, Path(argv[2]).read_bytes())
        print(f"ADDITIONS_ONLY (+{r['added']} lines)" if r["ok"] else "VIOLATION")
        for p in notes + r["problems"]:
            print("  - " + p)
        return 0 if r["ok"] else 1
    if argv[:1] != ["splice"] or len(argv) < 2:
        print(__doc__)
        return 2
    args, opts = argv[2:], {}
    try:
        for f in ("--marker", "--insert", "--out"):
            if f in args:
                i = args.index(f)
                opts[f] = args[i + 1]
                del args[i:i + 2]
    except IndexError:
        print("REFUSED: a flag is missing its value", file=sys.stderr)
        return 2
    after, inplace = "--after" in args, "--in-place" in args
    args = [a for a in args if a not in ("--after", "--in-place")]
    target = Path(argv[1])
    if args or "--marker" not in opts or "--insert" not in opts or (("--out" in opts) == inplace) or not target.is_file():
        print("REFUSED: need FILE, --marker, --insert and exactly one of --out / --in-place", file=sys.stderr)
        return 2
    old = target.read_bytes()
    try:
        edited, notes = apply_edits(old, edits)
        new = splice(edited, opts["--marker"], Path(opts["--insert"]).read_text(encoding="utf-8"), after)
    except ValueError as e:
        print(f"REFUSED: {e}")
        return 1
    r = check(edited, new)
    if not r["ok"]:
        print("VIOLATION (nothing written)")
        for p in r["problems"]:
            print("  - " + p)
        return 1
    for n in notes:
        print("  - " + n)
    if inplace:
        shutil.copyfile(target, str(target) + ".bak")
        target.write_bytes(new)
        dest = target
    else:
        dest = Path(opts["--out"])
        dest.write_bytes(new)
    print(f"ADDITIONS_ONLY (+{r['added']} lines) -> {dest}")
    return 0


def _selftest() -> bool:
    ok = {}
    base = ("# Plan\r\n\r\nIntro paragraph that is long enough to count as a real paragraph for the duplicate check here.\r\n"
            "\r\n## A\r\nalpha\r\n\r\n# APPENDIX V\r\nend\r\n").encode()
    ins = "## NEW\nfresh line\n"
    new = splice(base, "# APPENDIX V", ins)
    ok["splice inserts before the unique marker"] = b"## NEW\r\nfresh line\r\n# APPENDIX V" in new
    ok["the inserted block takes the file's CRLF style"] = b"\n" not in new.replace(b"\r\n", b"")
    ok["check passes a pure insertion"] = check(base, new)["ok"] and check(base, new)["added"] == 2
    aft = splice(base, "## A", ins, after=True)
    ok["--after inserts after the marker line"] = b"## A\r\n## NEW\r\nfresh line\r\nalpha" in aft
    try:
        splice(base + b"# APPENDIX V again\r\n", "# APPENDIX V", ins)
        ok["a marker that occurs twice is refused"] = False
    except ValueError:
        ok["a marker that occurs twice is refused"] = True
    try:
        splice(base, "# NOT THERE", ins)
        ok["a missing marker is refused"] = False
    except ValueError:
        ok["a missing marker is refused"] = True
    edited = new.replace(b"alpha", b"alpha2")
    r = check(base, edited)
    ok["an edited old line is a VIOLATION naming it"] = not r["ok"] and "alpha" in r["problems"][0]
    moved = base.replace(b"## A\r\nalpha\r\n", b"alpha\r\n## A\r\n") + b"x\r\n"
    ok["a reordered old line is a VIOLATION"] = not check(base, moved)["ok"]
    ok["a file that did not grow is a VIOLATION"] = not check(base, base)["ok"]
    para = b"Intro paragraph that is long enough to count as a real paragraph for the duplicate check here.\r\n"
    dup = base.replace(b"# APPENDIX V", b"\r\n" + para + b"\r\n# APPENDIX V")
    ok["a doubled long paragraph is a VIOLATION"] = not check(base, dup)["ok"]
    ok["switching CRLF to LF is a VIOLATION"] = not check(base, new.replace(b"\r\n", b"\n"))["ok"]
    trail = new.replace(b"alpha\r\n", b"alpha \r\n")
    rt = check(base, trail)
    ok["trailing-whitespace edits are named as such"] = not rt["ok"] and "trailing whitespace" in rt["problems"][0]
    with tempfile.TemporaryDirectory() as td:
        f, i = Path(td) / "plan.md", Path(td) / "ins.md"
        f.write_bytes(base)
        i.write_text(ins, encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = main(["splice", str(f), "--marker", "# APPENDIX V", "--insert", str(i), "--in-place"])
            rc_twice = main(["splice", str(f), "--marker", "##", "--insert", str(i), "--out", str(Path(td) / "o.md")])
            rc_both = main(["splice", str(f), "--marker", "x", "--insert", str(i)])
            dupi = Path(td) / "dup.md"
            dupi.write_bytes(para + b"\r\n\r\nmore\r\n")
            rc_dup = main(["splice", str(f), "--marker", "## A", "--insert", str(dupi), "--out", str(Path(td) / "o2.md")])
        ok["a splice that fails the check writes nothing (exit 1)"] = rc_dup == 1 and not (Path(td) / "o2.md").exists()
        ok["--in-place writes the file and keeps a .bak of the old bytes"] = (
            rc == 0 and Path(str(f) + ".bak").read_bytes() == base and f.read_bytes() == new)
        ok["refusals exit 1 (ambiguous marker) and 2 (no --out/--in-place)"] = rc_twice == 1 and rc_both == 2 \
            and not (Path(td) / "o.md").exists()
        # explicit in-place row edits (2026-10-24; the GT198-GT208 fold edited three §0 rows, L1177)
        import json
        g = Path(td) / "g.md"
        g.write_bytes(base)
        ej = Path(td) / "e.json"
        ej.write_text(json.dumps([["alpha", "alpha, GT9"]]), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as out_e:
            rc_e = main(["splice", str(g), "--marker", "# APPENDIX V", "--insert", str(i), "--out",
                         str(Path(td) / "e.md"), "--edits", str(ej)])
        e_new = (Path(td) / "e.md").read_bytes() if (Path(td) / "e.md").exists() else b""
        ok["a listed row edit passes and is reported"] = rc_e == 0 and b"alpha, GT9\r\n" in e_new \
            and "allowed in-place edit" in out_e.getvalue()
        with contextlib.redirect_stdout(io.StringIO()):
            rc_unlisted = main(["check", str(g), str(Path(td) / "e.md")])
            rc_listed = main(["check", str(g), str(Path(td) / "e.md"), "--edits", str(ej)])
        ok["the same row edit is a VIOLATION when not listed"] = rc_unlisted == 1 and rc_listed == 0
        ej.write_text(json.dumps([["alpha", "alp"]]), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            rc_shrink = main(["check", str(g), str(Path(td) / "e.md"), "--edits", str(ej)])
        ok["a planted edit that rewords (NEW lacks OLD) is refused"] = rc_shrink == 1
        try:
            apply_edits(base + b"alpha\r\n", [["alpha", "alpha2"]])
            ok["an edit whose OLD occurs twice is refused"] = False
        except ValueError:
            ok["an edit whose OLD occurs twice is refused"] = True
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
