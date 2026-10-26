---
name: literal-execution
description: Take the user literally - "do this literally, do not talk about it, just do it" - read his prompt as a contract before acting - do the exact verb on the exact object, in the order he gave, at the quantity he gave - by parsing asks, questions, quantities ("2 of each", "44 next steps"), scope words (all, every, literally, only), ordering ("only after", "first ... then") and negations ("no X unless Y") and checking the finished work against them. Use this at the start of EVERY the user prompt that asks for work, whenever he says "literally", "only after", "all", "exactly", "do this", or repeats himself, and before reporting done. the user, 10-15 - "you not taking me more literally is causing me more work". Pairs with finish-everything, token-thrift and quota-prompt.
---

# literal-execution

the user's rule, in his words: *"you not taking me more literally is causing me more work"* (10-15). And: *"Do this ONLY After you are done with LITERALLY all your work"* (10-11).

1. **Parse the prompt** with the tool before planning. Write down each ask, each quantity, each ordering word and each "no / never / unless".
2. **Do the verb he used, on the object he named.** "Remove D70" means delete that row, not annotate it. A question stays a question: answer it, and don't turn it into a task (`question-not-ruling`).
3. **Respect order words.** "Only after X" means X is finished first. "First … then …" is a sequence.
4. **Check before reporting.** Run `check(parsed, done)`: unmet asks, short quantities and broken negations must all be empty.
5. **When it's truly ambiguous, ask one short question.** Don't guess wide and do extra.

**How literal?** That's the user's call, per prompt, through `reading-dial` (#code / #spec default / #brief / #human). This skill is the parser and checker the code and spec modes stand on.

## The tool (ships with this skill)

`literal_parse.py` - pure stdlib, selftest 8/8:

```
from literal_parse import parse, check
p = parse(prompt_text)          # asks, questions, quantities, scope, ordering, negations
check(p, done_items)            # unmet / short / violated / complete
```

## Uses and limits

The parser is regex-based. It catches the shapes the user actually uses, but not every English construction, so read its output and correct it. Matching done items to asks is by shared words, which makes it a gap-finder, not proof.

## the user's order outranks a project rule written to restrain Claude (2026-10-15)

Workspace rules ("never edit the decision log", "append-only", "a correction is a new entry") restrain CLAUDE. They
never bind the user. When his literal order collides with one of them, his order wins:

1. **Do the exact verb on the exact object.** "remove D70 now" = delete the D70 row (and its true citations:
   retire-a-rule). Do not substitute the rule-compliant version (a superseding row) and call it done.
2. **Note the exception where the rule's readers will see it:** in the commit body, "Edited DECISIONS.md on the user's
   explicit order (MAX_PROMPTS_<date> P<n>: 'remove D70 now'); append-only rule waived for this edit only."
3. **The waiver is per order, not standing.** The rule still binds the next unprompted edit. the user: "we can edit the
   decision log we just can't have you doing it unless commanded by me in a very specific way".
4. **Only if the order is genuinely unclear about the object** (which row? delete or replace?) ask one short question.
   A rule existing is not ambiguity.

Evidence (transcript 4443f5bc, 2026-10-15): "remove D70 now" (15:27Z) produced D160 superseding D70 instead of a
deleted row. the user: "so no D70?", then "I told you to delete it goofy", then "its okay to make mistakes but you not
taking me more literally is causing me more work and espicially you more work", then the clarification above (15:33Z)
and "I probably have other rules I didn't mean for you to take so serious". The memory note take-max-literally was
written that day; this section puts the clause into the skill. Auditing which rules restrain only Claude:
rules-binding-audit.
