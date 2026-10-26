"""gradable_acceptance - lint plan cards so every acceptance line is decidable by a script (backs gradable-acceptance,
which also absorbs the plan-to-cards draft).

A card starts at a heading like `#### K12 · title` or a bold id line like `**O01** (title)` (override with --card-re).
Inside a card the tool reads the ASSERTIONS block (numbered `1.` or `- A1.` items after an `ASSERTIONS:` line; also
`Acceptance:` / `Finish line:` / `Done when:`) and grades each assertion:
  OK        it carries a hook a script can decide: inline code, a comparison (== != >= <= > < >= <=), a shorthand
            check (CHK( RED<FIX PLANT( BD13 TJ:), exit code, sha256, a file path, a count, or exists / equals /
            contains / is in / returns / matches
  VAGUE     it leans on a judgement word (clean, good, nice, reasonable, readable, robust, appropriate, intuitive,
            elegant, works well, makes sense, as expected, high quality, properly, sufficient, user-friendly) and has
            no hook
  NO_HOOK   nothing in it can be decided by a script
Per card:
  COUNT       fewer than --min (4) or more than --max (7) assertions
  NO_PLANT    no assertion is planted / red-first (PLANT, planted, mutant, RED<FIX, red-first, KILLED)
  NO_REAL     no assertion touches real data, landing or replication (real data, real-data, BD13, replicat,
              landed, origin/main, live, cold session)
  MISSING     a required field is absent (default: READING, FAILS IF, KILL; `--fields` to change) or READING has
              fewer than 2 BURNED readings
  REUSE_BAD   with --root: a `path:line` reference in the card does not resolve (file missing or line beyond its end);
              `--key TB=DIR` maps path prefixes. NOT FOUND lines are honest and pass.

    python gradable_acceptance.py PLAN.md [--only O01,K12] [--root DIR] [--key TB=DIR ...] [--min 4] [--max 7]
                                  [--fields READING,FAILS IF,KILL] [--card-re REGEX] [--summary]
    python gradable_acceptance.py --selftest
Exit 0 every card gradable, 1 problems, 2 bad arguments.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

CARD_RE = r"^(?:#{2,6}\s+([A-Z]{1,4}\s?\d+[a-z]?)\s*[·:.-]|\*\*([A-Z]{1,4}\s?\d+[a-z]?)\*\*)"
ASSERT_HEAD = re.compile(r"^\s*[-*]?\s*\**(ASSERTIONS|Acceptance|Finish line|Done when)\**\s*:?\**\s*:?\s*$", re.I)
FIELD_LINE = re.compile(r"^\s*[-*]\s+\**[A-Z][A-Z /→>-]{2,}\**\s*[:.]")
ITEM = re.compile(r"^\s*(?:[-*]\s+)?(?:A?\d+[.)]|[-*])\s+(.*\S)")
HOOK = re.compile(
    r"`[^`]+`|==|!=|>=|<=|≥|≤|(?<![-=])>(?!=)|(?<![<=])<(?![=<])|\bCHK\(|RED<FIX|\bPLANT\(|\bBD13\b|\bTJ:|"
    r"\bexit(?:s)?\s+(?:code\s+)?\d|\bsha256\b|[\w.-]+/[\w./-]+\.\w+|\b\d+(?:\.\d+)?\b|"
    r"\b(exists?|equals?|contains?|is in|returns?|matches|is present|is absent|appears?|ancestor|committed|"
    r"lists?|includes?|holds?|sha\d*s?|fingerprints?|import[- ]closure|tests\.json|passing|grep|git \w+|NOT RUN)\b|"
    r"\b[A-Z]{2,}(?:_[A-Z]+)+\b", re.I)
JUDGE = re.compile(r"\b(clean|good|nice|reasonable|readable|robust|appropriate|intuitive|elegant|works well|"
                   r"makes sense|as expected|high[- ]quality|properly|sufficient(?:ly)?|user[- ]friendly|"
                   r"looks? (?:right|fine|ok)|well[- ]designed|polished|solid)\b", re.I)
PLANT = re.compile(r"\bPLANT|planted|\bplants?\b|mutant|RED<FIX|red[- ]first|KILLED", re.I)
REAL = re.compile(r"real[- ]data|\bBD13\b|replicat|\blanded\b|origin/main|\blive\b|cold session|real run", re.I)
REF = re.compile(r"((?:[A-Z]{2}/)?[\w./-]+\.(?:py|md|toml|json|jsonl|txt|sh|ps1|bat|cfg|yaml|yml)):(\d+)(?:-(\d+))?")


def cards(text: str, card_re: str = CARD_RE) -> list:
    rx = re.compile(card_re)
    out, cur = [], None
    for n, ln in enumerate(text.splitlines(), 1):
        m = rx.match(ln)
        if m:
            cur = {"id": next(g for g in m.groups() if g).replace(" ", ""), "line": n, "lines": []}
            out.append(cur)
        elif ln.startswith("#") and cur is not None and re.match(r"^#{1,3}\s", ln):
            cur = None                                     # a higher-level heading closes the card
        if cur is not None:
            cur["lines"].append((n, ln))
    return out


def assertions(card) -> list:
    out, inside, base = [], False, None
    for n, ln in card["lines"]:
        if ASSERT_HEAD.match(ln):
            inside, base = True, len(ln) - len(ln.lstrip())
            continue
        if not inside:
            continue
        if not ln.strip():
            continue
        ind = len(ln) - len(ln.lstrip())
        if ind <= base and (FIELD_LINE.match(ln) or not ITEM.match(ln)):
            inside = False
            continue
        m = ITEM.match(ln)
        if m and ind > base or (m and ind == base and re.match(r"^\s*\d+[.)]", ln)):
            out.append({"line": n, "text": m.group(1)})
        elif out:
            out[-1]["text"] += " " + ln.strip()
    return out


def grade(text: str) -> str:
    if HOOK.search(text):
        return "OK"
    return "VAGUE" if JUDGE.search(text) else "NO_HOOK"


def burned_count(body: str) -> int:
    """Readings marked BURNED: each BURNED occurrence counts its enumerated '(n)' items on that line, or 1."""
    n = 0
    for m in re.finditer(r"\bBURNED\b(.*)", body):
        rest = re.sub(r"^\s*\(\d+\)\s*:", ":", m.group(1))       # 'BURNED (1):' is a count header, not an item
        n += max(1, len(re.findall(r"\(\d+\)", rest)))
    return n


def resolve(ref: str, root: Path, keys: dict) -> Path:
    head = ref.split("/", 1)
    if len(head) == 2 and head[0] in keys:
        return Path(keys[head[0]]) / head[1]
    return root / ref


def lint(text: str, root=None, keys=None, lo=4, hi=7, fields=("READING", "FAILS IF", "KILL"), card_re=CARD_RE,
         only=None, strict=False) -> list:
    keys = keys or {}
    report = []
    for c in cards(text, card_re):
        if only and c["id"] not in only:
            continue
        body = "\n".join(ln for _, ln in c["lines"])
        probs = []
        al = assertions(c)
        if not al and not strict:
            report.append({"id": c["id"], "line": c["line"], "assertions": 0, "problems": [], "skipped": True})
            continue
        for a in al:
            g = grade(a["text"])
            if g != "OK":
                probs.append((a["line"], g, a["text"][:90]))
        if not lo <= len(al) <= hi:
            probs.append((c["line"], "COUNT", f"{len(al)} assertions (want {lo}-{hi})"))
        if al and not any(PLANT.search(a["text"]) for a in al):
            probs.append((c["line"], "NO_PLANT", "no planted / red-first assertion"))
        if al and not any(REAL.search(a["text"]) for a in al):
            probs.append((c["line"], "NO_REAL", "no real-data / landed / replicated assertion"))
        for f in fields:
            if not re.search(r"(?<![A-Za-z])" + re.escape(f) + r"(?:\*\*|\s*[:.(])", body):
                probs.append((c["line"], "MISSING", f"field {f}"))
        if "READING" in fields and re.search(r"READING", body) and burned_count(body) < 2:
            probs.append((c["line"], "MISSING", "READING has fewer than 2 BURNED readings"))
        if root is not None:
            for n, ln in c["lines"]:
                if "NOT FOUND" in ln:
                    continue
                for m in REF.finditer(ln):
                    p = resolve(m.group(1), Path(root), keys)
                    want = int(m.group(3) or m.group(2))
                    if not p.is_file():
                        probs.append((n, "REUSE_BAD", f"{m.group(0)}: file not found"))
                    else:
                        with p.open("rb") as fh:
                            count = sum(1 for _ in fh)
                        if want > count:
                            probs.append((n, "REUSE_BAD", f"{m.group(0)}: file has {count} lines"))
        report.append({"id": c["id"], "line": c["line"], "assertions": len(al), "problems": probs})
    return report


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    args, opts, keys = list(argv), {}, {}
    try:
        while "--key" in args:
            i = args.index("--key")
            k, v = args[i + 1].split("=", 1)
            keys[k] = v
            del args[i:i + 2]
        for f in ("--only", "--root", "--min", "--max", "--fields", "--card-re"):
            if f in args:
                i = args.index(f)
                opts[f] = args[i + 1]
                del args[i:i + 2]
    except (IndexError, ValueError):
        print("REFUSED: a flag is missing its value (or --key is not NAME=DIR)", file=sys.stderr)
        return 2
    summary, strict = "--summary" in args, "--strict" in args
    args = [a for a in args if a not in ("--summary", "--strict")]
    if len(args) != 1 or args[0].startswith("--") or not Path(args[0]).is_file():
        print(__doc__)
        return 2
    rep = lint(Path(args[0]).read_text(encoding="utf-8", errors="replace"), opts.get("--root"), keys,
               int(opts.get("--min", 4)), int(opts.get("--max", 7)),
               tuple(x.strip() for x in opts.get("--fields", "READING,FAILS IF,KILL").split(",") if x.strip()),
               opts.get("--card-re", CARD_RE), set(opts["--only"].split(",")) if "--only" in opts else None, strict)
    skipped = sum(1 for c in rep if c.get("skipped"))
    rep = [c for c in rep if not c.get("skipped")]
    if skipped:
        print(f"{skipped} card heading(s) without an ASSERTIONS block skipped (--strict grades them)")
    kinds, bad = {}, 0
    for c in rep:
        if c["problems"]:
            bad += 1
        for _, k, _ in c["problems"]:
            kinds[k] = kinds.get(k, 0) + 1
        if not summary:
            for n, k, d in c["problems"]:
                print(f"{c['id']:<6} L{n:<6} {k:<9} {d}")
    print(f"{len(rep)} card(s), {sum(c['assertions'] for c in rep)} assertions, {bad} card(s) with problems" +
          ("" if not kinds else ": " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))))
    if not rep:
        print("NO CARDS FOUND (check --card-re)")
        return 1
    return 1 if bad else 0


def _selftest() -> bool:
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "src").mkdir()
        (td / "src" / "mod.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        good = (
            "#### K1 · good card\n"
            "- **VERIFIED REUSE:** `f` TB/mod.py:2; `g` NOT FOUND, TB/gone2.py:5 must be written\n"
            "- **READING:** TAKEN: x. BURNED: (1) cheap thing; (2) other cheap thing.\n"
            "- **FAILS IF** a grid cell differs. **KILL:** retire it.\n"
            "- **ASSERTIONS:**\n"
            "  1. `src/mod.py` defines `lower` and `cegar`.\n"
            "  2. CHK(tv-blend; t1, t2).\n"
            "  3. RED<FIX for each behaviour.\n"
            "  4. PLANT(plants.json; 3): three plants KILLED.\n"
            "  5. The receipt lists all 10 screens with their sha256 (real-data assertion).\n"
            "  6. BD13.\n\n")
        bad = (
            "**O02** (bad card)\n"
            "- READING: one reading only.\n"
            "  - BURNED: just one.\n"
            "- KILL: none.\n"
            "- ASSERTIONS:\n"
            "  - A1. The output looks clean and readable.\n"
            "  - A2. Everyone is happy with the design.\n"
            "  - A3. `x.json` exists.\n"
            "- LABELS: TESTED.\n\n"
            "#### K3 · reuse card\n"
            "- READING: BURNED: (1) a; (2) b. FAILS IF x. KILL: y.\n"
            "- uses TB/mod.py:9 and TB/gone.py:1\n"
            "- ASSERTIONS:\n"
            "  1. PLANT(p; 3) KILLED.\n  2. landed on origin/main.\n  3. `a` == 1.\n  4. count >= 2.\n\n"
            "#### K4 · heading with no assertions block\nprose only\n\n"
            "# Next top section\nnot a card\n")
        text = good + bad
        k4 = {c["id"]: c for c in lint(text, strict=True)}.get("K4")
        ok["a card with no ASSERTIONS block is skipped, and graded COUNT under strict"] = (
            {c["id"]: c for c in lint(text)}["K4"].get("skipped") is True and k4 is not None
            and any(k == "COUNT" for _, k, _ in k4["problems"]))
        rep = {c["id"]: c for c in lint(text, root=td / "src", keys={"TB": str(td / "src")})}
        kinds = {cid: {k for _, k, _ in c["problems"]} for cid, c in rep.items()}
        ok["four cards are found (heading and bold-id forms)"] = set(rep) == {"K1", "O02", "K3", "K4"}
        ok["a fully gradable card has no problems"] = rep["K1"]["problems"] == [] and rep["K1"]["assertions"] == 6
        ok["a judgement-word assertion is VAGUE"] = any(k == "VAGUE" and "clean" in d for _, k, d in rep["O02"]["problems"])
        ok["an assertion with no hook is NO_HOOK"] = any(k == "NO_HOOK" and "happy" in d for _, k, d in rep["O02"]["problems"])
        ok["fewer than 4 assertions is COUNT"] = "COUNT" in kinds["O02"]
        ok["no planted assertion is NO_PLANT, no real-data one is NO_REAL"] = {"NO_PLANT", "NO_REAL"} <= kinds["O02"]
        ok["a missing FAILS IF field is MISSING"] = any(k == "MISSING" and "FAILS IF" in d for _, k, d in rep["O02"]["problems"])
        ok["one BURNED reading is not enough"] = any("BURNED" in d for _, k, d in rep["O02"]["problems"])
        reuse = [d for _, k, d in rep["K3"]["problems"] if k == "REUSE_BAD"]
        ok["a reuse line past the file end or to a missing file is REUSE_BAD"] = (
            len(reuse) == 2 and any("3 lines" in d for d in reuse) and any("not found" in d for d in reuse))
        ok["a NOT FOUND reuse line is honest and passes"] = not any("NOT FOUND" in d for _, _, d in rep["K1"]["problems"])
        ok["the LABELS line after the assertions is not read as an assertion"] = rep["O02"]["assertions"] == 3 and not any(
            "LABELS" in a["text"] for c in cards(text) for a in assertions(c))
        ok["a higher-level heading closes the card"] = all("not a card" not in ln for _, ln in cards(text)[-1]["lines"])
        f = td / "plan.md"
        f.write_text(text, encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc1 = main([str(f)])
            rc0 = main([str(f), "--only", "K1"])
            f.write_text("no cards here\n", encoding="utf-8")
            rcn = main([str(f)])
        ok["exit 1 with problems, 0 when the chosen cards are clean, 1 when no card is found"] = (rc1, rc0, rcn) == (1, 0, 1)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
