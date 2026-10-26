---
name: dead-lane-check
description: Before running any experiment or test on a trading idea, look the lane up in the verdict record (memory notes, GRAVEYARD.md, receipts, kill logs, DECISIONS, PREREG files) and state its standing verdict - DEAD / OPEN / ALIVE, the newest dated line winning and a CORRECTED or SUPERSEDED line beating its own date - with every source line printed; refuse to re-run a DEAD lane unless the new run names what is different. Ships lane_verdict.py. Use this whenever you are about to test, backtest, sweep or "just check" a strategy, signal, indicator or market idea, when the user asks "why are you predicting coin movements?", "a real edge at what?", "why so many wasteful tests?", and before any experiments/sketches file.
---
# dead-lane-check

## The problem
085faced 10-15T22:21-22:23: asked to run the tools on the forward record, Claude downloaded prices and ran 28 tests,
including short-horizon coin prediction. the user: "A real edge at what", "why are you trying to predict coin movements?
why so many wasteful tests?", "stop wasting tokens dude". The record already held the answer. A run of this tool on
2026-10-16 with `coin prediction` over the memory folder and GRAVEYARD.md answered STANDING DEAD in one line, citing
the note written after that exchange. The record also corrects itself (memory autotrade-strategy-state: "PREDICTION
IS UNTESTED, NOT DEAD (CORRECTED 2026-10-07 ...)"), so the newest dated line must win, not the loudest one.

## Procedure
1. Name the lane in 1-3 words (every word must appear in a line, matched on its first 5 letters): `coin prediction`,
   `reversal`, `trend`, `calendar`.
2. `python lane_verdict.py <lane words> --record ~\.claude\projects\C--Users-the user\memory --record <workspace>\GRAVEYARD.md --record <workspace>\receipts`
3. Read the STANDING line and the earlier ones: one line can mention two lanes (a "prediction markets: calibrated"
   line is not about coin prediction), so narrow the words if the hits mix lanes.
4. DEAD (exit 3): do not run it. Run it only if you can name what is new - other data, another horizon, a cost tier
   never tested - and pass that as `--different "..."`; put the same sentence in the pre-registration (pre-register).
5. OPEN or ALIVE: go ahead through test-a-condition / backtest-verdict; quote the standing line in the report.
6. Exit 1 (no verdict found): search by hand once (prompt-genealogy, GRAVEYARD) before calling the lane new.

## Usage
```
python lane_verdict.py coin prediction --record <memory dir> --record <workspace>\GRAVEYARD.md
lane 'coin prediction': STANDING DEAD (2026-10-15)  <- ...\memory\stop-wasting-tokens.md:11
  Asked to "run the tools on the forward record", I downloaded prices and ran 28 tests, including short-horizon coin prediction (already known dead)...
DEAD lane: do not re-run it. Name what is different (--different "...") or stop.          # exit 3
python lane_verdict.py --selftest
```
`--year` sets the year for "10-07"-style dates (default 2026), `--json`. Exit 0 / 3 / 1 / 2 as above. Reads only.

## Proof
`--selftest`: 10 checks (all words required, stem match, newest-dated line wins over an older DEAD, OPEN read before
DEAD on "UNTESTED, NOT DEAD", CORRECTED wins a same-date tie, hidden folders skipped, --different, exit codes, two
dates in a line). Planted 6, caught 4 on the first run; the survivors (earliest date taken; stems not cut) got a
two-date test and a plural query, and the rerun caught 6 of 6.

Pairs with token-thrift (and the finders-discipline memory note), test-a-condition, backtest-verdict, pre-register, signal-vetting,
fascination-forge (its kill-log bins are this record), research-spine.
