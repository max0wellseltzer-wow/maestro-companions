---
name: lot-acceptance
description: Acceptance sampling for long lists of claims, borrowed from factory quality control - with exact hypergeometric arithmetic say how many of N claims, rows, receipts or "done" items to re-verify so a lot with at least D bad ones (or a bad rate p) is caught with confidence C, draw that sample reproducibly from a seed BEFORE looking, and after checking give the exact upper bound on how many bad items the lot can still hold, with ACCEPT, REJECT or SAMPLE-TOO-SMALL. Use this whenever a peer report, packet, ledger, receipt list or scan output has too many claims to re-check them all, when the user asks "how many of these do I need to verify?", "can I trust the rest if 20 checked out?", "spot-check this", and before signing off a batch on a handful of checks. Pairs with peer-verify and sprt-sequential.
---
# lot-acceptance

## The pitch [IMAGINED]
A bolt factory cannot test every bolt, so it tests a sample and accepts or rejects the lot (Dodge and Romig's
sampling tables, later MIL-STD-105). A peer report with 120 numbers, a 400-row ledger or 60 "done" items is a lot.
Re-verifying three proves almost nothing; re-verifying all is too dear. The sample size is arithmetic, not a feeling.

## The mechanism [REAL]
Hypergeometric probabilities with `math.comb` (sampling without replacement from a finite lot): the smallest n with
P(catch at least one of D bad) >= C, the exact upper bound on bad items after finding k in n, a seeded draw by
item number or file line. Closest live skills: reservoir-sample draws a uniform sample from a stream but says nothing
about how big it must be or what it proves; sprt-sequential tests a rate as evidence arrives; peer-verify reruns
claims one by one. Real numbers from the tool: to catch 6 bad items in a lot of 120 with 95% confidence you must
re-verify 47 (and that sample catches a single bad item only 39% of the time).

## Procedure
1. Count the lot N and decide what you must not miss: D bad items (or a rate) and confidence C. `plan`.
2. `draw` the sample with a seed written down first (the seed in the receipt makes the pick auditable).
3. Verify exactly those items (peer-verify, numbers-pass, a rerun).
4. `bound` with the number found bad. ACCEPT: zero bad and the bound is within what you can tolerate. REJECT: any bad
   item - re-verify everything or send it back. SAMPLE-TOO-SMALL: zero found but the sample cannot rule out the
   tolerated level; draw more.

## The tool (real output)
```
python lot.py plan 120 --defects 6
lot 120, catch >= 6 bad with 95%: re-verify n = 47 (accept only if all 47 check out)
  power vs    1 bad: 0.392
  power vs    3 bad: 0.779
  power vs    6 bad: 0.953
  power vs   12 bad: 0.998
python lot.py bound 120 38 --found 0 --max-bad 6
found 0 bad in 38 of 120: at most 7 bad in the lot (5.8%) at 95% -> SAMPLE-TOO-SMALL
python lot.py draw claims.txt 47 --seed 20261016
python lot.py --selftest
```

## Proof
Selftest 12/12: p_zero against the product formula; plan(100, 5, 95%) = 45 and minimal; fewer than the binomial
bound; an all-bad lot needs 1; the cdf sums to 1; the bound sits exactly at the 5% edge; a full census bound equals
the count found; more bad found raises the bound; a 4000-lot simulation agrees within 2%; draw is reproducible, in
range and numbered from 1.
Planted 5, caught 4; the survivor (bound loop starting at 0 instead of k) is an equivalent mutant: the cdf is
monotone in D, so the loop lands on the same bound.

## Pairs with
peer-verify (what to do with each sampled claim), sprt-sequential, reservoir-sample, bootstrap-ci, mark-recapture
(how many problems no checker saw).

## Provenance
- skill-foundry dry run 2026-10-16: `lot-acceptance: PASSES ALL GATES` (finder top hit reservoir-sample norm 0.19 vs 0.6; metaphor BUILD; no collision).
- OUT THERE extra (manufacturing quality control), built for the N2 claims group.
