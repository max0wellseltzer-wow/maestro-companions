"""falsifier-view - for each claim, the observation that would refute it (backs falsifier-view).

    python falsifier_view.py --selftest
    python falsifier_view.py <file|text> [--json]
Each sentence is typed by its claim forms - universal (always/never/all), numeric (a number), forecast (will, next
week), causal (because/due to), comparative (better/worse than), conditional (if X, Y) - and every form yields its
own refuting observation. A sentence is UNFALSIFIABLE when it has no claim form, is only a preference (wants,
should), or is vague (somehow, etc., kind of) with no number to pin it down.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, numbers_with_units, report, run_cli, sentences, view  # noqa: E402

NAME = "falsifier-view"
VAGUE = re.compile(r"\b(?:somehow|etc|sort of|kind of|in a sense|arguably|somewhat|some(?:thing|how)?|maybe|perhaps)\b", re.I)
PREF = re.compile(r"\b(?:wants?|wish(?:es)?|would like|should|prefers?|hopes?|ought)\b", re.I)
DATE = re.compile(r"\b(?:today|tomorrow|tonight|next (?:week|month|year|session)|by \w+day|on \w+day|in \d+ \w+|"
                  r"\d{4}-\d{2}-\d{2}|this (?:week|month))\b", re.I)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .!?")[:90]


def forms(s: str) -> list:
    """[(form, refuting observation)] for one sentence."""
    out = []
    m = re.search(r"\b(always|never|all|every|none|no one|nobody|everyone)\b", s, re.I)
    if m:
        out.append(("universal", f"one counterexample to '{m.group(1).lower()}' - a single case where it does not hold"))
    nums = numbers_with_units(re.sub(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?|\b[A-Z]\d+\b|#\d+", " ", s))
    if nums:
        v, u, _ = nums[0]
        tol = re.search(r"\b(?:\+/-|plus or minus|within|±)", s)
        out.append(("numeric", f"a fresh measurement of the quantity landing outside {v:g}{u}" +
                    (" plus its stated tolerance" if tol else " (no tolerance stated - name one before measuring)")))
    if re.search(r"\b(?:will|going to|shall|won't)\b", s, re.I):
        d = DATE.search(s)
        out.append(("forecast", f"'{d.group(0)}' passes and it has not happened" if d
                    else "no deadline given - set a date, else time can never refute it"))
    m = re.search(r"\b(because|due to|since|caused by|thanks to|so that|leads? to|led to)\b", s, re.I)
    if m:
        out.append(("causal", f"the effect without the cause after '{m.group(1).lower()}', or the cause present and the effect absent"))
    m = re.search(r"\b(better|worse|faster|slower|more|less|higher|lower|cheaper)\b(\s+than\s+[\w\- ]+)?", s, re.I)
    if m:
        base = _clean(m.group(2) or "")
        out.append(("comparative", f"a side-by-side measure where the order reverses" + (f" ({base})" if base else " (no baseline named)")))
    m = re.match(r"\s*(?:if|when|whenever)\s+([^,]+),\s*(.+)", s, re.I)
    if m:
        out.append(("conditional", f"'{_clean(m.group(1))}' happens and '{_clean(m.group(2))}' does not follow"))
    return out


def apply(subject, kind=None, **opts) -> dict:
    k, text = load_subject(subject, kind or (None if isinstance(subject, (list, tuple)) else "text"))
    if k == "plan":
        text = ". ".join(text)
    elif k != "text":
        raise ValueError(f"{NAME} reads text, not {k}")
    sents = sentences(text)
    if not sents:
        raise ValueError(f"{NAME} needs non-empty text")
    f, bad = [], []
    for i, s in enumerate(sents):
        fs = forms(s)
        vague = bool(VAGUE.search(s)) and not numbers_with_units(s)
        pref = bool(PREF.search(s)) and not fs
        why = "a preference, not a claim" if pref else "no claim form" if not fs else "vague with no number" if vague else ""
        if why:
            bad.append(i)
            f.append({"what": f"s{i} UNFALSIFIABLE ({why}): {_clean(s)}", "sentence": i, "falsifiable": False, "why": why})
            continue
        for form, obs in fs:
            f.append({"what": f"s{i} {form}: refuted by {obs}", "sentence": i, "form": form, "falsifiable": True})
    n = len(sents)
    kinds = sorted({d["form"] for d in f if d.get("form")})
    return view(NAME, "text", f, f"{n - len(bad)}/{n} sentences falsifiable; unfalsifiable s{bad}; forms seen {kinds}",
                unfalsifiable=bad, falsifiable_share=round((n - len(bad)) / n, 3))


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["text"], kind="text")
    s0 = {d["form"] for d in p["findings"] if d.get("sentence") == 0 and d.get("form")}
    ok["probe: sentence 0 is universal, numeric, forecast and causal at once"] = {"universal", "numeric", "forecast", "causal"} <= s0
    ok["probe: 'next week' becomes the refuting date"] = any("'next week' passes" in d["what"] for d in p["findings"])
    ok["probe: 'the user wants it fast' is a preference and 'Somehow ... etc.' is vague"] = (
        1 in p["stats"]["unfalsifiable"] and 5 in p["stats"]["unfalsifiable"])
    q = apply("If the cache is warm, the screener finishes in 4 min. The new model is better than the old one.")
    forms_q = {d.get("form") for d in q["findings"]}
    ok["planted conditional and comparative-with-baseline are typed"] = {"conditional", "comparative", "numeric"} <= forms_q and \
        any("the old one" in d["what"] for d in q["findings"])
    ok["a forecast with no date says time can never refute it"] = any(
        "no deadline" in d["what"] for d in apply("The edge will come back.")["findings"])
    ok["dates and ids (2026-10-07, D157, #41) are not quantities to refute"] = forms("Logged 2026-10-07 under D157 on #41.") == []
    ok["planted pure mood sentence is unfalsifiable"] = apply("Things feel kind of off lately.")["stats"]["unfalsifiable"] == [0]
    try:
        apply(PROBES["series"])
        ok["planted bad input (series) is refused"] = False
    except ValueError:
        ok["planted bad input (series) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
