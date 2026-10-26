---
name: view-from-the-end
description: Start from a plan's goal step and back-chain the preconditions each earlier step must deliver, listing unmet preconditions and steps the goal never reaches. Use this whenever the user has a plan and wants to know which steps the result really depends on. Pairs with view-from-zero, topo-sort and abort-modes.
---

# view-from-the-end

A **time** lens that runs the plan backwards from its goal. Each step gets a contract:

- **Making verbs** (download, build, write, compute ...) deliver their objects.
- **Other verbs** need their objects.
- **Every step** delivers "its result", which is what "the result / the change" refers to.

Walking back from the goal, a step joins the chain only if it delivers something the chain still needs. The output names four things:

- the chain;
- the **UNMET** preconditions, which nothing delivers and so must already exist;
- the **OFF-CHAIN** steps, whose output the goal never needs;
- any **ORDER** violation, where a step needs something only a later step makes.

## The tool (ships with this skill)

```
python view_from_the_end.py <plan> [--opt goal=STEP_NO] [--json]
python view_from_the_end.py --selftest
```

```python
from view_from_the_end import apply
v = apply(["fetch the prices", "send the report to the user", "build the report from the prices"])
```

Example finding: `ORDER step 2 needs 'report' which only a later step makes`

## Uses and limits

- An OFF-CHAIN step is either wasted work or an unstated link. The lens cannot tell which, so it names both.
- Contracts come from the first-word verb and word overlap, a heuristic. Steps phrased without a verb first are misread.
- Proper names (people) are never treated as preconditions.
