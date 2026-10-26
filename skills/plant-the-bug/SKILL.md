---
name: plant-the-bug
description: Prove a new test (or a guard, cache check or shortcut) can actually fail by planting bugs in the code one at a time and watching the tests go red, then rule on every planted bug that SURVIVES (missing test / weak assertion / equivalent mutant / design smell / stale fixture) and act on the ruling. Ships plant_runner.py (byte-exact apply and restore, verdicts KILLED / SURVIVED / MISSING), survivor_court.py (checks the rulings) and pyc_fresh.py (so a stale .pyc cannot fake a verdict); inside the Autotrade workspace the in-repo tools/plant.py does the same job. Use this whenever you have just written a test or guard, before registering it as done, when a test passes the first time it runs, when a new test must be red on the old code (red-on-old swaps only the source file, never git stash), after each rule change (--compare), and whenever a green result feels too easy. Not for automatic in-memory mutants against a skill's own --selftest (use mutation-audit) and not for a static scan of assertions that can never fail (use weak-assert-scan).
---

# plant-the-bug

A test that has never been red proves nothing. This session planted bugs in about a dozen modules and found real gaps each time:
a test that passed whatever the sort order was, a fast path whose "behind" check nothing exercised, a title that was never escaped.
Before `tools/plant.py` each round was a throwaway script; now it is one command.

1. **Write cases.** A JSON list of `{"file": "path/relative/to/cwd.py", "old": "exact text", "new": "replacement"}`. Aim for 5 to 9
   per module, each a plausible mistake, not noise: flip a comparison (`<` to `<=`), drop a guard (`if False:`), change a constant
   (`30` to `31`), remove the line that restores or records state, swap two arguments, replace `!=` with `is None`, delete the
   escape / the lock / the validity check.
2. **Run:** `python <workspace>/tools/plant.py cases.json --cwd tv-screener -- python -m pytest tests/test_x.py -q -x -p no:cacheprovider`
   Each case is applied to the first occurrence only, byte for byte (line endings survive), tested, and the file is put back
   exactly even if the run is interrupted.
3. **Read the verdicts.**
   - KILLED: good.
   - SURVIVED: either a test is missing (add one that fails for exactly that bug, then re-run) or the change is harmless. Say which.
     Equivalent mutants exist (SQLite turns a divide by zero into NULL anyway; a redundant reset): remove the dead code instead of
     leaving an unkillable line.
   - MISSING: the old text is not in the file. Fix the case; never skip it.
4. **Write the numbers in the commit or the report:** "8 planted bugs, all killed" is a claim a receipt can show; "tests pass" is not.
5. Do not plant bugs in files another session is editing, and never in a tree you cannot restore (the tool restores, but a
   crashed machine does not): commit first.

## The tool (ships with this skill)
```
python ~/.claude/skills/plant-the-bug/plant_runner.py cases.json --cwd . -- python -m pytest tests/test_x.py -q -x
python ~/.claude/skills/plant-the-bug/plant_runner.py --selftest
# library: from plant_runner import run_cases, format_report
```
A portable, repo-free version of the procedure above: same `{"file","old","new"}` cases, first occurrence only, byte-exact
apply and restore in `finally:`, verdicts KILLED / SURVIVED / MISSING (and TIMEOUT), and the "N planted bugs: K killed,
S survived, M missing" line. Exit 0 only when every case is killed. Inside <workspace>, `tools/plant.py` remains the
in-repo option; feed `run_cases()` output to `survivor_court.py` (below) for rulings.

## Ruling on survivors (merged from survivor-court)

On 2026-10-12/13 every new piece of code had survivors, and every ruling fell into one of five verdicts. Write one next to each SURVIVED/MISSING mutant and act:
1. **MISSING TEST** - real behaviour nothing checks (seen: exact boundaries like a 0.5% gap / 5.0x jump / 1.25 tolerance, a refusal naming a symbol never sent, a commit the peer already took). Write the killing test; re-run.
2. **WEAK ASSERTION** - the assertion cannot fail (`x or True`, `a or "0 days" in out`, `if False`, a substring also inside another message). Tighten to the exact value/line. Seen four times in two days, all in tests Claude had just written.
3. **EQUIVALENT** - cannot change behaviour. Prove it in one sentence, then remove the redundant code or comment why it exists. Never count it as caught.
4. **DESIGN SMELL** - unkillable without a contorted test = the code mixes two jobs; split it (the Alpaca stream timeout moved into a thin adapter with its own fake clock).
5. **STALE FIXTURE** - the mutant text is not in the file (MISSING). Fix the case, never drop it.

Re-run until every case is KILLED or proven EQUIVALENT; report "N of N caught, M equivalent (why)", never "all green". Plant at boundaries and conditions first.

```
python ~/.claude/skills/plant-the-bug/survivor_court.py results.json rulings.json --tests tests/test_x.py
python ~/.claude/skills/plant-the-bug/survivor_court.py --selftest
# library: from survivor_court import judge, scan_weak_assertions
# rulings.json: {"3": {"ruling": "EQUIVALENT", "why": "the later filter drops every row this lets in"}}
```
Flags unruled survivors, unknown ruling words, EQUIVALENT without a proof, a MISSING case not ruled STALE FIXTURE, and a ruling on a KILLED case; keeps every non-EQUIVALENT ruling OPEN until a re-run kills it; computes the "N of N caught, M equivalent (why), K open" line. `--tests` scans test files for assertions that cannot fail.

Append to ~\.claude\skills\plant-the-bug\SKILL.md (candidate #21, test-oracle-edge-clamp). No tool.
----------------------------------------------------------------------------------------------------------------------

## BASELINE_RED: the test is red before anything is planted (added 2026-10-16)
A new test that fails on the UNMUTATED code is not a found bug until its own oracle is cleared. Twice in a row in
session 4443f5bc (transcript L4907 "assert (47 == 47 and 59 == 60)", L4927 "assert 1 == 9") the fault was the
test's guard at the edge of the data: "a target before c's first date clamps to c's first bar... I'll test against
a's pick" (L4935). Earlier the same session: "the one failing test had the lag sign wrong" (L129).
1. Suspect the oracle first: how does the TEST compute the expected value? A lookup that clamps an index to the first
   or last bar, a nearest-date search, an off-by-one lag sign, a window that is shorter at the ends.
2. Compare against the source of truth the code itself uses (the event's own pick, the recorded timestamp), never a
   clamped or re-derived proxy of it.
3. Give the edge its own test: a target before the first bar and after the last bar, each with the expected
   behaviour written down (clamp, skip, or refuse) - the edge is where both bugs above lived.
4. Only when the oracle is shown right is the red a real code bug: fix the code, then plant as usual.
5. Report it: "BASELINE_RED on test_x: oracle clamped at the first bar; fixed the test, added test_x_before_first_bar".
Never weaken the assertion to make the baseline green (the no-test-weakening guard, GT35, refuses that for a reason).

Tool placement: copy `plant-the-bug__pyc_fresh.py` to `~\.claude\skills\plant-the-bug\pyc_fresh.py` (candidate #23).
Append the text below the line to plant-the-bug/SKILL.md.
----------------------------------------------------------------------------------------------------------------------

## Stale bytecode can fake a verdict (added 2026-10-16)
Errata E26 (2026-10-15): plant.py "could report false KILLED and false SURVIVED: Python trusts a cached .pyc whose
header matches the source's size and whole-second mtime". A same-size mutant applied and restored within one second
runs the OLD code. `PYTHONDONTWRITEBYTECODE=1` was then set by hand in many runs - but it only stops WRITING; a .pyc
left by an earlier run is still READ. plant_runner.py runs the command with the caller's environment, so it has the
same exposure.
1. Wrap the test command with `pyc_fresh.py` (ships with this skill): it points `PYTHONPYCACHEPREFIX` at a fresh empty
   folder (reads and writes both go there), sets `PYTHONDONTWRITEBYTECODE=1`, and deletes the folder afterwards:
   `python plant_runner.py cases.json --cwd . -- python pyc_fresh.py -- python -m pytest tests/test_x.py -q -x`
2. A tool run as a script (`python tool.py --selftest`) compiles its own file fresh, but every module it IMPORTS is
   still cached: wrap it too when the mutant is in an imported module.
3. `python pyc_fresh.py --selftest` reproduces the hazard on this machine (2026-10-16, Python 3.13): a same-size,
   same-mtime edit still printed the old value in a plain run AND with PYTHONDONTWRITEBYTECODE=1; under pyc_fresh it
   printed the new one. 6 PASS; planted 2, caught 2.

Append to ~\.claude\skills\plant-the-bug\SKILL.md (candidate #22, symmetric-test survivors; COVERED by "Ruling on survivors", this adds the pre-plant question). No tool.
----------------------------------------------------------------------------------------------------------------------

## Before planting: would order or identity change any assertion? (added 2026-10-16)
Session 4443f5bc (transcript L4893): 2 of 4 planted bugs SURVIVED - `if probe is not None: probe(picks[::-1])` and
`targets = [rng.choice(times)...` - because every assertion was symmetric: sums, sets, counts and sorted lists do
not notice reversed, shuffled or swapped inputs. The ruling was MISSING TEST both times, found only after planting.
Ask this before writing the cases, and add the killing test first:
1. Would reversing the input change any assertion? If the code's output depends on order, some assertion must too
   (compare the exact sequence, the first and last element, or a running value).
2. Would shuffling or re-sampling change any assertion? Pin the seed and assert one exact drawn value.
3. Would swapping two symmetric arguments (a, b) / (start, end) / (picks, targets) change any assertion?
4. Then plant exactly those mutants (`x` -> `x[::-1]`, swap arguments, `rng.choice` -> first element). A survivor
   here is a MISSING TEST, never EQUIVALENT unless one sentence proves the output cannot depend on order.

## Red on old, re-score after each rule change, a plant file that says how to run it (added 2026-10-24)
1. **Red on old: swap only the source file.** A new test for a fixed bug must be red on the OLD code. `git stash`
   takes the new test with it, so the "red" proves nothing (2026-10-21, L7139: "That red check was invalid: the
   stash took the new test with it"). Use:
   `python plant_runner.py red-on-old --source harvest/mirror.py --ref HEAD -- python -m pytest -q tests/test_mirror.py -k html`
   It puts `git show REF:file` in place of that ONE file, runs the test (must fail), restores the new bytes exactly,
   runs again (must pass). Verdicts RED_ON_OLD_GREEN_ON_NEW / NOT_RED_ON_OLD / NOT_GREEN_ON_NEW / SAME_AS_OLD (the
   fix is already committed: use `--ref <fix>~1`). Real run 2026-10-24 in the harvest_fred scratch clone, E12 fix
   1fa85ce: `RED_ON_OLD_GREEN_ON_NEW {'rc_old': 1, 'rc_new': 0}`, clone left clean.
2. **Re-score after each rule change.** A new rule can quietly make a planted bug survive (2026-10-20, L2073: the
   new rule moved 35/1/4 to 33/2/5 and one plant survived). Keep the last results and compare:
   `plant_runner.py cases.json --out r2.json --compare r1.json -- <test>` prints REGRESSION (KILLED -> SURVIVED),
   FIXED and NEW per case and exits 1 on a regression. Re-score dev AND holdout too when the code is an extractor.
3. **Plant file header.** A plants/*.json file should say how to run it (2026-10-21, L5834: the session grepped the
   repo to find the runner for tests/plants/gt199.json). plant_runner accepts
   `{"how_to_run": "...", "run": ["python", "-m", "pytest", "-q", "tests/test_x.py"], "cwd": ".", "cases": [...]}`
   (then no `--` command is needed) or a list whose header element has no "file" (`{"_header": "..."}`). Limit: the
   in-repo tools/plant.py reads only a bare list today - a header element there would count as a case; extending
   it is a repo change for the lead session.
Selftest 14/14 (6 new; planted: a test that cannot see the old bug must read NOT_RED_ON_OLD).

## The prove-it-can-fail family (one question, three tools)

Mining layer 10 (2026-10-16, route-audit on 280 skills) found that mutation-audit, weak-assert-scan and
fake-secret-sentinels all route to this skill, and that this skill routed to command-tour. They answer one
question: can this check fail? Use this table to pick the tool instead of searching again:

| situation | tool |
|---|---|
| a test, guard or fast path you just wrote: plant bugs by hand, rule on each survivor | this skill, tools/plant.py |
| a skill's own `--selftest`: automatic mutants in memory, kill rate per line | mutation-audit |
| a test file that might hold assertions that can never fail (`or True`, `x == x`, an asserted tuple) | weak-assert-scan (static, nothing runs) |
| a CLI's usability: dozens of real commands, the frictions a person hits | command-tour (not a test-strength tool) |

The layer suggested merging the three into one folder. That is not done here, because merging deletes skill
folders and is the library owner's call. The table gives the single entry point without deleting anything.
