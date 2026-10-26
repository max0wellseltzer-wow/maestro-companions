---
name: cross-cutting-check
description: Apply the geologist's law of cross-cutting relationships to an ordered record (DECISIONS.md, errata, numbered plans) - a row may only cite ids defined above it - and report INTRUSIONS (a row cites an id first defined later), PHANTOMS (cited ids never defined, e.g. a deleted decision still referenced), INVERSIONS (rows out of numeric order) and duplicate definitions, with configurable define and cite regexes. Use this whenever a decision or rule row is deleted, renumbered or retired, after a merge touched DECISIONS.md or an errata list, before citing a D-number, and when the user asks whether the decisions file still hangs together.
---
# cross-cutting-check

## The problem
[IMAGINED] In geology an intrusion is younger than every layer it cuts, so the order of layers can be read from what
cuts what. [REAL] DECISIONS.md is append-only and its rows cite earlier rows; on 2026-10-15 the user removed D70 (D160),
and rows were renumbered across branches (decision-renumber). The first scan (2026-10-16, read-only) of
`<workspace>\DECISIONS.md` found 162 ids and 18 findings: D70 is still cited at lines 77, 78 and 98 although it no
longer exists (PHANTOM), D89 and D90 are cited but never defined, five rows cite a decision defined below them
(line 26 cites D42 defined at line 49) and four rows sit out of numeric order.

## Procedure
1. Run on the record (defaults fit `| D12 | ...` tables; `--def` / `--ref` for other notations, e.g. errata headings).
2. PHANTOM: the cited row was deleted or never landed - fix the citation or restore the row by a new row.
3. INTRUSION: a row was edited after later rows existed, or rows were reordered - check its history (atavism-check,
   chain-fork-guard) before trusting it.
4. INVERSION / DUPLICATE_DEF: a merge interleaved numbering - decision-renumber.

## Tool
```
python cross_cutting.py <workspace>\DECISIONS.md --summary
  162 id(s) defined, 18 finding(s): INTRUSION 5, INVERSION 4, PHANTOM 9
python cross_cutting.py <workspace>\DECISIONS.md
  INTRUSION     L26     D42      cited here, first defined later at line 49
  PHANTOM       L77     D70      cited, never defined
python cross_cutting.py errata.md --def "^##\s+(E\d+)" --ref "\b(E\d+)\b"
python cross_cutting.py --selftest      # 11 PASS lines
```
Exit 0 conformable, 1 findings, 2 bad arguments.

## Proof
Selftest 11/11. Planted 7, caught 7 (`_work/p_cross.json`: later definitions, duplicate definitions, inversion,
phantoms, word-glued tokens, numeric vs string id order, --ignore-before).

## Provenance
skill-foundry dry run 2026-10-16: `cross-cutting-check: PASSES ALL GATES (dry run - nothing created)` (top finder hit
rule-conflict norm 0.27). metaphor-to-algorithm: `BUILD (no skill covers >= 50% of the algorithm query)`; closest
rule-conflict (coverage 0.46) - it compares what rules SAY to each other, not the order in which ids are defined and
cited; superposition (live) checks timestamps line by line, not citations. OUT THERE extra: pitch [IMAGINED],
mechanism and DECISIONS.md evidence [REAL].

Pairs with decision-renumber, retire-a-rule, rule-conflict, superposition and chain-fork-guard.
