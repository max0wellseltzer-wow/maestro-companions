---
name: peacock-tail
description: Honest-advertising audit of the skill library - for each tool-backed skill, extract what its SKILL.md claims (functions named in code spans and from-imports, claimed selftest pass counts, the capability clauses of its description) and check each claim against the tool - identifiers it really defines or uses, the PASS/FAIL lines its selftest really prints, and the words in its function names, docstrings and selftest check names - then rank skills by over-claim score. Use this whenever the user asks whether skill descriptions are honest or inflated, after a skill wave or a merge, before trusting a selftest count in a SKILL.md, or when a skill promises more than it seems to do. Pairs with mutation-audit, skill-health, route-audit, exaptation-finder, collision-registry and skill-finder.
---

# peacock-tail

Born from the user's nature prompts. The seed is **sexual selection**: the peacock's tail does nothing for survival and exists to be noticed. Biology's check on showy traits is the handicap principle: trust a signal only when it is costly to fake. A SKILL.md description is a signal, because it decides whether the router picks the skill. The tool is the body. This audit asks, claim by claim, whether the body backs the signal.

## The tool (ships with this skill)

`peacock.py` - pure stdlib + exaptation-finder and skill-finder, selftest 8/8 (synthetic library, about 7 s):

```
python peacock.py --run                     # whole library; runs every selftest (no args = selftest)
python peacock.py --only a,b --no-run       # quick static pass on some skills
python peacock.py --run --top 25
from peacock import audit, audit_skill, clauses, code_spans, tool_facts, run_counts
```

Three kinds of claim are checked:

- **Named functions.** A name followed by an open parenthesis, bare or after the tool's module name, inside code spans (fenced blocks, indented examples, `inline` code) and `from module import a, b` lines are checked against every identifier the tool's code defines or uses. Prose such as "word(s)" is not a claim. Flagged as "not defined".
- **Selftest counts.** A pass count written after the word selftest (n/n) is compared with the number of PASS/FAIL lines the tool's `--selftest` really prints. The selftest is run from a neutral cwd with `-B` and a 60 s timeout. A claim passes if it matches one tool's count or the sum over the skill's tools. Flagged as "count".
- **Capabilities.** The description before its "Use this/when" trigger is split into clauses. A clause with no content word anywhere in the tool's function names, argument names, docstrings or selftest check names is flagged as "unbacked".

Score = 2 per missing function + 3 per wrong count + 1 per unbacked clause. Doc-only skills have no body to check and are left out.

Real run (2026-10-15, selftests run): 257 tool-backed skills, 80 with at least one unbacked claim. Most over-claiming:

- windows-port-audit (11): names file methods it hunts for, and three clauses (ctypes handles, POSIX-only modules, case-twin globs) leave no trace in function names, docstrings or check names.
- candidate-then-gate (8): documents `match` and `cross_venue_candidates`, which live in <workspace> experiments, not in `gate_eval.py`.
- writer-pen (7).
- bootstrap-ci (5): a coverage figure read as a selftest count (a false positive).
- research-spine (5): the 4/4 refers to nerve_center.py in Autotrade, while the shipped `spine_check.py` prints 6.

This tool's own first draft was flagged too, for example text and an inline 7/7 in its description, and was reworded.

## Uses and limits

- A flag is a prompt to look, not a verdict. A clause can be true in prose the matcher cannot see; windows-port-audit names file-reading methods because those are the calls it hunts, not calls it makes. A SKILL.md that documents code in another repo (<workspace> experiments) is flagged too, because that code is not in the shipped tool. A count is flagged only when it follows the word selftest, but a coverage figure placed there (bootstrap-ci's "56/60 coverage") still trips it. A genuinely wrong selftest count is plainly stale. Fix the SKILL.md.
- Word overlap is a weak test of capability. The handicap-grade check is a selftest that exercises the claim. mutation-audit tells you whether those tests can fail.
- `--run` executes every tool's selftest, which takes minutes on the full library. Keep it serial on this machine and use `--only` while iterating.
