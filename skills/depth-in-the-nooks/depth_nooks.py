"""depth_nooks - every enumerated item of a plan section gets its depth line (backs depth-in-the-nooks).

For each block headed `Depth in the nooks of §X` (any heading level; change with --depth-re) the tool finds section X
(a heading `## X.` / `## X ` / `### X.`; `itself` blocks mean the section that holds the block), enumerates the
section's items - numbered lines at column 0 (`1. **Wired.** ...`) and `###`/`####` sub-headings inside it - and
matches each item to a depth line (a top-level `- **label** ...` bullet of the block) by its number ("Proof 1",
"R1", "1") or by a shared significant title word. Reports:
  NO_DEPTH          an item with no depth line
  NO_CONCEPT        a depth line that cites no concept id (C1..Cn; --concept-re to change)
  THEORY_NO_STATUS  a depth line that leans on a named theorem / lemma / law / bound / caveat but carries no status
                    (CITED-UNVERIFIED, CITED, PROVED, VERIFIED)
  NO_SECTION        a depth block whose section heading cannot be found
    python depth_nooks.py PLAN.md [--only BD,HR] [--concept-re REGEX] [--depth-re REGEX] [--summary]
    python depth_nooks.py --selftest
Exit 0 every item has depth, 1 problems, 2 bad arguments.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

DEPTH_RE = r"^#{2,6}\s+Depth in the nooks of\s+§?\s*([A-Za-z0-9.]+)"
CONCEPT_RE = r"\bC\d+\b"
STOP = set("with that this from into each every their there which where what when have will must only also than "
           "then them they does item items line lines plan".split())
THEORY = re.compile(r"\b[A-Z][a-z]+(?:[-' ][A-Za-z&]+)*\s+(?:theorem|lemma|law|inequality|bound|caveat|hypothesis)\b"
                    r"|\b(?:theorem|lemma)\b")
STATUS = re.compile(r"CITED-UNVERIFIED|\bCITED\b|\bPROVED\b|\bVERIFIED\b")


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z-]{3,}", s.lower()) if w not in STOP}


def blocks(lines, depth_re=DEPTH_RE):
    rx = re.compile(depth_re)
    out = []
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if m:
            lvl = len(ln) - len(ln.lstrip("#"))
            end = next((j for j in range(i + 1, len(lines)) if re.match(r"^#{1,%d}\s" % lvl, lines[j])), len(lines))
            out.append({"tag": m.group(1).rstrip("."), "line": i + 1, "start": i, "end": end, "itself": "itself" in ln})
    return out


def find_section(lines, tag, before):
    rx = re.compile(r"^(#{2,4})\s+§?" + re.escape(tag) + r"(?:\.\s|\.?$|[\s:])")    # 'HR.' yes, 'HR.1' no
    best = None
    for i, ln in enumerate(lines[:before]):
        if rx.match(ln):
            best = i
    return best


def items(lines, start, stop):
    out = []
    for i in range(start + 1, stop):
        ln = lines[i]
        m = re.match(r"^(\d+)\.\s+(.*)", ln)
        if m:
            title = re.sub(r"\*\*(.+?)\*\*.*", r"\1", m.group(2))
            out.append({"line": i + 1, "num": m.group(1), "title": title[:80]})
            continue
        h = re.match(r"^#{3,4}\s+(?!Depth in the nooks)(.*)", ln)
        if h:
            num = re.match(r"([A-Z]{0,4}\.?\d+(?:\.\d+)?)", h.group(1))
            out.append({"line": i + 1, "num": num.group(1) if num else None, "title": h.group(1)[:80]})
    return out


def depth_lines(lines, b):
    out = []
    for i in range(b["start"] + 1, b["end"]):
        m = re.match(r"^[-*]\s+\*\*(.+?)\*\*\s*(.*)", lines[i])
        if m:
            body = m.group(2)
            j = i + 1
            while j < b["end"] and re.match(r"^\s+[-*]\s", lines[j]):
                body += " " + lines[j].strip()
                j += 1
            out.append({"line": i + 1, "label": m.group(1), "body": body})
    return out


def matches(item, dl) -> bool:
    lab = dl["label"]
    if item["num"] and re.search(r"(?<![\w.])" + re.escape(item["num"]) + r"(?![\w])", lab):
        return True
    iw, lw = _words(item["title"]), _words(lab)
    return bool(iw & lw)


def lint(text: str, only=None, concept_re=CONCEPT_RE, depth_re=DEPTH_RE) -> list:
    lines = text.splitlines()
    crx = re.compile(concept_re)
    report = []
    for b in blocks(lines, depth_re):
        if only and b["tag"] not in only:
            continue
        probs = []
        if b["itself"]:
            sec = find_section(lines, b["tag"], b["start"])
        else:
            sec = find_section(lines, b["tag"], b["start"])
        dls = depth_lines(lines, b)
        for d in dls:
            if not crx.search(d["label"] + " " + d["body"]):
                probs.append((d["line"], "NO_CONCEPT", d["label"][:60]))
            txt = d["label"] + " " + d["body"]
            if THEORY.search(txt) and not STATUS.search(txt):
                probs.append((d["line"], "THEORY_NO_STATUS", THEORY.search(txt).group(0)))
        its = []
        if sec is None:
            probs.append((b["line"], "NO_SECTION", f"no heading for §{b['tag']} above the block"))
        else:
            its = items(lines, sec, b["start"])
            for it in its:
                if not any(matches(it, d) for d in dls):
                    probs.append((it["line"], "NO_DEPTH", f"{it['num'] or ''} {it['title']}".strip()[:70]))
        report.append({"tag": b["tag"], "line": b["line"], "items": len(its), "depth_lines": len(dls),
                       "problems": probs})
    return report


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    args, o = list(argv), {}
    try:
        for f in ("--only", "--concept-re", "--depth-re"):
            if f in args:
                i = args.index(f)
                o[f] = args[i + 1]
                del args[i:i + 2]
    except IndexError:
        print("REFUSED: a flag is missing its value", file=sys.stderr)
        return 2
    summary = "--summary" in args
    args = [a for a in args if a != "--summary"]
    if len(args) != 1 or args[0].startswith("--") or not Path(args[0]).is_file():
        print(__doc__)
        return 2
    rep = lint(Path(args[0]).read_text(encoding="utf-8", errors="replace"),
               set(o["--only"].split(",")) if "--only" in o else None, o.get("--concept-re", CONCEPT_RE),
               o.get("--depth-re", DEPTH_RE))
    kinds = {}
    for r in rep:
        for n, k, d in r["problems"]:
            kinds[k] = kinds.get(k, 0) + 1
            if not summary:
                print(f"§{r['tag']:<6} L{n:<6} {k:<16} {d}")
    if summary:
        for r in rep:
            print(f"§{r['tag']:<6} items {r['items']:<4} depth lines {r['depth_lines']:<4} problems {len(r['problems'])}")
    print(f"{len(rep)} depth block(s), {sum(r['items'] for r in rep)} items, {sum(len(r['problems']) for r in rep)} "
          "problem(s)" + ("" if not kinds else ": " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))))
    if not rep:
        print("NO DEPTH BLOCKS FOUND")
        return 1
    return 1 if kinds else 0


def _selftest() -> bool:
    ok = {}
    plan = ("# Plan\n\n## BD. The standard\nIntro.\n\n"
            "1. **Wired.** connected to consumers.\n"
            "2. **Real data.** a receipt on real data.\n"
            "3. **Adversary.** an attacker tried.\n"
            "4. **Teeth.** plants kill claims.\n\n"
            "#### Depth in the nooks of §BD\n"
            "- **Proof 1 wired** - C13. wiring tests the contract.\n"
            "- **Proof 2 real data** - C10. fixtures are beliefs.\n"
            "  - Breaks: own world twice.\n"
            "- **Proof 3 adversary** - C7 and the Knight & Leveson caveat: same family shares blind spots.\n"
            "- **Regression rows** - an append-only history.\n\n"
            "## HR. Another\n### HR.1 Burned readings\ntext\n### HR.2 Softening register\ntext\n\n"
            "#### Depth in the nooks of §HR\n"
            "- **HR.1** - C2 (Newman's lemma, CITED-UNVERIFIED).\n"
            "- **Softening register** - C4.\n"
            "- **Extra note** - the concept sits in the sub-bullet.\n  - Why: C9.\n\n"
            "#### Depth in the nooks of §ZZ\n- **x** - C1.\n")
    rep = {r["tag"]: r for r in lint(plan)}
    bd = {(k, d.split()[0] if d else "") for _, k, d in rep["BD"]["problems"]}
    ok["three depth blocks are found"] = set(rep) == {"BD", "HR", "ZZ"}
    ok["numbered items are enumerated (4 in BD)"] = rep["BD"]["items"] == 4
    ok["an item with no depth line is NO_DEPTH (item 4 Teeth)"] = any(
        k == "NO_DEPTH" and "Teeth" in d for _, k, d in rep["BD"]["problems"])
    ok["items matched by number are not flagged"] = not any(
        k == "NO_DEPTH" and ("Wired" in d or "Real" in d) for _, k, d in rep["BD"]["problems"])
    ok["a depth line without a concept id is NO_CONCEPT"] = any(
        k == "NO_CONCEPT" and "Regression" in d for _, k, d in rep["BD"]["problems"])
    ok["a named caveat without a status is THEORY_NO_STATUS"] = any(
        k == "THEORY_NO_STATUS" for _, k, _ in rep["BD"]["problems"])
    ok["a cited lemma with CITED-UNVERIFIED passes"] = not any(
        k == "THEORY_NO_STATUS" for _, k, _ in rep["HR"]["problems"])
    ok["sub-heading items match by id or by title word"] = rep["HR"]["items"] == 2 and rep["HR"]["problems"] == []
    ok["a block whose section is missing is NO_SECTION"] = any(k == "NO_SECTION" for _, k, _ in rep["ZZ"]["problems"])
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "p.md"
        f.write_text(plan, encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc1 = main([str(f)])
            rc0 = main([str(f), "--only", "HR"])
            rcb = main([str(f), "--only"])
        ok["exit 1 with problems, 0 for a clean block, 2 on a bad flag"] = (rc1, rc0, rcb) == (1, 0, 2)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
