---
name: means-ends-swap
description: Links plan steps by the nouns they share, then swaps means and ends to list steps that serve nothing downstream, steps nothing motivates, and what the final goal would serve if it were only a means. Use this whenever the user writes a plan and wants to check that every step feeds the goal and the goal feeds something. Pairs with upstream-view, downstream-view, view-from-the-end and pov-core.
---

# means-ends-swap

A **value** lens that swaps purposes. A step is a means to a later step when the two share an object noun. With means and ends swapped, the lens asks four questions:
- What does the goal serve if it is only a means? The last step feeds nothing in the plan, so its purpose is unstated.
- Which middle steps are ends in themselves? These are dead-end means that feed no later step.
- Which steps does nothing earlier make necessary? These are unmotivated.
- Which adjacent steps could swap with no loss? These have an unforced order.

## The tool (ships with this skill)

`means_ends_swap.py`: pure stdlib on top of pov-core. Selftest 6/6.

```
python means_ends_swap.py <plan.md|"- a\n- b"> [--json]
python means_ends_swap.py --selftest
from means_ends_swap import apply; apply(["fetch the prices", "clean the prices", "write the report"])
```

Example (pov-core probe plan):

```
[means-ends-swap] (plan) 6 steps, 0 means->end links; 5 dead-end means, 5 unmotivated, 5 unforced adjacent orders
  - goal as a means: 'tell the user the result' feeds nothing in the plan - its purpose is unstated
```

Zero links is the real finding for that plan. Its steps never name a shared artifact (bars, cache, screener, record), so the dependencies exist only in the writer's head.

## Uses and limits

- Links are lexical: "rebuild the cache" and "run the screener" are unlinked even though one feeds the other. Write the artifact into each step to make the link visible.
- The first word of each step is taken as its verb and skipped.
- For which steps the goal truly needs, use ablation-ladder; for cycles, use ouroboros.
