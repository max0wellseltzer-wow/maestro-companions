# Statistical fallacies as forgery routes

Harvested 2026-10-23 from K-Dense AI's science-superpowers (MIT, `skills/preregistering-analysis/statistical-fallacies.md`), rewritten for this library: each classic trap is read from the forger's side and mapped to the `rubric.json` route that models it and the skill that closes it. Where a trap has no route it is marked NO ROUTE (a candidate to add if it ever bites).

| Trap | How it sneaks in | Route id | Closes with |
|---|---|---|---|
| p-hacking / data dredging | try many cuts (outlier in/out, log, subgroup, covariates), report the one that crosses the bar | `search_then_report_best` | deflated-sharpe, pbo-overfit, pre-register |
| HARKing | see a striking effect, then write the hypothesis as if predicted; or edit the pre-reg after the number | `moved_bar_after_freeze` | pre-register (INTEGRITY check) |
| Garden of forking paths | one analysis was run, but a different one would have been chosen had the data looked different | `search_then_report_best` (the variants are implicit) | pre-register, prereg-everywhere |
| Optional stopping | peek at the running score, stop when it crosses the bar | `optional_stopping` | sprt-sequential, pre-register |
| Multiple comparisons | twenty cells, one significant, reported alone | `search_then_report_best` | fdr-control, significance-budget, deflated-sharpe |
| Data leakage | scale/impute/select features on the full panel before the split; a feature sees the future | `lookahead_in_features`, `tuned_on_test_set` | light-cone, walk-forward-split |
| Overfitting | tune on the test set, report in-sample fit as predictive | `in_sample_only`, `tuned_on_test_set` | walk-forward-split, pbo-overfit |
| p-value misread | p = .04 read as "96% real"; p = .20 read as "no effect" | NO ROUTE (a reading error, not a forgery) | bootstrap-ci, base-rate-view |
| Underpowered study | a small sample hits the bar by luck and overstates the size (winner's curse) | `small_sample_luck` | sprt-sequential, bootstrap-ci, winners-curse |
| Confounding / Simpson | pooled effect reverses inside subgroups because of a lurking variable | `one_regime_window` (regime as the confounder) | regime-split |
| Base-rate neglect | a rare true edge screened at high specificity is still mostly false positives | NO ROUTE | base-rate-view, fdr-control |
| Survivorship / selection | universe or sample built from what survived; conditioning on a collider | `survivorship_universe` | data-hygiene, survivorship-view |
| Regression to the mean | select the extremes, intervene, credit the bounce | NO ROUTE | signal-nulls (a shuffle null bounces too), pre-register |

**The fix that ties them together** (their words, kept because it is the same as ours): pre-register the primary analysis and decision rule, fix the sample, split before you preprocess, correct for multiplicity, label everything unregistered as exploratory, report effect sizes with intervals. Those are exactly the degrees of freedom a forger uses.

**Use.** When a claim's open-route list looks short but the result still smells, walk this table from the top: each row is a route the rubric may be missing a field for. Add the field to the claim (or the route to the rubric) and rerun `forgery_plan.py`.
