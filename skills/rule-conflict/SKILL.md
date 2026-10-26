---
name: rule-conflict
description: Read a SET of standing rules (a DECISIONS or DESIGN_HINTS markdown table, list rows with ids like D71, or a folder of rule files) and report where they collide - rules REMOVED/SUPERSEDED/RETIRED/replaced yet still invoked by a later rule, direct contradictions (same subject, opposite modality - always vs never, must vs must not, allowed vs forbidden), duplicate rules, dangling references to rule ids nobody defines, and ids defined twice. Read-only. Use this whenever the user asks whether the rules agree, adds or retires a decision, before citing an old rule id as authority, or when two instructions seem to pull opposite ways. Pairs with rule-miner, retire-a-rule, rules-binding-audit, decision-renumber and smuggled-premise.
---

# rule-conflict

Reverses **rule-miner**. Angle flip: rule-miner reads prompts and pulls rules OUT of them (one rule at a time, from speech toward the rulebook); rule-conflict reads the rulebook as a whole and asks where its rules fight each other.

Rules pile up faster than anyone rereads them. A rule gets REMOVED in row D160 while row D161 still says "per D70"; two sessions write "always X" and "never X" in rows a hundred apart; an id is reserved and never filled. Each is invisible row by row and obvious once the set is read together.

## The tool (ships with this skill)

`rule_conflict.py` - pure stdlib (plus skill-finder's tokenizer), read-only, selftest 8/8:

```
python rule_conflict.py <workspace>/DECISIONS.md [more.md | folder] [--top 30] [--dup 0.8] [--jac 0.12] [--shared 4] [--common 0.15]
python rule_conflict.py --selftest
from rule_conflict import load, analyse, render   # analyse(load([path])) -> {items:[{kind, ids, reason}], dead, partial, counts}
```

How each kind is found:
- **dead rules**: an upper-case SUPERSEDED/REMOVED/RETIRED/REVERSED at the start or in the status cell of a row, "Dn is REMOVED", "supersedes/replaces/retires Dn", or "Dn was replaced by Dm". "Supersedes D77(6)" or "D2's wording" or "IN PART" counts as a PARTIAL supersede and does not kill the rule.
- **still-cited**: a rule numbered after both the dead rule and its killer cites the dead id in a sentence with no history word (was, replaced, retired, renumbered, ->, ...).
- **contradiction**: two sentences from different live rules, one negative (never, must not, do not, forbidden...) and one positive (always, must, allowed, may...), sharing >= `--shared` key terms with Jaccard >= `--jac`, where neither rule cites the other (an explicit amendment is not a conflict). In sets of 30+ rules, words in >= `--common` of all rules are dropped as boilerplate, and parenthesised provenance ("(was D84 on claude/...)") is ignored.
- **duplicate**: whole-rule content Jaccard >= `--dup`, except a dead rule against its own replacement.
- **dangling**: a cited id with the set's main prefix that no row defines and that is not a known-removed id.

## Uses and limits

- Read-only: it opens files for reading only; the selftest checks the bytes are unchanged.
- The contradiction finder is a key-term heuristic. Long prose rows share few terms, so it misses paraphrased conflicts and flags some pairs that merely discuss the same object from two angles. Treat each hit as "read these two together", not as a ruling.
- Combining files whose id spaces overlap (DECISIONS D1-D7 and DESIGN_HINTS section D's D1-D7) reports id-collisions by design: the same id means two things.
- Rule order is the numeric id, not the file order; a later-numbered rule citing a dead rule is what gets flagged.
