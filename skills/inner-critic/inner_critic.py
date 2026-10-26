"""inner-critic - the single harshest, specific question for every claim in a text (backs inner-critic).

    python inner_critic.py --selftest
    python inner_critic.py <file|text> [--json]
Each sentence is scanned for weak spots, each with a severity: an absolute word (5), a performance number with no
sample size or period (5), a causal leap (4), an appeal to a crowd or authority (3), a hedge that hides the
mechanism (3), an unsourced number (3), a dated commitment (2), an undefined condition (2). The critic asks ONE
question per claim, aimed at its most severe weak spot and quoting the claim's own words, then ranks the claims.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, numbers_with_units, report, run_cli, sentences, view  # noqa: E402

NAME = "inner-critic"
ABS = re.compile(r"\b(always|never|all|none|every(?:one|thing)?|guaranteed|obviously|certainly|clearly|impossible|nothing)\b", re.I)
PERF = re.compile(r"\b(sharpe|return|win rate|cagr|profit|edge|alpha|accuracy|hit rate)\b", re.I)
SAMPLE = re.compile(r"\b(\d+\s*(?:trades?|bars?|days?|years?|months?|samples?|obs)|n\s*=|out[- ]of[- ]sample|since \d{4}|from \d{4})\b", re.I)
CAUSE = re.compile(r"\b(because|so that|therefore|thus|due to|caused by|which means|hence)\b", re.I)
CROWD = re.compile(r"\b(they say|everyone knows|people say|experts|the crowd|(?:[A-Z]\w+) (?:wants|says|thinks))\b")
HEDGE = re.compile(r"\b(somehow|maybe|probably|perhaps|sort of|kind of|etc\.?|roughly|seems?)\b", re.I)
WHEN = re.compile(r"\b(next (?:week|month|year)|tomorrow|soon|by (?:monday|friday|\w+day)|will)\b", re.I)
COND = re.compile(r"\bif ([^,]{3,60}),", re.I)
SOURCE = re.compile(r"\b(from|per|according to|measured|source|via|cited|https?://)\b", re.I)


def critique(s: str) -> list:
    """[(severity, spot, question)] for one sentence, harshest first."""
    out = []
    nums = numbers_with_units(s)
    p = PERF.search(s)
    if p and nums and not SAMPLE.search(s):
        out.append((5, f"{p.group(1)} with no sample", f"{p.group(1)} of {nums[0][0]:g} over how many trades, in which period, after what costs - and how many variants died before this one?"))
    m = ABS.search(s)
    if m and m.group(1).lower() in ("obviously", "certainly", "clearly"):
        out.append((5, f"certainty '{m.group(1)}'", f"'{m.group(1)}' to whom? Show the evidence - if it were on the page, the word would not be needed."))
    elif m:
        out.append((5, f"absolute '{m.group(1)}'", f"You wrote '{m.group(1)}' - name the one case where it fails, because a single counterexample sinks the whole sentence."))
    c = CAUSE.search(s)
    if c:
        before, after = s[:c.start()].strip(" ,"), s[c.end():].strip(" .,")
        out.append((4, f"causal leap '{c.group(1)}'", f"What else would give '{before[-50:]}' even if '{after[:50]}' were false?"))
    a = CROWD.search(s)
    if a:
        out.append((3, f"appeal to '{a.group(1)}'", f"Who exactly is behind '{a.group(1)}', and what is their record on calls like this?"))
    h = HEDGE.search(s)
    if h:
        out.append((3, f"hedge '{h.group(1)}'", f"'{h.group(1)}' hides the mechanism - what exactly, measured how?"))
    if nums and not SOURCE.search(s) and not (p and not SAMPLE.search(s)):
        v, u, _ = nums[0]
        out.append((3, f"unsourced {v:g}{u}", f"Where does {v:g}{(' ' + u) if u else ''} come from - measured, quoted or guessed, and by whom?"))
    w = WHEN.search(s)
    if w:
        out.append((2, f"commitment '{w.group(1)}'", f"What must be true for '{w.group(1)}' to hold, and what is the plan when it is not?"))
    d = COND.search(s)
    if d:
        out.append((2, "undefined condition", f"What precisely counts as '{d.group(1).strip()}', and who checks it?"))
    return sorted(out, key=lambda t: -t[0])


def apply(subject, kind=None, **opts) -> dict:
    k, text = load_subject(subject, kind or (None if isinstance(subject, (list, tuple)) else "text"))
    if k == "plan":
        text = ". ".join(text)
    elif k != "text":
        raise ValueError(f"{NAME} reads text claims, not {k}")
    sents = sentences(text)
    if not sents:
        raise ValueError(f"{NAME} needs non-empty text")
    f = []
    for i, s in enumerate(sents):
        spots = critique(s)
        sev, spot, q = spots[0] if spots else (1, "no weak spot", "What evidence would make you delete this sentence?")
        f.append({"what": f"[{sev}] \"{s[:60]}\" -> {q}", "severity": sev, "spot": spot, "sentence": i,
                  "other_spots": [t[1] for t in spots[1:]]})
    f.sort(key=lambda d: (-d["severity"], d["sentence"]))
    worst = f[0]
    return view(NAME, "text", f, f"{len(f)} claims critiqued; harshest at severity {worst['severity']} on {worst['spot']}",
                mean_severity=round(sum(d["severity"] for d in f) / len(f), 2), worst_sentence=worst["sentence"])


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["text"], kind="text")
    ok["probe: the launch claim is hit at severity 5 (Sharpe 3.4 with no sample, or 'obviously')"] = (
        p["findings"][0]["sentence"] == 0 and p["findings"][0]["severity"] == 5)
    ok["probe: 'crowd is always wrong' gets the absolute-word question"] = any(
        "crowd" in d["what"] and "'always'" in d["what"] for d in p["findings"])
    ok["one question per claim"] = len(p["findings"]) == len(sentences(PROBES["text"]))
    q = critique("Win rate was 71% because the filter removes chop.")
    ok["planted performance number with no sample is the harshest spot"] = q[0][0] == 5 and "win rate" in q[0][1].lower()
    ok["planted causal leap is also listed"] = any("causal" in t[1] for t in q)
    ok["a sampled, sourced number is not called unsourced"] = not any(
        "unsourced" in t[1] for t in critique("Sharpe was 0.8 over 400 trades since 2015, measured from the cache."))
    try:
        apply([1.0, 2.0])
        ok["planted bad input (series) is refused"] = False
    except ValueError:
        ok["planted bad input (series) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
