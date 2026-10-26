---
name: doc-truth
description: Check that every command a doc shows still matches its script - for each `python X.py ...` invocation in a SKILL.md, README or plan (code blocks, inline backticks, and commands nested after ' -- ') it flags MISSING_SCRIPT, UNKNOWN_FLAG (a --flag the script, or a local helper module it imports, never mentions as a quoted literal, an argv key or a '--' + name build) and UNKNOWN_COMMAND (a misspelt sub-command of a dispatching script), and with --run-selftest runs each documented selftest and catches a stale "N PASS" count. Use this whenever a tool's flags or sub-commands change, before landing a SKILL.md or README edit, as a library-wide sweep after merges or renames, and when the user says the docs drifted or a documented command did not work.
---
# doc-truth

## The problem
Plan U26 (eager-cray, 2026-10-13) asked for "docs that cannot drift": every documented flag must exist and every example
must run. Nothing enforced it. The library-wide run on 2026-10-16 (658 docs in about 3 s) found `peacock.py --run`
documented twice although the script only knows `--no-run`, and 46 doc lines naming scripts that do not exist at the
path given - most are repo-relative (`tools/jobs.py` x5, `tools/receipt.py` x3, `tools/claude_sync.py` x3) and only
resolve inside <workspace>, a few are example names (`thatfile.py`); read those rows with that in mind.

## Procedure
1. Run it on the doc or folder you changed (a folder means every SKILL.md below it; `--all-md` for every .md).
2. UNKNOWN_FLAG / UNKNOWN_COMMAND: fix the doc or the parser - whichever is wrong - in the same change.
3. MISSING_SCRIPT: fix the path, or say in the doc where the script lives (repo-relative), never leave it silent.
4. Before landing a tool change, add `--run-selftest` so the "N PASS lines" a doc promises equals the real count.
A flag counts as known when the script or a local module it imports (same folder, or a sibling skill folder - the
library's sys.path pattern) has it as a quoted literal, as the bare name in a `x[2:]` argv loop, or builds it with
`'--' + name`. Flags inside a quoted argument and after ` -- ` belong to another command and are checked against it.
All-caps script names (X.py, TOOL.py) are placeholders and skipped.

## Tool
```
python doc_truth.py ~\.claude\skills
  UNKNOWN_FLAG     ...\peacock-tail\SKILL.md:15  peacock.py --run
  MISSING_SCRIPT   ...\chain-the-queue\SKILL.md:12  tools/jobs.py
  658 doc(s) checked, 48 problem(s): MISSING_SCRIPT 46, UNKNOWN_FLAG 2
python doc_truth.py my-skill\SKILL.md --run-selftest
python doc_truth.py --selftest        # 14 PASS lines
```
Exit 0 clean, 1 problems, 2 bad arguments. Each false positive found on the real library (shared CLI helpers,
positional words read as sub-commands, '--' + name builds, flags of a quoted or wrapped command) was fixed and pinned
by a selftest case; this group's own 22 docs check clean.

## Proof
Selftest 14/14. Planted 7, caught 7 (`_work/p_doctruth.json`: comment stripping, per-backtick segments, helper
following, bare-key loops, stale PASS count, missing script, sub-command dispatch).

## Provenance
skill-foundry dry run 2026-10-16: `doc-truth: PASSES ALL GATES (dry run - nothing created)` (top finder hit
built-not-wired norm 0.27). Source [REAL: <workspace>\plans\tv_blend_v3_raw\skills\doc-truth\SKILL.md, plan U26].
The draft's "every number is an include from a receipt" step is numbers-pass's job and was not rebuilt.

Pairs with skill-health (frontmatter and selftests), peacock-tail (claims vs selftest counts), numbers-pass and
command-tour.
