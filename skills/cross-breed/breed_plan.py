"""breed_plan - pick the reproduction operator for two parents, then judge the child's vigor (backs cross-breed).

The cross-breed method as two functions. `choose_operator(kind, mode)` maps what the parents ARE (words,
phrases, numbers, signals, modules, skills...) and the mode you want (broad pollination vs 1-to-1 sex) to the
operators that fit, and names the sibling tool that implements each where one exists. `vigor(a, b, child)`
then judges the offspring on any higher-is-better score: KEEP (hybrid vigor - beats both parents), STERILE
(between the parents - no gain), or DEPRESSION (worse than both - outbreeding depression, cull it).

    from breed_plan import choose_operator, vigor
    choose_operator("signals", "1:1")   # -> [{"operator": "heterosis", "tool": "signal-fusion"}, ...]
    vigor(0.10, 0.12, 0.15)             # -> "KEEP (hybrid vigor)"
    python breed_plan.py --selftest
"""
from __future__ import annotations

import sys

TABLE = {
    "words":    {"1:1": [("crossover", "word-sex")]},
    "phrases":  {"1:1": [("crossover", "word-sex")]},
    "numbers":  {"1:1": [("mediant / means", "word-sex")]},
    "signals":  {"1:1": [("heterosis", "signal-fusion"), ("reassortment", "reassort")],
                 "broad": [("polyploidy", "polyploid"), ("quorum", "quorum-sense")]},
    "modules":  {"1:1": [("reassortment", "reassort"), ("graft", "graft"), ("symbiogenesis", None)],
                 "broad": [("viral spread", "safe-bulk-edit")]},
    "skills":   {"1:1": [("graft", "graft"), ("meiosis", None)],
                 "broad": [("pollination", None), ("primordial soup", "cross-breed")]},
    "capabilities": {"1:1": [("conjugation", "horizontal-transfer"), ("horizontal transfer", "horizontal-transfer")]},
}


def choose_operator(kind: str, mode: str = "1:1") -> list:
    """Operators that fit parents of `kind` in `mode` ('1:1' or 'broad'), each with its implementing tool."""
    if kind not in TABLE:
        raise ValueError(f"unknown parent kind '{kind}'; known: {sorted(TABLE)}")
    return [{"operator": op, "tool": tool} for op, tool in TABLE[kind].get(mode, [])]


def vigor(a: float, b: float, child: float, eps: float = 1e-12) -> str:
    """Judge an offspring by a higher-is-better score against its two parents."""
    if child > max(a, b) + eps:
        return "KEEP (hybrid vigor)"
    if child < min(a, b) - eps:
        return "DEPRESSION (worse than both parents - cull)"
    return "STERILE (no gain over the better parent)"


def _selftest() -> bool:
    ok = {}
    ok["numbers map to the mediant/means operator (word-sex)"] = (
        choose_operator("numbers")[0]["tool"] == "word-sex")
    ok["signals 1:1 map to heterosis (signal-fusion)"] = (choose_operator("signals")[0]["operator"] == "heterosis")
    ok["broad mode returns broad operators"] = ("polyploidy" in [o["operator"] for o in choose_operator("signals", "broad")])
    bad = False
    try:
        choose_operator("feelings")
    except ValueError:
        bad = True
    ok["an unknown parent kind is rejected"] = bad
    ok["a child beating both parents is KEEP"] = vigor(0.10, 0.12, 0.15).startswith("KEEP")
    ok["a child between its parents is STERILE"] = vigor(0.10, 0.12, 0.11).startswith("STERILE")
    ok["a child worse than both is DEPRESSION"] = vigor(0.10, 0.12, 0.05).startswith("DEPRESSION")
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
