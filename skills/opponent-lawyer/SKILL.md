---
name: opponent-lawyer
description: Finds exploitable ambiguity in a rule or contract text - may versus shall, any versus all, an inclusive or, undefined reasonable-type terms, missing time bounds and dangling exceptions - and writes the hostile reading for each. Use this whenever the user writes a rule, a decision row, a terms clause or a guard that someone could read against him. Pairs with pov-core, terms-reader, rule-conflict and hostile-caller-pass.
---

# opponent-lawyer

A **persona** lens: every clause is read by opposing counsel looking for a way to do less, do something else, or never do it. It finds nine traps:
- permissive may and can;
- should used as a soft duty;
- any (one instance of their choosing is enough);
- all (one missing case voids the clause);
- an inclusive or, and and/or;
- elastic terms (reasonable, promptly, small, etc.);
- exceptions (unless, except, subject to);
- undefined actors;
- duties with no deadline.

Each hit carries the hostile reading. Exposure is the weighted sum of hits, and the weakest clause is named.

## The tool (ships with this skill)

`opponent_lawyer.py` - pure stdlib on pov-core, selftest 7/7. Reads `text` and `plan`.

```
python opponent_lawyer.py DECISIONS.md
python opponent_lawyer.py --selftest
```
Example: `[permissive] clause 1: 'may' grants a right, not a duty - I may simply not do it - "The operator may run the backup."`

## Uses and limits

- Use it on decision rows, skill rules, guard hooks' stated policies, and terms a data source makes the user accept. terms-reader reads the vendor's terms. This lens reads the user's own.
- It reads words, not intent. "May" in "May 5" or a list's "or" that is exclusive by context are false hits. `either ... or` is skipped.
- It finds where a reading can be twisted. It does not say which reading a court or a reviewer would choose.
