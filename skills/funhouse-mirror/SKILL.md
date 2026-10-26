---
name: funhouse-mirror
description: Scales each weight of an item-scoring rule by ten and by a tenth and lists which conclusions (the leader, the top half, the last place) survive each distortion. Use this whenever the user ranks options with a weighted score and wants to know which weights the ranking hangs on. Pairs with reverse-stress-test, pbo-overfit and pov-core.
---

# funhouse-mirror

A **distort** lens. It stretches one weight at a time by 10x and by 0.1x and watches the ranking in the warped mirror. A conclusion that looks the same in every mirror does not depend on the weights. One that warps under a single stretch was decided by that weight, often a weight nobody chose carefully.

## The tool (ships with this skill)

`funhouse_mirror.py`: pure stdlib on top of pov-core. Selftest 6/6.

```
python funhouse_mirror.py <items.json|table.csv> [--opt weights=sharpe:1,turnover:-0.2,drawdown:-1] [--json]
python funhouse_mirror.py --selftest
from funhouse_mirror import apply, conclusions
```

Example (pov-core probe items, default weights +1 benefit, -1 costs):

```
[funhouse-mirror] (items) weights {'sharpe': 1.0, 'turnover': -1.0, 'drawdown': -1.0}; robust conclusions: leader; fragile: top half, last place
  - last place reversion survives 5/6 distortions; hangs on sharpe x10
```

The score is a weighted sum of raw columns. By default the first numeric column gets +1 and the rest get -1. The three conclusions are the leader, the top-half set and the last place. Each distortion line names the conclusions it broke and what they became.

## Uses and limits

- It scores on raw columns, so the units matter. That is the point: a column measured in bigger units silently carries more weight.
- One weight at a time. Joint distortions and interactions are not explored; for the full worst case, use reverse-stress-test.
- Paper-only for strategy rankings.
