"""outsider_council - put a subject before five outsiders: a chef, a pilot, a nurse, a judge and a farmer (backs the
outsider-council skill). PERSONA lens of the point-of-view family.

Each outsider carries four concerns from their own trade, each a cue-word pattern. The lens scores which concerns the
subject already covers (cue present in some sentence), names the concerns it leaves uncovered, and picks the one
sentence that outsider would interrogate: the sentence with the most hits on that trade's cues (ties -> the longer
sentence). Coverage across the five gives the outsider most at home and the one most alarmed. Cue lists are
hand-written heuristics; an outsider sees only words, not meaning.

    python outsider_council.py --selftest
    python outsider_council.py <file|text> [--json]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, report, run_cli, sentences, view, words  # noqa: E402

NAME = "outsider-council"
KINDS = {"text", "plan"}
COUNCIL = {
    "chef": {"prep order": r"\b(first|then|before|after|prep|prepare|order)\b",
             "timing": r"\b(minutes?|hours?|time|timing|nightly|daily|week|tonight|deadline)\b",
             "taste test": r"\b(taste|try|sample|check|test|score)\b",
             "clean station": r"\b(clean|tidy|delete|remove|cache|clear)\b"},
    "pilot": {"checklist": r"\b(checklist|verify|check|confirm|cross-check)\b",
              "abort point": r"\b(abort|stop|fallback|backup|if .{0,30} fails?|rollback|halt)\b",
              "conditions": r"\b(weather|conditions?|regime|revises?|data|source)\b",
              "fuel budget": r"\b(fuel|budget|cost|costs|limit|bps|memory|hours?)\b"},
    "nurse": {"dose": r"\b(dose|size|sizing|amount|percent|%|weight)\b",
              "monitoring": r"\b(monitor|watch|track|record|log|alert|heartbeat)\b",
              "side effects": r"\b(side effects?|risk|drawdown|harm|break|breaks|regress)\b",
              "consent": r"\b(ask|consent|approve|tell|max wants|agree)\b"},
    "judge": {"evidence": r"\b(evidence|proof|data|backtest|measured|receipt|test)\b",
              "burden": r"\b(prove|show|because|must|demonstrate)\b",
              "precedent": r"\b(before|again|old|previous|history|last time|precedent)\b",
              "other side": r"\b(they|counter|oppos\w*|however|but|crowd)\b"},
    "farmer": {"season": r"\b(season|cycle|regime|month|year|quarter)\b",
               "patience": r"\b(wait|patience|slow|later|forward|next)\b",
               "yield": r"\b(yield|return|returns|sharpe|profit|harvest|result)\b",
               "bad weather": r"\b(weather|drought|storm|crash|fails?|lost|loss)\b"}}


def apply(subject, kind=None, **opts) -> dict:
    kd, val = load_subject(subject, kind)
    if kd not in KINDS:
        raise ValueError(f"outsider-council reads text or plans, not {kd}")
    sents = [s for s in (val if kd == "plan" else sentences(val)) if words(s)]
    if not sents:
        raise ValueError("nothing for the council to read")
    low = [s.lower() for s in sents]
    f, cov = [], {}
    for who, concerns in COUNCIL.items():
        hit = {c: [i for i, s in enumerate(low) if re.search(p, s)] for c, p in concerns.items()}
        covered = [c for c, ix in hit.items() if ix]
        missing = [c for c in concerns if c not in covered]
        per = [sum(i in ix for ix in hit.values()) for i in range(len(sents))]
        focus = max(range(len(sents)), key=lambda i: (per[i], len(sents[i])))
        cov[who] = len(covered) / len(concerns)
        f.append({"what": f"{who}: covers {len(covered)}/4 ({', '.join(covered) or 'nothing'}); missing "
                          f"{', '.join(missing) or 'none'}; interrogates s{focus + 1}: {sents[focus][:60]}",
                  "persona": who, "coverage": cov[who], "missing": missing, "focus": focus + 1})
    home, alarmed = max(cov, key=cov.get), min(cov, key=cov.get)
    gaps = sorted({m for x in f for m in x["missing"]})
    return view(NAME, kd, f, f"five outsiders: the {home} is most at home ({cov[home]:.0%}), the {alarmed} most "
                f"alarmed ({cov[alarmed]:.0%}); {len(gaps)} trade concerns uncovered", coverage=cov,
                at_home=home, alarmed=alarmed)


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["text"])
    ok["probe text: five outsiders each score 0-100% coverage"] = (
        len(p["findings"]) == 5 and all(0 <= c <= 1 for c in p["stats"]["coverage"].values()))
    ok["probe text: the pilot sees the abort point ('If the nightly job fails again, we stop')"] = (
        "abort point" not in p["findings"][1]["missing"])
    plan = apply(PROBES["plan"])
    ok["probe plan: the nurse misses dose and side effects"] = {"dose", "side effects"} <= set(plan["findings"][2]["missing"])
    farm = apply("Plant in the spring season. Wait patiently for the harvest yield. A drought can come any year.")
    ok["planted farm note: the farmer covers 4/4 and is most at home"] = (
        farm["stats"]["coverage"]["farmer"] == 1.0 and farm["stats"]["at_home"] == "farmer")
    ok["planted farm note: the pilot finds no checklist"] = "checklist" in farm["findings"][1]["missing"]
    j = apply("The backtest is the evidence. They say it is wrong. The old version was the precedent. We must prove it.")
    ok["planted brief: the judge interrogates the evidence sentence or covers all 4"] = j["stats"]["coverage"]["judge"] == 1.0
    for label, bad in (("series", PROBES["series"]), ("items", PROBES["items"])):
        try:
            apply(bad)
            ok[f"planted bad input ({label}) is refused"] = False
        except ValueError:
            ok[f"planted bad input ({label}) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
