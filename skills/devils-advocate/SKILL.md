---
name: devils-advocate
description: Finds each conclusion sentence, classifies it (causal, numeric, absolute, forecast, recommendation) and writes a counter-argument from a template filled with that claim's own cause, number or subject, with an exposure score. Use this whenever the user states a conclusion and wants it argued against before acting. Pairs with steelman, skeptic-eye, swap-cause-effect and pov-core.
---

# devils-advocate

A VANTAGE lens of the point-of-view family (engine: pov-core). It takes the other side of every conclusion. Each sentence with a verdict marker is classified by its most attackable form (causal, absolute, recommendation, forecast, comparison or numeric). It is negated into a COUNTER-CLAIM ("will" -> "will not", "always" -> "not always", "better" -> "worse") and given a counter-reason built from its own cause, effect or number. An exposure score out of 5 (absolute word, no number, no source, single cause, future tense) orders which conclusion to attack first.

## The tool (ships with this skill)

```
python devils_advocate.py --selftest
python devils_advocate.py <file|text> [--json]
```
```python
from devils_advocate import apply, negate
v = apply(note); v["findings"][0]            # the most exposed conclusion and its counter
negate("We will launch next week.")         # -> 'We will not launch next week.'
```

Example: `[devils-advocate] (text) 5 conclusions argued against; attack s1 first (causal, exposure 3/5)`, whose top finding is `[causal, exposure 3/5] s1: COUNTER We will not obviously launch the new screener next week because ... - 'we will obviously launch the new screener next wee' could happen without 'the bac...`

## Uses and limits

- The counters are arguments to test, not findings. A counter can be weaker than the claim.
- Negation is a word-level rewrite and can produce awkward grammar.
- Reads text and plans. Sentences without a verdict marker are left alone.
