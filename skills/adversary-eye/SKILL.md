---
name: adversary-eye
description: List per plan step what an adversary controls and could tamper with, the check that would catch it, and the first unverified input. Use this whenever the user has a pipeline or landing plan that pulls outside data, runs code or pushes changes. Pairs with staged-secret-scan, fake-secret-sentinels and omniscient-narrator.
---

# adversary-eye

A **persona** lens that walks the plan as the attacker. Each step is classed by its verbs and nouns into six attack surfaces:

- **ingest:** the outside source and the wire;
- **at-rest:** the stored copy;
- **execute:** code, dependencies and environment;
- **measure:** the metric and its inputs;
- **publish:** branch, credentials and review gate;
- **message:** the channel.

For each surface it states how an adversary would tamper and which check would catch it. It also finds the FIRST UNVERIFIED INPUT: an ingest step with no later verify, hash, compare or audit step. Every step after that inherits whatever the input serves.

## The tool (ships with this skill)

```
python adversary_eye.py <plan> [--json]
python adversary_eye.py --selftest
```

```python
from adversary_eye import apply
v = apply(["download the prices", "hash and compare the prices with a second source", "run the screener"])
```

Example finding: `FIRST UNVERIFIED INPUT step 1: download the stock bars - nothing after it verifies the data, so 5 later step(s) inherit whatever it serves`

## Uses and limits

- The "adversary" includes accidents. A vendor that revises bars (TradingView does) acts like a tamperer.
- Classes come from a word list, so a step phrased in unusual words reads as "no surface named".
- It names the threats and the checks. It does not test whether the checks exist in the code.
