---
name: inner-critic
description: Writes the harshest specific critique question for each claim in a text, aimed at its weakest spot such as an unsourced number, an absolute word or a causal leap. Use this whenever the user drafts a claim or result note and wants the most cutting objection to each line. Pairs with skeptic-eye, opponent-lawyer, doubt-mind and pov-core.
---

# inner-critic

A PERSONA lens of the point-of-view family (engine: pov-core). The inner critic does not list every doubt; it goes for the throat. For each sentence the lens scores its weak spots by severity (performance number with no sample 5, absolute or certainty word 5, causal leap 4, appeal to a crowd 3, hedge 3, unsourced number 3, dated commitment 2, undefined condition 2) and asks ONE question at the worst one, quoting the sentence's own words. Claims are then ranked harshest first.

## The tool (ships with this skill)

```
python inner_critic.py --selftest
python inner_critic.py <file|text> [--json]
```
```python
from inner_critic import apply
apply("result_note.md")["findings"][0]["what"]
```
Example: `[5] "Win rate was 71% because the filter removes chop." -> win rate of 71 over how many trades, in which period, after what costs - and how many variants died before this one?`

## Uses and limits

- Weak spots are found by regex. A claim that is wrong without any marker word gets only the default question.
- One question per sentence by design; other weak spots are listed in `other_spots`.
- It attacks the wording, not the facts. Pair it with doubt-mind or numbers-pass to check the substance.
