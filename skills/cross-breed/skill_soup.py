"""skill_soup - the primordial-soup / viral-soup engine: breed a population of candidate skills from parents.

Reproduction here is abiogenesis in a soup: throw many parent skills together, let every pair cross under
some reproduction operator, name the offspring, and keep the viable/novel ones. This skill USES our other
reproduction skills to do its work - it imports word-sex to NAME each offspring (a portmanteau of the two
parents) and borrows cross-breed's operator table to decide HOW each pair combines. It is the generator
that scales toward hundreds of candidate skills; grading/building them is the separate step.

    from skill_soup import soup
    python skill_soup.py forward calibration harvest signal memory    # breed all pairs -> candidates
    python skill_soup.py --selftest     # 6/6; uses word-sex for naming, culls sterile/dup pairs
"""
from __future__ import annotations

import os
import sys

# Use our OWN word-sex skill to name offspring (reproduction skills breeding reproduction skills).
_WS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "word-sex")
try:
    sys.path.insert(0, _WS)
    from word_sex import breed as _word_breed   # type: ignore
except Exception:
    _word_breed = None

# cross-breed's operator table (the reproduction mode fixes how the two parents combine).
OPERATORS = {
    "crossover": "splices a clause of {a} with a clause of {b}",
    "graft": "grafts {a} as a scion onto {b} as proven rootstock",
    "conjugation": "passes one portable capability from {a} laterally into {b}",
    "reassortment": "swaps a whole module between {a} and {b}",
    "symbiogenesis": "lets {a} absorb {b} permanently as an organelle",
    "meiosis": "halves {a} and {b} to essentials, recombines the cores",
    "pollination": "broadcasts {a}'s discipline across everything {b} touches",
    "heterosis": "fuses {a} and {b}, kept only if the child beats both",
    "mutation": "mutates {a} under {b}'s selection pressure",
}
_OPS = list(OPERATORS)


def name_offspring(a: str, b: str) -> str:
    """Breed a NAME for the child from the two parent names, via the word-sex skill (fallback: a splice)."""
    if _word_breed:
        kids = _word_breed(a, b, 1)
        if kids:
            return kids[0][0]
    return (a[: max(1, len(a) // 2)] + b[len(b) // 2:]).lower()


def soup(parents: list[str], per_pair: int = 1) -> list[dict]:
    """Cross every unordered pair of distinct parents under a rotating operator; name + describe each child.
    Culls self-pairs and duplicate pairs. Returns candidate offspring skills (name/parents/operator/blurb)."""
    out, seen = [], set()
    uniq = [p for i, p in enumerate(parents) if p not in parents[:i]]
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = uniq[i], uniq[j]
            key = frozenset((a, b))
            if a == b or key in seen:
                continue
            seen.add(key)
            op = _OPS[(i + j) % len(_OPS)]
            out.append({"name": name_offspring(a, b), "parents": [a, b], "operator": op,
                        "blurb": OPERATORS[op].format(a=a, b=b)})
    return out


def _selftest() -> bool:
    ok = {}
    parents = ["forward", "calibration", "harvest", "signal", "memory"]
    pop = soup(parents)
    ok["breeds every distinct pair (C(5,2)=10 candidates)"] = (len(pop) == 10)
    ok["no self-pairs, no duplicate pairs"] = (len({frozenset(c["parents"]) for c in pop}) == 10
                                               and all(c["parents"][0] != c["parents"][1] for c in pop))
    ok["every offspring is named and novel (not a bare parent)"] = all(
        c["name"] and c["name"] not in parents for c in pop)
    ok["operators come from the cross-breed table"] = all(c["operator"] in OPERATORS for c in pop)
    ok["deterministic"] = (soup(parents) == pop)
    ok["word-sex was available and used for naming"] = (_word_breed is not None)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    print("  e.g.", ", ".join(f"{c['name']}({c['operator']})" for c in pop[:4]))
    return all(ok.values())


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    for c in soup(argv):
        print(f"{c['name']:18s} = {c['parents'][0]} x {c['parents'][1]} [{c['operator']}] - {c['blurb']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
