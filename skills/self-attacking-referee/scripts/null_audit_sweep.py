"""null_audit_sweep - audit any luck test (a "null") on known-no-edge worlds, clustered and unclustered.

A null answers "how often would luck alone score this well?". It is only honest if, on worlds that have NO edge, it
calls an edge about alpha of the time. The trap found 2026-10-13/15 (merge plan W3, errata E77/E81): a rule that
fires on many stocks on the SAME days shares those days' market move; a null that scatters each stock's events onto
its own random days misses that shared move and calls luck an edge (measured 0.28-0.33 instead of 0.05).

Worlds (the W3 test's "none" kind): STOCKS x DAYS, a market factor plus noise, the rule firing on CLUSTER_DAYS
cluster days on FIRE_SHARE of the stocks plus scattered single events, and no edge. The unclustered twin has no
cluster days (only scattered events): a sound null and a per-stock null should both sit near alpha there - if they
do not, the probe (not the null) is broken.

The null under test has the tv-screener trackrec signature:
    null(draws, H, sign, reps, rng) -> (means, fallback_count)
where draws = [(region, event_positions), ...]; region has .ts, .eligible, .vdec (lists) and .out[H] (forward
returns by position). means = the null's pooled mean for each of `reps` replications.

    python null_audit_sweep.py run  <module:function | path/to/file.py:function> [--path DIR]... [--worlds 100]
                                    [--seed 20261013] [--edge 0.006] [--alpha 0.05] [--reps 99]
    python null_audit_sweep.py run  builtin:per_stock_scatter        # the reference that fails
    python null_audit_sweep.py run  builtin:date_blocked             # the reference that passes
    python null_audit_sweep.py find <dir>                            # candidate nulls in a codebase (AST, heuristic)
    python null_audit_sweep.py --selftest

Verdicts: CALIBRATED, FAILS_ON_CLUSTERS (exit 1), MISCALIBRATED (exit 1), NO_POWER (exit 1, only with --edge).
A rate counts as "high" when it is above alpha + 2 binomial standard errors for the number of worlds. Stdlib only.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import math
import random
import sys
import tempfile
import time
from bisect import bisect_left
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Worlds:
    stocks: int = 120
    days: int = 260
    cluster_days: int = 6
    fire_share: float = 0.4
    scatter: float = 0.002
    mkt_sd: float = 0.01
    idio_sd: float = 0.02
    H: int = 1
    reps: int = 99
    alpha: float = 0.05


CLUSTERED = Worlds()
UNCLUSTERED = replace(CLUSTERED, cluster_days=0, scatter=0.03)     # rt_null_sanity.py's twin


class Region:
    """Duck-type of trackrec.Region: positions index .eligible/.ts/.vdec/.out[H]."""
    __slots__ = ("ts", "eligible", "vdec", "out")

    def __init__(self, H: int):
        self.ts, self.eligible, self.vdec, self.out = [], [], [], {H: []}


def world(rng: random.Random, w: Worlds) -> list:
    mkt = [rng.gauss(0, w.mkt_sd) for _ in range(w.days)]
    days = set(rng.sample(range(20, w.days - 2), w.cluster_days)) if w.cluster_days else set()
    draws = []
    for _ in range(w.stocks):
        ret = [m + rng.gauss(0, w.idio_sd) for m in mkt]
        reg, evs = Region(w.H), []
        for t in range(w.days - w.H):
            reg.eligible.append(t)
            reg.ts.append(t)
            reg.vdec.append(rng.randrange(10))
            reg.out[w.H].append(ret[t + w.H])
            if (t in days and rng.random() < w.fire_share) or rng.random() < w.scatter:
                evs.append(t)
        if evs and len(evs) < len(reg.eligible):
            draws.append((reg, evs))
    return draws


def reject_rate(null, w: Worlds, worlds: int, seed: int, edge: float = 0.0) -> float:
    """Share of worlds where the null calls the events' mean an edge at alpha (one-sided, upper)."""
    rng = random.Random(seed)
    rejects = 0
    for _ in range(worlds):
        draws = world(rng, w)
        if edge:
            for reg, evs in draws:
                for e in evs:
                    reg.out[w.H][e] += edge
        n = sum(len(evs) for _, evs in draws)
        real = sum(reg.out[w.H][p] for reg, evs in draws for p in evs) / n
        means, _ = null(draws, w.H, 1.0, w.reps, random.Random(rng.randrange(1 << 30)))
        rejects += (1 + sum(m >= real for m in means)) / (1 + len(means)) <= w.alpha
    return rejects / worlds


# ---- reference nulls ------------------------------------------------------------------------------------------
def per_stock_scatter(draws, H, sign, reps, rng):
    """Each stock's events moved to its OWN random positions (the random_timing / old matched_null shape)."""
    means = []
    for _ in range(reps):
        tot, cnt = 0.0, 0
        for reg, evs in draws:
            for pos in rng.sample(range(len(reg.eligible)), len(evs)):
                tot += sign * reg.out[H][pos]
                cnt += 1
        means.append(tot / cnt)
    return means, 0


def date_blocked(draws, H, sign, reps, rng):
    """Every event of one date moves to ONE random date; each event takes its own stock's bar there (E81)."""
    times = sorted({t for reg, _ in draws for t in reg.ts})
    plan = [(reg, reg.ts[e]) for reg, evs in draws for e in evs]
    stamps = sorted({s for _, s in plan})
    means = []
    for _ in range(reps):
        targets = rng.sample(times, len(stamps)) if len(times) >= len(stamps) else [rng.choice(times) for _ in stamps]
        moved = dict(zip(stamps, targets))
        tot = 0.0
        for reg, stamp in plan:
            pos = min(bisect_left(reg.ts, moved[stamp]), len(reg.ts) - 1)
            tot += sign * reg.out[H][pos]
        means.append(tot / len(plan))
    return means, 0


BUILTINS = {"per_stock_scatter": per_stock_scatter, "date_blocked": date_blocked}


def load_null(spec: str, paths=()):
    """'builtin:name', 'pkg.module:function' or 'path/to/file.py:function'."""
    target, _, fn = spec.rpartition(":")
    if not target or not fn:
        raise SystemExit(f"bad null spec {spec!r}: want module:function")
    if target == "builtin":
        return BUILTINS[fn]
    for p in reversed(list(paths)):
        sys.path.insert(0, str(Path(p).resolve()))
    if target.endswith(".py"):
        path = Path(target).resolve()
        sp = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(sp)
        sys.modules[path.stem] = mod
        sp.loader.exec_module(mod)
    else:
        mod = importlib.import_module(target)
    return getattr(mod, fn)


def high(rate: float, alpha: float, worlds: int) -> bool:
    return rate > alpha + 2 * math.sqrt(alpha * (1 - alpha) / worlds)


def verdict(clustered: float, unclustered: float, alpha: float, worlds: int, power=None) -> str:
    hc, hu = high(clustered, alpha, worlds), high(unclustered, alpha, worlds)
    if hc and not hu:
        return "FAILS_ON_CLUSTERS"
    if hc or hu:
        return "MISCALIBRATED"
    if power is not None and not high(power, alpha, worlds):
        return "NO_POWER"
    return "CALIBRATED"


def audit(null, worlds=100, seed=20261013, edge=0.0, clustered=CLUSTERED, unclustered=UNCLUSTERED) -> dict:
    t0 = time.time()
    rc = reject_rate(null, clustered, worlds, seed)
    ru = reject_rate(null, unclustered, worlds, seed)
    pw = reject_rate(null, clustered, worlds, seed, edge) if edge else None
    return {"clustered": rc, "unclustered": ru, "power": pw, "alpha": clustered.alpha, "worlds": worlds,
            "verdict": verdict(rc, ru, clustered.alpha, worlds, pw), "seconds": round(time.time() - t0, 1)}


def print_audit(name: str, r: dict) -> None:
    lim = r["alpha"] + 2 * math.sqrt(r["alpha"] * (1 - r["alpha"]) / r["worlds"])
    print(f"null: {name}   worlds: {r['worlds']} per kind   alpha: {r['alpha']}   'high' means > {lim:.3f}")
    print(f"  false-alarm rate, clustered no-edge worlds:   {r['clustered']:.2f}")
    print(f"  false-alarm rate, unclustered no-edge twin:   {r['unclustered']:.2f}")
    if r["power"] is not None:
        print(f"  power, clustered worlds with planted edge:    {r['power']:.2f}")
    print(f"VERDICT: {r['verdict']}   ({r['seconds']} s)")


# ---- find: candidate nulls in a codebase (heuristic) ----------------------------------------------------------
_NAME_HINT = ("null", "random_timing", "permut", "shuffle", "placebo", "random_positions", "blocked_timing")
_RAND_CALLS = {"sample", "shuffle", "choice", "randrange", "random_positions", "randint", "choices"}


def find(root: Path) -> list:
    out = []
    for py in sorted(Path(root).rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        mod = ".".join(py.relative_to(root).with_suffix("").parts)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            named = any(h in node.name.lower() for h in _NAME_HINT)
            per_item = False
            for loop in (n for n in ast.walk(node) if isinstance(n, (ast.For, ast.comprehension))):
                body = loop.body if isinstance(loop, ast.For) else [loop]
                for sub in (s for b in body for s in ast.walk(b)):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, (ast.Attribute, ast.Name)):
                        nm = sub.func.attr if isinstance(sub.func, ast.Attribute) else sub.func.id
                        if nm in _RAND_CALLS:
                            per_item = True
            src = ast.get_source_segment(py.read_text(encoding="utf-8", errors="replace"), node) or ""
            date_grouped = ("stamp" in src or "dict(zip(" in src) and per_item
            if named or (per_item and "reps" in src):
                shape = "DATE_GROUPED?" if date_grouped else ("PER_ITEM_DRAW" if per_item else "UNKNOWN")
                out.append((f"{mod}:{node.name}", py.as_posix(), node.lineno, shape))
    return out


# ---- selftest -------------------------------------------------------------------------------------------------
def _selftest() -> bool:
    ok = {}
    t0 = time.time()
    # smaller, faster worlds of the same kind (3 cluster days so the shared move is unmistakable in 40 worlds)
    small_c = replace(CLUSTERED, stocks=60, days=120, cluster_days=3, reps=39)
    small_u = replace(UNCLUSTERED, stocks=60, days=120, reps=39)
    W = 40
    r_ps = audit(per_stock_scatter, W, 20261013, 0.0, small_c, small_u)
    r_db = audit(date_blocked, W, 20261013, 0.015, small_c, small_u)
    print(f"  per_stock_scatter: clustered {r_ps['clustered']:.2f} unclustered {r_ps['unclustered']:.2f} "
          f"-> {r_ps['verdict']}")
    print(f"  date_blocked:      clustered {r_db['clustered']:.2f} unclustered {r_db['unclustered']:.2f} "
          f"power {r_db['power']:.2f} -> {r_db['verdict']}")
    ok["per-stock scatter null FAILS on clustered no-edge worlds (well above alpha: >= 0.15)"] = (
        r_ps["clustered"] >= 0.15 and r_ps["verdict"] == "FAILS_ON_CLUSTERS")
    ok["per-stock scatter null sits near alpha on the unclustered twin (the probe is sound)"] = not high(
        r_ps["unclustered"], 0.05, W)
    ok["date-blocked null PASSES on clustered worlds and has power on a planted edge"] = (
        r_db["verdict"] == "CALIBRATED" and not high(r_db["clustered"], 0.05, W) and r_db["power"] >= 0.5)

    def always_luck(draws, H, sign, reps, rng):
        return [float("inf")] * reps, 0
    tiny = replace(small_c, stocks=30)
    r_nl = audit(always_luck, 10, 1, 0.01, tiny, replace(small_u, stocks=30))
    ok["a null that never rejects is called NO_POWER, not CALIBRATED"] = r_nl["verdict"] == "NO_POWER"
    ok["verdict logic: both high -> MISCALIBRATED"] = verdict(0.4, 0.4, 0.05, 100) == "MISCALIBRATED"

    tmp = Path(tempfile.mkdtemp(prefix="nas_"))
    (tmp / "pkg_nulls").mkdir()
    (tmp / "pkg_nulls" / "__init__.py").write_text("", encoding="utf-8")
    (tmp / "pkg_nulls" / "mine.py").write_text(
        "def my_null(draws, H, sign, reps, rng):\n    return [0.0] * reps, 0\n"
        "def helper():\n    return 1\n", encoding="utf-8")
    (tmp / "pkg_nulls" / "scan.py").write_text(
        "def random_timing(per, reps, rng):\n    out = []\n    for s in per:\n        out.append(rng.sample(s, 2))\n"
        "    return out\n", encoding="utf-8")
    f1 = load_null("pkg_nulls.mine:my_null", [tmp])
    f2 = load_null(f"{(tmp / 'pkg_nulls' / 'mine.py').as_posix()}:my_null")
    ok["loads a null by module:function (with --path) and by file.py:function"] = (
        f1([], 1, 1.0, 3, None)[0] == [0.0] * 3 and f2([], 1, 1.0, 2, None)[0] == [0.0] * 2)
    found = {c[0]: c[3] for c in find(tmp)}
    ok["find lists null-shaped functions with their draw shape, not helpers"] = (
        found.get("pkg_nulls.scan:random_timing") == "PER_ITEM_DRAW" and "pkg_nulls.mine:my_null" in found
        and "pkg_nulls.mine:helper" not in found)
    a = reject_rate(date_blocked, tiny, 5, 7)
    b = reject_rate(date_blocked, tiny, 5, 7)
    ok["same seed, same rate (deterministic)"] = a == b
    secs = time.time() - t0
    ok[f"selftest under 60 s (took {secs:.1f} s)"] = secs < 60
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv: list) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")      # a cp1252 console must not crash on a Greek letter
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "find" and len(argv) == 2:
        rows = find(Path(argv[1]))
        for name, path, line, shape in rows:
            print(f"CANDIDATE {name}  {shape}  ({path}:{line})")
        print(f"{len(rows)} candidate(s). Audit each with: run <module:function> (adapt its signature first if needed)")
        return 0
    if argv[0] == "run" and len(argv) >= 2:
        opts, paths, i = {}, [], 2
        while i < len(argv):
            if argv[i] == "--path":
                paths.append(argv[i + 1])
            else:
                opts[argv[i]] = argv[i + 1]
            i += 2
        alpha = float(opts.get("--alpha", 0.05))
        reps = int(opts.get("--reps", 99))
        c, u = replace(CLUSTERED, alpha=alpha, reps=reps), replace(UNCLUSTERED, alpha=alpha, reps=reps)
        r = audit(load_null(argv[1], paths), int(opts.get("--worlds", 100)), int(opts.get("--seed", 20261013)),
                  float(opts.get("--edge", 0.0)), c, u)
        print_audit(argv[1], r)
        return 0 if r["verdict"] == "CALIBRATED" else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
