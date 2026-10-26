"""negative_space - diff a text against a domain checklist to list what is not said (backs negative-space).

Three built-in checklists, each item a set of cue patterns:
  trading  costs, sample size, out-of-sample, drawdown, data source, benchmark, sizing, regime/period,
           multiple testing, paper vs live
  plan     owner, deadline, success measure, rollback, budget, dependencies, verification, done-definition
  code     tests, error handling, rollback, performance, secrets, docs, compatibility, edge cases
The domain is the one whose trigger words occur most (override with domain=). Each checklist item is COVERED (with
the cue that matched) or ABSENT. The absent items are the negative space: the shape of what the text avoids.

    python negative_space.py <file|text> [--opt domain=trading|plan|code] [--json]
    python negative_space.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, report, run_cli, view  # noqa: E402

KINDS = {"text", "plan"}
TRIGGER = {"trading": r"sharpe|backtest|return|strategy|trade|market|price|screener|edge|bps",
           "plan": r"\bstep|plan|will\b|then\b|next|first|deadline|goal",
           "code": r"function|\bdef\b|module|bug|commit|refactor|api|class|script|\.py"}
CHECK = {
    "trading": {"costs": r"cost|fee|slippage|bps|commission|spread", "sample size": r"sample|\bn\s*=|observations|\d+\s*(trades|years|months)",
                "out-of-sample": r"out[- ]of[- ]sample|\boos\b|holdout|walk[- ]forward|forward record|unseen",
                "drawdown": r"drawdown|\bdd\b|worst loss|max loss", "data source": r"\bdata\b|source|feed|vendor",
                "benchmark": r"benchmark|buy[- ]and[- ]hold|baseline|versus|\bvs\b", "sizing": r"size|sizing|leverage|position|kelly",
                "regime/period": r"regime|period|\b(19|20)\d\d\b|bull|bear", "multiple testing": r"tried|variants|selection|deflated|pbo|multiple",
                "paper vs live": r"paper|live|real money"},
    "plan": {"owner": r"\bowner|\bwho\b|assigned|\b(i|max|we) will", "deadline": r"deadline|\bby (monday|tuesday|wednesday|thursday|friday|\d)|tomorrow|next week|\bdate",
             "success measure": r"metric|success|measure|target|kpi|score|pass", "rollback": r"rollback|revert|undo|fallback|\bstop\b",
             "budget": r"cost|budget|hours|minutes|time box", "dependencies": r"depends|requires|blocked|needs|after\b",
             "verification": r"test|check|verify|selftest|review", "done-definition": r"\bdone\b|finished|complete|landed"},
    "code": {"tests": r"test|selftest|assert", "error handling": r"error|exception|raise|try\b|fail",
             "rollback": r"rollback|revert|undo|flag", "performance": r"fast|slow|perf|latency|memory|o\(n", "secrets": r"secret|key|token|password",
             "docs": r"doc|readme|comment", "compatibility": r"compat|version|migration|windows|linux", "edge cases": r"edge|empty|null|none|zero|boundary"},
}


def apply(subject, kind=None, domain=None, **opts) -> dict:
    k, val = load_subject(subject, kind)
    if k not in KINDS:
        raise ValueError(f"negative-space reads text or a plan, not {k}")
    text = "\n".join(val) if k == "plan" else val
    if not text.strip():
        raise ValueError("empty text")
    if domain and domain not in CHECK:
        raise ValueError(f"unknown domain {domain!r}; pick one of {sorted(CHECK)}")
    hits = {d: len(re.findall(rx, text, re.I)) for d, rx in TRIGGER.items()}
    dom = domain or max(hits, key=lambda d: hits[d])
    findings, covered = [], 0
    for item, rx in CHECK[dom].items():
        m = re.search(rx, text, re.I)
        if m:
            covered += 1
            findings.append({"what": f"covered  {item} (cue '{m.group(0)}')", "item": item, "covered": True})
        else:
            findings.append({"what": f"ABSENT   {item} - the text never says", "item": item, "covered": False})
    findings.sort(key=lambda f: f["covered"])
    absent = [f["item"] for f in findings if not f["covered"]]
    return view("negative-space", k, findings, f"{dom} checklist: {len(absent)} of {len(CHECK[dom])} items unsaid "
                f"({', '.join(absent) or 'none'})", domain=dom, absent=absent, triggers=hits)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["text"])
    ok["probe: the screener note reads as a trading claim"] = v["stats"]["domain"] == "trading"
    ok["probe: out-of-sample, drawdown and benchmark are unsaid"] = {"out-of-sample", "drawdown", "benchmark"} <= set(v["stats"]["absent"])
    ok["probe: costs (5 bps) and data source are covered"] = not {"costs", "data source"} & set(v["stats"]["absent"])
    p = apply("Step 1: the user will rebuild the cache by Friday. Then we check that the tests pass.")
    ok["planted plan: rollback and budget are unsaid, owner and deadline covered"] = (
        p["stats"]["domain"] == "plan" and {"rollback", "budget"} <= set(p["stats"]["absent"])
        and not {"owner", "deadline"} & set(p["stats"]["absent"]))
    ok["domain= forces the code checklist"] = apply(PROBES["text"], domain="code")["stats"]["domain"] == "code"
    try:
        apply(PROBES["text"], domain="poetry")
        ok["planted bad input (unknown domain) is refused"] = False
    except ValueError:
        ok["planted bad input (unknown domain) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("negative-space", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
