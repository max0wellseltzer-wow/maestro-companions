"""forgery_plan - take the FAKER's side: what is the cheapest way to produce this evidence without the effect being
real? (backs the forgery-plan skill; handicap-test reversed).

handicap-test sits with the believer and scores each piece of evidence by how costly it would be to fake.
forgery-plan sits with the forger: given a claimed result described by a few fields, it lists every cheap route
to that same evidence with NO real effect behind it (from rubric.json beside this file), marks each route OPEN or
CLOSED from the fields, names the check or skill that closes it, and returns the verdict: the cheapest route still
open. A field the claim does not state never closes a route - silence counts as OPEN (unknown).

Claim fields (all optional except kind):
    kind                 backtest | forward_record | test_pass | model_metric | data_finding
    variants_tried       how many variants / parameter sets / signals were tried before this one was reported
    period               "2019-01-01..2024-06-30" or a number of years (-> period_years)
    preregistered, out_of_sample, shared (code+data), deflated (DSR/PBO applied), lookahead_checked, hac,
    overlapping_samples, walk_forward, point_in_time_universe, regimes_checked, costs_included,
    sessions_on_data, n_obs, null_compared, planted_bug_caught, mutation_kill_rate, timestamped_externally

    from forgery_plan import plan, report
    print(report(plan({"kind": "backtest", "variants_tried": 200, "out_of_sample": False})))
    python forgery_plan.py --claim claim.json [--rubric my_rubric.json]
    python forgery_plan.py --selftest
"""
from __future__ import annotations

import json
import operator
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SK = HERE.parents[0]
OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}


def load_rubric(path=None) -> dict:
    return _validate(json.loads(Path(path or HERE / "rubric.json").read_text(encoding="utf-8")))


def _validate(rub: dict) -> dict:
    for r in rub["routes"]:
        for c in r["closed_if"]:
            if c.get("op") not in OPS or "field" not in c:
                raise ValueError(f"route {r['id']}: bad clause {c}")
        if not r.get("closes_with"):
            raise ValueError(f"route {r['id']}: names no check that closes it")
        if not 0 <= r["cost"] <= 1:
            raise ValueError(f"route {r['id']}: cost must be in [0, 1]")
    return rub


def _period_years(p):
    if isinstance(p, (int, float)):
        return float(p)
    a, b = (date.fromisoformat(s.strip()) for s in str(p).split(".."))
    return (b - a).days / 365.25


def plan(claim: dict, rubric=None) -> dict:
    rub = _validate(rubric) if isinstance(rubric, dict) else load_rubric(rubric)
    kind = claim.get("kind")
    if kind not in rub["kinds"]:
        raise ValueError(f"kind must be one of {rub['kinds']}, got {kind!r}")
    f = dict(claim)
    if "period" in f and "period_years" not in f:
        f["period_years"] = _period_years(f["period"])
    rows = []
    for r in rub["routes"]:
        if kind not in r["kinds"]:
            continue
        by, unknown = None, []
        for c in r["closed_if"]:
            if c["field"] not in f:
                unknown.append(c["field"])
            elif OPS[c["op"]](f[c["field"]], c["value"]):
                by = f"{c['field']} {c['op']} {c['value']}"
                break
        status = "CLOSED" if by else ("OPEN (unknown)" if len(unknown) == len(r["closed_if"]) else "OPEN")
        rows.append({"id": r["id"], "cost": r["cost"], "how": r["how"], "status": status, "closed_by": by,
                     "closes_with": r["closes_with"], "unstated": unknown})
    rows.sort(key=lambda x: (x["status"] == "CLOSED", x["cost"], x["id"]))
    open_ = [x for x in rows if x["status"] != "CLOSED"]
    return {"kind": kind, "routes": rows, "open": len(open_), "closed": len(rows) - len(open_),
            "cheapest_open": open_[0] if open_ else None,
            "forgery_cost": open_[0]["cost"] if open_ else 1.0}


def report(p) -> str:
    c = p["cheapest_open"]
    head = (f"{p['kind']}: {p['open']} forgery route(s) OPEN, {p['closed']} closed. "
            + (f"VERDICT cheapest open route = {c['id']} (cost {c['cost']:.2f}) - {c['how']}; close it with "
               f"{', '.join(c['closes_with'])}" if c else "VERDICT no listed route is open (forgery cost 1.00)"))
    lines = [head]
    for r in p["routes"]:
        tail = f"closed by {r['closed_by']}" if r["closed_by"] else (
            f"unstated: {', '.join(r['unstated'])}" if r["unstated"] else "fields say open")
        lines.append(f"  {r['status']:<15} {r['cost']:.2f} {r['id']:<32} -> {', '.join(r['closes_with'])}  ({tail})")
    lines.append("  A closed route means the cheap fake is ruled out, not that the effect is real.")
    return "\n".join(lines)


def _selftest() -> bool:
    ok = {}
    rub = load_rubric()
    missing = sorted({s for r in rub["routes"] for s in r["closes_with"] if not (SK / s / "SKILL.md").exists()})
    ok["rubric loads and every closing check names an existing skill"] = not missing
    if missing:
        print("  missing skills:", missing)
    bt = plan({"kind": "backtest", "variants_tried": 200, "period": "2021-01-01..2023-06-30", "preregistered": False,
               "out_of_sample": False, "shared": False, "overlapping_samples": True, "costs_included": False})
    print(report(bt))
    ok["best-of-200 in-sample backtest: many routes open (>= 10)"] = bt["open"] >= 10
    ok["... and the verdict is search-then-report-best at cost 0.01"] = (
        bt["cheapest_open"]["id"] == "search_then_report_best" and bt["forgery_cost"] == .01)
    fw = plan({"kind": "forward_record", "variants_tried": 1, "period": "2025-10-01..2026-10-01", "preregistered": True,
               "out_of_sample": True, "shared": True, "timestamped_externally": True, "n_obs": 160})
    print(report(fw))
    ok["pre-registered, timestamped, shared forward record: one route open (one regime window, cost 0.30)"] = (
        fw["open"] == 1 and fw["cheapest_open"]["id"] == "one_regime_window" and fw["forgery_cost"] == .30)
    one = plan({"kind": "backtest", "variants_tried": 1, "out_of_sample": False})
    s1 = {r["id"]: r["status"] for r in one["routes"]}
    s200 = {r["id"]: r["status"] for r in plan({"kind": "backtest", "variants_tried": 200,
                                                "out_of_sample": False})["routes"]}
    ok["one field flips exactly the routes it closes (variants_tried 200 -> 1)"] = (
        sorted(k for k in s1 if s1[k] != s200[k]) == ["search_then_report_best"])
    bare = plan({"kind": "model_metric"})
    ok["silence never closes a route (all unknown -> OPEN (unknown))"] = (
        bare["closed"] == 0 and all(r["status"] == "OPEN (unknown)" for r in bare["routes"]))
    tp = plan({"kind": "test_pass", "shared": True, "mutation_kill_rate": .9})
    ok["a test pass with no planted-bug evidence: verdict 'test cannot fail'"] = tp["cheapest_open"]["id"] == "test_cannot_fail"
    try:
        plan({"kind": "vibes"})
        ok["planted bad input (unknown kind) is rejected"] = False
    except ValueError:
        ok["planted bad input (unknown kind) is rejected"] = True
    try:
        plan({"kind": "backtest"}, {"kinds": ["backtest"], "routes": [
            {"id": "x", "cost": .1, "how": "", "kinds": ["backtest"], "closes_with": ["y"],
             "closed_if": [{"field": "a", "op": "=~", "value": 1}]}]})
        ok["a malformed rubric clause is rejected"] = False
    except ValueError:
        ok["a malformed rubric clause is rejected"] = True
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if "--claim" not in argv:
        print(__doc__)
        return 2
    claim = json.loads(Path(argv[argv.index("--claim") + 1]).read_text(encoding="utf-8"))
    rub = argv[argv.index("--rubric") + 1] if "--rubric" in argv else None
    print(report(plan(claim, rub)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
