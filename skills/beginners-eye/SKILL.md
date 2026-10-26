---
name: beginners-eye
description: Grade each sentence's reading level and list the jargon, acronyms and domain terms a newcomer would need defined, in order of first use. Use this whenever the user writes something for someone new to the project or wants a reply in plain terms. Pairs with plain-terms, max-lexicon and expert-eye.
---

# beginners-eye

A **persona** lens that reads as someone on their first day. It grades every sentence with Flesch-Kincaid, using a vowel-group syllable count, and flags those above the chosen grade. It also builds the glossary a newcomer needs, in order of first use: acronyms, CamelCase names, coded ids (D71), domain jargon (Sharpe, backtest, bps, cache ...) and words of four or more syllables. Each term is marked "defined on the spot" (a parenthesis, "is a", "means" or a dash straight after it) or NOT defined.

## The tool (ships with this skill)

```
python beginners_eye.py <file|text> [--opt grade=10] [--json]
python beginners_eye.py --selftest
```

```python
from beginners_eye import apply
v = apply(open("SKILL.md").read(), grade=8)
```

Example finding: `TERM 'Sharpe' (domain jargon) first used in s1 - NOT defined`

## Uses and limits

- The syllable count and the jargon list are heuristics, and the jargon list leans toward this workspace (trading and dev).
- A term defined in another document still reads as undefined here.
- It measures difficulty, not correctness. Pair it with expert-eye to cover the other reader.
