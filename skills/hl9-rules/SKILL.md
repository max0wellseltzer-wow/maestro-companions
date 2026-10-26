---
name: hl9-rules
description: Lint a report to the user or a plan item against the fifteen mechanical rules of HL9 (R1-R15) and print all fifteen rows, so no rule is skipped silently - the text-decidable ones are checked here (reading block with 2 BURNED readings, hedges tied to artefacts, completion words only with BEYOND_DONE and labelled guarantees, p-values with tries and results with baselines, no bare no-edge verdict, answer-first ledger with NOT RUN, five CYST answers and a filed hostile review); the rest print NOT_CHECKED with the skill that decides them, or EVIDENCED from an --evidence file, and --strict fails any without evidence. Use this whenever a report, receipt or landing note is about to go to the user, before an item is claimed done, and when the user asks whether a report followed the rules.
---
# hl9-rules

## The problem
THE_ONE_PLAN PART 5 / HL9 (2026-10-13) made fifteen mechanical rules LAW for every item and every report, each "one
check in tools/plan_counts.py --items and in tools/report_lint.py" - and neither tool was ever written (the plan's
own K-card audit lists both as NOT FOUND). So the rules were applied by memory, and the ones that need a tool were
skipped without anyone saying so. Run on a real subagent report rescued 2026-10-16, the lint gives FAIL 3 (no reading
block; no ledger or NOT RUN; no CYST or filed review), PASS 4, NOT_CHECKED 8 - which is the honest state of most
reports in this workspace.

## Procedure
1. Before sending a report, run the lint on it.
2. Fix every FAIL in the text (add the reading block, tie each hedge to an artefact, put tries beside each p, a
   baseline beside each result, a floor beside each "no edge", the ledger and NOT RUN, the CYST answers).
3. For each NOT_CHECKED rule either run the named skill and pass its output file with `--evidence ev.json`
   (`{"R5": "plants.json", ...}`) or say in the report that it was not checked.
4. Use `--strict` in a gate: an unevidenced rule then fails.

## Tool
```
python hl9_lint.py _work\rescued_a0941010.md
  R1   reading block                  FAIL         no READING block
  R14  four looks + ledger + NOT RUN  FAIL         first line is not an answer; no DONE / RUNNING / BLOCKED / NOT STARTED ledger; no NOT RUN line
  15 rule(s): FAIL 3, NOT_CHECKED 8, PASS 4
python hl9_lint.py report.md --evidence ev.json --strict
python hl9_lint.py --selftest      # 14 PASS lines
```
The text rules are regex heuristics: a PASS means no violation was found in the wording, not that the work is sound.
Exit 0 no FAIL, 1 a FAIL (or an unevidenced rule under --strict), 2 bad arguments.

## Proof
Selftest 14/14. Planted 8, caught 8 (`_work/p_hl9.json`: BURNED count, hedges, BEYOND_DONE exemption, p tries, floor,
NOT RUN, strict on unchecked rules, CYST answer count).

## Provenance
skill-foundry dry run 2026-10-16: `hl9-rules: PASSES ALL GATES (dry run - nothing created)` (top finder hit
declared-count norm 0.27). Source [REAL: <workspace>\plans\tv_blend_v3_raw\THE_ONE_PLAN_2026-10-13.md PART 5 and
PART 7 HL9; skills\hl9-rules\SKILL.md].

Pairs with receipt-report (the ledger), restriction-matrix (reading block), numbers-pass (R8), gradable-acceptance and
self-attacking-referee (R6).
