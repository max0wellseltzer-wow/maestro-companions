---
name: steelman
description: Extracts the claims of an opposing text, scores each for strength (number, mechanism, source, specificity), strips strawman markers and overreach and rebuilds the strongest version from the top claims. Use this whenever the user is about to dismiss a view he disagrees with. Pairs with opponent-lawyer, devils-advocate, strip-adjectives and pov-core.
---

# steelman

A VANTAGE lens of the point-of-view family (engine: pov-core). It changes the view of an opposing argument from its weakest reading to its strongest. Each claim is scored for strength: number +2, mechanism +2, source +2, specificity +1. Overreach is then repaired rather than mocked. Sneer and filler words are cut, absolutes are softened to their defensible form (never -> rarely, always -> usually) and "!" becomes ".". The top half of the claims (at least 3) form the steelman, and the dropped claims are the view's weakest parts.

## The tool (ships with this skill)

```
python steelman.py --selftest
python steelman.py <file|text> [--json]
```
```python
from steelman import apply, repair
v = apply(opposing_text); v["stats"]["steelman"], v["stats"]["kept"]
repair("They say the crowd is always wrong!")   # -> ('The crowd is usually wrong.', [...edits])
```

Example: `[steelman] (text) steelman from 4 of 7 claims, 3 repaired, mean strength +1.2 over the whole: We will launch the new screener next week because the backtest Sharpe was 3.4 and it rarely lost. ...`

## Uses and limits

- It can only strengthen what the text contains. It never invents evidence or a mechanism.
- Softening is word-level. "All costs" becomes "most costs" even when "all" was literally true.
- Reads text and plans with at least 2 claims.
