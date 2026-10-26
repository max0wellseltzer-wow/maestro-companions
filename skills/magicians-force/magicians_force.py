"""magicians_force - is a "random" selection really free, or is the card forced?

[IMAGINED pitch] A card magician "forces" a card: the spectator feels free to choose, but the same card comes out
every time. A seeded sampler can do the same - a shuffle null that ignores its seed, a subsample that always keeps
the first rows, a bootstrap whose block starts never reach the end of the series - and every replicate is the same
replicate wearing a different seed.
[REAL mechanism] Call the selection function under N seeds. If it picks k of n items, each item's inclusion count is
Binomial(N, k/n) under a fair sampler. Report:
  SEED IGNORED   every seed gave the identical selection (the seed is not wired)
  FORCED         items chosen far more often than the binomial allows (z > zmax, default 4.5 ~ 1 in 10**5 per item)
  SHUNNED        items chosen far less often (e.g. never)
  POSITION BIAS  Spearman correlation between an item's position in the population and its inclusion count
  chi-square uniformity statistic over all items with a Wilson-Hilferty p-value
Works for fixed-size and variable-size selections (expected rate = mean selection size / n).

    python magicians_force.py mod.py:sample --population pop.txt --seeds 500
        (sample(seed) -> iterable of chosen items; or sample(seed, population) when --pass-population)
    from magicians_force import audit
    python magicians_force.py --selftest
Exit: 0 FAIR, 1 FORCED / SHUNNED / SEED IGNORED / POSITION BIAS, 2 bad input.
"""
from __future__ import annotations

import importlib.util
import math
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def _chi2_sf(x: float, df: int) -> float:
    if df <= 0:
        return 1.0
    z = ((x / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))   # Wilson-Hilferty
    return _norm_sf(z)


def _spearman(xs, ys) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for q in range(i, j + 1):
                r[order[q]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def audit(select, population, seeds: int = 400, zmax: float = 4.5, rho_max: float = None) -> dict:
    pop = list(population)
    n = len(pop)
    if n < 2:
        raise ValueError("population needs at least 2 items")
    idx = {p: i for i, p in enumerate(pop)}
    counts = [0] * n
    seen, sizes, unknown = set(), [], set()
    for s in range(seeds):
        chosen = list(select(s))
        sizes.append(len(set(chosen)))          # inclusion, not multiplicity (bootstraps repeat items)
        seen.add(tuple(sorted(map(str, chosen))))
        for c in set(chosen):
            if c in idx:
                counts[idx[c]] += 1
            else:
                unknown.add(c)
    p = (sum(sizes) / seeds) / n
    mu, sd = seeds * p, math.sqrt(seeds * p * (1 - p)) if 0 < p < 1 else 0.0
    z = [(c - mu) / sd if sd else 0.0 for c in counts]
    forced = [(pop[i], counts[i], round(z[i], 2)) for i in range(n) if z[i] > zmax]
    shunned = [(pop[i], counts[i], round(z[i], 2)) for i in range(n) if z[i] < -zmax]
    chi2 = sum(((c - mu) ** 2) / mu for c in counts) if mu else 0.0
    rho = _spearman(list(range(n)), counts)
    rho_max = rho_max if rho_max is not None else 4.5 / math.sqrt(n - 1)
    flags = []
    if len(seen) == 1 and seeds > 1:
        flags.append("SEED IGNORED")
    if forced:
        flags.append("FORCED")
    if shunned:
        flags.append("SHUNNED")
    if abs(rho) > rho_max and sd:
        flags.append("POSITION BIAS")
    if unknown:
        flags.append("OUTSIDE POPULATION")
    return {"n": n, "seeds": seeds, "rate": p, "expected": mu, "distinct_selections": len(seen), "forced": forced,
            "shunned": shunned, "chi2": chi2, "chi2_p": _chi2_sf(chi2, n - 1) if mu else 1.0, "rho": rho,
            "flags": flags, "verdict": "FAIR" if not flags else " + ".join(flags), "unknown": sorted(map(str, unknown))[:5]}


def format_report(r: dict) -> str:
    out = [f"{r['seeds']} seeds over {r['n']} items: inclusion rate {r['rate']:.4f}, expected count {r['expected']:.1f}, "
           f"{r['distinct_selections']} distinct selections",
           f"chi-square {r['chi2']:.1f} on {r['n'] - 1} df (p ~ {r['chi2_p']:.3g}); position rank correlation {r['rho']:+.3f}"]
    out += [f"FORCED   {i}  chosen {c} times (z {z:+})" for i, c, z in r["forced"][:10]]
    out += [f"SHUNNED  {i}  chosen {c} times (z {z:+})" for i, c, z in r["shunned"][:10]]
    if r["unknown"]:
        out.append(f"chose items outside the population: {', '.join(r['unknown'])}")
    out.append(f"VERDICT {r['verdict']}")
    return "\n".join(out)


# ---------------------------------------------------------------- selftest
def _selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(("PASS " if cond else "FAIL ") + name)
        fails += 0 if cond else 1

    pop = [f"S{i:03d}" for i in range(60)]
    fair = audit(lambda s: random.Random(s).sample(pop, 10), pop, seeds=400)
    check("a seeded random.sample is FAIR", fair["verdict"] == "FAIR")
    check("chi-square p of a fair sampler is not tiny", fair["chi2_p"] > 0.001)
    ign = audit(lambda s: random.Random(7).sample(pop, 10), pop, seeds=50)
    check("a sampler that ignores its seed is SEED IGNORED (and FORCED)", "SEED IGNORED" in ign["flags"]
          and "FORCED" in ign["flags"])

    def sticky(s):
        rng = random.Random(s)
        return ["S000"] + rng.sample(pop[1:], 9)
    st = audit(sticky, pop, seeds=400)
    check("one always-kept item is FORCED and named", [f[0] for f in st["forced"]] == ["S000"])

    def headish(s):
        rng = random.Random(s)
        return rng.sample(pop[:40], 10)          # the tail of the population is never reached
    hd = audit(headish, pop, seeds=400)
    check("never reaching the tail is SHUNNED + POSITION BIAS", "SHUNNED" in hd["flags"]
          and "POSITION BIAS" in hd["flags"] and len(hd["shunned"]) == 20)

    def blocks(s):                               # bootstrap block start in [0, n - L) misses the last rows
        rng = random.Random(s)
        st0 = rng.randrange(0, 60 - 10)
        return pop[st0:st0 + 5]
    bl = audit(blocks, pop, seeds=600)
    check("block starts that cannot reach the end show POSITION BIAS or SHUNNED",
          bool({"POSITION BIAS", "SHUNNED"} & set(bl["flags"])))
    check("an item outside the population is reported",
          "OUTSIDE POPULATION" in audit(lambda s: ["ZZZ"] + pop[:2], pop, seeds=5)["flags"])
    print("selftest:", "ALL PASS" if not fails else f"{fails} FAILED")
    return 0 if not fails else 1


def main(argv) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return _selftest()
    args = list(argv)

    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return default
    try:
        popf, seeds = opt("--population"), int(opt("--seeds", "400"))
        pass_pop = "--pass-population" in args
        if pass_pop:
            args.remove("--pass-population")
        pop = [x.strip() for x in Path(popf).read_text(encoding="utf-8").splitlines() if x.strip()]
        path, _, fn = args[0].rpartition(":")
        p = Path(path).resolve()
        sys.path.insert(0, str(p.parent))
        spec = importlib.util.spec_from_file_location("_mf_" + p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        f = getattr(mod, fn)
        r = audit((lambda s: f(s, list(pop))) if pass_pop else f, pop, seeds)
    except (ValueError, OSError, IndexError, AttributeError, ImportError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(format_report(r))
    return 0 if r["verdict"] == "FAIR" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
