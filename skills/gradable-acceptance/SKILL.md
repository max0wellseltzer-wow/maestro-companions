---
name: gradable-acceptance
description: Lint a plan's per-item cards so every acceptance line is something a script can decide - each assertion is OK (it carries a hook - inline code, a comparison, CHK/RED<FIX/PLANT/BD13, an exit code, a sha, a path, a count), VAGUE (judgement words like clean, robust, readable with no hook) or NO_HOOK; per card it demands 4-7 assertions, at least one planted or red-first and one real-data, landed or replicated, the READING / FAILS IF / KILL fields with 2+ BURNED readings, and (with --root) that every file - line reuse reference resolves. Absorbs the plan-to-cards draft. Use this whenever a plan item, objective card or finish line is written or edited, before claiming an item is ready to build, and when the user asks whether the plan's acceptance can be graded without him.
---
# gradable-acceptance

## The problem
The eager-cray plan (2026-10-13) promised "4-7 assertions a script can decide from git, files and check records
alone, with no human judgement" for every §OB.1a / §K2 / §IC card - and 0 cards were ever locked. Nothing checked the
promise. The first run on 2026-10-16 over THE_ONE_PLAN found 109 cards with assertion blocks and 562 assertions:
23 NO_HOOK lines ("The Screens-tab render test passes." names no test id), 1 VAGUE ("secretscan is clean." - should
be "exits 0"), 48 cards with no real-data / landed / replicated assertion and 3 with no planted one.

## Procedure
1. Write the card: READING (taken + 2 BURNED), VERIFIED REUSE with file:line you opened (or NOT FOUND), FAILS IF,
   KILL, then ASSERTIONS 1..n.
2. Run the lint on the file (`--only ID` for one card; `--root DIR --key TB=DIR` to resolve reuse lines).
3. Rewrite every VAGUE / NO_HOOK line as a predicate (a command and its exit, a value compared, a file that must
   exist). Add a PLANT and a real-data assertion when missing.
4. Cards without an ASSERTIONS block are skipped by default; `--strict` grades them too.

## Tool
```
python gradable_acceptance.py <workspace>\plans\tv_blend_v3_raw\THE_ONE_PLAN_2026-10-13.md --summary
  139 card heading(s) without an ASSERTIONS block skipped (--strict grades them)
  109 card(s), 562 assertions, 59 card(s) with problems: NO_HOOK 23, NO_PLANT 3, NO_REAL 48, VAGUE 1
python gradable_acceptance.py plan.md --only K12 --root C:\work --key TB=C:\work\tv-blend
  (one row per problem: card id, line, kind, detail - e.g. REUSE_BAD path:line: file has N lines)
python gradable_acceptance.py --selftest      # 14 PASS lines
```
Exit 0 every graded card clean, 1 problems or no card found, 2 bad arguments. The hook list is a heuristic: an OK
line can still be wrong, but a VAGUE or NO_HOOK line certainly needs a person.

## Proof
Selftest 14/14. Planted 8, caught 8 (`_work/p_gradable.json`: judgement words, count bounds, plant requirement,
BURNED counting, reuse line bounds, NOT FOUND exemption, field lines after the block, heading closes a card).

## Provenance
skill-foundry dry run 2026-10-16: `gradable-acceptance: PASSES ALL GATES (dry run - nothing created)` (top finder hit
prove-the-read norm 0.22). Sources [REAL: <workspace>\plans\tv_blend_v3_raw\skills\gradable-acceptance\SKILL.md and
skills\plan-to-cards\SKILL.md; THE_ONE_PLAN §OB.1a and §K2 cards]. plan-to-cards is folded in (same job, card level):
its "4-7 assertions", BURNED readings and "reuse line names code that was not opened" checks are functions here.

Pairs with test-expectation-oracle, restriction-matrix, prove-the-read, plant-the-bug and cold-replication.
