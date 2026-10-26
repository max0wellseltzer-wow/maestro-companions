"""Run: python -m pytest -q .claude/skills/self-attacking-referee/scripts/test_null_tournament.py"""
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import null_tournament as NT

N = 400


def iid(rng):
    return [rng.gauss(0, 1) for _ in range(N)]


def ar1(rng, phi=0.6):
    x, out = 0.0, []
    for _ in range(N):
        x = phi * x + rng.gauss(0, 1)
        out.append(x)
    return out


def drift(rng):
    return [v + 0.25 for v in iid(rng)]


def _t(xs):
    return abs(statistics.fmean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs))))


def naive_t(xs):
    return _t(xs) > 1.96


def batch_means(xs, k=10):
    """t on k batch means: batches long enough that AR(1) dependence between them is negligible (t_9 crit 2.262)."""
    m = len(xs) // k
    return _t([statistics.fmean(xs[i * m:(i + 1) * m]) for i in range(k)]) > 2.262


JUDGES = {"naive t": naive_t, "batch means": batch_means, "always": lambda xs: True}
WORLDS = {"iid": iid, "ar1 0.6": ar1}


def test_tournament_keeps_the_calibrated_test_and_kills_the_naive_one():
    res = {e.name: e for e in NT.tournament(JUDGES, WORLDS, drift, trials=300, seed=11)}
    assert res["batch means"].survives, NT.table(list(res.values()))
    assert res["naive t"].dies_on() == ["ar1 0.6"]
    assert set(res["always"].dies_on()) == {"iid", "ar1 0.6"}


def test_survivors_rank_first_then_by_power():
    res = NT.tournament(JUDGES, WORLDS, drift, trials=300, seed=11)
    assert res[0].name == "batch means" and [e.survives for e in res] == [True, False, False]


def test_max_rate_is_a_hard_cap_even_when_ci_contains_alpha():
    # a judge rejecting exactly 8% at 50 trials: CI contains 5%, but 0.08 > 0.075 cap
    flips = iter([True] * 4 + [False] * 46)
    res = NT.tournament({"x": lambda xs: next(flips)}, {"iid": iid}, trials=50)
    assert res[0].dies_on() == ["iid"]


def test_table_names_the_world_that_killed_each_test():
    out = NT.table(NT.tournament(JUDGES, WORLDS, trials=120, seed=2))
    assert "DIES on ar1 0.6" in out and "SURVIVES" in out
