"""hl9_lint - the fifteen mechanical rules (HL9, R1-R15) over one report or item, with no rule skipped silently
(backs hl9-rules).

Every run prints all fifteen rows. Text-decidable rules are checked here:
  R1  reading block: >= 3 readings, of which >= 2 BURNED and one TAKEN
  R2  hedge lint: each later / next step / could / would / should / optional / parked / first pass / if the user wants /
      when budget allows line names an artefact (a path, a sha, a D/E/K/O id, a test id) or a BURNED entry
  R4  closed status: complete / completed / finished / solved / "is done" only on a line that says BEYOND_DONE;
      every "guarantee" line carries PROVED / TESTED(id) / MONITORED(lens) / POLICY
  R8  numbers: every p-value on a line with its tries (tries / trials / of N / N=); every Sharpe / edge / return line
      with a baseline (baseline / vs / random / buy-and-hold / null)
  R11 floor first: a "no edge" / "no effect" / "dead" verdict appears only with a floor, MDE, power or UNDERPOWERED
  R14 report shape: the first line is an answer (not a heading, greeting or "Here is"), a ledger with DONE / RUNNING /
      BLOCKED / NOT STARTED words, and a NOT RUN line or section
  R15 CYST: a CYST block with >= 5 answered items, and a hostile / independent review named with a file
The rest need git, runs or another tool; they print NOT_CHECKED with the skill that decides them, and count as
EVIDENCED when --evidence maps the rule to a file that exists (e.g. {"R5": "plants.json"}). With --strict a
NOT_CHECKED rule without evidence fails the report.
  R3 prose <= code (diffstat)            -> code-cage / git diff --stat
  R5 red for the right reason, 3 plants  -> plant-the-bug, plant-ledger
  R6 controls on every gate              -> self-attacking-referee
  R7 disjoint oracle + real CLI          -> command-tour, test-expectation-oracle
  R9 pre-register, one look              -> pre-register
  R10 baseline + search charge           -> deflated-sharpe, pbo-overfit
  R12 fast = slow on damaged inputs      -> speed-proof, fast-path-proof
  R13 no islands                         -> built-not-wired

    python hl9_lint.py REPORT.md [--only R1,R2] [--evidence ev.json] [--strict]
    python hl9_lint.py --selftest
Exit 0 no FAIL (and, under --strict, no unevidenced NOT_CHECKED), 1 otherwise, 2 bad arguments.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

NAMES = {1: "reading block", 2: "hedge lint", 3: "prose <= code", 4: "closed status", 5: "red for the right reason",
         6: "controls on every gate", 7: "disjoint oracle + real CLI", 8: "numbers audit", 9: "pre-register",
         10: "baseline + search charge", 11: "floor first", 12: "fast = slow", 13: "no islands",
         14: "four looks + ledger + NOT RUN", 15: "CYST + hostile review"}
ELSEWHERE = {3: "code-cage / git diff --stat", 5: "plant-the-bug, plant-ledger", 6: "self-attacking-referee",
             7: "command-tour, test-expectation-oracle", 9: "pre-register", 10: "deflated-sharpe, pbo-overfit",
             12: "speed-proof, fast-path-proof", 13: "built-not-wired"}
HEDGE = re.compile(r"\b(later|next step|could|would|should|optional|parked|first pass|if the user wants|when budget allows)\b",
                   re.I)
ARTEFACT = re.compile(r"[\w./\\-]+\.(?:py|md|json|jsonl|toml|txt|csv|ps1|bat|sh)\b|\b[0-9a-f]{7,40}\b|"
                      r"\b[DEKOU]\d{1,4}\b|\btest_\w+|BURNED", re.I)
DONE_WORDS = re.compile(r"\b([Cc]omplete|[Cc]ompleted|[Ff]inished|[Ss]olved)\b|\b(?:is|all|[Aa]ll) done\b")  # DONE (caps) is a ledger state
GUARANTEE = re.compile(r"\bguarantee", re.I)
GLABEL = re.compile(r"\bPROVED\b|\bTESTED\(|\bMONITORED\(|\bPOLICY\b")
PVAL = re.compile(r"\bp\s*(?:=|<|>|<=|>=|≤)\s*0?\.\d+|\bp-value", re.I)
TRIES = re.compile(r"\btries\b|\btrials?\b|\bof \d+|\bN\s*=\s*\d+|\bn\s*=\s*\d+", re.I)
PERF = re.compile(r"\b(sharpe|edge|excess return|return of|cagr)\b", re.I)
BASE = re.compile(r"baseline|\bvs\.?\b|versus|random|buy[- ]and[- ]hold|\bnull\b|benchmark", re.I)
NOEDGE = re.compile(r"\bno edge\b|\bno effect\b|\bedge is dead\b|\bis dead\b|\bnothing there\b", re.I)
FLOOR = re.compile(r"UNDERPOWERED|\bMDE\b|\bfloor\b|\bpower\b|minimum detectable", re.I)
LEDGER = re.compile(r"\b(DONE|RUNNING|BLOCKED|NOT STARTED)\b")


def check(text: str) -> dict:
    lines = text.splitlines()
    res = {}

    def put(n, status, detail):
        res[n] = (status, detail)
    # R1
    if not re.search(r"\bREADING\b", text):
        put(1, "FAIL", "no READING block")
    else:
        burned = 0
        for m in re.finditer(r"\bBURNED\b(.*)", text):
            rest = re.sub(r"^\s*\(\d+\)\s*:", ":", m.group(1))
            burned += max(1, len(re.findall(r"\(\d+\)", rest)))
        taken = len(re.findall(r"\bTAKEN\b", text))
        if burned < 2 or taken < 1 or burned + taken < 3:
            put(1, "FAIL", f"{taken} TAKEN + {burned} BURNED readings (need 1 + 2, total >= 3)")
        else:
            put(1, "PASS", f"{taken} TAKEN + {burned} BURNED")
    # R2 (lines of the CYST block are the critic's questions, not hedges)
    cyst_lines, inside = set(), False
    for i, ln in enumerate(lines):
        if re.search(r"\bCYST\b", ln):
            inside = True
        elif inside and not ln.strip():
            inside = False
        if inside:
            cyst_lines.add(i)
    bad = [i + 1 for i, ln in enumerate(lines) if i not in cyst_lines and HEDGE.search(ln) and not ARTEFACT.search(ln)]
    put(2, "FAIL" if bad else "PASS", f"unmatched hedges on lines {bad[:8]}" if bad else "every hedge names an artefact")
    # R4
    claims = [i + 1 for i, ln in enumerate(lines) if DONE_WORDS.search(ln) and "BEYOND_DONE" not in ln]
    guar = [i + 1 for i, ln in enumerate(lines) if GUARANTEE.search(ln) and not GLABEL.search(ln)]
    if claims or guar:
        put(4, "FAIL", (f"completion words without BEYOND_DONE on lines {claims[:8]}" if claims else "") +
            ("; " if claims and guar else "") + (f"unlabelled guarantees on lines {guar[:8]}" if guar else ""))
    else:
        put(4, "PASS", "status words closed")
    # R8
    pv = [i + 1 for i, ln in enumerate(lines) if PVAL.search(ln) and not TRIES.search(ln)]
    pf = [i + 1 for i, ln in enumerate(lines) if PERF.search(ln) and re.search(r"\d", ln) and not BASE.search(ln)
          and not FLOOR.search(ln) and not NOEDGE.search(ln)]
    if pv or pf:
        put(8, "FAIL", (f"p without tries on lines {pv[:8]}" if pv else "") + ("; " if pv and pf else "") +
            (f"result without a baseline on lines {pf[:8]}" if pf else ""))
    else:
        put(8, "PASS", "p-values carry tries, results carry baselines")
    # R11
    if NOEDGE.search(text) and not FLOOR.search(text):
        put(11, "FAIL", "a no-edge verdict with no floor / MDE / power / UNDERPOWERED anywhere")
    else:
        put(11, "PASS", "no bare no-edge verdict")
    # R14
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    probs = []
    if not first or first.startswith("#") or re.match(r"^(here is|here's|thanks|thank you|hi\b|hello)", first, re.I):
        probs.append("first line is not an answer")
    if not LEDGER.search(text):
        probs.append("no DONE / RUNNING / BLOCKED / NOT STARTED ledger")
    if not re.search(r"\bNOT RUN\b", text):
        probs.append("no NOT RUN line")
    put(14, "FAIL" if probs else "PASS", "; ".join(probs) or "answer first, ledger, NOT RUN")
    # R15
    cyst = re.search(r"\bCYST\b", text)
    answers = 0
    if cyst:
        after = text[cyst.end():].splitlines()[1:]
        for ln in after:
            if re.match(r"^\s*(?:\d+[.)]|[-*])\s+\S", ln):
                answers += 1
            elif ln.strip() and not ln.startswith(" ") and answers:
                break
    review = re.search(r"(hostile|independent|adversar|fresh)[^\n]*\b[\w./\\-]+\.(md|json|txt)\b", text, re.I)
    p15 = []
    if answers < 5:
        p15.append(f"CYST block with {answers} answered items (need 5)")
    if not review:
        p15.append("no hostile / independent review named with a file")
    put(15, "FAIL" if p15 else "PASS", "; ".join(p15) or "CYST answered, review filed")
    return res


def lint(text, only=None, evidence=None, strict=False) -> list:
    res, rows = check(text), []
    for n in range(1, 16):
        if only and n not in only:
            continue
        if n in res:
            s, d = res[n]
        else:
            ev = (evidence or {}).get(f"R{n}")
            if ev and Path(ev).is_file():
                s, d = "EVIDENCED", f"{ev} (decided by {ELSEWHERE[n]})"
            elif ev:
                s, d = "FAIL", f"evidence file {ev} does not exist"
            else:
                s, d = ("FAIL" if strict else "NOT_CHECKED"), f"needs {ELSEWHERE[n]}" + (" (--strict)" if strict else "")
        rows.append((n, s, d))
    return rows


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    args, o = list(argv), {}
    try:
        for f in ("--only", "--evidence"):
            if f in args:
                i = args.index(f)
                o[f] = args[i + 1]
                del args[i:i + 2]
        strict = "--strict" in args
        args = [a for a in args if a != "--strict"]
        if len(args) != 1 or not Path(args[0]).is_file():
            raise ValueError("need one REPORT file")
        only = {int(x.strip().lstrip("Rr")) for x in o["--only"].split(",")} if "--only" in o else None
        ev = json.loads(Path(o["--evidence"]).read_text(encoding="utf-8")) if "--evidence" in o else None
        rows = lint(Path(args[0]).read_text(encoding="utf-8", errors="replace"), only, ev, strict)
    except (ValueError, OSError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    for n, s, d in rows:
        print(f"R{n:<3} {NAMES[n]:<30} {s:<12} {d}")
    counts = {}
    for _, s, _ in rows:
        counts[s] = counts.get(s, 0) + 1
    print(f"{len(rows)} rule(s): " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 1 if counts.get("FAIL") else 0


def _selftest() -> bool:
    ok = {}
    good = ("Not done: the cache build is RUNNING; everything else is DONE.\n\n"
            "READING. TAKEN: build the lint. BURNED: (1) describe it; (2) a subset only.\n\n"
            "| item | state | proof |\n|---|---|---|\n| lint | DONE | hl9_lint.py, 12 PASS |\n"
            "| cache | RUNNING | see jobs.json |\n\n"
            "The guarantee is TESTED(test_lint_shape).\n"
            "Edge 0.4% per trade vs random entry, p = 0.03 after 12 tries.\n"
            "The reversion lane shows no edge at this sample; it is UNDERPOWERED (MDE 0.8%).\n"
            "Next step: wire it into precommit (D161 names the hook).\n\n"
            "NOT RUN: the PC parity pass.\n\n"
            "CYST\n1. what would kill it: a hedge rule miss\n2. weakest link: regexes\n3. cheapest check: plants\n"
            "4. what I did not run: PC\n5. who disagrees: the referee\n\n"
            "Hostile review by a fresh agent filed in reviews/hl9_review.md.\n")
    r = {n: s for n, s, _ in lint(good)}
    ok["a well-formed report passes every text rule"] = all(r[n] == "PASS" for n in (1, 2, 4, 8, 11, 14, 15))
    ok["all fifteen rules print a row (none skipped silently)"] = len(lint(good)) == 15 and sum(
        1 for s in r.values() if s == "NOT_CHECKED") == 8
    bad = ("# Report\nHere is what I did. The feature is complete.\n"
           "We could add caching later.\n"
           "Sharpe 1.9 on the full sample, p = 0.01.\n"
           "There is no edge in reversion.\n"
           "This guarantees no look-ahead.\n")
    rb = {n: (s, d) for n, s, d in lint(bad)}
    ok["R1 fails with no reading block"] = rb[1][0] == "FAIL"
    ok["R2 fails on a hedge with no artefact"] = rb[2][0] == "FAIL" and "3" in rb[2][1]
    ok["R4 fails on 'complete' without BEYOND_DONE and on an unlabelled guarantee"] = (
        rb[4][0] == "FAIL" and "completion" in rb[4][1] and "guarantee" in rb[4][1])
    ok["R8 fails on p without tries and Sharpe without a baseline"] = (
        rb[8][0] == "FAIL" and "tries" in rb[8][1] and "baseline" in rb[8][1])
    ok["R11 fails on a bare no-edge verdict"] = rb[11][0] == "FAIL"
    ok["R14 fails: heading first, no ledger, no NOT RUN"] = rb[14][0] == "FAIL" and rb[14][1].count(";") == 2
    ok["R15 fails without CYST answers and a filed review"] = rb[15][0] == "FAIL"
    one = good.replace("BURNED: (1) describe it; (2) a subset only.", "BURNED: describe it.")
    ok["one BURNED reading is not enough for R1"] = {n: s for n, s, _ in lint(one)}[1] == "FAIL"
    short = good.split("CYST")[0] + "CYST\n1. a\n2. b\n\nHostile review by a fresh agent in reviews/r.md.\n"
    ok["a CYST block with 2 answers fails R15 even with a filed review"] = {n: s for n, s, _ in lint(short)}[15] == "FAIL"
    ok["BEYOND_DONE on the line makes 'complete' lawful"] = {n: s for n, s, _ in lint(
        good + "Item K12 is complete: BEYOND_DONE (receipt r.json).\n")}[4] == "PASS"
    with tempfile.TemporaryDirectory() as td:
        ev = Path(td) / "plants.json"
        ev.write_text("{}", encoding="utf-8")
        rs = {n: s for n, s, _ in lint(good, evidence={"R5": str(ev), "R9": str(Path(td) / "nope.json")}, strict=True)}
        ok["--evidence turns a rule EVIDENCED, a missing file FAILs, strict fails the unevidenced rest"] = (
            rs[5] == "EVIDENCED" and rs[9] == "FAIL" and rs[3] == "FAIL")
        p = Path(td) / "rep.md"
        p.write_text(good, encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc0 = main([str(p)])
            rc1 = main([str(p), "--strict"])
            rco = main([str(p), "--only", "R1,R2"])
        ok["exit 0 clean, 1 under --strict without evidence, --only limits rows"] = (rc0, rc1, rco) == (0, 1, 0)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
