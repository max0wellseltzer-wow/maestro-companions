---
name: exaptation-finder
description: The skill library's function index - walks every tool .py with ast, records each public top-level function (skill, file, args with defaults, docstring line, return hints, lines), ranks them for a plain-language need by TF-IDF over name, argument and docstring words so existing code gets reused before new code is written, and maps the blast radius of changing one function (direct callers, transitive callers, selftests, SKILL.md mentions). Use this whenever the user or a session is about to write a helper, asks "do we already have a function that does X?", wants to reuse code across skills, or is about to change a shared function and asks what will break. Pairs with skill-finder, convergence-detector, peacock-tail, skill-finder, skill-graph and collision-registry.
---

# exaptation-finder

Born from the user's nature prompts. The seed is **exaptation**: a trait that evolved for one job gets co-opted for another, as feathers grew for warmth and later carried flight. Library code works the same way. A Gauss-Jordan inverse written for hac-regression is exactly what cointegration needs. skill-finder searches skills; this searches the functions inside them, so a need is matched to code that already exists before anyone writes a fresh copy.

The same index answers the reverse question, "who depends on this?" That half was merged in from pleiotropy-map (see below).

## The tool (ships with this skill)

`exaptation.py` - pure stdlib + skill-finder's tokeniser, selftest 13/13 (synthetic library in a temp dir, about 2 s):

```
python exaptation.py "invert a square matrix" --top 5      # rank functions for a need
python exaptation.py --impact matrix-lite:matrix_lite.inv  # blast radius of changing one function
python exaptation.py --stats                               # index size, unparsable files
from exaptation import index_functions, find, impact, build_graph, tool_files, skill_dirs, parse
```

- `index_functions(root, include_private=False, keep_ast=False, errors=None)` returns one record per top-level function: `skill, file, module, name, args` (defaults rendered, keyword-only included), `arg_names, doc` (first docstring line), `returns` (the annotation, or a sketch of the return statements such as `dict{distance,ops}` or `tuple(2)`), and `lines`. It skips test_* files, evals/, synced/ and __pycache__. A file that does not parse is skipped and reported, and the walk continues.
- `find(need, root, top)` ranks functions by TF-IDF over snake_case name tokens (counted double), argument names and the docstring line. It gives partial credit to abbreviations, so `inv` answers "invert". It returns [] rather than noise.
- This is the shared index: convergence-detector, peacock-tail and skill-finder's salvage import it instead of keeping their own walkers.

First run (2026-10-15): 1014 public functions in 246 skills, 0 unparsable. "invert a square matrix" puts `matrix-lite:matrix_lite.inv` first with score 9.0. The next hit scores 3.4.

## Blast radius (merged from pleiotropy-map)

**Pleiotropy**: one gene shapes many traits, so a mutation that fixes one trait can break three others. `impact("skill:module.func")` builds a function-level reference graph and walks it backwards from the target. The graph covers every tool and test_* file. Imports are resolved per file: `from m import f as g`, plus `import m as x` with `x.f`. A local function that only shares the name does not count as a caller, and neither does a parameter that shadows the import. It reports:

- tier 1: direct callers, in the same module or in importers;
- tier 2 and up: transitive callers (`main` and module-level code are walked but not listed);
- tests: the `_selftest` and test_* units that would notice the change;
- docs: skills whose SKILL.md mentions the function;
- blast radius: the number of distinct skills touched.

First run on `matrix-lite:matrix_lite.inv` (2026-10-15): blast radius **10 skills**. Tier 1 has 7 direct callers: adf-test `_t_of`, black-litterman `posterior` and `weights`, cointegration `_solve`, hac-regression `_inv`, and matrix-lite's own `solve` and `_selftest`. Tiers 2 to 5 reach frac-diff, markov-chain, mda-importance, pair-trade-vet and signal-vetting through `solve`, `adf` and `ols`. 10 selftests exercise it. Only matrix-lite's own SKILL.md mentions it.

## Uses and limits

- Search before you write a helper. If a hit is close but private (`_x`), import the public function that wraps it, or promote it in its own skill. Do not copy it.
- Run `--impact` before changing a shared function. Then run the listed selftests, or skill-health with `--only` and the listed skills.
- The search ranks by word overlap only. A function with no docstring and a terse name is hard to find. That is also a sign it needs a docstring.
- Static analysis cannot see `getattr`, `importlib` or functions passed around as values under other names, so the blast radius is a lower bound.
