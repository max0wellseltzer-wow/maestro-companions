---
name: reproductive-strategy
description: Decide how to generate candidates for a task - clone the best (asexual), cross two parents (sexual, paying the two-fold cost), broadcast many cheap careless variants (r) or make a few careful refinements (K) - by simulating all four under one budget on a fitness landscape whose optimum moves at a given rate, with a defect load per candidate, and reporting the winner, the scores and a regime map over change rate and defect rate. Use this whenever the user asks whether to tweak the current best or try many wild variants, how many candidates to generate and how carefully, whether combining two good versions beats refining one, or how the answer changes when the target keeps moving (markets, shifting requirements). Pairs with broadcast-spawn, egg-lay, evolution-arena, cross-breed, red-queen and candidate-then-gate.
---

# reproductive-strategy

Seed: **sex vs cross-pollination x generate-then-cull x egg laying**. Biology runs four ways of making offspring, and the theory says which pays when:
- **Asexual cloning** is cheap and precise.
- **Sex** pays the **two-fold cost** (Maynard Smith 1978, *The Evolution of Sex*: only half the parents bear young). In return it recombines.
- **r-selection** spawns many cheap, careless offspring.
- **K-selection** raises a few, carefully (MacArthur & Wilson 1967; Pianka 1970).

The **Red Queen hypothesis** (Van Valen 1973; Bell 1982) says variation-making strategies win when the environment keeps moving, and precision wins when it holds still. The tool tests that prediction instead of assuming it. The numbers below are this model's settings, not values from the papers.

## The tool (ships with this skill)

`repro.py` - pure stdlib, seeded, selftest 7/7 (about 3 s):

```
from repro import Setting, run, compare, regime_map, format_map
c = compare(Setting(change_rate=0.3, defect_rate=0.1, budget=32, sigma=0.05, dims=8))
c["winner"], c["ranking"], c["scores"], c["candidates_per_gen"]
print(format_map(regime_map(change_rates=(0, 0.05, 0.2), defect_rates=(0, 0.3))))
python repro.py compare change_rate=0.2 defect_rate=0.1
python repro.py map
```

| strategy | cost per candidate | step size | defect rate |
|---|---|---|---|
| clone | 1 | sigma | base |
| sex (from a carried pool of 8) | 2 | sigma | base |
| r | 1/4 | 4 sigma | 2x base |
| K | 4 | sigma/2 | base/4 |

- Defective candidates are born dead and their budget is wasted.
- The best individual is kept (elitism). The score is minus the mean distance to the **current** optimum after burn-in, which measures how far the strategy lags behind a moving target.
- Selftest numbers. Static landscape: clone -0.050, sex -0.073, K -0.116, r -0.147, so precision wins. Optimum moving 0.4 per generation: r -0.62 while every other strategy loses the target (about -10 to -13), so exploration wins. The regime map holds with a 0.3 defect rate.

## Uses and limits

Use it to decide whether to refine the current champion or broadcast variants (prompt variants, parameter sweeps, strategy mutations), and how that choice shifts as the target drifts. Measure your own drift rate first. Then map `change_rate` to "how far the right answer moves between iterations" and `sigma` to your typical edit size.

Honest finding: on this smooth single-peak landscape, **sex never wins**. r takes the fast regime, and crossover between near-identical parents adds little. Recombination's real advantages need epistasis, clonal interference (`mutated_genes=2` gives sparse mutation, the Fisher-Muller setting), or coevolving parasites, and this landscape has none of them. Use `mullers-ratchet` and `cross-breed` when the gain from combining is concrete: two versions with fixes in different places. The costs and multipliers are dials, not measurements, so set them to your real costs before believing a winner.
