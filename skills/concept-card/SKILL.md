---
name: concept-card
description: Lint typed concept cards (definition, formal object, theory with a status, assumptions A1..An tagged HOLDS / FAILS / UNKNOWN each with the test that decides it, failure, dual, measure, forces, open question) and flag a card that forces no code as GLOSSARY - with --root the forced paths and functions must exist. Use this whenever a new root idea, concept or theory enters a plan, when a plan section claims conceptual depth, before building code a concept is said to force, and when the user asks whether a concept is real work or just a definition.
---
# concept-card

## The problem
THE_ONE_PLAN §CD.1 (2026-10-13) typed a concept card with ten fields and said a card that forces no code is a
glossary entry; §CD.2 then wrote fourteen cards C1-C14 by hand and `plan_counts --concepts` was never built. The
first lint (2026-10-16) of those fourteen cards: 6 have problems - 5 assumptions carry no closed tag ("Only partly",
"Partially holds" instead of HOLDS / FAILS / UNKNOWN) and 2 HOLDS assumptions name no test that decides them.

## Procedure
1. Write the card with every field; give Theory a status (CITED-UNVERIFIED until someone checks the source).
2. Tag every assumption HOLDS / FAILS / UNKNOWN and name the test (or unit id) that decides it; "partly" is not a tag -
   split the assumption into the part that holds and the part that fails.
3. Forces must name code: a unit id, a `path.py::function`, or `code`. Run with `--root` once the code exists.
4. Lint; fix every row before the card is cited by other sections.

## Tool
```
python concept_card.py <workspace>\plans\tv_blend_v3_raw\THE_ONE_PLAN_2026-10-13.md
  C2    L14378  NO_TEST   A3 is HOLDS but names no deciding test
  C7    L14493  NO_TAG    A2 Killing planted mutants means killing real bugs. Only partly
  14 card(s), 6 with problems: NO_TAG 5, NO_TEST 2
python concept_card.py cards.md --root <workspace>\tv-blend --only C1
python concept_card.py --selftest      # 10 PASS lines
```
Default cards are `**C<n> · title**` lines; use `--card-re` for other notations and `--fields` for another field set.
Exit 0 clean, 1 problems or no card, 2 bad arguments.

## Proof
Selftest 10/10. Planted 6, caught 6 (`_work/p_concept.json`: status requirement, FAILS exemption, glossary check,
function existence, heading ends a card, continuation lines).

## Provenance
skill-foundry dry run 2026-10-16: `concept-card: PASSES ALL GATES (dry run - nothing created)` (top finder hit
read-as-code norm 0.21). Source [REAL: <workspace>\plans\tv_blend_v3_raw\skills\concept-card\SKILL.md; plan CD.1-CD.2].

Pairs with depth-in-the-nooks (one depth line per item), research-integrity (claim status), source-labels and
metaphor-to-algorithm.
