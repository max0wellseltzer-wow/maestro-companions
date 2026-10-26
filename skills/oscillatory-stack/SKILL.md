---
name: oscillatory-stack
description: Run and audit the user's Oscillatory Fire stack (Controlled Fire + Fascination Drive + Oscillatory Fire with its 19 hardenings) - keep a JSONL log per cycle and check it - fascination lock timestamped before the audit and unedited (sha), a locked rejection set whose rivals are hotter and name the constraint they break, the graded self-limitation tax on near-wall claims, a declared fate for every unclaimed surplus (fate changes pay a consistency cost), pivots that pay rate x distance (word-set Jaccard by default, a measurable answer to the stack's open residue) and every softening turned into the next Object of Interest. Use this whenever the user asks for Oscillatory Fire, open-ended research or design under the stack, says pivot, fascination, rejection set or self-limitation tax, or wants a past oscillation audited.
---
# oscillatory-stack

## The problem
the user's upload FULL_OSCILLATORY_HISTORY_AND_CURRENT_STACK.md (frozen 2026-10-13) lists 19 hardenings: Rule omega,
costly audit, pre-declaration lock, recursive lock, rejection set, intensity anchor, intensity as
constraint-breaking, Sacred Four, self-limitation tax (graded), purpose-locked surplus, priced and graded pivots.
controlled-fire covers the single-gate discipline and fascination-forge the detector harness; nothing checks that an
oscillation actually obeyed the hardenings - each is easy to skip silently ("I locked it" with the lock written after
the audit). The stack's own open residue is how to measure the distance between Objects of Interest.

## Procedure
1. Alpha: name the Object of Interest and its intensity; write the lock sentence, hash it, timestamp it BEFORE the
   audit. Lock the rejection set: rivals hotter than the object, each naming the constraint it breaks.
2. Beta: attack under Controlled Fire (controlled-fire skill). For each near-wall claim record strength, the current
   standard and what you state; the stated value must give up tax x the excess; give every surplus a fate.
3. Gamma: record softenings found by the Rule-omega audit; the next cycle's object must be one of them. A pivot records
   its target and pays rate x distance.
4. Append the cycle to the log and run the audit; a finding is the next Object of Interest, not a footnote.

## Tool
```
python oscillatory_audit.py oscillation.jsonl [--tax 0.5] [--rate 1.0]
  cycle 1: 3 finding(s)
    - LOCK_AFTER_AUDIT
    - TAX_UNPAID 'c1' stated 0.85 > allowed 0.7
    - PIVOT_UNDERPAID distance 1.00 needs 1.00, paid 0.1
python oscillatory_audit.py distance "gate failure prediction" "gate failure order prediction"
  0.250
python oscillatory_audit.py --selftest      # 15 PASS lines
```
No oscillation log exists yet; the tool has run on its selftest logs only. Exit 0 clean, 1 findings, 2 bad arguments.

## Proof
Selftest 15/15 (every check fires on a planted bad log and stays quiet on a good one). Planted 7, caught 7
(`_work/p_osc.json`: lock order, equal-intensity rival, flat tax, pivot distance, softening, Jaccard, fate change).

## Provenance
skill-foundry dry run 2026-10-16: `oscillatory-stack: PASSES ALL GATES (dry run - nothing created)` (top finder hit
fascination-forge norm 0.21). Source [REAL: <workspace>\plans\tv_blend_v3_raw\FULL_OSCILLATORY_HISTORY_AND_CURRENT_STACK.md
and skills\oscillatory-stack\SKILL.md]. The Jaccard distance is one proposal for the open residue, not the user's ruling.

Pairs with controlled-fire (the beta attack), fascination-forge (alpha's detectors), restriction-matrix and
smuggled-premise.
