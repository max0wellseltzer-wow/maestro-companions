"""decorative - does a forecasting module beat a flat do-nothing baseline on worlds where there IS something to find?

A module is a Python function  forecast(history: list[float]) -> float  (the next value). The flat baseline is
the expanding mean of the history (or 0 with --flat zero). On each planted world (a known, learnable structure)
and on a null world (iid noise: nothing to learn), both forecast every step after a warm-up over S seeded
series; per series d = MSE(module) - MSE(flat). The mean of d across series gets a one-sided t-test.

  EARNS-ITS-KEEP  beats flat significantly on at least one planted world, and not on the null world
  DECORATIVE      beats flat on no planted world: the module's complexity buys nothing measurable
  SUSPECT-LEAK    beats flat on the null world, where nothing is predictable: look-ahead or a bug

Planted worlds: ar1 (phi 0.4), season (period-7 sine + noise), regime (mean +-0.6 switching every ~40 steps).
Custom worlds: --world file.py:func with func(rng: random.Random, n: int) -> list[float].

    python decorative.py module.py:forecast [--worlds ar1,season,regime] [--seeds 20] [--n 300] [--flat mean|zero]
    python decorative.py --selftest
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import random
import sys

PLANTED = ("ar1", "season", "regime")


def _t_sf_normal_approx(t: float, df: int) -> float:
    """One-sided upper-tail p for a t statistic (Student t via incomplete beta)."""
    x = df / (df + t * t)
    a, b = df / 2.0, 0.5
    tiny = 1e-300

    def cf(a, b, x):
        qab, qap, qam = a + b, a + 1.0, a - 1.0
        c, d = 1.0, 1.0 - qab * x / qap
        d = 1.0 / (d if abs(d) > tiny else tiny)
        h = d
        for m in range(1, 300):
            m2 = 2 * m
            for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
                d = 1.0 + aa * d
                d = 1.0 / (d if abs(d) > tiny else tiny)
                c = 1.0 + aa / c
                c = c if abs(c) > tiny else tiny
                h *= d * c
            if abs(d * c - 1.0) < 3e-14:
                break
        return h

    if x >= 1.0:
        two = 1.0
    else:
        lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
        two = (math.exp(lbt) * cf(a, b, x) / a if x < (a + 1.0) / (a + b + 2.0)
               else 1.0 - math.exp(lbt) * cf(b, a, 1.0 - x) / b)
    return two / 2 if t > 0 else 1 - two / 2


def world(name: str, rng: random.Random, n: int) -> list:
    if name == "null":
        return [rng.gauss(0, 1) for _ in range(n)]
    if name == "ar1":
        x, out = 0.0, []
        for _ in range(n):
            x = 0.4 * x + rng.gauss(0, 1)
            out.append(x)
        return out
    if name == "season":
        ph = rng.uniform(0, 2 * math.pi)
        return [math.sin(2 * math.pi * t / 7 + ph) + rng.gauss(0, 1) for t in range(n)]
    if name == "regime":
        m, out = rng.choice((-0.6, 0.6)), []
        for _ in range(n):
            if rng.random() < 1 / 40:
                m = -m
            out.append(m + rng.gauss(0, 1))
        return out
    raise ValueError(f"unknown world {name}")


def _load(spec: str):
    path, _, func = spec.rpartition(":")
    s = importlib.util.spec_from_file_location(f"_deco_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    return getattr(mod, func)


def evaluate(forecast, worlds: dict, seeds: int = 20, n: int = 300, warm: int = 50, flat: str = "mean",
             alpha: float = 0.05) -> dict:
    """worlds = {name: generator(rng, n)}; the name 'null' marks the no-structure world."""
    rows = {}
    for wi, (name, gen) in enumerate(worlds.items()):
        ds = []
        for s in range(seeds):
            x = gen(random.Random(1000 * wi + s), n)
            se_m = se_f = 0.0
            run = sum(x[:warm])
            for t in range(warm, n):
                f0 = run / t if flat == "mean" else 0.0
                fm = float(forecast(x[:t]))
                se_m += (x[t] - fm) ** 2
                se_f += (x[t] - f0) ** 2
                run += x[t]
            ds.append((se_m - se_f) / (n - warm))
        md = sum(ds) / seeds
        sd = math.sqrt(sum((d - md) ** 2 for d in ds) / (seeds - 1))
        t = md / (sd / math.sqrt(seeds)) if sd > 0 else (0.0 if md == 0 else math.copysign(math.inf, md))
        p = _t_sf_normal_approx(-t, seeds - 1) if not math.isinf(t) else (0.0 if t < 0 else 1.0)
        rows[name] = {"mean_dmse": md, "t": t, "p_better": p, "beats": p < alpha and md < 0}
    planted = [k for k in rows if k != "null"]
    if rows.get("null", {}).get("beats"):
        verdict = "SUSPECT-LEAK"
    elif any(rows[k]["beats"] for k in planted):
        verdict = "EARNS-ITS-KEEP"
    else:
        verdict = "DECORATIVE"
    return {"rows": rows, "verdict": verdict, "seeds": seeds, "n": n, "flat": flat}


def render(res: dict) -> str:
    out = [f"{'world':<10} {'mean dMSE':>11} {'t':>7} {'p(better)':>9}  beats flat?"]
    for k, r in res["rows"].items():
        out.append(f"{k:<10} {r['mean_dmse']:>+11.4f} {r['t']:>7.2f} {r['p_better']:>9.4f}  {'YES' if r['beats'] else 'no'}")
    out.append(f"VERDICT: {res['verdict']} (flat = {res['flat']}, {res['seeds']} series x {res['n']} steps per world)")
    return "\n".join(out)


def _selftest() -> int:
    ok = []

    def ck(c, what):
        ok.append(bool(c))
        print(("PASS " if c else "FAIL ") + what)

    ck(abs(_t_sf_normal_approx(1.833113, 9) - 0.05) < 1e-4, "one-sided t(9) p at 1.833 is 0.05")
    W = {k: (lambda k: lambda r, n: world(k, r, n))(k) for k in ("null", *PLANTED)}

    def ar_fit(h):                       # least-squares AR(1) on the history: a real module
        m = sum(h) / len(h)
        num = sum((h[i] - m) * (h[i - 1] - m) for i in range(1, len(h)))
        den = sum((v - m) ** 2 for v in h) or 1.0
        return m + num / den * (h[-1] - m)

    def fancy(h):                        # looks busy, learns nothing: a long-window smoothed mean of a mean
        w = h[-200:]
        return sum(sum(w[: i + 1]) / (i + 1) for i in range(len(w))) / len(w) * 0 + sum(h) / len(h)

    r = evaluate(ar_fit, W, seeds=12, n=200)
    ck(r["verdict"] == "EARNS-ITS-KEEP" and r["rows"]["ar1"]["beats"], f"AR(1) fitter -> {r['verdict']}")
    ck(not r["rows"]["null"]["beats"], "AR(1) fitter does not beat flat on the null world")
    r = evaluate(ar_fit, {"null": W["null"], "ar1": W["ar1"], "noise2": W["null"]}, seeds=8, n=150)
    ck(r["verdict"] == "EARNS-ITS-KEEP", "one planted world won is enough (a module need not win everywhere)")
    r = evaluate(fancy, W, seeds=12, n=200)
    ck(r["verdict"] == "DECORATIVE", f"busy module that is just the mean -> {r['verdict']}")
    r = evaluate(lambda h: sum(h) / len(h), {"ar1": W["ar1"]}, seeds=3, n=90)
    ck(abs(r["rows"]["ar1"]["mean_dmse"]) < 1e-12, "a module identical to flat scores dMSE exactly 0 (no peeking)")
    r = evaluate(lambda h: h[-1], W, seeds=12, n=200)
    ck(r["verdict"] == "DECORATIVE", f"naive last-value forecast (worse than flat at phi 0.4) -> {r['verdict']}")
    store = {}

    def leaky_world(rng, n):
        x = world("null", rng, n)
        store["x"] = x
        return x

    r = evaluate(lambda h: store["x"][len(h)], {"null": leaky_world, "ar1": W["ar1"]}, seeds=8, n=120)
    ck(r["verdict"] == "SUSPECT-LEAK", f"module that peeks at the next value -> {r['verdict']}")
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.py"
        p.write_text("def forecast(h):\n    return sum(h) / len(h)\n", encoding="utf-8")
        rc = main([f"{p}:forecast", "--seeds", "4", "--n", "80", "--worlds", "ar1"])
        ck(rc == 3, "CLI: a flat-copy module exits 3 (DECORATIVE)")
    print(f"{sum(ok)}/{len(ok)} passed")
    return 0 if all(ok) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("module", nargs="?", help="file.py:forecast")
    ap.add_argument("--worlds", default=",".join(PLANTED))
    ap.add_argument("--world", action="append", default=[], help="custom planted world file.py:func(rng, n)")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--flat", choices=("mean", "zero"), default="mean")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.module:
        ap.error("give file.py:forecast or --selftest")
    worlds = {"null": lambda r, n: world("null", r, n)}
    for k in (w for w in a.worlds.split(",") if w):
        worlds[k] = (lambda k: lambda r, n: world(k, r, n))(k)
    for spec in a.world:
        worlds[spec.rpartition(":")[2]] = _load(spec)
    res = evaluate(_load(a.module), worlds, a.seeds, a.n, flat=a.flat)
    print(render(res))
    return {"EARNS-ITS-KEEP": 0, "DECORATIVE": 3, "SUSPECT-LEAK": 4}[res["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
