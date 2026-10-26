---
name: future-self
description: Lists a plan's irreversible steps (delete, push, publish, send, drop, overwrite) and deferred costs (later, TODO, temporary, skip) and phrases them as next-week and next-year regrets with a regret count per horizon. Use this whenever the user is about to execute a plan with a one-way door or a shortcut he may pay for later. Pairs with pov-core, abort-modes, sunk-cost-check and bystander-eye.
---

# future-self

A **time / persona** lens: the plan is read back by the user a week and a year from now. NEXT WEEK regrets are one-way doors, meaning steps whose verb cannot be undone (delete, push, land, send, rebuild...) unless the same step names its undo (archive, tag, backup, dry-run). NEXT YEAR regrets are deferred costs (for now, TODO, hardcode, manual) and things that keep growing on their own (logs, caches, nightly jobs). The first unguarded door is the point of no return.

## The tool (ships with this skill)

`future_self.py` - pure stdlib on pov-core, selftest 7/7. Reads `plan` and `text`.

```
python future_self.py plan.md
python future_self.py --selftest
```
```
from future_self import apply     # stats: next_week, next_year, guarded, point_of_no_return
```
Example: `[future-self] (plan) 3 next-week regret(s) (unguarded one-way doors), 2 next-year regret(s) (deferred or growing costs), 0 guarded door(s); point of no return at step 2 of 6`

## Uses and limits

- Use it before branch deletes, merges, migrations, posts and anything with "for now" in it. abort-modes turns the doors it finds into an abort plan.
- The verb lists are heuristic. "Tell" counts as one-way because a message cannot be unsent, even though it is often harmless.
- An undo counts only if it appears in the same step. An archive made two steps earlier is not seen.
