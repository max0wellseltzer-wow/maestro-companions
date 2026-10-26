"""Pick an "is it luck?" test by tournament, not by habit. Every candidate test runs on several worlds where the
answer is KNOWN to be "no effect" (iid, autocorrelated, fat-tailed, trending volatility... shaped like your data);
a test survives only if its false-alarm rate is near alpha on EVERY null world. Survivors are ranked by power on a
planted-effect world. Stdlib only; uses the self-attacking-referee engine for each audit.

    from null_tournament import tournament, table
    res = tournament({"naive t": t1, "batch means": t2}, {"iid": w1, "ar1": w2}, alt_world=w3, trials=500)
    print(table(res))

Survival rule (fixed BEFORE the run, never tuned after seeing it): the Wilson 95% interval of the false-alarm
rate must contain alpha or lie below it, AND the rate itself must be <= max_rate (default 1.5 x alpha).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # referee.py sits beside this file
from referee import Audit, Judge, World, audit


@dataclass(frozen=True)
class Entry:
    name: str
    by_world: dict[str, Audit]
    power: float | None
    max_rate: float

    def dies_on(self) -> list[str]:
        return [w for w, a in self.by_world.items()
                if a.calibration == "ANTI_CONSERVATIVE" or a.false_alarm_rate > self.max_rate]

    @property
    def survives(self) -> bool:
        return not self.dies_on()


def tournament(judges: dict[str, Judge], null_worlds: dict[str, World], alt_world: World | None = None, *,
               trials: int = 500, alpha: float = 0.05, max_rate: float | None = None, seed: int = 0) -> list[Entry]:
    """Same seed per world for every judge, so judges are compared on identical fake data (paired)."""
    cap = 1.5 * alpha if max_rate is None else max_rate
    out = []
    for name, judge in judges.items():
        by_world = {w: audit(judge, world, trials=trials, alpha=alpha, seed=seed + i)
                    for i, (w, world) in enumerate(null_worlds.items())}
        power = None if alt_world is None else audit(judge, alt_world, alt_world, trials=trials, alpha=alpha,
                                                     seed=seed + 999).power
        out.append(Entry(name, by_world, power, cap))
    return sorted(out, key=lambda e: (not e.survives, -(e.power or 0.0), e.name))


def table(entries: list[Entry]) -> str:
    worlds = list(entries[0].by_world) if entries else []
    head = f"{'test':<18}" + "".join(f"{w:>12}" for w in worlds) + f"{'power':>8}  verdict"
    rows = [head]
    for e in entries:
        cells = "".join(f"{e.by_world[w].false_alarm_rate:>12.3f}" for w in worlds)
        pw = "n/a" if e.power is None else f"{e.power:.3f}"
        verdict = "SURVIVES" if e.survives else "DIES on " + ", ".join(e.dies_on())
        rows.append(f"{e.name:<18}{cells}{pw:>8}  {verdict}")
    return "\n".join(rows)


def _selftest() -> bool:
    """Hermetic, synthetic worlds only: `python null_tournament.py --selftest` (exit 0 = all pass)."""
    import math
    import random
    import statistics

    n, trials = 100, 400
    seed = random.Random("null_tournament/selftest").randrange(2 ** 31)

    def iid(rng):
        return [rng.gauss(0, 1) for _ in range(n)]

    def fat(rng):                                        # Laplace: fat-tailed, mean zero
        return [rng.expovariate(1) - rng.expovariate(1) for _ in range(n)]

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
    res = tournament({"naive t": naive_t, "always": lambda xs: True, "never": lambda xs: False},
                     {"iid": iid, "fat": fat}, alt_world=shifted, trials=trials, seed=seed)
    by = {e.name: e for e in res}
    t = by["naive t"]
    fa = t.by_world["iid"].false_alarm_rate
    checks[f"pure noise: naive t false alarms near nominal 5% on iid (rate {fa:.3f})"] = 0.02 <= fa <= 0.08
    checks[f"planted effect: naive t detects a 0.4-sd shift (power {t.power:.3f})"] = (t.power or 0) >= 0.9
    checks["naive t survives the iid and fat-tailed null worlds"] = t.survives
    checks["planted bad test: always-reject dies on every null world"] = by["always"].dies_on() == ["iid", "fat"]
    checks["ranking: survivors first, by power (naive t > never > always)"] = [e.name for e in res] == [
        "naive t", "never", "always"]
    ar = tournament({"naive t": naive_t}, {"ar1": ar1}, trials=trials, seed=seed)[0]
    checks[f"planted bad world: naive t dies on autocorrelated noise (rate "
           f"{ar.by_world['ar1'].false_alarm_rate:.3f})"] = ar.dies_on() == ["ar1"] and ar.power is None
    twin = tournament({"a": naive_t, "b": naive_t}, {"iid": iid}, trials=100, seed=seed)
    checks["paired: identical judges get identical audits (same seed per world)"] = (
        twin[0].by_world == twin[1].by_world)
    tab = table(res)
    checks["table: one row per judge with SURVIVES / DIES verdicts"] = (
        len(tab.splitlines()) == 4 and "SURVIVES" in tab and "DIES on iid, fat" in tab)
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    return all(checks.values())


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] == "--selftest":
        sys.exit(0 if _selftest() else 1)
