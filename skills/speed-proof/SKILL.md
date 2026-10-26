---
name: speed-proof
description: How to make code faster WITHOUT changing a single answer, with proof - declare the benchmark before the candidate exists (CPU seconds, min of N), find where the time really is (imports first), prefer structural wins, keep every derived copy (cache, index, column file) honest with a source signature and an exact fallback, prove old and new answers identical by fingerprint, plant bugs in the mechanism, and report what was NOT sped up. Use this skill whenever anyone says "make it faster", "too slow", "takes forever", "speed up", "3x", "optimise", "profile", "benchmark", or proposes a cache, index, precomputed table or memo, or must prove two runs (1 vs 2 workers, old vs new code) wrote identical SQLite tables - even if they only complain about the time and never say "performance".
---

# speed-proof

A speed-up is a claim with three parts: how much faster, measured how, and that nothing else changed. Most "optimisations"
prove one of the three. This skill makes all three cheap to prove, because the day it was written (2026-10-11, a stock screener
made 4.9-7.9x faster on a 4 GB PC shared with other sessions) each missing part bit at least once: wall-clock timings swung 3x
between identical runs, three planted bugs survived tests that only compared answers, and `import` of an unused dependency was
0.9 s of every command. The sibling skills cover single steps; this is the whole walk. Read them when the step says so:
`measure-first` (where is the time), `fast-path-proof` (a cache must prove itself), `plant-the-bug` (tests must be able to fail).

## 1. Declare the benchmark before you touch the code
Write down, in a file, BEFORE the first edit: the exact commands, the metric, the target, and the baseline numbers.
`scripts/bench.py` does it in one command and records the sha256 of every source file and the git head with it, so "the baseline
was taken on the original code" is a fact in a file, not a sentence in a report:

    python <this skill>/scripts/bench.py declare bench.json --tree . --repeat 5 --out bench/baseline.json

`bench.json` names the commands (argv lists), a target ratio, and per-command regexes to strip volatile lines (a timestamp header)
before fingerprinting. Commit `bench/baseline.json` before the first code change. Why first: a benchmark chosen after the
candidate exists is chosen to flatter it, and a baseline re-measured later runs on a machine in a different state.

**The metric is CPU seconds of the child process, min of N (N >= 3, one untimed warm-up), not one wall-clock run.** On a
shared machine another job can double a wall-clock time; it cannot add CPU seconds to your process. Report the median beside the
min when the spread is wide. bench.py measures CPU from inside the child (`time.process_time()` at exit), because on Windows the
parent cannot read a child's CPU time through `os.times()`.

## 2. Find where the time is, then name it
Follow `measure-first`, and add two probes that are easy to forget:
- `python -X importtime -c "import pkg.module" 2>&1 | sort -t'|' -k2 -n | tail` - start-up is part of every run. If a read-only
  command loads a heavy library it never calls, that is the first win and the cheapest.
- `python -m cProfile -o p.out -m pkg.module ...` then sort by `tottime` (own time), not only `cumulative`.
Write the top three lines with their seconds into the report before designing anything. A design that does not attack the top
line is decoration.

## 3. Design the door, not the shortcut
Prefer a change of SHAPE to a change of constants: decide a condition for all rows in one pass instead of one row at a time;
store what a query reads contiguously (column-major for "one field of every row"); import lazily; compute once per run, not once
per item. Shaving constants inside the old shape rarely reaches 3x and always costs readability. Use only the standard library
and the project's declared dependencies: an installed-but-undeclared package (numpy was on the PC, not in pyproject) is a
dependency for the user to decide, not for you to assume. If a cage helps you avoid the autopilot answer, `code-cage` is the tool.

## 4. A derived copy carries its own proof
Any cache, index, precomputed table or flattened copy is DERIVED data, and derived data lies the moment its source moves. Read
`references/vouching.md`. The short form:
- take a SIGNATURE of the source (size, mtime, and the write-ahead log for SQLite) BEFORE you read the source to build the copy;
  store it beside the copy; serve the copy only while the live signature still equals the stored one;
- when it does not, fall back to the exact slow path and SAY SO (a one-line note), never guess;
- a gate that checks dates cannot see wrong values with the right date: give it an audit command (`verify`) that recomputes the
  copy from the source and diffs, and a rebuild command; put the rebuild in the nightly chain;
- `fast-path-proof` has the three states (current, incomplete, behind) and the damaged-input tests every copy needs.

## 5. Prove the answers are identical
Two proofs, both cheap once bench.py has the fingerprints:
- `python bench.py measure bench.json --tree <new> --out bench/candidate.json` then `python bench.py compare bench/baseline.json
  bench/candidate.json` - every command's fingerprint (stdout with the declared volatile lines stripped) must be IDENTICAL, and
  the ratio must meet the target; `compare` exits non-zero otherwise, so it is also a test.
- Where a fast path replaces a slow one inside the program, run BOTH on the real data (`--source slow` style switch) and diff the
  full result, not a sample. Run it on damaged inputs too (a stale copy, a missing row): the answer must not change, only the time.
If the output has a volatile field (timestamp, seconds), strip it in bench.json and say so; never relax the comparison further.
- When the program WRITES SQLite (a cache, an index, a latest table), fingerprint every table it wrote with
  `scripts/sqlite_fp.py`: names quoted (`rsi@prev`), rows keyed by column NAME (column order is a creation accident),
  file metadata excluded by name and stated (`--exclude seen.stat`), and `diff` names the table, column and key of
  every differing cell:

      python <this skill>/scripts/sqlite_fp.py fp   CACHE_DIR --exclude seen.stat --exclude states.ind
      python <this skill>/scripts/sqlite_fp.py diff RUN1/cache RUN2/cache --exclude seen.stat --exclude states.ind
      IDENTICAL (excluded: seen.stat, states.ind)        # real, 2026-10-24: 200-stock fixture, 1 vs 2 workers, 27 s
      python <this skill>/scripts/sqlite_fp.py --selftest   # 8 checks

  Without the exclusions the same pair prints `supertrend.db|seen: column 'stat' differs in 200 row(s)` - the CSV's
  size:mtime, not an answer. Exclude only columns you can name as metadata; everything else must match exactly.

## 6. Plant bugs in the mechanism, not only in the answers
Use `plant-the-bug` (`tools/plant.py` in this workspace, or the same loop by hand). Beyond the usual flips (`<` to `<=`, a dropped
guard), plant the bugs only a speed-up can have: skip the signature check; make the gate too strict (every row falls back: the
answers stay right and the speed-up silently vanishes); serve a stale copy; count a lag one off. The second kind survives any
test that compares answers only - test the mechanism itself (the gate's mask against brute force, the fallback counter, the
`verify` audit catching a corrupted copy). Every planted bug must turn a test red; a survivor is a gap or dead code, and you say which.

## 7. Report (use `references/report_template.md`)
A table: command, before, after, ratio - in CPU seconds, min of N, machine named. One line naming the equality proof and where it
lives. One line per thing NOT sped up and why (by design, by budget, by someone else's file). And the rent verdict: is the code
at least as clear as before for the next reader? If a 3x came with a module nobody can follow, say so and offer the plain
version; a lost cage reported honestly is a good outcome, a clever module shipped to save face is the failure this skill exists
to prevent. Numbers in the report come from the bench files, never from memory.

## Scars (each line is an incident, dated; do not shorten the list, add to it)
- 2026-10-11 wall-clock swung 3x between identical runs on a shared PC -> CPU seconds, min of N, benchmark declared first.
- 2026-10-11 a date-matching gate passed a copy whose VALUES were wrong -> an audit (`verify`) beside every gate.
- 2026-10-11 three planted bugs survived answer-only tests (a too-strict gate is right and slow) -> test the mechanism.
- 2026-10-11 `import pkg` loaded the heaviest dependency for read-only commands (0.9 s each) -> importtime first; a subprocess test
  that the light modules never load it.
- 2026-10-11 a signature taken AFTER reading the source could vouch for a copy of a file that changed during the read -> take it before.
- 2026-10-11 a derived file's hash changed when git converted line endings -> normalise before hashing anything a seal pins.
- 2026-10-11 a flag existed on one command and not its sibling -> the regression tour runs the same flags on the whole family.
- 2026-10-11 a 4.9-7.9x result was first reported as 3.6-5.1x because the baseline had been measured under load -> re-measure the
  baseline on the same idle machine as the candidate, back to back, before quoting any ratio.
- 2026-10-22 (max-24, L8390-8753) the refresh-cache fingerprint broke on a column named `rsi@prev` (unquoted SELECT),
  then two identical runs "differed" because seen.stat holds the CSV's size+mtime -> quote every name, key rows by
  column name, exclude named metadata columns: scripts/sqlite_fp.py (prototypes scratchpad\speed\drive.py and
  latest_diff.py). The 1-vs-2-worker split lesson itself lives in caste-split.
