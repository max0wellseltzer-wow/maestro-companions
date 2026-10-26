"""devils_advocate - argue against every conclusion in a text (backs the devils-advocate skill). VANTAGE lens of the
point-of-view family.

A conclusion is a sentence with a verdict marker (will, should, must, because, so, therefore, better, always, never,
wants, or a number). Each one is classified by its most attackable form - causal, absolute, forecast,
recommendation, comparison, numeric - and gets a COUNTER-CLAIM: the sentence negated (not after its first auxiliary,
always -> not always, better -> worse) plus a counter-reason from that type's template, filled with the claim's own
cause, effect, number or verb. An exposure score (absolute word, no number, no source, single cause, future tense)
ranks which conclusions the advocate should attack first. Heuristic parsing; the counters are arguments to test, not
findings.

    python devils_advocate.py --selftest
    python devils_advocate.py <file|text> [--json]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, numbers_with_units, report, run_cli, sentences, view, words  # noqa: E402

NAME = "devils-advocate"
KINDS = {"text", "plan"}
TYPES = [("causal", r"\b(because|since|therefore|due to|so that|caused)\b"),
         ("absolute", r"\b(always|never|obviously|guaranteed|everyone|nobody|certainly)\b"),
         ("recommendation", r"\b(should|must|need to|have to|we stop|let's)\b"),
         ("forecast", r"\b(will|going to|next (week|month|year)|soon)\b"),
         ("comparison", r"\b(better|worse|more|less|than|beats?)\b"),
         ("numeric", None)]
AUX = r"\b(will|is|was|are|were|should|must|can|has|have|does|did)\b"
FLIP = {"always": "not always", "never": "sometimes", "better": "worse", "worse": "better", "everyone": "not everyone",
        "obviously": "not obviously", "more": "less", "less": "more"}


def negate(s: str) -> str:
    t, n = s.rstrip(".!?"), 0
    for a, b in FLIP.items():
        t, k = re.subn(rf"\b{a}\b", b, t, count=1, flags=re.I)
        n += k
    if not n:
        t, n = re.subn(AUX, lambda m: m.group(0) + " not", t, count=1, flags=re.I)
    return (t if n else "It is not true that " + t[:1].lower() + t[1:]) + "."


def counter(kind: str, s: str) -> str:
    low = s.lower()
    nums = numbers_with_units(s)
    num = f"{nums[0][0]:g}{nums[0][1]}" if nums else "that figure"
    if kind == "causal":
        m = re.split(r"\b(?:because|since|due to|caused)\b", low, maxsplit=1)
        eff, cause = (m[0].strip(" ,"), m[1].strip(" .,")) if len(m) == 2 else (low.split(" so ")[-1], low.split(" so ")[0])
        return f"'{eff[:50]}' could happen without '{cause[:50]}'; a third factor may drive both"
    if kind == "absolute":
        w = re.search(TYPES[1][1], low).group(0)
        return f"one counterexample breaks '{w}'; the claim needs every case, the counter needs one"
    if kind == "recommendation":
        return "acting has a cost the sentence does not price; doing nothing may be cheaper"
    if kind == "forecast":
        return "plans dated 'next' slip more often than not; the base rate of on-time launches is the prior"
    if kind == "comparison":
        return "better on one metric and window can be worse on another; the comparison names neither"
    return f"{num} from one sample is a point, not a distribution; it may not repeat"


def apply(subject, kind=None, **opts) -> dict:
    kd, val = load_subject(subject, kind)
    if kd not in KINDS:
        raise ValueError(f"devils-advocate argues with text, not {kd}")
    out = []
    for i, s in enumerate(val if kd == "plan" else sentences(val)):
        low = s.lower()
        kinds = [k for k, p in TYPES if p and re.search(p, low)] + (["numeric"] if numbers_with_units(s) else [])
        if not kinds or len(words(s)) < 3:
            continue
        exp = (bool(re.search(TYPES[1][1], low)) + (not numbers_with_units(s)) + (not re.search(r"\b(data|log|test|source|measured|from)\b", low))
               + bool(re.search(TYPES[0][1], low) and " and " not in low) + bool(re.search(TYPES[3][1], low)))
        out.append({"what": f"[{kinds[0]}, exposure {exp}/5] s{i + 1}: COUNTER {negate(s)[:80]} - {counter(kinds[0], s)}",
                    "sentence": i + 1, "type": kinds[0], "exposure": exp})
    if not out:
        raise ValueError("no conclusion found to argue against")
    out.sort(key=lambda x: (-x["exposure"], x["sentence"]))
    return view(NAME, kd, out, f"{len(out)} conclusions argued against; attack s{out[0]['sentence']} first "
                f"({out[0]['type']}, exposure {out[0]['exposure']}/5)", counters=len(out),
                types=sorted({x["type"] for x in out}))


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["text"])
    ok["probe text: the launch claim is argued as causal, the crowd claim as absolute"] = (
        any(x["sentence"] == 1 and x["type"] == "causal" for x in p["findings"])
        and any(x["type"] == "absolute" for x in p["findings"]))
    ok["negate: auxiliary gets 'not', always -> not always"] = (
        negate("We will launch next week.") == "We will not launch next week."
        and negate("The crowd is always wrong!") == "The crowd is not always wrong.")
    c = counter("causal", "Returns rose because volume spiked.")
    ok["planted causal: the counter names the claim's own cause and effect"] = "returns rose" in c and "volume spiked" in c
    q = apply("Returns rose 4% last month. Everyone will obviously copy us next week.")
    ok["planted: the absolute forecast is the most exposed and attacked first"] = (
        q["findings"][0]["sentence"] == 2 and q["findings"][0]["exposure"] >= 3)
    ok["planted numeric: a lone number gets the one-sample counter"] = "4%" in counter("numeric", "Returns rose 4% last month.")
    ok["a sentence with no verdict marker is not argued"] = len(apply("The cat sat. We should stop the job now.")["findings"]) == 1
    for label, bad in (("series", PROBES["series"]), ("no conclusion", "The sky. A tree. Some grass here.")):
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
