---
name: map-vs-territory
description: Compares numbers that docstrings and comments claim (lines, functions, checks, arguments, defaults) with what the code measures by ast, listing drifted claims and undocumented magic numbers. Use this whenever the user trusts a module's docstring or a skill's claimed counts. Pairs with declared-count, prove-the-read, decorative-check and pov-core.
---

# map-vs-territory

An EPISTEMIC lens of the point-of-view family (engine: pov-core). The docstrings and comments are the map, and the ast is the territory. Every documented count is checked against its measurement: N lines, N functions, N checks, N args and "param defaults to N". An exact count must match, "about N" passes within 25% and a range passes inside it. It then checks the other direction and lists the numeric literals in the code that no doc mentions, as undocumented magic numbers.

## The tool (ships with this skill)

```
python map_vs_territory.py --selftest
python map_vs_territory.py <file.py> [--json]
```
```python
from map_vs_territory import apply
v = apply("path/to/tool.py"); v["stats"]["drift"], v["stats"]["magic"]
```

Example: `[map-vs-territory] (code) 0 documented numbers checked: 0 drifted from the code; 3 undocumented magic numbers`

## Uses and limits

- It only reads claims that follow the patterns above. Prose like "a handful of checks" is not checked.
- A "checks" claim is measured as `ok[...] =` assignments or `test_` functions, which is the house selftest style.
- Reads Python code only. Unparseable code is refused.
