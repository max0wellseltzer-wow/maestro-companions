---
name: decision-renumber
description: How to land branches that each drafted their own DECISIONS.md numbers without editing a row on main, losing a row, or using a number twice - order-only conflict resolution, "(was Dnn on <branch>)" prefixes, one renumber line in the branch's plan, and a checker script that proves append-only. Use whenever a merge, rebase or cherry-pick touches DECISIONS.md, when a branch or plan says "claims D..", when two sessions might take the same number, when a mailbox post reserves numbers, and before telling anyone "the next free decision is Dnn" - and to find the next free D/E id (decision D, erratum E, GT card or any prefixed id) that no branch claims by scanning main, every remote branch, unlanded commit messages ('errata E77 to write') and the work tree, listing every id two branches both claim, before writing a new D-row, E-erratum or GT card or when landing a branch that drafted its own ids, and when DECISIONS.md shows two rows with one number or a peer pushed the D number you just used.
---

# decision-renumber

Earned on 2026-10-13 (wave 4): D79-D90 had THREE claims at once - autotrade-ba's merge plan reserved D79/D80 for
eager-cray and D81-D90 for bold-lamport's proposals; bold-lamport then wrote D79-D88 as real rows (the user confirmed them);
eager-cray's branch still said D87-D89; and main had meanwhile taken D91-D153 for tv-lens. Issue #33 and the D92-D152
key row are the same story earlier. The rule that resolves all of it is in root CLAUDE.md: decision numbers come from
main; a row on main is never edited; a branch renumbers its OWN drafts.

## The procedure

1. **Read main, not a plan.** `git fetch` and look at `origin/main:DECISIONS.md`. A plan's or a mailbox post's
   reservation is a wish; a row on main is a fact. If a branch's rows were the user-confirmed under their numbers and main
   has not used those numbers, they keep them (bold-lamport kept D79-D88). Otherwise they move to the next free.
2. **Ask who else is landing decisions right now** (ListAgents + SendMessage, mailbox #41). Two sessions taking "the
   next free number" at the same minute is how the clash happens. Say the number you are taking before you write it.
3. **Resolve a DECISIONS.md conflict by ORDER ONLY.** Both sides' rows survive byte for byte; you only choose where
   each block goes (ascending by number). Do it with a script that splices the two hunks, not by hand-editing rows.
4. **A moved row gets a prefix and nothing else:** `| D154 | (was D88 on claude/eager-cray-nof1xc) <the row as
   written> |`. Keep its status words (PROPOSED stays PROPOSED - landing a row is not the user deciding it). A row that is
   already on main under another number (eager-cray's D87 = main's D91) is dropped from the incoming side, not repeated.
5. **The branch's own documents keep their draft numbers.** Add ONE line where the plan states them:
   "Landed on main (date, wave) as: D87 -> D91, D88 -> D154, D89 -> D155." Rewriting every mention is churn and
   breaks the link to the mailbox history. (Exception: machine-read text such as a manifest's LAWS list must cite the
   real rows - tv-forge E69 found a manifest quoting main's D69-D83, which are other decisions. When mentions must
   move, use renumber_refs.py: see "Appendix: moving mentions with proof".)
6. **Run the checker against the base you merged onto:**
   `python .claude/skills/decision-renumber/check_decisions.py --base origin/main`
   It must say `APPEND_ONLY` and `VERDICT: OK`. It names GAPS (state them: "D89 and D90 are unused") and NEXT_FREE.
7. **Announce in one line** on #41 and to live peers: the new rows, the moves, the gaps, the next free number.
8. **A row recording the user's choice is written by the session that heard it**, quoting his words and their source
   (MAX_PROMPTS file + prompt number). Decline to write one from a peer's paraphrase (2026-10-13: D156 was written by
   the session that held the user's "Alpaca only for now", not by the one asked to).

## The checker (check_decisions.py)

Exit 1 on a DUPLICATE number or a ROW_EDITED_OR_REMOVED base line; reports OUT_OF_ORDER, GAPS, NEW_ROWS, NEXT_FREE.
Proven 2026-10-13: on main a5d00c5 vs c994ee8 it read OK (149 base lines kept, new D79-D88, D154-D156, gaps D89/D90);
a planted duplicate D155 and a planted one-word edit of D78 both turned it red for that reason.

## Traps
- `| D92-D152 key |` style rows are notes, not numbered rows; the checker ignores them on purpose.
- A clean `git merge` of DECISIONS.md is not proof: a silent auto-merge can still give two rows one number. Run the checker.
- CRLF: the live checkout may store CRLF; compare in the repo's own encoding (the checker reads text, line by line).

## Appendix: moving mentions with proof (renumber_refs.py)
Use this only on step 5's exception path: text that must cite main's real rows. That means a manifest's LAWS list,
or a project CLAUDE.md that every session reads as law. On 2026-10-13 tv-lens/tv-forge arrived citing their drafts
D69-D129, which on main are other decisions. A hand sweep moved 503 mentions (+23), and it made one slip: it also
"moved" the root CLAUDE.md, a file BOTH sides had, which already cited main's numbers. The script makes both lessons
mechanical:
```
python .claude/skills/decision-renumber/renumber_refs.py --repo <clone> --base <main-ref> --branch <branch> --lo 69 --hi 129 --offset 23
python .claude/skills/decision-renumber/renumber_refs.py ... --apply
```
- It only touches files the branch ADDED (`git diff --diff-filter=A base...branch`), so a file main also has is
  never rewritten.
- In .py files it only touches comments and docstrings, by tokenizer position. Runtime strings, and tests that match
  them, keep the drafted number. It prints a proof per file: the AST with docstrings blanked is identical before and
  after (AST_SAME). Otherwise it refuses the file (AST_CHANGED, exit 1).
- It never touches prompts/, errata.md, progress.txt, tests.json, *.json or *.chain.jsonl.
- Then add the key row to DECISIONS.md (`| D92-D152 key | ... old + 23 = new |`) and a one-line note at the top of
  each swept CLAUDE.md, and still run check_decisions.py.
Tests: `python -m pytest -q .claude/skills/decision-renumber/test_renumber_refs.py` (5). They cover: comments and
docstrings only, with code strings kept; .md moved whole and .toml in comments only, with range bounds respected;
skipped files; a planted code change refused; and only ADDED files touched (the CLAUDE.md slip, replayed).
Selftest: `python check_decisions.py --selftest` and `python renumber_refs.py --selftest` (hermetic: temp dirs + temp git repos).

## Next free id across branches, before you write (merged from free-id-reserve)
Ids clash before anyone lands: on 2026-10-15 "E72 is already TAKEN ... renumber to E73", "no branch has already claimed
D159" needed an ad-hoc loop, and E77 existed only as "errata E77 to write" in W3's commit message. The checker above
works at landing and on D only; next_free_id.py looks across every branch BEFORE you write, for any prefixed family.
1. `git fetch` first (the tool never fetches; say when you fetched).
2. Run it in the repo whose ledger you will write (errata are per project):
   `python next_free_id.py --repo <repo> --kind E --base origin/master --worktree`
3. CLASH = two branches define one id with different text: main's row wins, the branch renumbers its own draft at
   landing (precommit-bundle does errata).
4. Take NEXT_FREE (above every hard and soft claim, so free on every branch); announce it ("taking E81 in tv-screener")
   before writing, then write, commit and push soon.
5. **A message is not a claim; a pushed row is.** On 2026-10-21 max-10 told autotrade-59 "please don't take D175";
   the message sat unread in its inbox and autotrade-59 took D175 and D176, then D177 after max-10's D177 had
   landed. Push the row (even a short one) within minutes of choosing the number, and re-run this tool right
   before every push of a ledger: `git fetch` and re-scan, never trust the scan from before your work.
6. When it happens anyway: the row that landed LATER renumbers ("(was D177 in root 5b128fb)"), unless the earlier
   one has fewer references to move; say which you chose and why in the commit and to the peer.
   Count the references, do not guess: `git grep -l "D180" origin/main -- . ':!DECISIONS.md' ':!MAX_PROMPTS*'`
   per side (and in each tv-* submodule). The side cited in more live files keeps the number.
7. A second clash with the SAME peer in one day means number-picking is racing: stop, agree a block per session on
   #41 and by SendMessage (e.g. "max-24 takes D181-D184, you take D185-D188"), and write rows only inside your block.
8. Before every append, re-run `next_free_id.py` right then (after `git fetch`) and append with record-row-append
   (`row_append.py --kind D --row "| D? | ..." --skip-if-present`), never with a hand d1NN.py script.
```
Scars:
- 2026-10-21 (max-24, L7521): appended D178 from an old read; another session's D178 (TradingView) was already
  there - DECISIONS.md read D175, D176, D178, D177, D178. Renumbered to D179 "(was D178 in root ee5672c)".
- 2026-10-21 (max-24, L7748): same peer, same day - my FRED row was pushed as D180 while autotrade-59's design-hints
  D180 was already cited in ten CLAUDE.md files. Mine moved to D181 (fewer references). The renumber commit then hit
  a rebase conflict on DECISIONS.md inside a one-line `rebase && ... ; push` (L7750-7759).
python next_free_id.py --repo <workspace>\tv-screener --kind E --base origin/master --worktree   # exit 1 if a CLASH exists
python next_free_id.py --repo <workspace> --kind D --base origin/main                           # DECISIONS.md by default
python next_free_id.py --repo <workspace> --kind GT --file "plans/*.md" --json
python next_free_id.py --headings <workspace>\plans\PLAN.md --under 31   # numbered headings: CLASH + NEXT_FREE section
python next_free_id.py --selftest                                                                # 14 checks, temp git repo
```
Section numbers are ids too: two sessions both wrote `### 31.7` on 2026-10-21. `--headings` lists every numbered
heading (`## 32.`, `### 31.7`) defined twice and the next free child number (31.10 sorts after 31.9). Exit 1 on a clash.
A claim is a line that starts with the id (after `|`, `-`, `*`, `#`, `**`); prose mentions are not claims; ids named in
unlanded commit messages are SOFT claims. Planted 4, caught 4.

## Provenance (note only; no change to the procedure)

Candidate #29 of the 2026-10-16 skill mining ("decision-number sweep with AST proof") is already covered by the
appendix above. Its source is transcript 4443f5bc lines ~1362-1455 (2026-10-13): 503 references D69-D129 moved to
D92-D152, with "every changed .py file must have an identical syntax tree... once docstrings are set aside" and
runtime strings kept - the origin of AST_SAME and the runtime-string rule. Nothing was missed; no new text needed
beyond this line of provenance.
