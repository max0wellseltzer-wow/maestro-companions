"""concept_card - lint typed concept cards; a card that forces no code is a glossary entry (backs concept-card).

A card starts at a bold id line like `**C1 · Identity: when are two things the same thing?**` (override --card-re) and
holds `- **Field:** value` lines. Checks per card:
  MISSING_FIELD     one of Definition, Formal object, Theory, Assumptions, Failure, Dual, Measure, Forces, Open
                    (change with --fields)
  THEORY_NO_STATUS  the Theory field names no status (PROVED, CITED, CITED-UNVERIFIED, VERIFIED, TESTED, NUMERICAL,
                    CONJECTURED, OPEN)
  NO_ASSUMPTIONS    the Assumptions field has no A1..An items
  NO_TAG            an assumption is not tagged HOLDS / FAILS / UNKNOWN
  NO_TEST           a HOLDS or UNKNOWN assumption names no test that decides it (test, check, measure, decided,
                    sweep, probe, inline code, or a unit id)
  GLOSSARY          the Forces field names no code: no unit id (CDU01, K12, IC 31 ...), no `code` and no path
  FORCE_MISSING     with --root: a forced path (`x/y.py`, optionally `::func`) does not exist, or the function is not
                    defined in it
    python concept_card.py PLAN.md [--only C1,C2] [--root DIR] [--fields a,b] [--card-re REGEX]
    python concept_card.py --selftest
Exit 0 all cards clean, 1 problems or no card, 2 bad arguments.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

CARD_RE = r"^\*\*(C\d+)\s*[·:]"          # concept ids C1..Cn; --card-re for other notations
FIELDS = ("Definition", "Formal object", "Theory", "Assumptions", "Failure", "Dual", "Measure", "Forces", "Open")
FIELD = re.compile(r"^\s*[-*]\s+\*\*([A-Za-z][A-Za-z /-]*?)\s*:\*\*\s*(.*)$")
STATUS = re.compile(r"\b(PROVED|CITED-UNVERIFIED|CITED|VERIFIED|TESTED|NUMERICAL|CONJECTURED|OPEN)\b")
TAG = re.compile(r"\b(HOLDS|FAILS|UNKNOWN)\b")
TESTY = re.compile(r"\btest|\bcheck|\bmeasur|\bdecided?\b|\bsweep|\bprobe|`[^`]+`|\b[A-Z]{2,4}\s?\d+\b", re.I)
UNIT = re.compile(r"\b(?:CDU|SKM|IC|K|O|U|PG|AB|X)\s?\d+\b")
CODE = re.compile(r"`([^`]+)`")
PATHLIKE = re.compile(r"([\w./-]+\.py)(?:::(\w+))?")


def parse(text: str, card_re: str = CARD_RE) -> list:
    rx = re.compile(card_re)
    cards, cur, field = [], None, None
    for n, ln in enumerate(text.splitlines(), 1):
        m = rx.match(ln)
        if m:
            cur = {"id": m.group(1), "line": n, "fields": {}}
            cards.append(cur)
            field = None
            continue
        if cur is None:
            continue
        if re.match(r"^#{1,6}\s", ln):
            cur, field = None, None
            continue
        f = FIELD.match(ln)
        if f and (len(ln) - len(ln.lstrip())) <= 1:
            field = f.group(1).strip().lower()
            cur["fields"][field] = {"line": n, "text": f.group(2), "items": []}
        elif field and ln.strip():
            cur["fields"][field]["items"].append((n, ln.strip()))
            cur["fields"][field]["text"] += " " + ln.strip()
    return cards


def lint(text, root=None, fields=FIELDS, card_re=CARD_RE, only=None) -> list:
    out = []
    for c in parse(text, card_re):
        if only and c["id"] not in only:
            continue
        p = []
        F = c["fields"]
        for f in fields:
            if f.lower() not in F:
                p.append((c["line"], "MISSING_FIELD", f))
        th = F.get("theory")
        if th and not STATUS.search(th["text"]):
            p.append((th["line"], "THEORY_NO_STATUS", th["text"][:70]))
        asum = F.get("assumptions")
        if asum is not None:
            items = []
            for n, ln in asum["items"]:
                m = re.match(r"^[-*]?\s*(A\d+)[.:)]\s*(.*)", ln)
                if m:
                    items.append([n, m.group(1), m.group(2)])
                elif items:
                    items[-1][2] += " " + ln
            if not items:
                p.append((asum["line"], "NO_ASSUMPTIONS", "no A1..An items"))
            for n, aid, body in items:
                t = TAG.search(body)
                if not t:
                    p.append((n, "NO_TAG", f"{aid} {body[:60]}"))
                elif t.group(1) in ("HOLDS", "UNKNOWN") and not TESTY.search(body):
                    p.append((n, "NO_TEST", f"{aid} is {t.group(1)} but names no deciding test"))
        fo = F.get("forces")
        if fo is not None:
            txt = fo["text"]
            codes = CODE.findall(txt)
            if not (UNIT.search(txt) or codes or PATHLIKE.search(txt)):
                p.append((fo["line"], "GLOSSARY", "forces no code (no unit id, `code` or path)"))
            if root is not None:
                for m in PATHLIKE.finditer(txt):
                    fp = Path(root) / m.group(1)
                    if not fp.is_file():
                        p.append((fo["line"], "FORCE_MISSING", m.group(0)))
                    elif m.group(2) and not re.search(rf"^\s*(?:async\s+)?def\s+{m.group(2)}\b",
                                                      fp.read_text(encoding="utf-8", errors="replace"), re.M):
                        p.append((fo["line"], "FORCE_MISSING", f"{m.group(0)} (function not defined)"))
        out.append({"id": c["id"], "line": c["line"], "problems": p})
    return out


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    args, o = list(argv), {}
    try:
        for f in ("--only", "--root", "--fields", "--card-re"):
            if f in args:
                i = args.index(f)
                o[f] = args[i + 1]
                del args[i:i + 2]
    except IndexError:
        print("REFUSED: a flag is missing its value", file=sys.stderr)
        return 2
    if len(args) != 1 or args[0].startswith("--") or not Path(args[0]).is_file():
        print(__doc__)
        return 2
    rep = lint(Path(args[0]).read_text(encoding="utf-8", errors="replace"), o.get("--root"),
               tuple(x.strip() for x in o["--fields"].split(",")) if "--fields" in o else FIELDS,
               o.get("--card-re", CARD_RE), set(o["--only"].split(",")) if "--only" in o else None)
    kinds = {}
    for c in rep:
        for n, k, d in c["problems"]:
            kinds[k] = kinds.get(k, 0) + 1
            print(f"{c['id']:<5} L{n:<6} {k:<16} {d}")
    bad = sum(1 for c in rep if c["problems"])
    print(f"{len(rep)} card(s), {bad} with problems" +
          ("" if not kinds else ": " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))))
    if not rep:
        print("NO CARDS FOUND (check --card-re)")
        return 1
    return 1 if bad else 0


def _selftest() -> bool:
    ok = {}
    good = ("**C1 · Identity**\n"
            "- **Definition:** an equivalence relation.\n"
            "- **Formal object:** a quotient set.\n"
            "- **Theory:** Newman's lemma (CITED-UNVERIFIED).\n"
            "- **Assumptions:**\n"
            "  - A1. Output equality is exact. **FAILS** for floats: (a+b)+c differs.\n"
            "  - A2. Tolerance is transitive. **UNKNOWN**, decided by the probe sweep in IC 31.\n"
            "- **Failure:** merges distinct blends.\n"
            "- **Dual:** distinction.\n"
            "- **Measure:** collision rate.\n"
            "- **Forces:**\n  - CDU01 and `src/canon.py::fingerprint`;\n"
            "- **Open:** the probe-set size.\n\n")
    bad = ("**C2 · Vague idea**\n"
           "- **Definition:** a thing.\n"
           "- **Theory:** some well-known framework.\n"
           "- **Assumptions:**\n"
           "  - A1. Markets are efficient.\n"
           "  - A2. Volume leads price. **HOLDS** in our experience.\n"
           "- **Forces:** a deeper understanding of markets.\n"
           "- **Open:** everything.\n\n"
           "## Next section\n**not a card**\n- **Dual:** a field outside any card\n")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "src").mkdir()
        (td / "src" / "canon.py").write_text("def fingerprint(x):\n    return x\n", encoding="utf-8")
        rep = {c["id"]: c for c in lint(good + bad, root=td)}
        kinds = {cid: [k for _, k, _ in c["problems"]] for cid, c in rep.items()}
        ok["two cards are parsed and a heading ends the last"] = set(rep) == {"C1", "C2"}
        ok["a complete card with a forced function that exists is clean"] = kinds["C1"] == []
        ok["missing fields are listed by name"] = sorted(d for _, k, d in rep["C2"]["problems"] if k == "MISSING_FIELD") == \
            ["Dual", "Failure", "Formal object", "Measure"]
        ok["a theory without a status is THEORY_NO_STATUS"] = "THEORY_NO_STATUS" in kinds["C2"]
        ok["an untagged assumption is NO_TAG"] = any(k == "NO_TAG" and "A1" in d for _, k, d in rep["C2"]["problems"])
        ok["a HOLDS assumption without a deciding test is NO_TEST"] = any(
            k == "NO_TEST" and "A2" in d for _, k, d in rep["C2"]["problems"])
        ok["a card that forces no code is GLOSSARY"] = "GLOSSARY" in kinds["C2"]
        (td / "src" / "canon.py").write_text("def other(x):\n    return x\n", encoding="utf-8")
        r2 = {c["id"]: c for c in lint(good, root=td)}
        ok["a forced function that is not defined is FORCE_MISSING"] = any(
            k == "FORCE_MISSING" for _, k, _ in r2["C1"]["problems"])
        ok["without --root forced paths are not resolved"] = lint(good)[0]["problems"] == []
        f = td / "p.md"
        f.write_text(good + bad, encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc1 = main([str(f)])
            rc0 = main([str(f), "--only", "C1"])
            f.write_text("nothing\n", encoding="utf-8")
            rcn = main([str(f)])
        ok["exit 1 with problems, 0 for a clean card, 1 when no card is found"] = (rc1, rc0, rcn) == (1, 0, 1)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
