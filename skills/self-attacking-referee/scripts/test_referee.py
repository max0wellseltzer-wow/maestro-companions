"""Run: python -m pytest -q .claude/skills/self-attacking-referee/scripts/test_referee.py"""
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import referee as R

N = 120


def iid(rng):
    return [rng.gauss(0, 1) for _ in range(N)]


def ar1(rng, phi=0.6):
    x, out = 0.0, []
    for _ in range(N):
        x = phi * x + rng.gauss(0, 1)
        out.append(x)
    return out


def shifted(rng):
    return [v + 0.4 for v in iid(rng)]


def naive_t(xs):
    """The autopilot judge: one-sample t on the mean, assuming independent draws."""
    return abs(statistics.fmean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs)))) > 1.96


def test_wilson_known_values():
    lo, hi = R.wilson(50, 1000)
    assert abs(lo - 0.0381) < 5e-4 and abs(hi - 0.0653) < 5e-4
    assert R.wilson(0, 10)[0] == 0.0 and R.wilson(10, 10)[1] > 1 - 1e-12


def test_naive_t_is_calibrated_on_iid_and_powered_on_a_real_shift():
    a = R.audit(naive_t, iid, shifted, trials=1500, seed=3)
    assert a.calibration == "CALIBRATED" and a.power_status == "POWERED", a.line()


def test_naive_t_cries_wolf_on_autocorrelated_null():
    a = R.audit(naive_t, ar1, trials=800, seed=4)
    assert a.calibration == "ANTI_CONSERVATIVE" and a.false_alarm_rate > 0.15, a.line()


def test_always_and_never_reject_are_caught():
    assert R.audit(lambda xs: True, iid, trials=200).calibration == "ANTI_CONSERVATIVE"
    deaf = R.audit(lambda xs: False, iid, shifted, trials=200)
    assert (deaf.calibration, deaf.power_status) == ("CONSERVATIVE", "POWERLESS")


def test_power_unmeasured_is_not_zero():
    a = R.audit(naive_t, iid, trials=50)
    assert a.power is None and a.power_status == "POWER_UNMEASURED"


def test_refereed_withholds_an_untrusted_verdict():
    rule = R.refereed(naive_t, ar1, trials=400, seed=5)
    out = rule([5.0] * 60 + [5.1] * 60)
    assert out["judge_said"] is True and out["verdict"] == "JUDGE_UNTRUSTED"


def test_refereed_says_not_testable_when_deaf():
    rule = R.refereed(lambda xs: False, iid, shifted, trials=200)
    assert rule(iid(__import__("random").Random(1)))["verdict"] == "NOT_TESTABLE"


def test_deterministic_by_seed():
    assert R.audit(naive_t, ar1, trials=100, seed=9) == R.audit(naive_t, ar1, trials=100, seed=9)
