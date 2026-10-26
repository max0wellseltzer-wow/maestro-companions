"""force - does a "free choice" procedure pick the same option on pure noise? (a magician's force)

A selection procedure (pick the best lookback / parameter / model / universe) should, on data with NO signal,
pick each of its k options about 1/k of the time. If one option wins far more often on noise, the procedure is
forcing it - by variance (fewer trades = wilder Sharpe), by edge effects, by tie-breaking - and a real-data win
for that option is weak evidence. The tool runs the procedure on R seeded null datasets and reports each
option's pick share with a Wilson 95% interval, the chi-square test against uniform, the normalised entropy of
the picks, and FORCED options (Wilson lower bound above 1/k) or FAIR.

    procedure file:  def choose(data) -> str          (returns the chosen option's label)
    null file:       def null(rng: random.Random)     (returns one no-signal dataset)
    python force.py proc.py:choose --null nullgen.py:null --options 5,20,100 [--reps 500] [--seed 1]
    python force.py --selftest
Exit 0 FAIR, 3 FORCED.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import random
import sys
from collections import Counter


def _gammq(a: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(a, x)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-15:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - gln)
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_sf(x: float, df: int) -> float:
    return _gammq(df / 2.0, x / 2.0)


def wilson(k: int, n: int, z: float = 1.959964) -> tuple:
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def force_test(choose, null, options: list, reps: int = 500, seed: int = 1, alpha: float = 0.05) -> dict:
    rng = random.Random(seed)
    picks = Counter(str(choose(null(rng))) for _ in range(reps))
    unknown = [o for o in picks if o not in options]
    if unknown:
        raise ValueError(f"procedure returned options not in --options: {unknown}")
    k = len(options)
    exp = reps / k
    chi = sum((picks.get(o, 0) - exp) ** 2 / exp for o in options)
    p = chi2_sf(chi, k - 1)
    H = -sum((c / reps) * math.log(c / reps) for c in picks.values() if c)
    rows = []
    for o in options:
        c = picks.get(o, 0)
        lo, hi = wilson(c, reps)
        rows.append({"option": o, "picks": c, "share": c / reps, "lo": lo, "hi": hi, "forced": lo > 1 / k})
    forced = [r["option"] for r in rows if r["forced"]]
    return {"rows": rows, "chi2": chi, "p": p, "entropy": H / math.log(k) if k > 1 else 1.0, "reps": reps,
            "verdict": "FORCED" if forced and p < alpha else "FAIR", "forced": forced}


def render(res: dict) -> str:
    k = len(res["rows"])
    out = [f"{'option':<14} {'picks':>6} {'share':>7}  Wilson95          (fair share {1 / k:.3f})"]
    for r in res["rows"]:
        out.append(f"{r['option']:<14} {r['picks']:>6} {r['share']:>7.3f}  [{r['lo']:.3f}, {r['hi']:.3f}]"
                   + ("  FORCED" if r["forced"] else ""))
    out.append(f"chi2 {res['chi2']:.2f} (df {k - 1}) p {res['p']:.3g}; normalised pick entropy {res['entropy']:.3f}")
    out.append(f"VERDICT: {res['verdict']}" + (f" - on pure noise the procedure picks {', '.join(res['forced'])}"
                                                if res["verdict"] == "FORCED" else ""))
    return "\n".join(out)


def _load(spec: str):
    path, _, func = spec.rpartition(":")
    s = importlib.util.spec_from_file_location(f"_force_{abs(hash(path))}", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return getattr(m, func)


def _selftest() -> int:
    ok = []

    def ck(c, what):
        ok.append(bool(c))
        print(("PASS " if c else "FAIL ") + what)

    ck(abs(chi2_sf(3.841459, 1) - 0.05) < 1e-5 and abs(chi2_sf(5.991465, 2) - 0.05) < 1e-5,
       "chi-square tail matches the table (3.84 df1, 5.99 df2 -> 0.05)")
    ck(abs(chi2_sf(43.773, 30) - 0.05) < 1e-4 and abs(chi2_sf(10.0, 2) - math.exp(-5)) < 1e-12,
       "chi-square tail in the continued-fraction branch (43.77 df 30 -> 0.05; df 2 is exp(-x/2))")
    ck(abs(chi2_sf(1.0, 4) - math.exp(-0.5) * 1.5) < 1e-12, "series branch: df 4 tail is exp(-x/2)(1+x/2)")
    seq = iter(["a"] * 60 + ["b"] * 30 + ["c"] * 10)
    r = force_test(lambda d: next(seq), lambda rng: None, ["a", "b", "c"], reps=100)
    ck(abs(r["chi2"] - 38.0) < 1e-9, f"chi-square of counts 60/30/10 is 38.0 (got {r['chi2']:.4f})")
    opts = ["n10", "n100", "n1000"]
    sizes = {"n10": 10, "n100": 100, "n1000": 1000}

    def null(rng):
        return {o: [rng.gauss(0, 1) for _ in range(n)] for o, n in sizes.items()}

    def best_mean(d):                       # 'pick the option with the best average' - a forced choice
        return max(d, key=lambda o: sum(d[o]) / len(d[o]))

    r = force_test(best_mean, null, opts, reps=300)
    ck(r["verdict"] == "FORCED" and r["forced"] == ["n10"], f"best raw mean on noise forces the 10-sample option ({r['rows'][0]['share']:.2f})")

    def best_t(d):                          # standardised: every option's statistic has the same null law
        return max(d, key=lambda o: sum(d[o]) / math.sqrt(len(d[o])))

    r = force_test(best_t, null, opts, reps=300)
    ck(r["verdict"] == "FAIR" and r["forced"] == [],
       f"best t-stat (same null law per option) is FAIR with no option flagged (p {r['p']:.2f}, shares "
       + "/".join(f"{x['share']:.2f}" for x in r["rows"]) + ")")

    def first_on_tie(d):                    # ties broken by list order on a coarse statistic
        s = {o: round(sum(d[o][:5]) / 5) for o in d}
        return max(opts, key=lambda o: s[o])

    r = force_test(first_on_tie, null, opts, reps=300)
    ck("n10" in r["forced"], "tie-breaking by list order forces the first option")
    try:
        force_test(lambda d: "other", null, opts, reps=10)
        ck(False, "an option outside --options is refused")
    except ValueError:
        ck(True, "an option outside --options is refused")
    print(f"{sum(ok)}/{len(ok)} passed")
    return 0 if all(ok) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("procedure", nargs="?")
    ap.add_argument("--null")
    ap.add_argument("--options")
    ap.add_argument("--reps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.procedure and a.null and a.options):
        ap.error("give proc.py:choose --null gen.py:null --options a,b,c (or --selftest)")
    res = force_test(_load(a.procedure), _load(a.null), a.options.split(","), a.reps, a.seed)
    print(render(res))
    return 3 if res["verdict"] == "FORCED" else 0


if __name__ == "__main__":
    sys.exit(main())
