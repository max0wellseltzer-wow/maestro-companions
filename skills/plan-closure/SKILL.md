---
name: plan-closure
description: Prove a plan file is self-contained - every section pointer has a heading, every item id has a card, every code is in the glossary, and every backticked path and line citation resolves to a real file and line in the right repo - and print CLOSED or the open references. Use this whenever the user asks if a plan leaves anything unexplained or references something we do not have, before a plan is called ready, after a subagent's evidence is pasted into a plan, and after any large plan edit. Pairs with plan-vs-git, status-honesty and proposed-numbers.
---

# plan-closure

Learned on 2026-10-17. the user asked: "so PLAN.md does not leave anything unexplained or refrence anything we do not have?"
Answering him took four separate checks:
- The plan cited §1.5, §1.9 and §2.11, which existed only in an older plan.
- It named build cards GT01-GT07 that it did not contain.
- It used about 60 codes (F51, PG10, RC1-RC6, SY rows) that it never defined.
- Later, 62 citations pasted from a subagent were bare file names like `panel.py:337` with no repo, and one milestone
  was mapped to the wrong code entirely.
Each problem was found by a script, never by rereading. This skill is those scripts made into one.

## The tool

`plan_closure.py`, stdlib plus git, `--selftest` 6/6.

```
python plan_closure.py plans/PLAN.md --root <workspace> --prefix harness/=tv-tests --prefix tv_blend/=tv-blend \
    --prefix screener/=tv-screener --prefix tv_core/=tv-core [--quiet]
python plan_closure.py --selftest
```

It prints one count per class. SECTION_REF, CARD_ID, CODE and CITATION are open references, and the run exits 1
while any remain. CREATED counts citations on a line that says "new" or "creates": files a card will create, which is
not an error.

Cost is bounded: each repo's tree is listed once (`git ls-tree`), and the blobs of every path whose lines are cited
are read with one `git cat-file --batch` per repo, so a plan costs about two git spawns per repo, never citations x
repos (a spawn is 0.5-2 s on this PC). Progress goes to stderr: each class as it finishes, one line per repo tree,
then a line every two seconds through the citation pass. The 2026-10-24 survey ran the old one-`git show`-per-path
version on the 588 KB PLAN.md (666 distinct paths x 15 repos): nothing printed, timeout at 590 s. The bounded version
does the same file, and a 1.7 MB copy of it, in under a minute.

## How to fix what it finds

- **SECTION_REF:** add the section, or point at the file that has it.
- **CARD_ID:** copy the card in, or state where it lives.
- **CODE:** add a glossary line, or write the code out in words.
- **CITATION:** give the full path. If it is a new file, the line must say so.
- A bare name like `panel.py` is a defect even when only one repo has it. Write the full path, so the reader never has
  to guess.

## Limits

- A citation that resolves proves the file and line exist, not that the line says what the plan claims.
- The code pattern is 1-3 capitals plus digits, so codes of other shapes need their own grep.
- A glossary entry that is wrong still counts as defined.
- Markers it accepts beside a missing path:
  - before the path (or before a list of paths): new, creates, writes, generated, no, absent, e.g.;
  - after it: (new …), (created …), (generated …), (on branch …), (on this branch …), (not in git), (scratch …),
    (absent), (not yet …), "does not exist".
  A path marked new once counts as new at every later mention. `.ext` names like `.blend.toml` are file types, not
  paths. Pass `extra_dirs` (plan_proof passes the branch checkout) for files that exist only on the current branch.
- A glossary family `X<n>` or range `X1-X100` defines every member. A wrong range hides a code that is really undefined.
