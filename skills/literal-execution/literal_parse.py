"""literal_parse - read the user's prompt as a contract before doing anything (backs the literal-execution skill).

Splits a prompt into ASKS (imperative clauses), and pulls out what the user actually constrained:
  quantities   "2 of your favorite tasks", "no less than 33 strategies", "44 ... next steps"
  scope        all / every / literally / only / each
  ordering     "only after X", "first X then Y", "before X", "when X is done"
  negations    "do not X", "no X unless Y", "never X", "stop X"
check(parsed, done) then lists every ask with no matching done item, every quantity not met, and every negation
the done items violate - the gap between what was asked and what was done.

    from literal_parse import parse, check
    p = parse(prompt_text); check(p, ["built the screener over all stocks", ...])
    python literal_parse.py --selftest
"""
from __future__ import annotations

import re
import sys

STOP = set("the a an and or of to in for on with is it this that be by as at are your my our you me i we "
           "all any some more most them they then".split())
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "dozen": 12, "a dozen": 12}
QTY = re.compile(r"\b(?:no less than |at least |exactly )?(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a dozen|dozen)"
                 r"\s+(?:of\s+)?(?:your\s+|my\s+|our\s+|the\s+)?(?:(?:favorite|favourite|most|best|important|useful|"
                 r"fascinating|utterly|amazing|new|more)\s+)*([a-z][a-z-]+(?:\s+(?!(?:and|or|then|to|of|for|with)\b)"
                 r"[a-z][a-z-]+)?)", re.I)
NEG = re.compile(r"\b(do not|don't|never|no|stop)\b\s+([^.,;!?]+?)(?:\s+unless\s+([^.;!?]+))?(?=[.,;!?]|$)", re.I)
ORDER = re.compile(r"\b(only after|after|before|first|then|when)\b\s+(.+?)(?=,|[.;!?]|\bthen\b|$)", re.I)
SCOPE = re.compile(r"\b(literally all|all|every|each|only|entire|whole)\b", re.I)


def _words(s):
    """Content words, crudely singularised so 'tasks' meets 'task'."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
            for w in re.findall(r"[a-z][a-z-]{2,}", s.lower()) if w not in STOP}


def parse(prompt: str) -> dict:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("empty prompt")
    clauses = [c.strip() for c in re.split(r"(?<=[.!?])\s+|\s*;\s*|\n+", prompt) if c.strip()]
    quantities = []
    for m in QTY.finditer(prompt):
        n = m.group(1).lower()
        quantities.append({"n": int(n) if n.isdigit() else NUM_WORDS[n], "of": m.group(2).lower().strip()})
    return {"asks": [c for c in clauses if not c.endswith("?")],
            "questions": [c for c in clauses if c.endswith("?")],
            "quantities": quantities,
            "negations": [{"not": m.group(2).strip().lower(), "unless": (m.group(3) or "").strip().lower() or None}
                          for m in NEG.finditer(prompt)],
            "ordering": [{"word": m.group(1).lower(), "clause": m.group(2).strip()} for m in ORDER.finditer(prompt)],
            "scope": sorted({m.group(1).lower() for m in SCOPE.finditer(prompt)})}


def check(parsed: dict, done: list) -> dict:
    """Asks with no done item sharing >= 2 content words (or 1 if the ask is short) are UNMET. Questions must be
    answered too. Negations are VIOLATED when a done item matches the forbidden phrase and not its 'unless'."""
    done_w = [(d, _words(d)) for d in done]
    unmet = []
    for a in parsed["asks"] + parsed["questions"]:
        need = 1 if len(_words(a)) <= 3 else 2
        if not any(len(_words(a) & w) >= need for _, w in done_w):
            unmet.append(a)
    short = []
    for q in parsed["quantities"]:
        hits = sum(1 for d, w in done_w if _words(q["of"]) & w)
        if hits < q["n"]:
            short.append({**q, "done": hits})
    violated = []
    for neg in parsed["negations"]:
        bad = _words(neg["not"])
        ok_if = _words(neg["unless"]) if neg["unless"] else set()
        for d, w in done_w:
            if bad and len(bad & w) >= min(2, len(bad)) and not (ok_if & w):
                violated.append({"rule": neg, "item": d})
    return {"unmet": unmet, "short": short, "violated": violated,
            "complete": not unmet and not short and not violated}


def _selftest() -> bool:
    ok = {}
    p = parse("first you must continue all your previous answers, then proceed with 2 of your favorite tasks, "
              "2 of your favorite specifications, and 44 favorite next steps.")
    ok["quantities read from the user's 10-06 prompt"] = (
        [(q["n"], q["of"]) for q in p["quantities"]][:2] == [(2, "tasks"), (2, "specifications")]
        and any(q["n"] == 44 for q in p["quantities"]))
    ok["ordering words captured (first ... then ...)"] = {o["word"] for o in p["ordering"]} >= {"first", "then"}
    o = parse("Do this ONLY After you are done with LITERALLY all your work please")
    ok["'ONLY After' is an ordering constraint, 'literally all' a scope"] = (
        o["ordering"][0]["word"] == "only after" and "literally all" in o["scope"])
    n = parse("no tests unless I ask for them or they improve the software")
    ok["negation with its exception is kept"] = (n["negations"][0]["not"].startswith("tests")
                                                 and "improve the software" in n["negations"][0]["unless"])
    r = check(n, ["ran 28 extra tests on the forward record"])
    ok["planted violation: an unrequested test breaks the negation"] = bool(r["violated"]) and not r["complete"]
    r2 = check(parse("Build the screener over all stocks. Sync it to the repo."),
               ["built the screener over all 12,747 stocks"])
    ok["an unmet ask is named, the met one is not"] = r2["unmet"] == ["Sync it to the repo."]
    r3 = check(p, ["continued previous answers", "task one", "task two", "specification one"])
    ok["a quantity left short is reported with its count"] = any(s["of"] == "specifications" and s["done"] == 1
                                                                for s in r3["short"])
    try:
        parse("   ")
        ok["planted bad input (empty prompt) is rejected"] = False
    except ValueError:
        ok["planted bad input (empty prompt) is rejected"] = True
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    import json
    print(json.dumps(parse(open(argv[0], encoding="utf-8").read()), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
