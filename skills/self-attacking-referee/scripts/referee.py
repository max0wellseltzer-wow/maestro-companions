"""A judge that attacks itself before it is allowed to rule. Stdlib only, deterministic by seed.

A judge is any function sample -> bool (True = "reject the null": an edge, a difference, a failure found).
Before its verdict on the real sample counts, the referee measures, on fake worlds shaped like the real case:
  false alarms  how often it rejects on worlds where the null is TRUE (should be about alpha)
  power         how often it rejects on a world with a planted effect of the size you care about
and reports both, with Wilson 95% intervals, beside the verdict. A judge whose false alarms are clearly above
alpha does not get to rule: the verdict becomes the named status JUDGE_UNTRUSTED (L0: a status, never a guess).

    from referee import audit, refereed
    a = audit(judge, null_world, alt_world, trials=1000, alpha=0.05, seed=1)
    print(a.line())
    ruling = refereed(judge, null_world, alt_world)(real_sample)
"""
from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Judge = Callable[[Sequence[float]], bool]
World = Callable[[random.Random], Sequence[float]]
Z95 = 1.959963984540054


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial rate; honest at 0 and n, unlike p +- z*se."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class Audit:
    trials: int
    alpha: float
    false_alarms: int
    power_hits: int | None          # None when no alt world was given: power UNMEASURED, not zero

    @property
    def false_alarm_rate(self) -> float:
        return self.false_alarms / self.trials

    @property
    def false_alarm_ci(self) -> tuple[float, float]:
        return wilson(self.false_alarms, self.trials)

    @property
    def power(self) -> float | None:
        return None if self.power_hits is None else self.power_hits / self.trials

    @property
    def calibration(self) -> str:
        lo, hi = self.false_alarm_ci
        if lo > self.alpha:
            return "ANTI_CONSERVATIVE"      # cries wolf: its "significant" means little
        if hi < self.alpha:
            return "CONSERVATIVE"           # safe but deaf; check power
        return "CALIBRATED"

    @property
    def power_status(self) -> str:
        if self.power_hits is None:
            return "POWER_UNMEASURED"
        lo, hi = wilson(self.power_hits, self.trials)
        return "POWERED" if lo >= 0.8 else "UNDERPOWERED" if hi >= 0.2 else "POWERLESS"

    def line(self) -> str:
        lo, hi = self.false_alarm_ci
        pw = "n/a" if self.power is None else f"{self.power:.3f}"
        return (f"false alarms {self.false_alarm_rate:.3f} [{lo:.3f}, {hi:.3f}] vs alpha {self.alpha} -> "
                f"{self.calibration}; power {pw} -> {self.power_status}; {self.trials} trials")


def audit(judge: Judge, null_world: World, alt_world: World | None = None, *, trials: int = 1000,
          alpha: float = 0.05, seed: int = 0) -> Audit:
    rng = random.Random(seed)
    fa = sum(bool(judge(null_world(rng))) for _ in range(trials))
    pw = None if alt_world is None else sum(bool(judge(alt_world(rng))) for _ in range(trials))
    return Audit(trials, alpha, fa, pw)


def refereed(judge: Judge, null_world: World, alt_world: World | None = None, **kw) -> Callable[[Sequence[float]], dict]:
    """Wrap a judge: the audit runs once, then every ruling carries it. An ANTI_CONSERVATIVE judge's verdict is
    withheld (JUDGE_UNTRUSTED); a POWERLESS judge's 'no effect' is reported as NOT_TESTABLE, not as absence."""
    a = audit(judge, null_world, alt_world, **kw)

    def rule(sample: Sequence[float]) -> dict:
        rejected = bool(judge(sample))
        if a.calibration == "ANTI_CONSERVATIVE":
            verdict = "JUDGE_UNTRUSTED"
        elif not rejected and a.power_status == "POWERLESS":
            verdict = "NOT_TESTABLE"
        else:
            verdict = "REJECT" if rejected else "NO_REJECT"
        return {"verdict": verdict, "judge_said": rejected, "audit": a.line(),
                "calibration": a.calibration, "power_status": a.power_status}

    return rule


def _selftest() -> bool:
    """Hermetic, synthetic worlds only: `python referee.py --selftest` (exit 0 = all pass)."""
    import statistics

    n, trials = 100, 600
    seed = random.Random("referee/selftest").randrange(2 ** 31)

    def iid(rng):
        return [rng.gauss(0, 1) for _ in range(n)]

    def ar1(rng, phi=0.6):
        x, out = 0.0, []
        for _ in range(n):
            x = phi * x + rng.gauss(0, 1)
            out.append(x)
        return out

    def shifted(rng):
        return [v + 0.4 for v in iid(rng)]

    def naive_t(xs):
        return abs(statistics.fmean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs)))) > 1.96

    checks: dict[str, bool] = {}
    lo, hi = wilson(50, 1000)
    checks["wilson: 50/1000 -> [0.0381, 0.0653]; honest at 0 and n; n=0 -> [0, 1]"] = (
        abs(lo - 0.0381) < 5e-4 and abs(hi - 0.0653) < 5e-4 and wilson(0, 10)[0] == 0.0
        and wilson(10, 10)[1] > 1 - 1e-12 and wilson(0, 0) == (0.0, 1.0))
    a = audit(naive_t, iid, shifted, trials=trials, seed=seed)
    checks[f"pure noise: naive t NOT called significant beyond ~5% ({a.line()})"] = (
        a.calibration == "CALIBRATED" and 0.02 <= a.false_alarm_rate <= 0.08)
    checks["planted 0.4-sd effect: detected, POWERED"] = a.power_status == "POWERED" and (a.power or 0) >= 0.9
    bad = audit(naive_t, ar1, trials=trials, seed=seed)
    checks[f"planted bad case: naive t on autocorrelated noise is ANTI_CONSERVATIVE "
           f"(rate {bad.false_alarm_rate:.3f})"] = bad.calibration == "ANTI_CONSERVATIVE" and bad.false_alarm_rate > 0.15
    deaf = audit(lambda xs: False, iid, shifted, trials=200, seed=seed)
    checks["always-reject cries wolf; never-reject is CONSERVATIVE and POWERLESS"] = (
        audit(lambda xs: True, iid, trials=200, seed=seed).calibration == "ANTI_CONSERVATIVE"
        and (deaf.calibration, deaf.power_status) == ("CONSERVATIVE", "POWERLESS"))
    un = audit(naive_t, iid, trials=50, seed=seed)
    checks["no alt world: power is UNMEASURED, not zero"] = un.power is None and un.power_status == "POWER_UNMEASURED"
    rng = random.Random("referee/selftest/samples")
    untrusted = refereed(naive_t, ar1, trials=300, seed=seed)([5.0] * 50 + [5.1] * 50)
    good = refereed(naive_t, iid, shifted, trials=300, seed=seed)
    checks["refereed: untrusted judge withheld, deaf judge NOT_TESTABLE, good judge rules REJECT on a real shift"] = (
        untrusted["verdict"] == "JUDGE_UNTRUSTED" and untrusted["judge_said"] is True
        and refereed(lambda xs: False, iid, shifted, trials=200, seed=seed)(iid(rng))["verdict"] == "NOT_TESTABLE"
        and good([v + 1.0 for v in iid(rng)])["verdict"] == "REJECT")
    checks["deterministic by seed"] = (audit(naive_t, ar1, trials=100, seed=seed)
                                       == audit(naive_t, ar1, trials=100, seed=seed))
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    return all(checks.values())


if __name__ == "__main__":
    import sys
    if sys.argv[1:] and sys.argv[1] == "--selftest":
        sys.exit(0 if _selftest() else 1)
