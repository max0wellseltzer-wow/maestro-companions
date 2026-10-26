---
name: finish-everything
description: Never quit early and never stop with an ask unfinished - before the final reply, list every ask and question in the user's prompt (via literal-execution), attach evidence that each is DONE (commit, file, output line), and keep working while any is NOT DONE; separately list EXTRA work that maps to no ask (drop it per token-thrift, or say why it improves the software). Use this before every final report, whenever the user says continue, keep going, don't stop until all are done, literally all the work, or asks "are you done?". Pairs with literal-execution, token-thrift, receipt-report and chain-the-queue.
---

# finish-everything

the user: *"so many prompts you just choose to prematurely quit on"* (10-07). *"Continue literally all the work from last cycle and far far more"* (10-11). *"keep going, don't stop until all are done"* (said four times, 10-12 and 10-13).

1. **Ask list.** Run `literal-execution`'s parser on the prompt. Every ask and every question becomes a row.
2. **Evidence per row.** Each row is DONE only with something checkable: a commit sha, a file path, a line of command output. "I did it" doesn't count.
3. **While anything is NOT DONE, keep working** (`chain-the-queue`). Report it as NOT DONE only when it's genuinely blocked on the user: his facts, money, permission, or a pen someone else holds. Say what would unblock it.
4. **Extras are visible.** Work that maps to no ask gets listed and justified as improving the software, or cut. This is how "finish everything" and "don't waste tokens" stay compatible.

## The tool (ships with this skill)

`finish_check.py` - pure stdlib (uses literal-execution), selftest 7/7:

```
from finish_check import finish_report
finish_report(prompt, ledger={ask: evidence, ...}, extras=[...])   # rows, not_done, extra, finished
python finish_check.py ledger.json        # exit 1 while anything is NOT DONE
```

Ledger keys and asks meet on a normalised form (whitespace collapsed, trailing `.?!;:,` dropped, casefolded), on
both the write side and the lookup, so `"fix the 3 gaps you found"` finds the ask `"Fix the 3 gaps you found."`.
(Survey 2026-10-24: a sentence prompt became 3 asks, all NOT DONE with the evidence under EXTRA, because the keys
were stored without the period.) The Stop hook's JSON reader uses the same form.

## Uses and limits

Ask extraction is only as good as the parser, so read the ask list and fix it. Evidence is checked for presence, not truth. Pair it with `numbers-pass` and `receipt-report` so the evidence is real.

## The Stop hook: the turn cannot end while an ask is open and unblocked (candidate #58, added 2026-10-16)

The skill alone did not bite: across 6 of 8 sessions the user typed "keep going / don't stop until all are done" 53 times
(4443f5bc 20, d7d9593f 16, e4e41a0f 9; 27 on 10-13 alone). f562dc10 10-11T10:54 "are you done with your tasks? if not
do not stop the work", 11:24 "do not dare stop"; 4443f5bc 10-16T00:37 "What is the hold up?". Each nudge cost a
round trip and an idle machine.

Tool: `stop_hook_open_asks.py` goes beside finish_check.py in this folder. It reads the ask ledger (finish_check's
JSON with a `blockers` map, or any markdown table with `ask` + `status` (+ `blocker`) columns, e.g. a SESSION_LEDGER
section) and exits 2 with the open list on stderr when an ask is NOT DONE and names no blocker (pen, check running,
the user's decision). A missing ledger never blocks; after 3 blocks with an unchanged list it lets the stop through
(progress resets the count), so it cannot trap a stuck session.
```
python stop_hook_open_asks.py --list --ledger <workspace>\SESSION_LEDGER_2026-10-16_x.md
OPEN     write E77
BLOCKED  delete branches  [the user's decision (D153)]                       # exit 1
python stop_hook_open_asks.py --selftest                                 # 10 PASS lines, exit 0
```
Install (the user's call - NOT installed; run hook-preflight first): add to `.claude/settings.json`
`"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python C:\\Users\\the user\\.claude\\skills\\finish-everything\\stop_hook_open_asks.py --ledger C:\\Autotrade\\SESSION_LEDGER_<this session>.md"}]}]}`.
Point it at THIS session's ledger (a glob over old ledgers would block on their stale rows). The ledger must hold an ask table for it to do anything; a session without one passes freely.
Proof: selftest 10/10 (benign exits 0, open ask exits 2, loop cap, progress reset, normalised keys); planted 5, caught 5.
