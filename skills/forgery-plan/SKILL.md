---
name: forgery-plan
description: Take the faker's side of a claimed result - from a few fields (kind backtest / forward record / test pass / model metric / data finding, variants tried, data period, pre-registered, out-of-sample, code and data shared, and more) list every cheap way to produce that same evidence with no real effect behind it (search-then-report-best, look-ahead, survivorship, overlapping-sample t-stats, tuning on the test set, cherry-picked period, a test that cannot fail, snooping across sessions, backdated forward logs...) from an editable rubric, mark each OPEN or CLOSED with the skill that closes it, and name the cheapest route still open. Use this whenever the user or a session claims something works, before promoting a strategy or finding, when reviewing another Claude's write-up, or when asking how this could be fooling us or what to check next. Reverses handicap-test; pairs with handicap-test, deflated-sharpe, walk-forward-split, light-cone, hac-regression, mutation-audit and pre-register.
---

# forgery-plan

Reverses **handicap-test**. handicap-test sits on the believer's side and scores evidence by how costly it would be to fake. forgery-plan flips the angle and sits with the forger, who asks one question: what is the cheapest way to produce exactly this evidence without the effect being real? Every route the claim's fields do not close stays open. The cheapest open route is the next thing to check, because it is the most likely way the claim is fooling us. The forger is usually the author, fooling themselves by accident.

## The tool (ships with this skill)

`forgery_plan.py` plus `rubric.json`, pure stdlib. `rubric.json` holds 19 routes (two added 2026-10-23: `optional_stopping` and `moved_bar_after_freeze`, see `statistical_fallacies.md`). Each route has a faker's cost, a `how`, the claim kinds it applies to, `closed_if` clauses and `closes_with` skills. Selftest 9/9:

- A best-of-200 in-sample backtest has 12 routes open. The verdict is `search_then_report_best` (cost 0.01), closed with deflated-sharpe, pbo-overfit or pre-register.
- A pre-registered, externally timestamped, shared one-year forward record has 1 route open: `one_regime_window` (cost 0.30), closed with regime-split or sprt-sequential.
- A test pass with no planted-bug evidence gets the verdict `test_cannot_fail`.
- A claim that states no fields leaves every route OPEN (unknown).
- Every `closes_with` entry names an existing skill folder.

```
from forgery_plan import plan, report
print(report(plan({"kind": "backtest", "variants_tried": 200, "period": "2021-01-01..2023-06-30",
                   "preregistered": False, "out_of_sample": False, "shared": False})))
python forgery_plan.py --claim claim.json [--rubric my_rubric.json]
```

Fields:

- `kind`
- `variants_tried`
- `period`, given as `"YYYY-MM-DD..YYYY-MM-DD"` or a number of years
- `preregistered`, `out_of_sample`, `shared`, `deflated`, `lookahead_checked`, `hac`, `overlapping_samples`, `walk_forward`, `point_in_time_universe`, `regimes_checked`, `costs_included`, `null_compared`, `planted_bug_caught`, `timestamped_externally`
- `sessions_on_data`, `n_obs`, `mutation_kill_rate`, `stopping_rule_fixed`, `prereg_integrity_checked`
- `statistical_fallacies.md` maps the 13 classic traps (p-hacking, HARKing, forking paths, optional stopping, leakage, survivorship, regression to the mean ...) to these routes and the skills that close them; walk it when the open-route list looks too short

## Uses and limits

- Run it before handicap-test, then go and close the cheapest open route with the named skill. Feed the result back as a field (for example `deflated: true`) and rerun. The verdict moves to the next-cheapest route.
- Silence is treated as OPEN, so a sparse claim lists many routes. That shows how much the claim leaves unsaid, not that it is wrong.
- A CLOSED route rests on the claim's own fields. Verify the important ones (timestamps, variant counts) against `forward-score`, `research-spine` or `lineage-ledger` records rather than taking them on trust.
- The costs are judgement, not measurement. Edit `rubric.json` to change them, and add routes as new failure modes turn up.
- Closing every listed route means the cheap fakes are ruled out. It does not mean the effect is real.
- Paper-only research.
