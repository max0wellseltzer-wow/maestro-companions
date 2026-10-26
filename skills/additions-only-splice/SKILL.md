---
name: additions-only-splice
description: Add a section to a large file (a 1.5 MB plan, DECISIONS, a memory file) without changing one existing line - insert a block before or after a marker that must occur exactly once, in the file's own newline style, and refuse to write unless the result passes the additions-only check (every old line still present in order, the file grew, no long paragraph doubled, newline style unchanged, trailing-whitespace edits named); also checks any OLD/NEW pair. An explicit --edits list of in-place row edits (each OLD once, NEW = OLD plus one insertion) is allowed and reported as the only non-additions. Use this whenever the user says only add, make no changes, append a section, do not touch the existing text, when splicing agent output into a plan, when about to write a splice*.py or append*.py for PLAN.md, when a fold must also grow a few index rows (§0 phase rows, Block C order line), or to prove after the fact that an edit was additions only.
---
# additions-only-splice

## The problem
The eager-cray session (2026-10-13) grew THE_ONE_PLAN to 1,557,864 bytes under the user's rule "only add, make no changes",
with a throwaway `ins.py`: insert before a marker that occurs once before `# APPENDIX V`, then check by multiset diff
that no old line vanished and no paragraph was pasted twice. The script died with the session. A plain Edit on a file
that size can silently reflow a line or convert CRLF, and "I only added" is then a claim, not a fact.

## Procedure
1. Pick a marker line that occurs exactly once (the tool refuses 0 or 2+ and prints where they are).
2. `splice` to `--out` first; read the +N count. Use `--in-place` only when sure (it keeps FILE.bak).
3. For an edit made any other way, run `check OLD NEW` before claiming it was additions only.
4. Corrections are new rows that supersede by addition; never edit the old row.
5. Exception, named up front: an index row that must grow (a plan fold adds card ids to §0 phase rows and the §14
   Block C order line; plan-card-fold lists them). Write them as a JSON list of [OLD, NEW] pairs with the Write tool
   and pass `--edits FILE` to `splice` or `check`. Each OLD must occur once; NEW must be OLD with one inserted run of
   text (no rewording, no newline); two insertions in one line are two pairs. The output names every allowed edit
   with its old line number; report those as the only non-additions. An edit not in the list is still a VIOLATION.

## Tool
```
python additions_only_splice.py splice THE_ONE_PLAN_2026-10-13.md --marker "# APPENDIX V" --insert section.md --out plan_new.md
  ADDITIONS_ONLY (+2 lines) -> plan_new.md
python additions_only_splice.py check OLD.md NEW.md
  VIOLATION
    - old line 7 missing or out of order (only trailing whitespace differs): 'alpha'
python additions_only_splice.py --selftest       # 19 PASS lines
python additions_only_splice.py check OLD.md NEW.md --edits edits.json     # [[OLD, NEW], ...] row edits allowed
python additions_only_splice.py splice PLAN.md --marker "## 31. " --insert sec.md --out new.md --edits edits.json
```
Real run 2026-10-24 (read-only, copies in scratch): the GT198-GT208 fold, `e2a7bcf^` vs `e2a7bcf` of plans/PLAN.md.
Without `--edits`: `VIOLATION - old line 73 missing or out of order`. With the five row edits listed:
```
ADDITIONS_ONLY (+210 lines)
  - allowed in-place edit at old line 73: 'GT175, GT177, GT179 (every card' -> +21 chars
```
Real run 2026-10-16: a 2-line section spliced into a copy of the 1.5 MB plan (marker `# APPENDIX V`), check passed;
the output went to scratch and was deleted. Exit 0 ok, 1 violation or marker refused (nothing written), 2 bad arguments.

## Proof
Selftest 15/15. Planted 7, caught 7 (`_work/p_splice.json`: marker count, CRLF block, order (multiset only),
growth, doubled paragraph, write-before-check, missing .bak).

## Provenance
skill-foundry dry run 2026-10-16: `additions-only-splice: PASSES ALL GATES (dry run - nothing created)` (top finder hit
safe-bulk-edit norm 0.21). Source [REAL: <workspace>\plans\tv_blend_v3_raw\skills\additions-only-splice\SKILL.md].
The check is riffle-check's invariant with one source; this skill adds the marker splice and the refuse-to-write gate.

Pairs with riffle-check (merged files), chain-fork-guard (append-only prefix), safe-bulk-edit and diff-patch,
and plan-card-fold (which lists the row edits a PLAN.md fold needs).

## Scars
- 2026-10-20 L1177: the GT198-GT208 fold needed three §0 row edits besides the append, so a throwaway splice789.py
  did it by `str.replace` with a count check, and the additions-only check could not be run on the result. Three
  more splice scripts were written in the same session (splice199.py, append30.py). Now `--edits`.
