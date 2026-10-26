---
name: remove-the-hero
description: Extracts the cause and effect sides of the causal statements in a text, deletes the most-cited cause and tests whether any remaining statement still explains each outcome. Use this whenever the user hears a story with one hero cause and wants to know if the outcome has any other explanation. Pairs with erase-the-center, inflate, counterparty-view and pov-core.
---

# remove-the-hero

An **obliterate** lens for causal stories. It reads each causal link: because, due to, thanks to, caused, drove, led to, so, therefore, since, if. Each link splits into a cause side and an effect side. The HERO is the word that turns up on the most cause sides, with ties going to the earliest in the text. The lens deletes every link the hero drives and checks each outcome it explained: does any other link still explain an effect that shares a word with it? If not, the outcome is ORPHANED and the story rests on the hero alone.

## The tool (ships with this skill)

`remove_the_hero.py`: pure stdlib on top of pov-core. Selftest 6/6.

```
python remove_the_hero.py <file|text> [--opt hero=word] [--json]
python remove_the_hero.py --selftest
from remove_the_hero import apply; apply(text, hero="campaign")
```

Example (pov-core probe text):

```
[remove-the-hero] (text) hero 'backtest' drives 1 of 2 causal links; without it 1 outcome(s) are orphaned, 0 still explained
  - ORPHANED 'We will obviously launch the new screener next week' - only 'backtest' ever explained it
```

## Uses and limits

- Causal links are found by marker regexes. A cause that is only implied is invisible, and the hero is a single word, so pass hero= for multi-word causes.
- "Still explained" means a word is shared with another link's effect. That is lexical overlap, not proof that the alternative cause is real.
- For whether the arrow could point the other way, use swap-cause-effect.
