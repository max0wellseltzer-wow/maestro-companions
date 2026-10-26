---
name: decorative-check
description: Make a forecasting or analytics module prove it beats a flat do-nothing baseline (the expanding mean, or zero) on planted worlds where there IS structure to find (AR(1), seasonality, mean regimes, or your own world), with a paired one-sided t-test over seeded series, and label it EARNS-ITS-KEEP, DECORATIVE (complexity that buys nothing measurable) or SUSPECT-LEAK (it beats flat on pure noise, so it is peeking). Use this whenever a new indicator, filter, forecaster, smoother, regime detector or metaphor-named module is added, when the user asks "does this module actually do anything?", "is this just decoration?", "would a constant do as well?", and before a module is wired into a screen or blend. Paper-only research. Pairs with self-attacking-referee, fascination-forge, metaphor-to-algorithm and signal-vetting.
---
# decorative-check

## The problem (deep mine D, read 2026-10-16)
The archived AH08 design carried a `flat_baseline_arm`: "a module must beat a flat baseline or be labelled
DECORATIVE". It never shipped. Meanwhile the 2026-10-15 merges folded 14 metaphor-named skills whose tools mostly
re-named ordinary algorithms; nothing asked whether each one's output beats doing nothing. A module that cannot
beat the expanding mean where structure is planted will not beat it on real data.

## Procedure
1. Expose the module as `forecast(history) -> next value` (wrap an indicator by turning its signal into a
   forecast; a filter becomes "forecast = mean if filter says no trade else signal").
2. Pick planted worlds that match the module's claim (a seasonality module -> `season`; a regime detector ->
   `regime`), or pass your own with `--world file.py:func`. Always keep the `null` world (added automatically).
3. Run. EARNS-ITS-KEEP needs one planted world won with p < 0.05 and no win on the null world.
4. DECORATIVE -> do not wire it in; either the claim is wrong or the module cannot find its own effect.
   SUSPECT-LEAK -> it predicts noise: hunt the look-ahead before anything else.

## The tool (table numbers below are illustrative, not a recorded run)
```
python decorative.py module.py:forecast --worlds ar1,season,regime --seeds 20 --n 300
world        mean dMSE       t p(better)  beats flat?
null           +0.0031    1.10    0.86    no
ar1            -0.1450  -12.3     0.0000  YES
...
VERDICT: EARNS-ITS-KEEP (flat = mean, 20 series x 300 steps per world)
python decorative.py --selftest
```
Exit 0 EARNS-ITS-KEEP, 3 DECORATIVE, 4 SUSPECT-LEAK. dMSE = module MSE - flat MSE per series (negative = better).

## Proof (selftest 9/9)
An AR(1) least-squares fitter EARNS (beats flat on ar1, not on null); one won world is enough; a busy module that
reduces to the mean and the naive last-value forecast are DECORATIVE; a module that reads the next value is
SUSPECT-LEAK; a module identical to flat scores dMSE exactly 0; one-sided t(9) p at 1.833 = 0.05.
Planted 4, caught 4 (any->all planted worlds, leak rule disabled, flat baseline peeking at x[t], doubled p).

## Limits
MSE on one-step forecasts; a module whose value is in sizing or timing needs a PnL world instead (pass it as a
custom world and forecast). Pairs with self-attacking-referee (is the judge honest?), fascination-forge (does a
detector see a planted effect?), metaphor-to-algorithm (is it a new algorithm?), signal-vetting.

## Provenance
- skill-foundry dry run 2026-10-16: `decorative-check: PASSES ALL GATES` (finder top hit self-attacking-referee norm 0.28 vs 0.6; metaphor BUILD; no collision).
- Concrete use: run kalman-filter's or ewma-vol's one-step forecast through decorative.py before a screen uses it as a feature.
