"""Survivor court recorder: every surviving (or MISSING) planted bug must get one of the five rulings, and the report
line is computed, never typed.

Input: plant results (a list of {"i": n, "verdict": "KILLED|SURVIVED|MISSING|TIMEOUT", ...} - exactly what
plant-the-bug's `plant_runner.run_cases()` returns, or tools/plant.py output turned into that shape) and rulings
{i: {"ruling": ..., "why": ...}}. Allowed rulings: MISSING TEST, WEAK ASSERTION, EQUIVALENT, DESIGN SMELL,
STALE FIXTURE. The court flags: an unruled survivor; an unknown ruling word; an EQUIVALENT without a one-sentence proof
in "why"; a MISSING case ruled anything but STALE FIXTURE; a ruling on a KILLED case. MISSING TEST / WEAK ASSERTION /
DESIGN SMELL / STALE FIXTURE stay OPEN (act, then re-run) - only KILLED and proven EQUIVALENT close a case. It also
scans test source for assertions that cannot fail (`or True`, `if False`, `assert True`, `x or "..." in out`).

Usage:
    python survivor_court.py results.json rulings.json [--tests tests/test_x.py ...]
    python survivor_court.py --selftest
Library:
    from survivor_court import judge, scan_weak_assertions
"""
import json
import re
import sys

RULINGS = ("MISSING TEST", "WEAK ASSERTION", "EQUIVALENT", "DESIGN SMELL", "STALE FIXTURE")
_WEAK = [
    (re.compile(r"\bor\s+True\b"), "`or True` makes the condition always true"),
    (re.compile(r"^\s*if\s+False\s*:", re.MULTILINE), "`if False:` block never runs"),
    (re.compile(r"^\s*assert\s+(True|1|\"[^\"]+\"|'[^']+')\s*(,|$)", re.MULTILINE), "assert on a constant"),
    (re.compile(r"assert\s+[^\n#]*\bor\s+[\"'][^\"'\n]*[\"']\s+in\b"), "`a or '...' in out` - one side may always hold"),
]


def judge(results, rulings):
    rulings = {int(k): v for k, v in (rulings or {}).items()}
    problems, open_cases, equivalent, killed = [], [], [], 0
    for r in results:
        i, v = int(r["i"]), r["verdict"]
        rul = rulings.get(i)
        if v in ("KILLED", "TIMEOUT"):
            killed += 1
            if rul:
                problems.append("#%d is KILLED but carries a ruling (%s)" % (i, rul.get("ruling")))
            continue
        if not rul:
            problems.append("#%d %s has no ruling" % (i, v))
            open_cases.append(i)
            continue
        word, why = rul.get("ruling"), (rul.get("why") or "").strip()
        if word not in RULINGS:
            problems.append("#%d ruling %r is not one of %s" % (i, word, ", ".join(RULINGS)))
            open_cases.append(i)
            continue
        if v == "MISSING" and word != "STALE FIXTURE":
            problems.append("#%d is MISSING (text not in file) so it must be STALE FIXTURE, not %s" % (i, word))
        if word == "EQUIVALENT":
            if len(why.split()) < 5:
                problems.append("#%d EQUIVALENT without a one-sentence proof in 'why'" % i)
                open_cases.append(i)
            else:
                equivalent.append((i, why))
        else:
            open_cases.append(i)
    n = len(results)
    line = "%d of %d caught, %d equivalent" % (killed, n, len(equivalent))
    if equivalent:
        line += " (" + "; ".join("#%d: %s" % e for e in equivalent) + ")"
    line += ", %d open" % len(open_cases)
    closed = not problems and not open_cases
    return {"line": line, "problems": problems, "open": open_cases, "closed": closed}


def scan_weak_assertions(src):
    hits = []
    for rx, why in _WEAK:
        for m in rx.finditer(src):
            hits.append((src.count("\n", 0, m.start()) + 1, why))
    return sorted(hits)


def _selftest():
    ok = True

    def check(cond, desc):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + desc)
        ok = ok and bool(cond)

    res = [{"i": 0, "verdict": "KILLED"}, {"i": 1, "verdict": "SURVIVED"}, {"i": 2, "verdict": "SURVIVED"},
           {"i": 3, "verdict": "MISSING"}]
    j = judge(res, {})
    check(not j["closed"] and sum("has no ruling" in p for p in j["problems"]) == 3, "flags all three unruled cases")
    good = {1: {"ruling": "EQUIVALENT", "why": "the later filter drops every row this lets in"},
            2: {"ruling": "MISSING TEST", "why": "boundary 0.5% unchecked"},
            3: {"ruling": "STALE FIXTURE", "why": "CRLF in file"}}
    j = judge(res, good)
    check(j["problems"] == [] and j["open"] == [2, 3], "MISSING TEST and STALE FIXTURE stay open until re-run")
    check(j["line"].startswith("1 of 4 caught, 1 equivalent (#1: the later filter"), "report line is computed")
    j = judge(res, {**good, 1: {"ruling": "EQUIVALENT", "why": "harmless"}})
    check(any("without a one-sentence proof" in p for p in j["problems"]), "rejects EQUIVALENT with no proof")
    j = judge(res, {**good, 3: {"ruling": "MISSING TEST", "why": "x"}})
    check(any("must be STALE FIXTURE" in p for p in j["problems"]), "rejects a MISSING case ruled as MISSING TEST")
    j = judge(res, {**good, 2: {"ruling": "fine", "why": "x"}})
    check(any("is not one of" in p for p in j["problems"]), "rejects an unknown ruling word")
    done = judge([{"i": 0, "verdict": "KILLED"}, {"i": 1, "verdict": "SURVIVED"}], {1: good[1]})
    check(done["closed"] and done["line"].endswith("0 open"), "all killed or proven equivalent closes the court")
    src = 'def test_a():\n    assert x == 1 or True\n    assert "ok" in out\n    assert y or "0 days" in out\n'
    w = scan_weak_assertions(src)
    check([ln for ln, _ in w] == [2, 4], "weak-assertion scan flags lines 2 and 4, not the honest line 3")
    return ok


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    with open(argv[0], encoding="utf-8") as f:
        results = json.load(f)
    with open(argv[1], encoding="utf-8") as f:
        rulings = json.load(f)
    j = judge(results, rulings)
    print(j["line"])
    for p in j["problems"]:
        print("- " + p)
    if "--tests" in argv:
        for path in argv[argv.index("--tests") + 1:]:
            with open(path, encoding="utf-8") as f:
                for ln, why in scan_weak_assertions(f.read()):
                    print("WEAK %s:%d %s" % (path, ln, why))
    return 0 if j["closed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
