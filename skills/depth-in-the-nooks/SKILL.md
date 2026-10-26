---
name: depth-in-the-nooks
description: Check that every enumerated item of a plan section has its depth line - for each "Depth in the nooks of §X" block find section X, list its numbered items and sub-headings, match each to a depth bullet by number or shared title word, and flag NO_DEPTH items, depth lines that cite no concept id (NO_CONCEPT), named theorems, laws or caveats with no status (THEORY_NO_STATUS - mark CITED-UNVERIFIED until checked) and blocks whose section is missing. Use this whenever a plan section gains items or a depth block, when the user asks whether the plan's depth is complete, before citing a section as conceptually grounded, and after splicing new items into a plan.
---
# depth-in-the-nooks

## The problem
THE_ONE_PLAN §CD.10 (2026-10-13) asked for one depth line per enumerated item - concept, why, needs, breaks, so - and
the plan grew 53 "Depth in the nooks of §X" blocks by hand. Nobody could say which items were still bare. The first
run (2026-10-16): §BD is complete (15 items, 0 problems), but across all 53 blocks there are 465 items with no
matching depth line (§V: 15 items, 1 depth line), 23 depth lines leaning on a named theorem or caveat with no
status (e.g. "the Knight & Leveson caveat" without CITED-UNVERIFIED in that line), 9 lines with no concept id and 3
blocks whose section heading does not exist.

## Procedure
1. Run with `--summary` to see items / depth lines / problems per block; pick the worst blocks.
2. `--only TAG` lists the bare items of one section; write one depth line each (`- **Item n title** - Cn. why;
   Breaks: ...; So: ...`).
3. Give every named theorem, law, bound or caveat a status in the same line.
4. Matching is a heuristic (number in the label, or a shared title word of 4+ letters): a NO_DEPTH row may be an item
   covered under another wording - rename the label so it matches, which also helps readers.

## Tool
```
python depth_nooks.py <workspace>\plans\tv_blend_v3_raw\THE_ONE_PLAN_2026-10-13.md --summary
  §V      items 15   depth lines 1    problems 15
  53 depth block(s), 836 items, 500 problem(s): NO_CONCEPT 9, NO_DEPTH 465, NO_SECTION 3, THEORY_NO_STATUS 23
python depth_nooks.py THE_ONE_PLAN_2026-10-13.md --only BD
  1 depth block(s), 15 items, 0 problem(s)
python depth_nooks.py --selftest      # 10 PASS lines
```
Exit 0 every item has depth, 1 problems, 2 bad arguments.

## Proof
Selftest 10/10. Planted 7, caught 7 (`_work/p_depth.json`: number match, word match, concept id, theory status,
sub-bullet folding, section prefix (`HR.` vs `HR.1`), sub-heading items).

## Provenance
skill-foundry dry run 2026-10-16: `depth-in-the-nooks: PASSES ALL GATES (dry run - nothing created)` (top finder hit
hr-diagram norm 0.18). Source [REAL: <workspace>\plans\tv_blend_v3_raw\skills\depth-in-the-nooks\SKILL.md; plan CD.10].

Pairs with concept-card (the concept ids the depth lines cite), gradable-acceptance, additions-only-splice (add the
depth lines without touching old text) and research-integrity.
