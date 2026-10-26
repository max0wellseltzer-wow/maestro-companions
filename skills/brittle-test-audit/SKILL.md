---
name: brittle-test-audit
description: Find over-specified tests by making changes that should NOT matter - reorder top-level function definitions, rename locals, reverse dict/set literal order, add a no-op line, reformat, change PYTHONHASHSEED, TZ and the working directory - in memory (the target module's changed source is compiled under its original path, the file is never written), rerun the test command per change, and name which perturbation broke which test. Use this whenever the user asks whether tests are brittle, flaky, over-fitted to implementation details, or why a harmless refactor or another machine turned tests red, and before trusting a suite that will gate refactors. Reverses mutation-audit; pairs with mutation-audit, weak-assert-scan, metamorphic-test and windows-port-audit.
---

# brittle-test-audit

Reverses **mutation-audit**. mutation-audit plants bugs that a good test SHOULD catch. This skill flips the angle and makes changes that a good test should NOT notice: a test that fails anyway is pinned to an accident of the implementation, not to its behaviour. A suite needs both properties. It must fail on real bugs (mutation-audit measures that) and keep passing through harmless changes (this skill measures that). A brittle test punishes every refactor, so people learn to ignore red runs.

## The tool (ships with this skill)

`brittle_audit.py`, pure stdlib. Selftest 10/10. It builds a synthetic module with 3 robust tests and 5 planted brittle ones, and each brittle test is broken by exactly its own perturbation: dict repr by `dict-order`, string-set order by `hashseed=*`, `vars()` order by `reorder-defs`, local hour by `tz=*`, relative fixture path by `cwd=temp`. The robust tests are never flagged and the file on disk is unchanged.

```
python brittle_audit.py --target mymod.py --test test_mymod.py [--module pkg.mymod] [--cwd DIR] [-- test args]
python brittle_audit.py --target mymod.py --test -m pytest -- -v test_mymod.py
from brittle_audit import audit, report, perturb_source
```

- Baseline: the original source, `PYTHONHASHSEED=0`, TZ unset, the given cwd. Only tests that pass at baseline are judged. If none pass, the audit refuses to run.
- Source perturbations: `reformat` (ast round trip, so line numbers shift), `noop-line`, `reorder-defs` (adjacent undecorated top-level defs reversed), `rename-locals` (skips functions that use locals/vars/eval/exec or nested defs), `dict-order` (constant-key dict and set literals reversed).
- Environment perturbations: `hashseed=1/2/3`, `tz=UTC0`, `tz=IST-5:30`, `cwd=temp`.
- Per-test results are read from house `PASS/FAIL name` lines, unittest `-v` and pytest `-v`. Without any of those, the whole command counts as one test. Exit code is 1 if anything is brittle.

## Uses and limits

- Run it after mutation-audit gives a suite a good kill rate. A suite can kill every mutant and still fail on a harmless reorder.
- Reading results: a failure under `dict-order` or `reorder-defs` is brittle unless the module's contract promises that order, in which case the test is right and the order should be documented. A failure under `reformat` or `noop-line` means the test pins line numbers or source text. A failure under `hashseed` means the test depends on set or dict iteration order of strings, so it is flaky across runs.
- Only one module is perturbed per run, and only in the test process: code that a test launches in a subprocess still sees the real file.
- `rename-locals` skips functions that use dynamic scope, so some functions are never renamed.
- Every perturbation is one subprocess run of the whole test command, so keep the command targeted on this 4 GB machine.
