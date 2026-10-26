---
name: rules-binding-audit
description: "Audit the rule files themselves (DESIGN_HINTS, CLAUDE.md, THE_INVARIANTS, RULES_CARD, shared_claude) rule by rule - who it binds (Claude, the user or the code), what enforces it (hook, test or prose only), whether the user can override it, whether it cites a retired decision, whether it repeats another rule - and whether any file states the meta clause that the rules bind Claude and the user can override them. Ships rules_audit.py. Use this whenever the user says 'go thru the rules and analyse them', after a rule caused friction or made Claude refuse or soften one of his orders, after a decision is removed, and before adding a new rule. Pairs with retire-a-rule, literal-execution, scar-to-rule and rule-miner."
---
# rules-binding-audit

## The problem (2026-10-15)
"remove D70 now" was softened into a superseding row because a workspace rule says the decision log is append-only.
the user: "we can edit the decision log we just can't have you doing it unless commanded by me in a very specific way. I
probably have other rules I didn't mean for you to take so serious", then "go thru the rules and analyse them for me
in other ways to". RULES_REVIEW_2026-10-15.md was written by hand; its main finding: no rule file says the rules bind
Claude and the user can override them. scar-to-rule and rule-miner mine errata and prompts - nothing audited the rule files.

## Procedure
1. **Run the audit** over every file Claude treats as law, with the decision log for retired ids:
   `python rules_audit.py DESIGN_HINTS_v3_2026-10-12.md CLAUDE.md THE_INVARIANTS.md plans/RULES_CARD.md --decisions DECISIONS.md`
2. **Read the table, not just the summary.** The tags are keyword heuristics. For each row decide:
   - **binds whom** - a rule that restrains Claude never binds the user (literal-execution);
   - **mechanism** - PROSE_ONLY rules are wishes (DESIGN_HINTS v3: "a rule must name its mechanism"); give each a
     hook/test or mark it advisory;
   - **override** - can the user lift it by an explicit order? If the text does not say, say it for him;
   - **RETIRED** - a rule citing a removed decision (retire-a-rule) is stale;
   - **DUP** - two copies drift apart; keep one and point to it.
3. **META_CLAUSE ABSENT** -> propose one sentence for the top of the root CLAUDE.md ("These rules bind Claude; the user
   can override any of them by an explicit order"), as a question to the user. Never write it unasked.
4. Report to the user in a short table (plain-terms): counts, the five most surprising rows, and the proposals. Edits to
   rule files happen only on his order.

## The tool
```
python rules_audit.py <files...> [--decisions DECISIONS.md] [--retired D70,D87] [--dup 0.6]
CLAUDE.md:38 | BINDS=CLAUDE(implied) | MECH=PROSE | OVERRIDE=NONE | - No minute-of-hour run windows (D161). ...
SUMMARY rules=55 PROSE_ONLY=32 NO_OVERRIDE=54 CITES_RETIRED=0 DUPLICATE_PAIRS=0 META_CLAUSE=ABSENT (...)
python rules_audit.py --selftest
```
Rules = rule-worded bullets, numbered items and table rows outside code fences, plus whole `**A1. Title.**`
paragraphs (DESIGN_HINTS v3 shape, with their `*Mechanism:*` line). Retired ids = rows whose status cell starts
REMOVED/SUPERSEDED/RETIRED/REVOKED, "D70 is REMOVED", "supersedes/replaces/removes D87" - a row merely using the word
(D161 "ceremonies retired as RULES") does not retire itself.

Real run 2026-10-16 on the four files above: 55 rules, 32 prose-only, 54 with no override path, 0 citing a retired
decision, META_CLAUSE ABSENT - the hand review's finding, reproduced mechanically. A first draft flagged D161 as
retired (it contains the word "retired"); fixed and covered by the selftest. Selftest 11/11. Planted 2, caught 2
(override test inverted; any row containing "removed" treated as retired).

Pairs with retire-a-rule, literal-execution, scar-to-rule, rule-miner and question-not-ruling.
