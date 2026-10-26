---
name: transcript-miner
description: Read every past session transcript in full via digests and fresh-context readers - for completeness audits ("are you done?", "what did I ask for"), rewriting rules from what really happened, finding repeated mistakes, or recovering lost asks. Use when the user says read the transcripts, all our sessions, study the work we've done, or "make 4 times sure you are done".
---

# transcript-miner

Raw transcripts are 2-35 MB each, mostly tool output. Read raw, they overflow any context; skimmed, they hide exactly the
asks that got lost. On 2026-10-12 this method read six sessions (~20,300 digested lines) in about four minutes with three
readers, and the audit found work Claude had forgotten (an unrun full-universe scan, an unopened pack, a skill never built,
open items under-reported) - things the user had already had to point out by hand.

## 1. Digest (one command, safe to share with readers)
```
python ~/.claude/skills/transcript-miner/scripts/digest.py ~\.claude\projects\C--Users-the user <out folder> [--since 2026-10-10]
```
Keeps the user's prompts verbatim, Claude's visible text, one line per tool call; drops tool output, reminders, notices.
Redacts long key-like strings AND any value assigned to a key/secret/token/password name (a 120-character cut once left
half a secret in a digest). Splits into ~180 KB parts with `INDEX.md`. Then run `python <workspace>\tools\secretscan.py
<out folder>` before anyone reads it.

## 2. Fan out fresh readers (one part or session per reader, in parallel)
Give each reader the parts' paths and the SAME report shape, so the reports merge:
1. Every ask of the user's, in order, with status DONE (evidence: digest line or file), PARTLY, NOT DONE; every "next I will"
   promise and whether it was kept.
2. the user's corrections and frustrations, quoted briefly with time, and what Claude had done wrong.
3. Recurring Claude failures, with counts and examples.
4. Practices that caught real bugs (the incident), and practices that cost time and caught nothing.
5. the user's standing preferences.
Tell readers: read IN FULL with offset/limit paging, cite timestamps, never quote a secret, modify nothing.

## 3. Merge and act
- The NOT DONE / PARTLY lists become the open queue (ledger section), checked against git and files before claiming
  anything is still open - a reader sees the transcript, not the repo.
- Repeated failures feed the rules (see `scar-to-rule`); each needs a mechanism, not a sentence.
- Report to the user: what was found open, what you did about it, what is his.

## Notes
- A blocked command is still in the transcript: the guard stopping it does not erase it from disk.
- Readers are fresh context on purpose: they do not share the session's blind spots. Verify their claims before acting.
- Tests: `scripts/test_digest.py` (4 tests; 7 of 7 planted bugs caught).
- Selftest: `python scripts/digest.py --selftest` (7 hermetic PASS/FAIL checks on a synthetic transcript; exit 0 = all pass).

## Every miner masks before it writes: mask_text.py (candidate #66, added 2026-10-16)

digest.py redacts keys, but only inside digest.py. On 2026-10-15/16 the layer-5 miner (tx_mine.py, a one-off script)
streamed all 138 transcripts and one prompt (f562dc10 10-11T22:39) carries a paper-trading key and secret in clear
text; the digests had to be re-run through a mask after the fact. Nothing masked e-mail addresses at all.

Tool: `mask_text.py` goes in `scripts/` beside digest.py. Import `mask()` in any ad-hoc miner and call it on every
string before it is written; or run it as a filter. It masks prefixed keys (PK/AK/SK + 14 caps/digits, sk-, ghp_,
xox, AIza), 32+ character alphanumeric runs (but keeps 40/64-character lowercase hex: git shas and sha256 digests),
values assigned to key/secret/token/password names (not KeyError text, `{PLACEHOLDER}`s or code expressions) and
e-mail addresses (<email> and noreply kept).
```
python mask_text.py --check <scratch dir>        # file:line: kinds, never the value; exit 1 if anything is unmasked
python mask_text.py --in-place <file> ...        # masks, keeps CRLF
from mask_text import mask
```
Before zipping, posting or committing any mining scratch: `--check` must print `0 line(s)`. A run on 2026-10-16 over
the layer-4+ mining folder (28 text files) gave 0 after the 20 hits it first raised were fixed as false positives (10 from an over-broad PK/AK/SK pattern; 10 ASSIGNED: KeyError,
`{ENV}` placeholders, `SECRET = re.compile`). If a real key is ever found, keys-in-process says: ask the user to rotate it.
Proof: selftest 9/9; planted 6, caught 5 first, the survivor (KeyError guard untested) got a test, then 6 of 6.
