"""steelman - rebuild an opposing view at its strongest (backs the steelman skill). VANTAGE lens of the
point-of-view family.

Every claim sentence of the opposing text is scored for strength: number +2, mechanism (because/since/so) +2,
source +2, specificity (8+ content words) +1. Strawman markers and overreach are then repaired, not counted against
the view: sneer and filler words ("obviously", "somehow", "etc", "they say") are cut, absolutes are softened to the
defensible form (always -> usually, never -> rarely, all -> most, guaranteed -> likely) and "!" becomes ".". The
steelman is the top half (at least 3) of the repaired claims by strength, in their original order; the dropped
claims are listed as the view's weakest parts. Heuristic word lists; it cannot invent evidence the text lacks.

    python steelman.py --selftest
    python steelman.py <file|text> [--json]
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, numbers_with_units, report, run_cli, sentences, view, words  # noqa: E402

NAME = "steelman"
KINDS = {"text", "plan"}
CUT = r"\b(obviously|clearly|somehow|basically|simply|just|they say|of course|everyone knows)\b,?\s*|,?\s*\betc\b\.?"
SOFTEN = {"always": "usually", "never": "rarely", "all": "most", "none": "few", "guaranteed": "likely",
          "everyone": "most people", "nobody": "few people", "certainly": "probably", "impossible": "unlikely"}
SOURCE = r"\b(data|measured|log|test|source|according|sample|study|record|backtest|from)\b"
CAUSE = r"\b(because|since|so that|therefore|due to|which means)\b"


def strength(s: str) -> int:
    low = s.lower()
    return (2 * bool(numbers_with_units(s)) + 2 * bool(re.search(CAUSE, low)) + 2 * bool(re.search(SOURCE, low))
            + int(sum(w not in STOP for w in words(s)) >= 8))


def repair(s: str):
    edits = []
    t, n = re.subn(CUT, "", s, flags=re.I)
    if n:
        edits.append(f"cut {n} sneer/filler")
    for a, b in SOFTEN.items():
        t, n = re.subn(rf"\b{a}\b", b, t, flags=re.I)
        if n:
            edits.append(f"{a}->{b}")
    if "!" in t:
        t = t.replace("!", ".")
        edits.append("!->.")
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = t[:1].upper() + t[1:] if t else t
    return t, edits


def apply(subject, kind=None, **opts) -> dict:
    kd, val = load_subject(subject, kind)
    if kd not in KINDS:
        raise ValueError(f"steelman rebuilds arguments in text, not {kd}")
    claims = [s for s in (val if kd == "plan" else sentences(val)) if len(words(s)) >= 3]
    if len(claims) < 2:
        raise ValueError("steelman needs at least 2 claims to choose the strongest")
    rows = []
    for i, s in enumerate(claims):
        r, edits = repair(s)
        rows.append({"i": i, "orig": s, "fixed": r, "edits": edits, "raw": strength(s), "score": strength(r)})
    k = max(3, math.ceil(len(rows) / 2)) if len(rows) > 3 else len(rows) - 1
    keep = {r["i"] for r in sorted(rows, key=lambda r: (-r["score"], r["i"]))[:k]}
    f = [{"what": f"KEEP s{r['i'] + 1} strength {r['score']}: {r['fixed'][:90]}"
                  + (f" [{', '.join(r['edits'])}]" if r["edits"] else ""), "claim": r["i"] + 1, "kept": True,
          "strength": r["score"]} for r in rows if r["i"] in keep]
    f += [{"what": f"DROP s{r['i'] + 1} strength {r['score']} (weakest part of the view): {r['orig'][:80]}",
           "claim": r["i"] + 1, "kept": False, "strength": r["score"]} for r in rows if r["i"] not in keep]
    steel = " ".join(r["fixed"] for r in rows if r["i"] in keep)
    gain = sum(rows[i]["score"] for i in keep) / len(keep) - sum(r["score"] for r in rows) / len(rows)
    nedit = sum(bool(r["edits"]) for r in rows)
    return view(NAME, kd, f, f"steelman from {len(keep)} of {len(rows)} claims, {nedit} repaired, mean strength "
                f"+{gain:.1f} over the whole: {steel[:160]}", steelman=steel, kept=sorted(i + 1 for i in keep),
                repaired=nedit)


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["text"])
    ok["probe text: the Sharpe 3.4 claim is kept and 'obviously' is cut"] = (
        1 in p["stats"]["kept"] and "obviously" not in p["stats"]["steelman"].lower())
    ok["probe text: 'the crowd is always wrong' is softened to 'usually'"] = (
        repair("They say the crowd is always wrong!")[0] == "The crowd is usually wrong.")
    planted = ("Trend following obviously never works. Costs ate 40 bps per trade in the 2019 backtest data, "
               "because turnover was high. Everyone knows it. Momentum crashed 30% in 2009 since shorts squeezed.")
    q = apply(planted)
    ok["planted: the two evidenced claims are kept, 'everyone knows it' is dropped"] = (
        {2, 4} <= set(q["stats"]["kept"]) and 3 not in q["stats"]["kept"])
    ok["planted: the kept overreach reads 'rarely works', not 'never'"] = repair("Trend obviously never works.")[0] == "Trend rarely works."
    ok["strength scores number, cause and source"] = strength("Costs were 5 bps because of data from the log.") == 6
    ok["probe plan: steelman keeps at least 3 steps"] = len(apply(PROBES["plan"])["stats"]["kept"]) >= 3
    for label, bad in (("series", PROBES["series"]), ("one claim", "Only one claim lives here.")):
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
