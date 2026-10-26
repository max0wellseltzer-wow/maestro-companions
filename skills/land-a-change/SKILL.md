---
name: land-a-change
description: Land a code change in this workspace with the exact ritual - tests, lint, tests.json registry, check_all.bat until it ends CHECK_ALL PASSED, submodule commit, push, root pointer bump - so nothing is registered-but-missing, unpushed, or red on a clean clone; land.py lands commits from a scratch clone into a live repo a peer session keeps committing to (pen, cherry-pick, tests.json union, re-check, push, root pointer), live_sync.py pulls the live tree to origin after a land without losing job-written chain lines, landing_gate.py grades the reported facts of a landing LAND or HOLD, peer_sweep.py finds a peer commit that swept your unfinished work, sibling_preflight.py tells a scratch-layout false red from a real one, and checked_tree.py proves the commit is the tree the green check saw. Use this whenever code in any tv-* project is ready to commit, when a landing races a peer, a push is rejected, after a land when the live <workspace> must catch up, tests.json conflicts, or a check is red only in a scratch clone. Not for a read-only ahead/behind table (tree-status) or the staged-only pre-commit gate (precommit-bundle).
---

# land-a-change

Repeated about 15 times this session; each skipped step cost a round trip (an unregistered test, a test file left out of a commit).

In the project folder (example `tv-screener`):
1. `python -m pytest <the test files you touched> -q` - green. Plant one bug and see it red if the test is new (rule 10).
2. `ruff check <paths>` - clean.
3. Register every new test id in `tests.json` (one entry per parametrized case), then run `tests/test_tests_json.py`.
4. `python <workspace>/tools/precheck.py <the paths you meant to change>` - compiles, nothing stray.
5. Full project check (`check.bat`) before the FIRST push of a session and after any change to shared code. Say in the report
   whether you ran it; "targeted tests only" is a fine statement, a silent skip is not.
6. `git add <files by name>` (never `-A`: the root has files that are not yours), commit with the Co-Authored-By line, `git push`.
7. In the root repo: `git add <project folder>` (the pointer) plus any root files you changed by name, commit, push.
8. If another session shares the project, tell it the commit id (SendMessage or mailbox #41).

Do not push when the check is red. Do not leave it for later: a clean clone must pass.

**A check outside the workspace is not the same check** (2026-10-13, wave 4). A scratch clone of ONE project loses
its siblings: tv_blend.stack looks for `quality-kit` beside itself and reported STACK_UNAVAILABLE in a clone under
the scratchpad. It would have passed in <workspace>. The reverse also happens: a clone can pass because it lacks
data the live tree has. Before calling a scratch-clone check red or green:
- recreate what the workspace gives it, read-only: `PYTHONPATH=<workspace>\<sibling>` or clone the siblings next to it;
- say in the report which siblings or data it ran with;
- keep the whole output (`*> file`), not the last lines.

**Landing a cloud branch on the PC:** run the windows-port-audit scanner (`--diff origin/main`) first. When the
merge touches DECISIONS.md, run decision-renumber's `check_decisions.py --base origin/main` before you push.

## The tool (ships with this skill)
```
python landing_gate.py --facts facts.json    # each step PASS / FAIL / STATED / N/A, then VERDICT: LAND or HOLD
python landing_gate.py --selftest
```
```python
from landing_gate import evaluate, bad_add_args, unregistered
steps, verdict = evaluate({"tests_green": True, "ruff_clean": True, "collected_ids": [...],
    "registered_ids": [...], "precheck_ok": True, "full_check": "targeted tests only",
    "git_add": "git add a.py tests/test_a.py", "co_authored": True, "root_pointer_bumped": True})
```
It runs nothing; it grades the facts you report against steps 1-8. Two parts are mechanical: a `git add` with `-A`,
`--all`, `.` or `*` fails, and every collected test id (each parametrized case) must be in tests.json. A full check that
was neither run nor stated is a FAIL (a silent skip), and a scratch-clone check must state its siblings.

## Racing a live peer: one-command landing (merged from race-lander)

Built 2026-10-12, when a peer committed between my full check and my push and `tests.json` conflicted five times in one session - the same 15 manual steps as one tested command, on top of steps 1-8 above and `writer-pen` (the lock).

```
python ~/.claude/skills/land-a-change/land.py --live <workspace>\tv-screener --clone <scratch clone> ^
       --root <workspace> --check check.bat --checked <sha your clone's full check passed on> --label "what lands"
```
Add `--dry-run` first if unsure. One line per step; act on the exit code:

| code | meaning | what to do |
|---|---|---|
| 0 | landed and pushed (or nothing new) | report the line it printed |
| 2 | bad arguments | fix the command |
| 3 | the pen is held | keep building in the clone; retry later (never force) |
| 4 | a real conflict (not just tests.json) | nothing landed, live tree restored: rebase the clone onto live, resolve, re-check |
| 5 | the full check failed after the merge | commits are in the live repo, NOT pushed: fix in place or reset to origin and redo |
| 6 | a push was rejected | someone pushed meanwhile: run it again |

Guarantees (each a test in `test_land.py`, 11 tests, 11 of 11 planted bugs caught via `land.py.mutants.json`):
- The peer's commits are never dropped: when live moved, yours are cherry-picked ON TOP; one the peer already took is skipped (`git cherry` patch ids).
- `tests.json` conflicts merge by **union by test name** (a colliding id gets a suffix); any other conflicted file stops everything and restores the live tree exactly, including commits picked before the conflict.
- The full check reruns whenever the landed HEAD is not the exact commit your clone's check passed on; "passed" = exit 0 AND the words CHECK PASSED.
- The pen is released on every path, including failures.

Not its job: targeted tests/ruff/planted bugs (steps 1-4, `plant-the-bug`) or deciding whether to land. `python land.py --selftest` (hermetic temp repos + temp bare origin; never the pen, never a real remote); `python -m pytest -q -p no:cacheprovider test_land.py`.

## Multi-repo landings: order, and the drift check at the end (2026-10-15)

Candidate #8 (COVERED by land-a-change + tree-status; this section only writes down what went right and the one
miss). On 2026-10-15 nine submodules were fast-forwarded and landed in one pass and it went smoothly because the
order held:
1. Each project first: its check, its commit, its push (steps 1-6). A project on a detached head (tv-blend was)
   gets a branch or is fast-forwarded before anything lands in it.
2. Only then the root: `git add <project>` pointers by name, commit, push (step 7).
3. Check that no sub-project version moves backwards: for every changed pointer,
   `git -C <project> merge-base --is-ancestor <old pointer> <new pointer>` must succeed.
4. Last, run tree-status with `--fetch` - not before, AT THE END. The one miss of 10-15: the live tree fell one
   commit behind because another session pushed while the landing ran. Only the closing tree-status showed it.
   Report "N behind after landing (peer push <sha>)" instead of "everything is pushed".

Evidence: transcript 4443f5bc L1305, L4491-L4617 (the drift at L4617).

## See also (merge conflicts in ledgers, and the marker gate) - added 2026-10-16
- precommit-bundle: progress.txt / errata.md (with id renumbering) / tests.json conflicts outside land.py, CRLF-safe.
- precommit-bundle: `marker_gate.py --staged` before every commit that follows a resolve; gate on its exit code, never `;`.

## Peer sweep: did a peer's commit carry my unfinished work? (added 2026-10-21)
In a tree two sessions share, a peer's `git add -A` commits whatever lies there. On 2026-10-21 tv-screener 6717641 (a
peer's "D180 design hints") took max-10's new test and its tests.json entry but not the code they test: main was red
until ad704a5. After every fetch, before you commit, run this on each repo you are editing:
```
python peer_sweep.py --repo <workspace>\tv-screener --since <your last base sha> --upto origin/master
python peer_sweep.py --repo . --since <sha> --run -- python -m pytest -q -p no:cacheprovider {files}
python peer_sweep.py --selftest     # 5 PASS lines (temp origin + two clones; my new untracked test swept by the peer)
```
SWEPT = a peer commit holds a file byte-equal to your working copy (your work landed under its name; push the rest
NOW). TOUCHED = it changed a file you have edits in (merge before committing). `--run` runs the swept test files in a
clean detached worktree of UPTO, never stashing the live tree: RED means main is half-landed. Exit 0 nothing of
yours, 3 SWEPT/TOUCHED, 1 RED, 2 bad args. Planted 4, caught 4 (the untracked-file case was a survivor until added).

## Sibling preflight: no more scratch-layout false reds (2026-10-16)
The warning above ("A check outside the workspace is not the same check") was hit three more times: tv-blend 4 tests
"STACK_UNAVAILABLE: quality-kit... not importable"; tv-desk "no data file at ...scratchpad\mall\tv-tests\tests\golden";
a tv-core test that "reads the root check_all.bat, which doesn't exist in the scratch layout". Prose did not stop it,
so run the preflight before any check outside <workspace>, and again on the log after a red:
```
python sibling_preflight.py tv-desk <scratch root>                  # MISSING tv-tests/tests/golden/frozen -> exit 3 LAYOUT
python sibling_preflight.py tv-desk <scratch root> --log check.log  # each FAILED/ERROR line LAYOUT or OTHER; exit 1 if any OTHER
python sibling_preflight.py --selftest                              # 9 PASS lines
```
- Exit 3 = LAYOUT: the run is neither red nor green. Add the siblings (clone them beside it, or `PYTHONPATH`) or run
  in the workspace; report it as LAYOUT, not as a failure.
- Exit 1 = at least one failure is not explained by a missing sibling: a real red.
- New sibling dependency found? Add it to a `--manifest` JSON ({"project": [{"path", "signs"}]}) and to DEFAULT.
Real run 2026-10-16: tv-blend in <workspace> -> OK; tv-desk in scratchpad\mall -> MISSING, LAYOUT.
Planted 5, caught 5 (missing-path test, LAYOUT sign match, OTHER exit, custom manifest, UTF-16 log).

Append to ~\.claude\skills\land-a-change\SKILL.md (candidate #49, commit-the-checked-tree).
Tool: copy land-a-change__checked_tree.py to ~\.claude\skills\land-a-change\checked_tree.py
----------------------------------------------------------------------------------------------------------------------

## Commit the tree the check saw, gated on the check's OWN exit code (added 2026-10-16)
Four errata, one shape: the green check and the commit were about different things. tv-forge E36: four edits
restored from a stash AFTER the green check went into afe7e4a. tv-forge E23 and tv-screener E30: the commit was
chained after `| tail`, so tail's exit 0 pushed a RED check. tv-screener E40: a test was registered as passing in
the same unconditional batch that ran it - it had FAILED. land.py's `--checked <sha>` covers its own landings; this
covers every other commit.
```
python checked_tree.py run -- check.bat        # records the working tree, runs the check, records ITS exit code
git add <files by name>
python checked_tree.py verify                  # exit 0 = every staged change is what the check saw, and it exited 0
python checked_tree.py --selftest              # 9 PASS lines (temp repo; the last two drive a real pre-commit hook)
```
verify exits 2 (and names each file) when: no record; the check's exit code was not 0; the tree changed while the
check ran; a staged file (or deletion) differs from the checked tree. Staging a SUBSET of the checked tree is fine.
Gate the commit on verify's exit code (`if ($?)` / `&&`), never `;` (pen-claim-gate). Hook, NOT installed (the user's
call): `.git/hooks/pre-commit` containing `python "~/.claude/skills/land-a-change/checked_tree.py" verify`.
Planted 5, caught 5 (exit code ignored; moving-tree check off; HEAD compared instead of the checked tree; real
index used instead of the working tree; staged deletions skipped).

## Live sync after a landing: the jobs keep writing (added 2026-10-24)
<workspace> is live: scheduled jobs append to `data/forward/screen_picks.jsonl`, `shared/bus.chain.jsonl`,
`shared/registry.chain.jsonl` while you land from a clone. Bringing the live tree up to origin was one hand-typed
line (backup, unstage, `pull --rebase --autostash`, size check; transcript L11991). Now:
```
python live_sync.py --live <workspace> --files data/forward/screen_picks.jsonl shared/bus.chain.jsonl shared/registry.chain.jsonl --unstage experiments
python live_sync.py ... --go          # does it; SYNCED or HOLD (backup kept)
python live_sync.py --selftest        # 7 PASS lines (temp bare origin + two clones; planted shrink is LOST)
```
Real dry run 2026-10-24: `back up shared/registry.chain.jsonl (4344976 bytes)`. Each file must still start with
its backed-up bytes (append-only); LOST, MISSING, a failed pull or conflict markers = HOLD, exit 1. Then run
`python <workspace>/tools/landing_guard.py --markers-only` on the live tree too.

## Scars (session max-24, 2026-10-20..24; append only)
- 2026-10-20 L786/L802/L847: a wip commit was pushed before the final rebase; the remote then carried a commit that
  was rewritten locally. Push only after the last rebase, once.
- 2026-10-22 L6123: a hand-typed sha in a command was wrong. Take shas from `git rev-parse` output, never retype.
- 2026-10-22 L6265: `git pull --rebase --autostash` popped the stash with conflict markers and the markers were
  committed. Run `python <workspace>/tools/landing_guard.py --markers-only` (or precommit-bundle's marker_gate.py
  `--staged`) after every autostash pop and before every push.
- 2026-10-21 L4759: landing_guard in a scratch clone scanned the live tree; set `GUARD_SCAN_ROOT` to the clone.
- 2026-10-23 L6742, L11533: `landing_guard.py --print-hook` writes a hook body with a hard-coded scratch path; read
  the printed body and fix the path before installing it anywhere.
- 2026-10-20 L1956, 2026-10-21 L4859: check.bat went red on ruff after a long run. Run `ruff check <changed files>`
  first; it takes seconds, the check takes minutes.
- 2026-10-23 L9743: a default was changed in code; the scheduled job passed the flag explicitly, so nothing changed
  live. Grep the task XML (`schtasks /query /tn <task> /xml`) for an explicit flag before claiming a default change
  reached the jobs.
- 2026-10-23 L11221: a clone made without submodules cannot `git add <project>` for the root pointer. Use
  `git update-index --cacheinfo 160000,<sha from rev-parse>,<project>`, then commit.
- 2026-10-23 L11991: live tree sync after a land typed by hand as one line; now `live_sync.py`.

## See also: precommit-bundle (candidate #67, added 2026-10-16)
- Between step 6's `git add` and its commit: `python ~/.claude/skills/precommit-bundle/pre_commit.py --repo <project>` (precommit-bundle) - staged-only markers, tests.json both ways, ruff, generated files, checked tree; it would have stopped about 40 follow-up commits (18 registrations, 12 red-check, 7 lint).
