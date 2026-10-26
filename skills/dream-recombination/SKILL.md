---
name: dream-recombination
description: A seeded "dream pass" over many past documents (transcripts, notes, prompt archives, findings files) - keep each document's most salient terms by TF-IDF, draw pairs of terms from two DIFFERENT documents weighted by salience, drop every pair that already co-occurs anywhere (KNOWN), then grade the rest awake - bridge terms that co-occur with both (rarest first) make a pairing BRIDGED, none makes it WILD - scored by salience product times 1 + ln(1 + bridges). Reads files with a byte cap. Use this whenever the user wants new combinations out of old sessions, asks "what have we never connected?", "dream up pairings from the transcripts", is stuck for ideas after a long run, or wants seeds for cross-breed or fascination-forge that come from his own history rather than a template. Pairs with cross-breed, transcript-miner, dream-logic and session-inspiration-packet.
---

# dream-recombination

Catalogue name: `dream-recombination` (#65; #62 in the 2026-10-13 doc, "a genuine candidate-generator for THIS task").

## The problem

CATALOG_JUDGED.md row 65 (2026-10-16) is PARTIAL. transcript-miner reads sessions, cross-breed combines two chosen things, and dream-logic recombines sentences inside ONE text. Nothing pairs ideas ACROSS documents that never met. Real run on 2026-10-16 over the deep-mine reports (scratchpad\deepmine, 4 finder folders): among the top four dreams was `plants` (C_d7d9593f/FINDINGS.md) x `treediff` (B_e4e41a0f/FINDINGS.md). That pairs planted-bug ledgers with tree-diff landing audits, two findings from different mines that no report connects. The other top pairs were code-file noise (`fifty x return`), which is why every dream gets an awake grade.

## Procedure

1. Point it at a folder or a list of files: `python dream_pairs.py C:\path\to\digests --top 20 --max-mb 2`.
2. Read the BRIDGED pairs first. Their bridge terms tell you why the pairing might make sense. WILD pairs are pure leaps.
3. Grade each pairing awake: one sentence on what it would compute. Send the survivors to cross-breed or fascination-forge. Change `--seed` for another night's dream.

## Tool

```
python dream_pairs.py FILE_OR_DIR ... [--top 20] [--per-doc 15] [--seed 7] [--max-mb 4] [--json]
python dream_pairs.py --selftest
```
Output: `6.104 BRIDGED plants x treediff   (C_d7d9593f/FINDINGS.md | B_e4e41a0f/FINDINGS.md)  via a0b2, action, answer`.

Selftest: 8 checks (dreams produced, no KNOWN pair survives, cross-document only, a BRIDGED pair via its bridge, isolated documents give WILD, same seed same dream, one document cannot dream, byte cap). **Planted 1, caught 1.** Letting co-occurring pairs through failed the KNOWN check.

## Limits

Terms are single words of 4+ letters, so code files contribute identifiers and noise. Grading is co-occurrence, not meaning. A dream is a seed, never a finding.

Pairs with cross-breed, transcript-miner, dream-logic (within one text) and session-inspiration-packet.

## Provenance

`skill-foundry dry run 2026-10-16: dream-recombination: PASSES ALL GATES`. Finder top hit: dream-logic, norm 0.26.
