---
name: chimera
description: Deliberately fuse three or more parents and find where the combination BREAKS - report clashing invariants (one part wants paper-mode, another live-mode) and requirements no part satisfies, so impossible combinations are caught before you build them. Use this whenever the user wants to combine several components/configs/services and check compatibility, stress-test whether N things can coexist, find the contradiction in a proposed integration, or asks "can we wire all of these together?". The red-team of cross-breed; a reproduction-family skill (chimera); pairs with cross-breed and symbiosis.
---

# chimera

Cross-breed looks for a vigorous child; chimera is its adversary - it fuses many parents on purpose to find the fault lines. A chimera (an organism of several parents' tissues) is viable only if the tissues don't contradict, and the useful output when they do is the exact contradiction: which invariant two parents disagree on, and which requirement nobody satisfies. Finding that a combination is impossible - cheaply, before building - is worth as much as finding one that works.

## The tool (ships with this skill)

`chimera.py` - pure stdlib, deterministic, selftest 6/6:

```
from chimera import chimerize
r = chimerize([
    {"name": "loader",   "provides": {"load"},  "requires": set(),      "invariants": {"mode": "paper"}},
    {"name": "executor", "provides": {"order"}, "requires": set(),      "invariants": {"mode": "live"}},  # clash
])
# r = {viable, conflicts, unmet_requires, provides, invariants}
python chimera.py --selftest
```

- **conflicts**: two parents assert different values for the same invariant (e.g. `mode: paper` vs `mode: live`) - named, so you see the contradiction.
- **unmet_requires**: something a parent needs that no parent provides.
- **viable** is True only when there are no conflicts and no unmet requirements.

## Why red-team a combination

Most integrations fail not because any part is bad but because two parts hold incompatible assumptions - and that surfaces late, at runtime, expensively. Declaring each part's provides/requires/invariants and chimerizing them turns that into a pre-flight check. Use it before wiring several components together; when you instead want to know whether a *pairing* helps both sides, use symbiosis, and when you want a vigorous offspring rather than a stress test, use cross-breed.
