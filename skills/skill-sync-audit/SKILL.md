---
name: skill-sync-audit
description: Compare the skill libraries (user ~/.claude/skills, <workspace>\.claude\skills, any repo copy) by name and content hash - list skills missing from a root, copies that drifted (with the differing files and the first differing SKILL.md line), copies that differ only in CRLF/LF - and propose the copy direction from the newest copy, as PowerShell lines to read before running. Ships skill_sync.py. Use this whenever the user says "make the skills global", "make sure all skills are global / universal", after creating or editing any skill in one place, and before trusting that a fix in one copy reached the other, and when the global and repo copies both changed and need a 3-way merge (merge3.py finds the base commit and runs git merge-file), or after a bulk sed across both copies.
---
# skill-sync-audit

## The problem
the user asked five times in three days for every skill to be global: 085faced 10-13T04:59 "globalize them", 05:01,
21:09, 10-15T17:56, 17:57 "make sure all /skills we ever create or ever created are global". Mining on 10-15 found
206 project skills against 240 user skills, and two copies of receipt-report whose descriptions began differently,
so a skill fixed in one copy stayed broken in the other. A run on 2026-10-16 found the two libraries in step
(281 skills: 245 SAME, 36 EOL-ONLY, 0 DRIFTED, 0 MISSING) - the check is what keeps it that way.

## Procedure
1. After any skill edit, and whenever the user asks about global skills, run
   `python skill_sync.py ~\.claude\skills <workspace>\.claude\skills`.
2. MISSING: copy from the root that has it (`--plan` prints the Copy-Item line), unless the skill is
   project-only on purpose (say why in the report).
3. DRIFTED: read both copies' differing files. The newest copy is only a proposal; merge by hand when both sides
   changed. Never overwrite a copy another session is editing (check the pen / peer notes first).
4. EOL-ONLY: harmless; leave it unless a tool hashes the file.
5. Rerun until `DRIFTED 0, MISSING 0`; the summary line is the receipt.

## Usage
```
python skill_sync.py ~\.claude\skills <workspace>\.claude\skills [--plan] [--names a,b] [--json]
DRIFTED   receipt-report files SKILL.md; SKILL.md line 3: 'description: Files are...' vs 'description: How to...'; newest in ...
EOL-ONLY  topo-sort
281 skills: SAME 245, EOL-ONLY 36, DRIFTED 0, MISSING 0                         # exit 0 (1 if drift/missing)
python skill_sync.py --selftest
```
Exit 0 in sync, 1 missing or drifted, 2 bad args. Reads only; copies nothing.

## Proof
`--selftest`: 8 checks (identical copies with differing __pycache__ stay SAME, MISSING names the root, the
receipt-report description drift is DRIFTED at line 3, newest copy is the source, CRLF-only is EOL-ONLY, a folder
without SKILL.md is ignored, plan lines, exit codes). Planted 5, caught 4 on the first run; the survivor (cache
folders not ignored) had a .pyc-only test - a non-.pyc cache file was added and the rerun caught 5 of 5.

## DRIFTED and both sides changed: the 3-way merge recipe (2026-10-21, skill-maestro)
The global copy had v10 concepts + v11 triage, the repo copy had the cloud's v10-v12; "newest wins" would have lost
one side. What worked (transcript L2653-L2814, prototype scratchpad\maestro_merge2\resolve.py):
1. **Archive the global copy first** (`~/.claude/skills_archive/<date>_<skill>-before-<change>/`).
2. **Base = the repo commit with the SMALLEST diff to the archived global copy**, over the file's history:
   `python merge3.py base <workspace> .claude/skills/<skill>/<file> <archived copy> --last 25`. That day:
   ba2b532 diff 659 against 8a4b07a (newest) diff 1579. Use enough `--last` to reach back past both lines of edits.
3. **Merge in scratch**: copy the global file to `merged_<file>`, then
   `python merge3.py merge <global> <base> <repo> --out <scratch>/merged_<file>` (prints each conflict's line and
   size). By hand in Git Bash it needs BOTH fixes that cost two failed runs: `export MSYS_NO_PATHCONV=1` before
   `git show "ba2b532:path"` (else `origin/main:path` arrives as `origin\main;...`, L2788 region), and
   `git merge-file -L global -L base -L repo "$(cygpath -w merged)" "$(cygpath -w base)" "$(cygpath -w theirs)"`
   (git.exe cannot stat `/c/...` paths; exit 255).
4. **Resolve each conflict on purpose.** 9 conflicts in about 2,700 lines that day; resolve.py had one function per
   block and asserted the block count (9) and no markers left. Then run the skill's selftest on the merged copy
   before it goes into either library.
5. After a bulk sed across both copies (L8193, design rules -> hints), run the audit again: both copies changed.
```
python merge3.py --selftest     # 7 PASS (temp git repo; planted wrong base and a planted overlapping edit)
```
Real run 2026-10-24 (read-only) on the Maestro history with `--last 8`: `BASE 4e51943 (diff 1418)`; the repo
moved on since 10-21, so the 10-21 base needs a longer `--last`.

Pairs with skill-health (are the tools green), skills-index, skill-finder, skill-foundry, writer-pen.

## Evidence from mining layer 10 (apply only if #61 skill-sync-audit is built; otherwise drop this file)

On 2026-10-15, 206 skills existed in both ~\.claude\skills and <workspace>\.claude\skills, and 17
project copies were stale. In all 17 the user copy was newer: autotrade-start, land-a-change, writer-pen,
mailbox-post, receipt-report, merge-cloud-branch, question-not-ruling, call-time-collaborators, lace-cycle,
signal-nulls, cascade, epigenetic-switch, hmm-regimes, interval-merge, word-sex, ratchet and topo-sort. Another
48 user skills had no project copy. A session in <workspace> loads both libraries, so it could follow last week's
land-a-change or writer-pen.

Re-run on 2026-10-16 (mine/layers4plus/drift.py, SKILL.md sha256 with CRLF normalised): 281 user, 281 project,
0 drifted. A sync ran in between. Drift therefore comes back after each skill wave unless the sync is a step of the
wave. Run the audit at the end of every wave (land-a-change, library-vitals) rather than once.
