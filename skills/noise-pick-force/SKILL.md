---
name: noise-pick-force
description: Test whether a selection procedure (pick the best lookback, parameter, model, universe or screen) is a magician's force - run it on many seeded pure-noise datasets and measure how its picks spread over its k options, with pick shares and Wilson intervals, a chi-square test against uniform and the normalised pick entropy; FORCED names the options it picks on noise far above 1/k (variance, edge effects, tie-breaking order), FAIR otherwise. Use this whenever a finder or optimiser chooses among options, when the same parameter keeps winning, when the user asks "is this choice real or built into the method?", "why does the longest lookback always win?", "would it pick this on random data?", and before reporting the winner of a sweep. Paper-only research. Pairs with pbo-overfit, deflated-sharpe, model-confidence-set, finders-discipline habits and symmetry-break.
---
# noise-pick-force

## The pitch [IMAGINED]
A card magician offers a "free choice" of any card, but the handling makes one card come to hand: the force.
A finder that offers "any lookback" but whose statistic is wilder for some options does the same: on pure noise
it hands you the same option, and a real-data win for that option is mostly the handling.

## The mechanism [REAL]
Plain statistics, nothing metaphorical: under a no-signal null, an unbiased argmax over k exchangeable options
picks each with probability 1/k. The tool estimates the pick distribution by simulation and tests it against
uniform. Selftest evidence: "pick the option with the best raw mean" where options have 10, 100 and 1000
observations picks the 10-sample option **45%** of the time on noise (fair = 33%), because its mean has the
widest spread; the same choice on t-statistics (equal null law) is FAIR (shares 0.35/0.31/0.35, p 0.62).
This is the finders-discipline rule (report the selection cost) made measurable for the selection step itself.
Closest live skill: pbo-overfit (probability the in-sample winner underperforms out of sample, from a CSCV split
of a performance matrix) - it scores the winner's out-of-sample rank on REAL data; noise-pick-force asks what the
procedure picks when there is nothing to find, and needs no real data at all. symmetry-break picks fairly from a
tie; this measures whether a pick was fair.

## Procedure
1. Wrap the selection as `choose(data) -> option label` and write `null(rng) -> data` that matches the real data's
   shape (same lengths, same number of trades per option) with the signal removed (demeaned or shuffled returns).
2. Run with every option listed (`--options`): an option never picked is information.
3. FORCED -> the winning option on real data must beat its own forced share: compare real-data wins with the
   null pick rate, or switch to a statistic with equal null law per option (t, not raw mean; Sharpe with equal
   trade counts). FAIR -> the selection step is not the problem (multiplicity still is: deflated-sharpe).

## The tool
```
python force.py proc.py:choose --null nullgen.py:null --options n10,n100,n1000 --reps 500
option          picks   share  Wilson95          (fair share 0.333)
n10               ...   0.45   [...]  FORCED
...
VERDICT: FORCED - on pure noise the procedure picks n10
python force.py --selftest
```
(shape of the selftest's best-raw-mean case). Exit 0 FAIR, 3 FORCED.

## Proof (selftest 8/8)
Chi-square tails match tables in both numerical branches (3.84/df1, 5.99/df2, 43.77/df30 -> 0.05; closed forms
for df 2 and 4); chi-square of counts 60/30/10 = 38.0; best raw mean FORCED onto the 10-sample option; best t FAIR
with no option flagged; tie-breaking by list order forced onto the first option; an unlisted option refused.
Planted 4, caught 4 (forced on raw share instead of Wilson bound, chi-square divided by reps, series-branch
off-by-one, unlisted option accepted).

## Provenance
- skill-foundry dry run 2026-10-16: `noise-pick-force: PASSES ALL GATES` (metaphor BUILD; finder top hit entropy-meter norm 0.18 vs 0.6; no collision; source-labels 1 REAL 1 IMAGINED). Renamed from magicians-force on 2026-10-16 because builder L_code_tests used that name for a different tool (seeded-sampler inclusion fairness).
- OUT THERE extra (card magic), K_evidence_stats, 2026-10-16.
