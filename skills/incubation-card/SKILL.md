---
name: incubation-card
description: Parks a problem as a dated deferred card with a content hash and a fresh-eyes question set built from its own open questions, conditions, numbers and unlinked key terms. Use this whenever the user is stuck and wants to set a problem aside and come back to it later. Pairs with skill-finder, promise-ledger, momentum and pov-core.
---

# incubation-card

A **time** lens: it moves a stuck problem from now to later in a form that later-you can pick up cold. The card carries a content hash id, the parked and revisit dates, and the gist (the sentence with the most key-term weight). The questions come only from the problem itself: its own OPEN questions, each "if X" as "did X happen?", each number with a unit as "still true on the revisit date?", each never / always / must as "what would break it?", and UNLINKED pairs of key terms that never share a sentence as "how does A relate to B?". On revisit, an unchanged hash means only fresh eyes have changed. Otherwise the card lists the questions added and dropped.

## The tool (ships with this skill)

`incubation_card.py` - pure stdlib on pov-core, selftest 7/7. Reads `text` and `plan`. Options: `--opt days=2`, `--opt today=YYYY-MM-DD`, `--opt out=card.json` (write), `--opt card=card.json` (revisit).

```
python incubation_card.py problem.md --opt days=3 --opt out=C:/path/card.json
python incubation_card.py problem.md --opt card=C:/path/card.json
python incubation_card.py --selftest
```
Example (shared probe): `[incubation-card] (text) card 1f5f412bdad1: 4 fresh-eyes question(s) (condition 1, number 1, absolute 2); revisit 2026-10-18; new card`

## Uses and limits

- Use it when a problem has eaten an hour with no progress. Park it, write the card somewhere durable (skill-finder, a dated file), and revisit on the date.
- It writes only where `out=` points. It never schedules a reminder, which is momentum or schedule's job.
- The questions are mechanical. They show what the text left open, not what its author forgot to write.
