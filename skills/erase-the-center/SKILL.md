---
name: erase-the-center
description: Finds the most central keyword of a text or plan - the one with the widest sentence span (in the most sentences), ties broken by co-occurrence degree (most distinct partner words), then first seen; discourse words like obviously/clearly/basically/really/just are never the center - erases every sentence that carries it and reports what is left to say, the new center and the words that vanish with it. Use this whenever the user suspects a note is all about one thing and wants to see what remains without it. Pairs with keystone-find, remove-the-hero, negative-space and pov-core.
---

# erase-the-center

An **obliterate** lens. Every sentence (or plan step) is a unit of keywords: content words of 3+ letters with stopwords dropped, a plural -s folded, and discourse words (obviously, clearly, basically, really, just, actually, simply, literally...) dropped. The CENTER is chosen in this order:
1. sentence span: the keyword found in the most units;
2. co-occurrence degree: on a tie, the word with more distinct co-occurring partner words;
3. first seen: on a further tie, the earliest word.

A discourse word is never a keyword, so it can never be the center, even when it would win the span or degree tie. The lens erases every unit that carries the center and reports:
- how much of the text goes with it;
- the units left, which are what there is still to say;
- the new center of the remainder;
- the words that vanish because they never appear without the center.

## The tool (ships with this skill)

`erase_the_center.py`: pure stdlib on top of pov-core. Selftest 7/7.

```
python erase_the_center.py <file|text|plan> [--opt center=word] [--json]
python erase_the_center.py --selftest
from erase_the_center import apply; apply(note, center="cache")
```

Example (pov-core probe text):

```
[erase-the-center] (text) without 'launch' 6 of 7 units remain, 8 words vanish, new center 'data'
  - vanish with it: backtest, lost, never, new, next, screener, sharpe, week
```

The probe repeats no keyword, so every word spans one sentence and the degree tie-break picks the first-seen word of the most connected sentence ('launch'; before discourse words were dropped it was 'obviously'). On a real note the center is usually a repeated noun.

## Uses and limits

- Keywords are surface words with a plural -s folded. Synonyms count as different topics. Use center= to erase a topic of your choice.
- Erasing works by whole sentences. A sentence that mentions the center in passing goes too.
- For a causal hero rather than a topical center, use remove-the-hero.
