---
name: worms-eye
description: Start from the lowest step of a plan or the leaf functions of code and list upward what each bottom step must assume about everything above it. Use this whenever the user wants the hidden assumptions a foundation step carries for the steps that rely on it. Pairs with birds-eye, smuggled-premise and abort-modes.
---

# worms-eye

A VANTAGE lens of the point-of-view family (engine: pov-core). Where birds-eye looks down on the map, this one looks up from the ground floor. For code, functions are ordered by call height (leaves first). Each function's assumptions are read off its AST: args that are iterated, opened as files, divided by, indexed or attribute-read, plus globals it reads. Each assumption is paired with the callers above that must honour it. For a plan, step 1 is the floor. Each step gets its verb's precondition (download needs a reachable source, land needs checks passed on this exact tree, ...) and the hand-offs later steps take from it. A step that hands nothing named upward is flagged as an implicit hand-off.

## The tool (ships with this skill)

```
python worms_eye.py --selftest
python worms_eye.py <file.py|plan.txt> [--kind code|plan] [--json]
```
```python
from worms_eye import apply
apply(code_src, kind="code")["stats"]["assumptions"]   # {func: [assumption, ...]}
```
Example: `level 0 score assumes 'k' is never 0; above it main must honour that`

## Uses and limits

- The AST patterns are a short fixed list. Type expectations that come from library calls, and keyword-only args, are not read.
- The plan verb table covers about 15 common verbs. Other verbs get only the hand-off check.
