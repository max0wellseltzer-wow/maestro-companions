---
name: outsider-council
description: Scores a subject against the concern lexicons of a chef, pilot, nurse, judge and farmer, giving each outsider's coverage, the concern it finds missing and the sentence it would interrogate. Use this whenever the user wants a plan or note looked at by trades far from trading. Pairs with expert-eye, alien-anthropologist, role-rotation and pov-core.
---

# outsider-council

A PERSONA lens of the point-of-view family (engine: pov-core). It looks at a subject through five trades far from trading. Each trade carries four concerns from its own work:
- chef: prep order, timing, taste test, clean station;
- pilot: checklist, abort point, conditions, fuel budget;
- nurse: dose, monitoring, side effects, consent;
- judge: evidence, burden, precedent, other side;
- farmer: season, patience, yield, bad weather.

The lens measures which concerns the subject already covers and names the ones it leaves out. For each outsider it also picks the sentence that outsider would interrogate first.

## The tool (ships with this skill)

```
python outsider_council.py --selftest
python outsider_council.py <file|text> [--json]
```
```python
from outsider_council import apply
v = apply(plan_text); v["stats"]["coverage"], v["stats"]["alarmed"]
```

Example: `[outsider-council] (text) five outsiders: the judge is most at home (100%), the chef most alarmed (25%); 8 trade concerns uncovered`

## Uses and limits

- Coverage is cue-word presence. "We check" counts as a checklist even if nothing is checked.
- The five trades and their cue lists are fixed and hand-written. They act as prompts for missing concerns, not as experts.
- Reads text and plans.
