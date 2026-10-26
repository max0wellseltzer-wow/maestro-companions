---
name: magicians-force
description: Card-magic audit of "random" selections - call a seeded selection function (a subsample, a shuffle null, a bootstrap replicate, a random universe) under many seeds and test whether the choice is really free - SEED IGNORED (every seed gives the same selection), FORCED items chosen far more than the binomial allows, SHUNNED items chosen far less (the tail never reached), POSITION BIAS (inclusion correlates with position), items outside the population, plus a chi-square uniformity statistic. Use this whenever a null, bootstrap, permutation test, random split or sampler feeds a verdict, when replicates look suspiciously alike, when the user asks whether a random sample is really random, or before trusting a p-value from resampling. Pairs with self-attacking-referee, signal-nulls, bootstrap-ci and monte-carlo-paths.
---
# magicians-force

## Pitch [IMAGINED]
A magician forces a card: the spectator feels free to pick, but the same card comes out every time. A seeded sampler
can force too - a seed that is never wired in, a subsample that always keeps the first rows, block starts that cannot
reach the end - and every replicate is the same replicate under a different seed.

## Mechanism [REAL]
Under a fair sampler that includes k of n items per call, each item's inclusion count over N seeds is Binomial(N,
k/n). The tool computes per-item z-scores (flag beyond 4.5, about 1 in 10**5 per item), the chi-square statistic over
all items with a Wilson-Hilferty p-value, the Spearman correlation of inclusion with position, and the number of
distinct selections. Inclusion, not multiplicity: an item drawn twice in one replicate counts once.

## Procedure
1. Expose one replicate as `f(seed) -> chosen items` (a small wrapper is fine; give the population as a file).
2. `python magicians_force.py wrap.py:f --population pop.txt --seeds 600`.
3. SEED IGNORED is always a bug. FORCED / SHUNNED may be by design (an always-kept benchmark row; a non-circular block
   bootstrap under-samples both ends) - then say so next to the result that uses it, or switch to a fair scheme.

## Usage
```
python magicians_force.py boot_wrap.py:moving_block --population pop100.txt --seeds 600
SHUNNED  0  chosen 66 times (z -27.0)
VERDICT FORCED + SHUNNED
python magicians_force.py --selftest          # 7 PASS lines
```
Exit: 0 FAIR, 1 any flag, 2 bad input.

## Evidence
Real run 2026-10-16 (read-only wrappers in _evidence/boot_wrap.py, 100 rows, block 10, 600 seeds): bootstrap-ci's
moving-block `block_ci` includes row 0 in 66 replicates against an expected 384 (z -27), rows 0-5 and 94 onward SHUNNED (the report lists the first 10),
rows 67-71 mildly FORCED - the known edge under-sampling of a non-circular moving-block bootstrap, undocumented in that
skill. monte-carlo-paths' circular `resample` is FAIR (chi-square 27.5 on 99 df). The first real run counted
duplicates as inclusions (rate 1.0, nothing flagged) - inclusion is now per distinct item. Planted 3, caught 3 (seed-ignored
check disabled, SHUNNED list emptied, outside-population items counted).

## Provenance
skill-foundry dry run 2026-10-16: "magicians-force: PASSES ALL GATES" (finder top hit test-expectation-oracle norm
0.20; metaphor BUILD - no library skill tests a sampler's inclusion distribution across seeds).

Pairs with self-attacking-referee (null audits), signal-nulls, bootstrap-ci, monte-carlo-paths, reservoir-sample.
