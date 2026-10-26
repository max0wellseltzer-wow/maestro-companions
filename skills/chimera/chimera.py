"""chimera - deliberately fuse 3+ parents to find where combination BREAKS (backs the chimera skill).

Reproduction here is the chimera: an organism of several parents' tissues. As a skill it is the RED TEAM of
cross-breed - instead of seeking a vigorous child, it fuses many parents on purpose and reports the fault
lines: invariants that clash (one parent says paper-mode, another says live-mode), and requirements no parent
satisfies. A chimera is "viable" only if nothing conflicts; otherwise it hands you the exact contradictions,
which is the useful output (it tells you which combinations are impossible before you waste time building them).
Pure stdlib.

    from chimera import chimerize
    python chimera.py --selftest   # 6/6; a clashing invariant and an unmet requirement are both surfaced
"""
from __future__ import annotations

import sys


def chimerize(parents: list[dict]) -> dict:
    """parents: each {name, provides:set, requires:set, invariants:{k:v}}. Fuse them and report conflicts
    (invariant clashes) and unmet requirements (something a parent needs that no parent provides). Viable iff
    neither occurs."""
    provides, requires, invariants, conflicts = set(), set(), {}, []
    for p in parents:
        provides |= set(p.get("provides", ()))
        requires |= set(p.get("requires", ()))
        for k, v in p.get("invariants", {}).items():
            if k in invariants and invariants[k] != v:
                conflicts.append({"invariant": k, "values": sorted([invariants[k], v], key=str),
                                  "between": [invariants.get("_src_" + k, "?"), p.get("name", "?")]})
            else:
                invariants[k] = v
                invariants["_src_" + k] = p.get("name", "?")
    unmet = sorted(requires - provides)
    invariants = {k: v for k, v in invariants.items() if not k.startswith("_src_")}
    return {"viable": not conflicts and not unmet, "conflicts": conflicts,
            "unmet_requires": unmet, "provides": sorted(provides), "invariants": invariants}


def _selftest() -> bool:
    ok = {}
    compatible = [
        {"name": "loader", "provides": {"load"}, "requires": set(), "invariants": {"mode": "paper"}},
        {"name": "scorer", "provides": {"score"}, "requires": {"load"}, "invariants": {"mode": "paper"}},
        {"name": "plotter", "provides": {"plot"}, "requires": {"score"}, "invariants": {}},
    ]
    r = chimerize(compatible)
    ok["compatible parents fuse into a viable chimera"] = (r["viable"] is True)
    ok["it aggregates everything provided"] = (r["provides"] == ["load", "plot", "score"])
    # an invariant clash: one parent is paper, another is live
    clash = compatible + [{"name": "executor", "provides": {"order"}, "requires": set(),
                           "invariants": {"mode": "live"}}]
    rc = chimerize(clash)
    ok["a clashing invariant makes it NON-viable"] = (rc["viable"] is False)
    ok["the clash names the invariant (mode)"] = (any(c["invariant"] == "mode" for c in rc["conflicts"]))
    # an unmet requirement: needs 'gpu' nobody provides
    needy = [{"name": "trainer", "provides": {"model"}, "requires": {"gpu"}, "invariants": {}}]
    rn = chimerize(needy)
    ok["an unmet requirement is surfaced"] = (rn["viable"] is False and rn["unmet_requires"] == ["gpu"])
    ok["a lone self-sufficient parent is viable"] = (
        chimerize([{"name": "x", "provides": {"a"}, "requires": {"a"}, "invariants": {}}])["viable"] is True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print("chimera is a library: from chimera import chimerize")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
