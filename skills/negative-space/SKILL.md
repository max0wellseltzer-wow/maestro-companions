---
name: negative-space
description: Diffs a text against a domain checklist for trading claims, plans or code changes and lists the checklist items it never mentions. Use this whenever the user reads a result or plan and wants to see what it does not say. Pairs with blind-spot-sweep, dark-matter, erase-the-center and pov-core.
---

# negative-space

An **around** lens: it reads the shape a text leaves empty. Three built-in checklists give the outline of a complete text:
- **trading**: costs, sample size, out-of-sample, drawdown, data source, benchmark, sizing, regime, multiple testing, paper vs live;
- **plan**: owner, deadline, success measure, rollback, budget, dependencies, verification, done-definition;
- **code**: tests, error handling, rollback, performance, secrets, docs, compatibility, edge cases.

The domain is picked by trigger words, or set with domain=. Each item is either COVERED, with the cue that matched, or ABSENT.

## The tool (ships with this skill)

`negative_space.py`: pure stdlib on top of pov-core. Selftest 6/6.

```
python negative_space.py <file|text> [--opt domain=trading|plan|code] [--json]
python negative_space.py --selftest
from negative_space import apply; apply(note, domain="plan")
```

Example (pov-core probe text):

```
[negative-space] (text) trading checklist: 8 of 10 items unsaid (sample size, out-of-sample, drawdown, benchmark, sizing, regime/period, multiple testing, paper vs live)
  - ABSENT   out-of-sample - the text never says
```

## Uses and limits

- A cue word counts as coverage even when it is used in passing ("data" covers data source). COVERED means the item is mentioned, not that it is handled well.
- The checklists are fixed. Extend CHECK in the tool for a new domain rather than forking the skill.
- Paper-only for trading claims.
