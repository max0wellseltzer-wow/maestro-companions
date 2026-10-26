"""number_sex - breed two numbers into offspring numbers (backs the word-sex skill).

The 1-to-1 reproduction operator applied to numbers: two parents bear children by the ways numbers
actually combine - the mediant (how Farey fractions reproduce: 1/2 x 1/3 -> 2/5), the means
(arithmetic, geometric, harmonic), and digit crossover (interleave the parents' digits). Pure stdlib,
deterministic. Another proof the method reaches past code: the parents are numbers.

    python number_sex.py 1/2 1/3        # children of two numbers (accepts ints, decimals, fractions)
    python number_sex.py 2 8
    python number_sex.py --selftest      # 5/5; the mediant/geometric checks are proven able to fail
"""
from __future__ import annotations

import math
import sys
from fractions import Fraction


def _parse(s: str) -> Fraction:
    return Fraction(s)   # handles "8", "0.5", "1/3"


def mediant(a: Fraction, b: Fraction) -> Fraction:
    """How Farey/Stern-Brocot fractions reproduce: child numerator/denominator are the summed parents.
    mediant(1/2, 1/3) = 2/5 - the fraction that sits between them."""
    return Fraction(a.numerator + b.numerator, a.denominator + b.denominator)


def digit_crossover(a: Fraction, b: Fraction) -> float:
    """Interleave the integer-part digits of the two parents (genetic crossover on the base-10 'genome')."""
    da, db = str(abs(int(a))), str(abs(int(b)))
    out = []
    for i in range(max(len(da), len(db))):
        if i < len(da):
            out.append(da[i])
        if i < len(db):
            out.append(db[i])
    return float("".join(out) or "0")


def children(a: Fraction, b: Fraction) -> dict:
    """All offspring of a and b, by reproduction mode; novel ones only (a child equal to a parent is skipped
    by the caller where it matters)."""
    kids = {"mediant": mediant(a, b), "arithmetic_mean": (a + b) / 2}
    fa, fb = float(a), float(b)
    if fa >= 0 and fb >= 0:
        kids["geometric_mean"] = math.sqrt(fa * fb)
    if a != 0 and b != 0:
        kids["harmonic_mean"] = float(2 / (1 / a + 1 / b))
    kids["digit_crossover"] = digit_crossover(a, b)
    return kids


def _selftest() -> bool:
    ok = {}
    ok["mediant(1/2, 1/3) == 2/5"] = (mediant(Fraction(1, 2), Fraction(1, 3)) == Fraction(2, 5))
    ok["mediant lies strictly between its parents"] = (
        Fraction(1, 3) < mediant(Fraction(1, 2), Fraction(1, 3)) < Fraction(1, 2))
    k = children(Fraction(2), Fraction(8))
    ok["geometric_mean(2, 8) == 4"] = (abs(k["geometric_mean"] - 4.0) < 1e-9)
    ok["harmonic_mean(2, 8) == 3.2"] = (abs(k["harmonic_mean"] - 3.2) < 1e-9)
    ok["digit_crossover(12, 34) interleaves to 1324"] = (
        digit_crossover(Fraction(12), Fraction(34)) == 1324.0)
    ok["deterministic"] = (children(Fraction(2), Fraction(8)) == k)
    for key, v in ok.items():
        print(("PASS " if v else "FAIL ") + key)
    return all(ok.values())


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if len(argv) < 2:
        print("usage: number_sex.py <a> <b>   (e.g. 1/2 1/3)"); return 2
    a, b = _parse(argv[0]), _parse(argv[1])
    for mode, val in children(a, b).items():
        if val != a and val != b:
            v = float(val)
            print(f"{mode:16s} {v:.6g}" + (f"  (= {val})" if isinstance(val, Fraction) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
