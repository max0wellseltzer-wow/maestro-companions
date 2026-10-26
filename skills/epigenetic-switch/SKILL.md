---
name: epigenetic-switch
description: Change behavior without changing the underlying code/config - keep a frozen base ('genome') and a separate overlay of environment-set marks that switch features on/off, where the base is never mutated, a child inherits the parent's marks, and clearing the marks reverts exactly to the base. Use this whenever the user wants feature flags, environment-specific overrides, per-run toggles, A/B variants, or config layering WITHOUT editing the base config, or asks to "turn X on for this run/env only" or "override without touching the defaults". A reproduction-family skill (epigenetics); pairs with reading-dial (an overlay that changes behaviour, not code), metamorphose and update-config (the built-in settings skill).
---

# epigenetic-switch

Epigenetics is the trick where the DNA never changes but marks on top of it switch genes on and off - and those marks are inherited. It is exactly the right model for configuration: keep one frozen base (the genome) and a separate overlay of marks that the environment sets. Behavior reads base + marks, the base is never edited, and a child run inherits the parent's marks and can then diverge. The payoff is that you can always revert to the genome by clearing marks - the defaults were never corrupted.

## The tool (ships with this skill)

`epigenetic_switch.py` - pure stdlib, deterministic, selftest 6/6:

```
from epigenetic_switch import effective, set_mark, inherit, clear_marks
cfg = effective(base, marks)          # base overlaid by marks; base untouched
marks = set_mark(marks, "risk", "on") # returns a NEW overlay (history stays clean)
child = inherit(marks)                # a child run carries the parent's marks
marks = clear_marks()                 # expression reverts exactly to the genome
python epigenetic_switch.py --selftest
```

## Why not just edit the config

Editing the base config to flip a flag for one run is how defaults rot: the override gets forgotten and becomes the new "default", and you can no longer tell what the real baseline was. Keeping marks separate means the genome is always recoverable and always auditable (you can see exactly what the environment switched). Use it for per-env overrides, per-run toggles, and inheritable experiment variants; when a mark should become permanent, promote it into the base deliberately (via update-config), not by accident.
