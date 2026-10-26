"""repro - which way to generate candidates: clone, cross, broadcast or refine? (backs the reproductive-strategy skill)

Seed: sex vs cross-pollination x generate-then-cull x egg laying. Four reproductive strategies compete on a
fitness landscape whose optimum MOVES at a given rate, under the same per-generation budget:

  clone  (asexual)  best + small mutation;               cost 1 per candidate
  sex    (sexual)   uniform crossover of two parents from a
                    carried population + small mutation;  cost 2 per candidate (the two-fold cost of sex:
                                                          Maynard Smith 1978 - only half the parents bear young)
  r      (r-select) many cheap, careless, large variants; cost 1/4 per candidate, defect rate x2
  K      (K-select) few careful, fine refinements;        cost 4 per candidate, defect rate x1/4

A defective candidate is born dead (wasted budget). Each generation keeps the best living individual (elitism)
and is scored by its distance to the CURRENT optimum - tracking lag. Theory being tested: on a static
landscape precision wins (clone / K); on a fast-moving one, exploration and variation win (sex / r) - the Red
Queen hypothesis for sex (Van Valen 1973; Bell 1982) and r/K selection (MacArthur & Wilson 1967; Pianka 1970).

    from repro import Setting, run, compare, regime_map
    compare(Setting(change_rate=0.3, defect_rate=0.1, budget=32))   # -> winner + score per strategy
    regime_map(change_rates=[0, 0.05, 0.2, 0.5], defect_rates=[0, 0.3])
    python repro.py --selftest
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import asdict, dataclass

STRATEGIES = ("clone", "sex", "r", "K")
COST = {"clone": 1.0, "sex": 2.0, "r": 0.25, "K": 4.0}
DEFECT_MULT = {"clone": 1.0, "sex": 1.0, "r": 2.0, "K": 0.25}
STEP_MULT = {"clone": 1.0, "sex": 1.0, "r": 4.0, "K": 0.5}


@dataclass(frozen=True)
class Setting:
    change_rate: float = 0.0     # distance the optimum moves per generation
    defect_rate: float = 0.0     # base chance a new candidate is born broken
    budget: float = 32.0         # cost units per generation (clone makes `budget` candidates)
    sigma: float = 0.05          # base mutation step per dimension
    dims: int = 8
    mutated_genes: float = 0.0   # expected genes mutated per birth; 0 = every gene (sparse = Fisher-Muller setting)
    generations: int = 60
    burn_in: int = 20            # generations ignored when scoring
    turn: float = 0.2            # how fast the optimum's heading wanders (radians-ish per generation)
    seed: int = 0

    def validate(self):
        if self.change_rate < 0 or self.sigma <= 0 or self.budget < COST["K"]:
            raise ValueError("need change_rate >= 0, sigma > 0 and budget >= 4 (one K candidate)")
        if not 0.0 <= self.defect_rate < 0.5:
            raise ValueError("defect_rate must be in [0, 0.5) (r doubles it)")
        if self.dims < 1 or self.generations <= self.burn_in or self.burn_in < 0:
            raise ValueError("need dims >= 1 and generations > burn_in >= 0")


def _optimum_path(st: Setting):
    rng = random.Random(f"repro/path/{st.seed}")
    theta = [rng.gauss(0, 1.0 / math.sqrt(st.dims)) for _ in range(st.dims)]
    head = [rng.gauss(0, 1) for _ in range(st.dims)]
    path = []
    for _ in range(st.generations):
        path.append(list(theta))
        head = [h + st.turn * rng.gauss(0, 1) for h in head]
        n = math.sqrt(sum(h * h for h in head)) or 1.0
        theta = [t + st.change_rate * h / n for t, h in zip(theta, head)]
    return path


def _dist(x, t):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(x, t)))


def run(strategy: str, st: Setting) -> dict:
    """One strategy on the setting's landscape. Score = -mean distance of the carried best to the moving
    optimum after burn-in (higher is better)."""
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    st.validate()
    path = _optimum_path(st)
    rng = random.Random(f"repro/{strategy}/{st.seed}")
    n = int(st.budget // COST[strategy])
    p_def = st.defect_rate * DEFECT_MULT[strategy]
    step = st.sigma * STEP_MULT[strategy]
    pm = min(1.0, st.mutated_genes / st.dims) if st.mutated_genes > 0 else 1.0
    best = [0.0] * st.dims
    pool = [list(best) for _ in range(8)]                     # sex carries a small breeding population
    trace, born, dead = [], 0, 0
    for theta in path:
        kids = []
        for _ in range(n):
            born += 1
            if rng.random() < p_def:
                dead += 1
                continue
            if strategy == "sex":
                a, b = rng.sample(pool, 2)
                base = [x if rng.random() < 0.5 else y for x, y in zip(a, b)]
            else:
                base = best
            kids.append([x + rng.gauss(0, step) if rng.random() < pm else x for x in base])
        ranked = sorted(kids + [best] + (pool if strategy == "sex" else []), key=lambda x: _dist(x, theta))
        best = ranked[0]
        if strategy == "sex":
            pool = [list(x) for x in ranked[:8]]
        trace.append(_dist(best, theta))
    tail = trace[st.burn_in:]
    return {"strategy": strategy, "score": -sum(tail) / len(tail), "trace": trace, "candidates_per_gen": n,
            "born": born, "dead": dead}


def compare(st: Setting) -> dict:
    res = {s: run(s, st) for s in STRATEGIES}
    order = sorted(STRATEGIES, key=lambda s: -res[s]["score"])
    return {"winner": order[0], "ranking": order, "scores": {s: res[s]["score"] for s in STRATEGIES},
            "candidates_per_gen": {s: res[s]["candidates_per_gen"] for s in STRATEGIES},
            "setting": asdict(st)}


def regime_map(change_rates=(0.0, 0.02, 0.1, 0.3, 0.6), defect_rates=(0.0, 0.2, 0.4), **kw) -> dict:
    """Winner for every (change_rate, defect_rate) cell."""
    grid = {}
    for c in change_rates:
        for d in defect_rates:
            grid[(c, d)] = compare(Setting(change_rate=c, defect_rate=d, **kw))["winner"]
    return {"change_rates": list(change_rates), "defect_rates": list(defect_rates), "winners": grid}


def format_map(m) -> str:
    lines = ["change\\defect " + " ".join(f"{d:>6}" for d in m["defect_rates"])]
    for c in m["change_rates"]:
        lines.append(f"{c:>13} " + " ".join(f"{m['winners'][(c, d)]:>6}" for d in m["defect_rates"]))
    return "\n".join(lines)


def _selftest() -> bool:
    ok = {}
    rng = random.Random("repro/selftest")
    seed = rng.randrange(10**6)
    static = compare(Setting(change_rate=0.0, seed=seed))
    fast = compare(Setting(change_rate=0.4, seed=seed))
    fmt = lambda c: ", ".join(f"{s} {c['scores'][s]:+.3f}" for s in c["ranking"])
    print(f"  static landscape: {fmt(static)}")
    print(f"  fast landscape (0.4/gen): {fmt(fast)}")
    ok["static landscape favours cloning / K (precision)"] = static["winner"] in ("clone", "K")
    ok["fast-moving landscape favours sex / r (Red Queen)"] = fast["winner"] in ("sex", "r")
    ok["the cost of exploration flips sign: r is last on the static landscape and first on the fast one"] = (
        static["ranking"][-1] == "r" and fast["ranking"][0] == "r")
    ok["two-fold cost of sex: half as many candidates as cloning on the same budget"] = (
        static["candidates_per_gen"]["sex"] * 2 == static["candidates_per_gen"]["clone"])
    again = compare(Setting(change_rate=0.4, seed=seed))
    ok["deterministic with seed"] = again["scores"] == fast["scores"]
    m = regime_map(change_rates=(0.0, 0.4), defect_rates=(0.0, 0.3), seed=seed)
    print("  regime map:\n    " + format_map(m).replace("\n", "\n    "))
    ok["regime map: the static column never picks sex/r, the fast column never picks clone/K"] = (
        all(m["winners"][(0.0, d)] in ("clone", "K") for d in m["defect_rates"])
        and all(m["winners"][(0.4, d)] in ("sex", "r") for d in m["defect_rates"]))
    try:
        compare(Setting(defect_rate=0.7))
        ok["planted bad input (defect_rate 0.7) is rejected"] = False
    except ValueError:
        ok["planted bad input (defect_rate 0.7) is rejected"] = True
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "compare":
        kw = dict(a.split("=", 1) for a in argv[1:])
        st = Setting(**{k: (int(v) if k in ("dims", "generations", "burn_in", "seed") else float(v))
                        for k, v in kw.items()})
        c = compare(st)
        print("winner:", c["winner"])
        for s in c["ranking"]:
            print(f"  {s:>5}  score {c['scores'][s]:+.4f}  candidates/gen {c['candidates_per_gen'][s]}")
        return 0
    if argv[0] == "map":
        print(format_map(regime_map()))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
