---
name: self-attacking-referee
description: Make any judge - a significance test, a metric threshold, a "did it beat the baseline" check, a detector, a gate - measure its OWN false-alarm rate and power on fake data shaped like the real case before its verdict counts, and print both beside the verdict; a judge that cries wolf has its ruling withheld as JUDGE_UNTRUSTED. Use whenever a verdict will be reported to the user or used to keep/kill an idea, whenever a new test, gate or threshold is written, when a p-value or "significant" comes from autocorrelated, overlapping, fat-tailed or selected data, and whenever someone says "is it significant", "did it pass", "is this real" - and to CHOOSE an "is it luck?" test by tournament (naive t, HAC, batch means, block bootstrap, shuffle, permutation on several known-null worlds) when picking a null/baseline, when two tests disagree, or a statistic looks suspiciously large - and to audit the nulls, i.e. audit any luck test, permutation or random-timing baseline on clustered same-day no-edge worlds vs the unclustered twin and sweep the codebase for every sibling null of the same shape, when a null is found flawed, before trusting a p-value from a screen or track record, when writing a new null, "is this p-value honest?", "are the other luck tests broken too?". Ships scripts/referee.py, scripts/null_tournament.py and scripts/null_audit_sweep.py (stdlib, seeded).
---

# self-attacking-referee

A verdict is only as good as its judge, and a judge's error rates are numbers you can measure. In this session's
fake-world check, a plain one-sample t-test on autocorrelated returns (AR(1), phi 0.6), where nothing is going on,
said "significant" **33.8%** of the time at alpha 5% (`referee.audit`, seed 4, 800 trials; an earlier run this session measured 31.5%, the null tournament
table below shows 33.3%). A "significant" from such a judge means little. Attaching the audit to the
verdict makes that visible at the point of use instead of in a postmortem.

## The procedure

1. **Name the judge** as a function `sample -> bool` (True = rejects the null / flags / passes the gate). If the
   judge is a script, wrap its call; do not re-implement it.
2. **Build the null world** that produces samples like the real one where the answer is KNOWN to be "no effect":
   same length, same autocorrelation, same tails, same selection (if you picked the best of 40, the null picks the
   best of 40 too). Fit those features from the real data; never from the result.
3. **Build the alt world**: the null plus the smallest effect you would care about (a cost-covering edge, not a huge
   one). Without it, power is UNMEASURED: report that, never "power 0".
4. **Audit before looking at the real verdict:**
   ```python
   import sys; sys.path.insert(0, ".claude/skills/self-attacking-referee/scripts")
   from referee import audit, refereed
   print(audit(judge, null_world, alt_world, trials=1000, alpha=0.05, seed=1).line())
   ruling = refereed(judge, null_world, alt_world, trials=1000, seed=1)(real_sample)
   ```
5. **Report the ruling with its audit line.** Verdicts:
   - `REJECT` / `NO_REJECT`: the judge is CALIBRATED or CONSERVATIVE.
   - `JUDGE_UNTRUSTED`: false alarms are clearly above alpha (the Wilson 95% interval lies above it). Withheld.
   - `NOT_TESTABLE`: the judge said "nothing" but is POWERLESS against the effect you care about. Absence of
     evidence is reported as exactly that.
6. If the judge is untrusted, run the **null tournament** (below) to pick a better one. Never adjust the threshold until the
   real sample passes: that is the selection the referee exists to expose.

## Rules
- The null world is fitted and frozen BEFORE the real verdict is read (pre-register it when money or a verdict is at
  stake: the pre-register skill).
- Same seed gives the same audit: quote the seed and trial count so anyone can rerun it.
- 1000 trials gives a +-1.4 point interval at 5%; use at least 500 before calling a judge calibrated.
- The referee measures the judge on YOUR null. A judge calibrated on iid data says nothing about autocorrelated data.
  That is the whole point.

## Tests
`python -m pytest -q .claude/skills/self-attacking-referee/scripts/test_referee.py` (8 tests). They check the
Wilson interval at known values; that a naive t is CALIBRATED and POWERED on iid data and ANTI_CONSERVATIVE on
AR(1); that always-reject and never-reject judges are caught; that unmeasured power is not zero; that the withheld
and not-testable verdicts are produced; and that audits are seed-deterministic.
Selftest: `python scripts/referee.py --selftest` (8 hermetic PASS/FAIL checks, exit 0 = all pass).

## Choosing the test: null tournament (merged from null-tournament)

Don't know the right test in advance - make the candidates compete where the answer is known.
1. **Survival rule first** (ships in the script; change only BEFORE a run, in writing): the Wilson 95% interval of the false-alarm rate contains alpha or lies below it, AND the rate is <= 1.5 x alpha (`max_rate`).
2. **At least three null worlds shaped like your data:** iid (sanity floor), the real autocorrelation (fit AR(1) or block-resample the demeaned series), the real tails (t(3) or resampled residuals), plus anything structural (overlapping windows, vol clusters, the cross-section's common factor, best-of-N selection). A test is only as safe as the nastiest world it survived.
3. **Candidates:** every test someone might reach for, including the naive one, so its failure is on record. **Alt world:** the smallest cost-covering effect, so survivors rank by power that matters.
4. **Run** (every judge sees the same seeded samples, so differences are the tests, not the luck):
   ```python
   import sys; sys.path.insert(0, ".claude/skills/self-attacking-referee/scripts")
   from null_tournament import tournament, table
   print(table(tournament(judges, null_worlds, alt_world, trials=500, seed=7)))
   ```
5. **Use the top survivor** and quote the table. Nothing survives -> `NO_VALID_TEST`, a named status, not the least-bad p-value.

```
test                       iid     ar1 0.6   power  verdict      (400 points, 300 trials, seed 11)
batch means              0.043       0.060   1.000  SURVIVES
always                   1.000       1.000   1.000  DIES on iid, ar1 0.6
naive t                  0.060       0.333   1.000  DIES on ar1 0.6
```
Tests: `python -m pytest -q .claude/skills/self-attacking-referee/scripts/test_null_tournament.py` (4: calibrated test survives and naive dies on exactly AR(1); survivors rank first then by power; the rate cap is hard even when the interval contains alpha; the table names the killing world). Selftest: `python scripts/null_tournament.py --selftest` (8 checks).

## Auditing a null and sweeping its siblings (merged from null-audit-sweep)

One flawed null means its siblings are suspect. 2026-10-13..15: W3 fixed tv-screener trackrec's volume-matched null (it
scattered each stock's events onto its own random days, so a rule firing on many stocks the SAME day missed their shared
market move: 0.28 false alarms instead of 0.05), but the default random_timing null had the identical flaw (33/100
clustered no-edge worlds called an edge) and stayed two more days; stock_scan's random_timing and condition_pnl share the shape.
1. **Audit the suspect null** on clustered no-edge worlds and the unclustered twin. `FAILS_ON_CLUSTERS` = sound scattered,
   broken on same-day clusters; `MISCALIBRATED` = high even on the twin (or the probe is broken); `NO_POWER` = never
   rejects a planted edge (`--edge`).
2. **Sweep:** `find <package dir>` lists every null-shaped function and whether it draws per item. Audit each (wrap its
   signature in a 5-line module if needed - never edit the repo to audit it).
3. **List the verdicts each failing null produced** and re-judge like for like (reproduce-before-rejudge).
4. **Fix with a test that fails first:** old null > 0.15 on these worlds, new one <= 0.10 (tests/test_trackrec_blocked_null.py).
5. Report each null's two rates, the verdict, and which saved verdicts it touches.
```
python scripts/null_audit_sweep.py run builtin:per_stock_scatter --worlds 100      # 0.32 / 0.06 -> FAILS_ON_CLUSTERS (83 s)
python scripts/null_audit_sweep.py run screener.trackrec:matched_null --path <repo>/tv-screener --path <repo>/tv-core --worlds 100
python scripts/null_audit_sweep.py run path/to/my_nulls.py:blocked_null --edge 0.006
python scripts/null_audit_sweep.py find <repo>/tv-screener/screener                 # 8 candidates on 2026-10-16
python scripts/null_audit_sweep.py --selftest                                       # about 10 s
```
The null takes trackrec's signature `null(draws, H, sign, reps, rng) -> (means, fallback)`; draws are `(region,
event_positions)` with `.ts`, `.eligible`, `.vdec`, `.out[H]`. Worlds = the W3 test's (120 stocks x 260 days, 6 cluster
days on 40% of stocks, 99 reps, alpha 0.05); "high" = above alpha + 2 binomial SE. One audit at a time (a heavy null's
100-world audit took 10 min). Real 2026-10-16: trackrec.matched_null 0.09 / 0.04 CALIBRATED; `find` named
intraday.backtest:random_timing, replay:_shuffles, rot:judge and trackrec:_score as next to audit. Limits: `find` is an AST
keyword heuristic (candidates, not judgements); the worlds model same-day clusters plus a market factor only, not
overlapping holding periods or sector clusters. Selftest planted 2, caught 2.

Related: signal-nulls (the HAC t and the shuffle trap: good candidate judges), test-a-condition, doubt-mind, plant-the-bug (does the judge's code fail when broken; the referee asks whether its
statistics do), reproduce-before-rejudge, fascination-forge.
