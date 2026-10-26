"""beginners_eye - read a text as a newcomer: grade each sentence (Flesch-Kincaid from a vowel-group syllable count),
flag those above a reading level, and build the glossary a beginner would need - acronyms, CamelCase names, coded ids,
domain jargon and four-plus-syllable words - in order of first use, marking which ones the text defines on the spot
(backs the beginners-eye skill). The syllable counter and jargon list are heuristics.

    python beginners_eye.py <file|text> [--opt grade=10] [--json]
    python beginners_eye.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, sentences, view, words  # noqa: E402

KINDS = {"text"}
JARGON = set("""sharpe sortino backtest bps drawdown screener cache nightly repo branch commit merge api json cli regime
volatility vol beta alpha kelly ewma garch hurst lookahead slippage spread turnover liquidity arbitrage carry momentum
reversion calibration ohlc bar bars ticker etf crypto submodule hook lint selftest stdlib regex yaml frontmatter
scheduler cron pipeline schema heuristic bootstrap overfit holdout walk-forward drift skew kurtosis quantile decile
percentile median variance covariance correlation sigma""".split())
DEFINE = re.compile(r"\s*(\(|,\s*(?:a|an|the|i\.e\.|which is|meaning)\b|\s+(?:is|are|means)\s+(?:a|an|the|when|how)\b|\s+-\s)",
                    re.I)


def syllables(w: str) -> int:
    w = w.lower().strip("'")
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def grade(s: str) -> float:
    ws = words(s)
    if not ws:
        return 0.0
    return 0.39 * len(ws) + 11.8 * sum(syllables(w) for w in ws) / len(ws) - 15.59


def jargon_kind(raw: str):
    w = raw.lower()
    if re.fullmatch(r"[A-Z]{2,}s?", raw):
        return "acronym"
    if re.search(r"[a-z][A-Z]", raw):
        return "CamelCase name"
    if re.search(r"\d", raw) and re.search(r"[A-Za-z]", raw):
        return "coded id"
    if w in JARGON:
        return "domain jargon"
    if syllables(w) >= 4 and w not in STOP:
        return "long word"
    return None


def apply(subject, kind=None, grade=10, **opts) -> dict:
    kind, text = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"beginners-eye reads text, not {kind}")
    sents = sentences(text)
    if not sents:
        raise ValueError("empty text")
    level = float(grade)
    f, seen = [], {}
    grades = [_g(s) for s in sents]
    for i, (s, g) in enumerate(zip(sents, grades), 1):
        if g > level:
            f.append({"what": f"GRADE {g:.1f} > {level:g} in s{i}: {s[:90]}", "type": "hard", "grade": round(g, 1)})
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-']*", s):
            raw = m.group(0)
            jk = jargon_kind(raw)
            if jk and raw.lower() not in seen:
                defined = bool(DEFINE.match(s[m.end():]))
                seen[raw.lower()] = defined
                f.append({"what": f"TERM '{raw}' ({jk}) first used in s{i} - "
                                  + ("defined on the spot" if defined else "NOT defined"),
                          "type": "term", "term": raw, "class": jk, "defined": defined})
    undefined = [t for t, d in seen.items() if not d]
    avg = sum(grades) / len(grades)
    summary = (f"mean grade {avg:.1f}; {sum(g > level for g in grades)}/{len(sents)} sentences above grade {level:g}; "
               f"{len(undefined)} term(s) a newcomer needs defined: {', '.join(undefined[:8])}")
    return view("beginners-eye", kind, f, summary, mean_grade=round(avg, 2), hard=sum(g > level for g in grades),
                undefined=undefined)


_g = grade


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["text"])
    terms = {x["term"].lower(): x for x in v["findings"] if x["type"] == "term"}
    ok["probe text: Sharpe, backtest and bps need defining"] = {"sharpe", "backtest", "bps"} <= set(v["stats"]["undefined"])
    ok["probe text: TradingView is a CamelCase name"] = terms["tradingview"]["class"] == "CamelCase name"
    low = apply(PROBES["text"], grade=6)
    ok["probe text: at grade 6 the long s1 and the TradingView s3 are too hard, nothing else"] = [
        x["what"].split(" in ")[1][:3] for x in low["findings"] if x["type"] == "hard"] == ["s1:", "s3:"]
    d = apply("The drawdown (the drop from a peak) was big.")
    ok["planted parenthetical definition counts as defined"] = d["stats"]["undefined"] == []
    ok["syllables: 'volatility' 5, 'cache' 1, 'make' 1"] = (syllables("volatility"), syllables("cache"),
                                                            syllables("make")) == (5, 1, 1)
    easy = apply("The cat sat. The dog ran.")
    ok["planted easy text: no hard sentences, no terms"] = easy["stats"]["hard"] == 0 and easy["stats"]["undefined"] == []
    ok["acronym and coded id detected"] = jargon_kind("ETF") == "acronym" and jargon_kind("D71") == "coded id"
    try:
        apply(PROBES["series"])
        ok["planted bad input (a series) is refused"] = False
    except ValueError:
        ok["planted bad input (a series) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("beginners-eye", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
