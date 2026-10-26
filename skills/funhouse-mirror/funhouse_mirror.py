"""funhouse_mirror - scale each parameter by ten and by a tenth and list which conclusions survive
(backs the funhouse-mirror skill).

The subject is a set of items scored by a weighted sum of raw numeric columns. The default weights are +1 for the
first numeric column (the benefit) and -1 for the rest (the costs). Pass your own as `--opt weights=sharpe:1,turnover:-0.2`.
The baseline gives three conclusions: the leader, the top-half set and the last place. Then the lens bends the mirror
on each weight in turn, x10 and x0.1, re-scores, and checks every conclusion. A conclusion that survives all 2m
distortions does not depend on the weights; one that breaks under a single weight is hanging on it.

    python funhouse_mirror.py <items.json|table.csv> [--opt weights=col:w,col:w] [--json]
    python funhouse_mirror.py --selftest
"""
from __future__ import annotations

import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, report, run_cli, view  # noqa: E402

KINDS = {"items", "table"}
FACTORS = (10.0, 0.1)


def conclusions(rows, labels, w):
    score = [sum(wt * r[c] for c, wt in w.items()) for r in rows]
    order = sorted(range(len(rows)), key=lambda i: -score[i])
    half = max(1, len(rows) // 2)
    return {"leader": labels[order[0]], "top half": frozenset(labels[i] for i in order[:half]),
            "last place": labels[order[-1]]}


def show(v):
    return "{" + ", ".join(sorted(v)) + "}" if isinstance(v, frozenset) else v


def apply(subject, kind=None, weights=None, **opts) -> dict:
    k, rows = load_subject(subject, kind)
    if k not in KINDS or len(rows) < 3:
        raise ValueError(f"funhouse-mirror needs 3+ items, got {k}")
    num = [c for c in rows[0] if all(isinstance(r.get(c), (int, float)) and not isinstance(r.get(c), bool) for r in rows)]
    if weights:
        w = {c.strip(): float(x) for c, x in (p.split(":") for p in str(weights).split(","))}
    else:
        w = {c: (1.0 if i == 0 else -1.0) for i, c in enumerate(num)}
    if not w or any(c not in num for c in w):
        raise ValueError(f"weights must name numeric columns of the items: {num}")
    key = next((c for c in rows[0] if c not in num), None)
    labels = [str(r[key]) if key else f"#{i}" for i, r in enumerate(rows)]
    base = conclusions(rows, labels, w)
    findings, survive = [], {c: 0 for c in base}
    hangs = {}
    for c in w:
        for fct in FACTORS:
            bent = conclusions(rows, labels, {**w, c: w[c] * fct})
            broke = [name for name in base if bent[name] != base[name]]
            for name in base:
                survive[name] += name not in broke
            for name in broke:
                hangs.setdefault(name, []).append(f"{c} x{fct:g}")
            findings.append({"what": f"{c} x{fct:g}: " + ("all conclusions survive" if not broke else
                             "; ".join(f"{n} {show(base[n])} -> {show(bent[n])}" for n in broke)),
                             "weight": c, "factor": fct, "broke": broke})
    n = 2 * len(w)
    for name in base:
        findings.insert(0, {"what": f"{name} {show(base[name])} survives {survive[name]}/{n} distortions"
                                    + (f"; hangs on {', '.join(hangs[name])}" if name in hangs else ""),
                            "conclusion": name, "survives": survive[name], "of": n})
    robust = [nm for nm in base if survive[nm] == n]
    return view("funhouse-mirror", k, findings, f"weights {w}; robust conclusions: {', '.join(robust) or 'none'}; "
                                               f"fragile: {', '.join(nm for nm in base if nm not in robust) or 'none'}",
                weights=w, robust=robust)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["items"])
    ok["probe: default weights sharpe +1, others -1, 3 x 2 distortions"] = (
        v["stats"]["weights"] == {"sharpe": 1.0, "turnover": -1.0, "drawdown": -1.0}
        and sum(1 for f in v["findings"] if "factor" in f) == 6)
    ok["probe: reversion is last (turnover 3.1) and only sharpe x10 moves it (to pm-calibration)"] = any(
        f.get("conclusion") == "last place" and "reversion" in f["what"] and f["survives"] == 5
        and "sharpe x10" in f["what"] for f in v["findings"])
    rows = [{"n": "a", "ret": 10, "risk": 1}, {"n": "b", "ret": 9, "risk": 0.1}, {"n": "c", "ret": 1, "risk": 0.5}]
    p = apply(rows, weights="ret:1,risk:-1")
    lead = next(f for f in p["findings"] if f.get("conclusion") == "leader")
    ok["planted: leader a flips to b under risk x10 and ret x0.1 (same ratio), survives the other two"] = (
        lead["survives"] == 2 and "risk x10" in lead["what"] and "ret x0.1" in lead["what"])
    ok["planted: last place c survives every distortion"] = "last place" in p["stats"]["robust"]
    ok["conclusions helper: top half of 3 items is the single best"] = conclusions(
        rows, ["a", "b", "c"], {"ret": 1.0})["top half"] == frozenset({"a"})
    try:
        apply(rows, weights="nope:1")
        ok["planted bad input (weight on a missing column) is refused"] = False
    except ValueError:
        ok["planted bad input (weight on a missing column) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("funhouse-mirror", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
