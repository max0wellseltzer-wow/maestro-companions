---
name: zealot-eye
description: Rewrites each claim into its absolutist form (some to all, often to always, may to must) and reports where the amplified claim breaks against counter-evidence elsewhere in the same text. Use this whenever the user wants to stress a belief by pushing it to its extreme to see where it stops being true. Pairs with pov-core, reverse-stress-test, smuggled-premise and skeptic-eye.
---

# zealot-eye

A **distort** lens: the zealot reads every softened claim at full strength. Quantifiers and modals are swapped for their extremes (`usually wins` becomes `always wins`, `small` becomes `zero`, `maybe` becomes `certainly`), and claims that are already absolute are taken as written. Each extreme is then tested against the rest of the same text. A sentence that shares a content word with it and carries a counter marker (lost, fails, except, but, not...) is its breaking point. An extreme with no breaking point is untested, not confirmed.

## The tool (ships with this skill)

`zealot_eye.py` - pure stdlib on pov-core, selftest 7/7. Reads `text` and `plan` (at least 2 claims).

```
python zealot_eye.py memo.md
python zealot_eye.py --selftest
```
```
from zealot_eye import apply, amplify      # amplify("Most bars are fine") -> ("All bars are fine", ["most->all"])
```
Example: `BREAKS #2 amplified [usually->always]: The strategy always wins. | broken by #3 on 'strategy' (lost): In March the strategy lost 9 percent.`

## Uses and limits

- Use it on theses, rules of thumb and "this usually works" claims before they harden into rules.
- The test bench is the text itself. A claim with no counter-evidence on the page stays UNTESTED, and the lens says so rather than calling it true.
- Matching on shared words is crude. It can pair sentences that share a word but not a subject.
