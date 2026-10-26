---
name: birds-eye
description: Draw the dependency map of a plan or a Python file from above - the roots (nothing above), the sinks (nothing below), the hub with most links, every cycle including self-calls, and for plans the loose steps that only their order connects to anything earlier; code edges are plain-name calls inside one file, plan edges are shared noun stems between steps. Ships birds_eye.py (--kind code or plan, --json, --selftest). Use this whenever the user wants the overhead layout of a module or a multi-step plan before changing it, asks what depends on what, where the cycles are, or which step nothing else relies on. Not for the order to run steps in or the critical path (use topo-sort), and not for the hidden assumptions a bottom step makes about the steps above it (use worms-eye). Pairs with topo-sort, worms-eye and keystone-find.
---

# birds-eye

A VANTAGE lens of the point-of-view family (engine: pov-core). It shows the whole layout at once from above. For python code, it draws an edge f -> g when f calls g and both are defined in the file. For a plan, it draws an edge from step i to a later step j when they share a noun stem. It lists each node's links, the roots (nothing above), the sinks (nothing below), the hub (most links) and every cycle, self-calls included. For plans it also lists 'loose' steps that only the order connects to anything earlier.

## The tool (ships with this skill)

```
python birds_eye.py --selftest
python birds_eye.py <file.py|plan.txt> [--kind code|plan] [--json]
```
```python
from birds_eye import apply
apply("~/.claude/skills/pov-core/pov_core.py")["summary"]
```
Example: `[birds-eye] (code) 3 nodes, 2 edges; 1 roots, 2 sinks, hub main, 0 cycles`

## Uses and limits

- Code edges come from plain-name calls only. Method calls (`obj.f()`), imports and dynamic dispatch are invisible.
- Plan edges are a noun-overlap guess. The probe plan has no shared nouns, so every step is loose, which is itself the finding that its hand-offs are implicit.
