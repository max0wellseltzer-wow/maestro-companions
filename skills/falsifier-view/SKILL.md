---
name: falsifier-view
description: Writes for each claim the concrete observation that would refute it (counterexample, missed date, value out of range, effect without cause) and flags the claims nothing could refute. Use this whenever the user reviews a thesis or result and wants to know what evidence would kill it. Pairs with pre-register, skeptic-eye, evidence-only and pov-core.
---

# falsifier-view

An EPISTEMIC lens of the point-of-view family (engine: pov-core). It turns each claim around: instead of asking what supports it, it writes down the observation that would prove it wrong. Each sentence is typed by its claim forms (universal, numeric, forecast, causal, comparative, conditional), and each form gives its own refuter. Sentences that are only preferences or vague with no number are flagged as unfalsifiable.

## The tool (ships with this skill)

```
python falsifier_view.py --selftest
python falsifier_view.py <file|text> [--json]
```
```python
from falsifier_view import apply
[f["what"] for f in apply("thesis.md")["findings"] if not f["falsifiable"]]
```
Example: `s0 forecast: refuted by 'next week' passes and it has not happened`

## Uses and limits

- Heuristic regex typing. One sentence can carry several forms, and each form gets its own refuter.
- The refuters are templates filled from the sentence. They tell you what to watch, not how to measure it. Pre-register them with pre-register before looking at the data.
- Paper-only where the claims are about trading: the lens never checks a claim against data.
