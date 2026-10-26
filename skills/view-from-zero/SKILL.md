---
name: view-from-zero
description: List everything a plan or text presupposes already exists (definite first mentions, re-verbs, possessives, named tools, implied accounts) as if starting from nothing. Use this whenever the user hands a plan to a fresh session or a new machine and wants the hidden prerequisites. Pairs with view-from-the-end, smuggled-premise and handoff-pack.
---

# view-from-zero

A **time** lens that reads the subject from an empty machine with no accounts and no history. It inventories every presupposition in five categories:

- **thing:** named with "the" before anything made it;
- **prior-state:** re-verbs such as rebuild, again or restart;
- **ownership:** our, the user's;
- **external:** capitalised tools, places and people;
- **access:** what verbs like land, push, download, tell or run quietly require (a repo with write rights, network and a source, a channel, a runtime).

## The tool (ships with this skill)

```
python view_from_zero.py <plan|text> [--kind plan|text] [--json]
python view_from_zero.py --selftest
```

```python
from view_from_zero import apply
v = apply(["download the stock bars", "rebuild the cache", "land the change on main"])
```

Example finding: `[thing] cache - named with 'the' before anything made it (line 2)`

## Uses and limits

- "A cache ... then the cache" correctly presupposes nothing, and making verbs create their object.
- It is heuristic phrase matching, so some flags are style ("the crowd") rather than real prerequisites. Read the list as a checklist, not a verdict.
- It names what must exist, not whether it does. Check the machine for that.
