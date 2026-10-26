---
name: max-inbox
description: Harvest every item waiting on the user - NEEDS_MAX / "needs the user" / "the user's call" / "OPEN until the user" lines in session ledgers, plans, DECISIONS_PROPOSED, the mailbox issue (#41) and unchecked boxes in YOUR_TASKS / MAX_ONLY files - drop the ones already answered, merge duplicates (same D/E/GT id or mostly the same words) and print one numbered list with sources, ready for max-walkthrough to turn into click-level steps. Ships max_inbox.py (--env-check marks items whose key variable NAME is already set, names only). Use this whenever the user asks "what do I still have to do", "the stuff I still have to do", "what's left for me", "anything I need to answer", "relist all tasks I have", before asking the user to set a key, at session start, and before closing a session. Also (formerly batch-max-questions) - "While a long check or job runs, gather every item that needs the user's authority (his facts, money, rules, a pen someone else holds) and ask them all in ONE AskUser". Also (formerly max-walkthrough) - "Write click-level steps for something only the user's hands can do (an install, a key rotation, a scheduled task, a setting on a website)".
---
# max-inbox

## The problem
the user loses track of his own blockers, and the list lives in a dozen files. He asked for it again and again:
085faced 10-07T08:01 "relist all tasks I have and give detailed easy to follow steps", 12:39, 12:41; 6317367e
10-06T04:46 "Be specific like I am mentally slow"; 4443f5bc 10-12T22:42 "Explain like I am a dumbass"; e4e41a0f
10-11T03:51 "Scan literally all our work for commands and file edits you need me to do". Items such as the Massive
storage clause and the repo creation waited days. Mining layer 8 (#41) found 20 more NEEDS-the user lines nobody had
collected. A run on 2026-10-16 over the newest ledger, two PC feeds, MAX_ONLY and #41 since 10-14 gave 5 items,
GT35 among them (NEEDS MAX since 10-13).

## Procedure
1. Export the mailbox: `gh issue view 41 --json body,comments,title > <scratch>\issue41.json`.
2. Run on named files and small folders (never the whole tree; dot-folders and data/cache/archive folders are pruned,
   add `--skip <name>` for more):
   `python max_inbox.py <workspace>\SESSION_LEDGER_<newest>.md <workspace>\plans\PC_FEED_<newest>.md <workspace>\MAX_ONLY_2026-10-11.md <workspace>\YOUR_TASKS_2026-10-07.md --issue <scratch>\issue41.json --since <date>`
3. Read each item at its source. Drop ones the files already answer (D69: ask the user only for his facts, money, rules);
   mark the rest by kind: decision, hands-on step, fact.
4. Hands-on steps go through max-inbox (numbered, one action each, python not python3). Decisions go into ONE
   batched question set (max-inbox), each with your recommendation.
5. Use `--all` to see the closed ones when the user asks "did I answer X already?".

## Usage
```
python max_inbox.py <files...> --issue issue41.json --since 2026-10-14
  1. 7. **GT35: test-weakening hook + judges without Bash. NEEDS MAX.** Root `wip/dreamy-rubin/gt35` @ 483f0f4.
       <- <workspace>\plans\PC_FEED_2026-10-13.md:49
5 item(s) waiting on the user                                                       # exit 1
python max_inbox.py --selftest
```
`--json` for machine use. Exit 0 empty, 1 items waiting, 2 bad args. Reads only; key-shaped strings are masked.

`--env-check` adds one line per item that names a key-shaped variable (`*_KEY`, `*_API_KEY`, `*_TOKEN`, `*_SECRET`,
`*_CONTACT`, `*_PASSWORD`, `*_ID`): where the NAME is set - Process, User, Machine (registry names via winreg) - or
NOT SET. Values are never read or printed. A "the user must set X" item whose X is set is probably done: check, then drop
it instead of asking him again (D69). Real run 2026-10-24 over MAX_ONLY, YOUR_TASKS and plans/PLAN.md (36 items):
```
 30. - the SEC half is NEEDS_MAX (a real contact for EDGAR's User-Agent, `HARVEST_CONTACT`) and does not block the
       <- <workspace>\plans\PLAN.md:5529
       env: HARVEST_CONTACT SET(Process,User)
```

Scars:
- 2026-10-21 (max-24, L4300-4315): the user asked twice "elI5 the stuff I still have to do seriouly try and help me out
  here"; the session hand-ran awk over PLAN.md §7 instead of this tool. Trigger words added.
- 2026-10-24: selftest 14/14 (planted: NEEDS_MAX and PLAN_V3 must not be read as key names; a set variable's value
  must never appear in the output).

## Proof
`--selftest`: 11 checks (GT35 in two files merges, answered lines dropped, task-file boxes only, pruned folders never
read, issue comments dated, key masking, --all, --since, the "the user's call" wording, exit codes). Planted 6, caught 6.

Pairs with max-inbox (the steps), max-inbox (the decisions), plain-terms (the wording),
mailbox-post (#41), finish-everything, autotrade-start.

## ask the user every open question in one batched message (merged from batch-max-questions)

### The problem (2026-10-15)
"While check_all runs, I'll ask you the questions only you can answer" - four questions in one AskUserQuestion, all four
answered before the check ended. A second batch was all approved. One AskUserQuestion was rejected because the user wanted
to clarify, and half a turn was lost guessing what he meant. D69 (no repeat questions) says codebase decisions are
mine; only his facts, money and rules are his - so the list is short, and it belongs in the dead time of a check.

### Procedure
1. When a long run starts (long-job's check_eta.py says more than about 10 minutes), list every open item and mark it
   NEEDS_MAX only if it is his fact, money, permission, rule, or a pen another session holds. Everything else: decide,
   act, report (no-repeat-questions / D69).
2. Drop any item the user already answered (search MAX_PROMPTS_<date>.md and the ledger first).
3. One AskUserQuestion, at most 4 questions. Each has the recommended option FIRST, labelled "(recommended)", with one
   line of why and what happens if he picks it; one option is always "something else / let me explain".
4. Ask it right after starting the run, then keep working (chain-the-queue). Do not block on the answer.
5. Rejected or "let me clarify" -> stop. Ask one plain question: "What would you like to clarify?" Do not re-ask the
   same batch and do not guess the clarification.
6. When the answers come back, record them verbatim (archive-max-prompts) and act on them when the run ends;
   a question stays a question (question-not-ruling) until he answers it.

### Example (shape)
Q1 "tv-forge failed only on the shared-chain guard; rerun it holding the pen?" - Yes, rerun now (recommended) / Land
without it / Let me explain. Q2 "Retire D70 everywhere or keep the row as history?" ...

No tool: the work is choosing the questions; AskUserQuestion is the mechanism. Planted 0, caught 0 (doc-only).

Pairs with question-not-ruling, literal-execution, chain-the-queue, finish-everything, long-job (check_eta.py).

## click-level steps for things only the user's hands can do (merged from max-walkthrough)

### The problem (2026-10-12, transcript 4443f5bc line 208, 22:42Z)
the user: "give me specific directions... Explain like I am a dumbass". The useful answer was numbered click-level steps,
each ending in a paste-able check (`! python tools/doctor.py --quick`), plus two things that bite every time: never
paste a key into chat, and Claude Code must be restarted before a new environment variable is visible. plain-terms
covers jargon only; nothing checked that the steps can be followed and verified. Earlier scars (DESIGN_RULES v3 A1):
steps written from memory ("YOU FIND THE API KEYS BOX") that did not match the live page.

### Procedure
1. **Check the live thing first** (the website, the installer, the setting) - steps from memory are labelled
   "from memory, unverified" or not sent.
2. **One action per step,** numbered, in the order he will do them; say where to click by the words on the screen.
3. **End every step in a check:** a command in backticks he pastes (`! python tools/doctor.py --quick`), or what he
   should see ("it says SUCCESS").
4. **Keys:** say "never paste a key into chat" once, where the key is handled; the key goes into a prompt box,
   `setx` or a file he controls. Ask him to confirm "done", not to send the value.
5. **Environment variables** (`setx`, `$env:`) load only in new processes: add a step to close and restart Claude Code
   (or open a new terminal), then verify.
6. **Windows:** `python`, never `python3`; PowerShell syntax unless the step says Git Bash (windows-gotchas).
7. **Run the checker,** then plain-terms on the text, then send.

### The tool
```
python walkthrough_check.py steps.md
PROBLEM NO_VERIFY step 4: end with a command to paste or what he should see
PROBLEM NO_RESTART: a new environment variable loads only after restarting Claude Code / a new terminal
2 problem(s)                                   (or WALKTHROUGH_OK)
python walkthrough_check.py --selftest
```
Checks: NO_VERIFY, TOO_LONG (over 60 words), NO_KEY_WARNING, KEY_INTO_CHAT, NO_RESTART, PYTHON3, SECRET_SHAPED.
"The Windows key" is a keyboard key and does not count as handling a secret. Selftest 8/8. Planted 1, caught 1 (the
per-step verify check switched off).

Pairs with plain-terms (jargon), windows-gotchas, keys-in-process and question-not-ruling (his "done?" is a question).

### See also: max-inbox (candidate #60, added 2026-10-16)
- max-inbox harvests every item waiting on the user (ledgers, plans, #41, YOUR_TASKS/MAX_ONLY boxes), deduplicated with sources; feed its hands-on items to this skill one by one.
