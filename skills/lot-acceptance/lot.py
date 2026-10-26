"""lot - acceptance sampling for claims (backs the lot-acceptance skill).

Factories cannot test every bolt; they test a sample and accept or reject the lot. A peer report with 120 numbers,
a ledger of 400 rows, 60 "done" items: re-verifying all is too dear, re-verifying three proves little. Exact
hypergeometric arithmetic (no normal approximation):
  plan    smallest sample n (accept on 0 bad) such that a lot of N with at least D bad items (or rate p) is
          caught with probability >= C
  draw    a seeded, reproducible sample of n item numbers (or lines of a file) - pick BEFORE looking
  bound   after checking n items and finding k bad: the largest number of bad items in the lot still consistent
          at confidence C (exact upper bound), and ACCEPT (k == 0 and the bound is within --max-bad) or REJECT
  power   chance this n catches D bad items, for a few D

    python lot.py plan 120 --defects 6 --confidence 0.95
    python lot.py plan 120 --rate 0.05
    python lot.py draw 120 31 --seed 20261016            # or: draw claims.txt 31 --seed ...
    python lot.py bound 120 31 --found 0 --confidence 0.95 --max-bad 6
    python lot.py --selftest
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path


def p_zero(N: int, D: int, n: int) -> float:
    """P(no bad item in a sample of n | N items, D bad)."""
    if n > N - D:
        return 0.0
    return math.comb(N - D, n) / math.comb(N, n)


def cdf(N: int, D: int, n: int, k: int) -> float:
    """P(at most k bad in the sample)."""
    tot = math.comb(N, n)
    return sum(math.comb(D, i) * math.comb(N - D, n - i) for i in range(0, min(k, D, n) + 1)) / tot


def plan(N: int, D: int, conf: float) -> int:
    if not (1 <= D <= N):
        raise ValueError("need 1 <= defects <= N")
    for n in range(0, N + 1):
        if 1 - p_zero(N, D, n) >= conf:
            return n
    return N


def upper_bound(N: int, n: int, k: int, conf: float) -> int:
    """Largest D with P(X <= k | D) >= 1 - conf (a D that large could still have produced <= k bad)."""
    best = k
    for D in range(k, N - (n - k) + 1):
        if cdf(N, D, n, k) >= 1 - conf:
            best = D
        else:
            break
    return best


def draw(N: int, n: int, seed: int) -> list[int]:
    return sorted(random.Random(seed).sample(range(1, N + 1), n))


def _selftest() -> bool:
    ok = True

    def t(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    t("p_zero matches the product formula", abs(p_zero(10, 2, 3) - (8 * 7 * 6) / (10 * 9 * 8)) < 1e-12)
    n = plan(100, 5, 0.95)
    t("plan(100, 5 bad, 95%) is minimal", 1 - p_zero(100, 5, n) >= 0.95 and 1 - p_zero(100, 5, n - 1) < 0.95)
    t("plan(100,5,95%) = 45", n == 45)
    t("hypergeometric needs fewer than the binomial bound", n < math.ceil(math.log(0.05) / math.log(0.95)))
    t("all items bad -> 1 sample is enough", plan(20, 20, 0.99) == 1)
    t("cdf sums to 1 at k = n", abs(cdf(30, 7, 10, 10) - 1.0) < 1e-12)
    ub = upper_bound(100, 45, 0, 0.95)
    t("0 found in 45 of 100 -> bound sits exactly at the 5% edge",
      cdf(100, ub, 45, 0) >= 0.05 and cdf(100, ub + 1, 45, 0) < 0.05)
    t("full census bound = found count", upper_bound(50, 50, 3, 0.95) == 3)
    t("finding more bad items raises the bound", upper_bound(100, 30, 2, 0.95) > upper_bound(100, 30, 0, 0.95))
    rng = random.Random(1)
    lot = [1] * 5 + [0] * 95
    hits = sum(any(rng.sample(lot, 45)) for _ in range(4000))
    t("simulation agrees with the exact catch rate (within 2%)", abs(hits / 4000 - (1 - p_zero(100, 5, 45))) < 0.02)
    t("draw is reproducible and in range", draw(120, 31, 7) == draw(120, 31, 7) and len(set(draw(120, 31, 7))) == 31
      and min(draw(120, 31, 7)) >= 1 and max(draw(120, 31, 7)) <= 120)
    t("a full draw numbers items 1..N (line numbers, not 0-based)", draw(10, 10, 1) == list(range(1, 11)))
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    conf = float(opt("--confidence", 0.95))
    op = argv[0]
    if op == "plan":
        N = int(argv[1])
        D = int(opt("--defects")) if "--defects" in argv else max(1, math.ceil(float(opt("--rate")) * N))
        n = plan(N, D, conf)
        print(f"lot {N}, catch >= {D} bad with {conf:.0%}: re-verify n = {n} (accept only if all {n} check out)")
        for d in sorted({1, max(1, D // 2), D, min(N, 2 * D)}):
            print(f"  power vs {d:>4} bad: {1 - p_zero(N, d, n):.3f}")
        return 0
    if op == "draw":
        src, n, seed = argv[1], int(argv[2]), int(opt("--seed", 0))
        if Path(src).is_file():
            lines = [ln for ln in Path(src).read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            for i in draw(len(lines), n, seed):
                print(f"{i:>5}  {lines[i - 1][:110]}")
        else:
            print(" ".join(map(str, draw(int(src), n, seed))))
        return 0
    if op == "bound":
        N, n, k = int(argv[1]), int(argv[2]), int(opt("--found", 0))
        ub = upper_bound(N, n, k, conf)
        mx = int(opt("--max-bad", 0))
        verdict = "ACCEPT" if k == 0 and ub <= max(mx, 0) else "REJECT" if k > 0 else "SAMPLE-TOO-SMALL"
        print(f"found {k} bad in {n} of {N}: at most {ub} bad in the lot ({ub / N:.1%}) at {conf:.0%} -> {verdict}")
        return 0 if verdict == "ACCEPT" else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main(sys.argv[1:]))
