---
name: hostile-caller-pass
description: Read an API with grants, authors, ids, evidence or person-only doors the way a caller who wants to cheat would - this workspace's own attack list from 12 TRUST errata - substring id matches, a dict refusal tested as a bool, a caller declaring itself "human" or "PASSED", isatty() as proof a person is here, evidence lists never checked against records, caller text stored as a trusted field, and grants or reveals that can be replayed. An AST scan plus a ready list of hostile inputs for tests. Use this whenever code decides who may do something, records who did it, accepts evidence or ids from a caller, has a person-only command, spends a one-time budget (holdout look, human ledger), or when the user asks "could an AI credit itself here?".
---
# hostile-caller-pass

## The problem
An AI that can credit itself or spend the human ledger breaks the integrity of every scored claim. The TRUST class
is the second biggest in the errata (40 entries); 12 of them in 4 projects are this attack list (mined 2026-10-16,
layer 4, candidate #54):
- tv-forge E1: `not capability.check(...)` - check returns a dict ({allowed, reason}), so every actor passed.
  E20: `model_id in actor` (a substring) since 790ed82. E21: the author block was compared with the call, but
  nobody asked whether the id can name one model. E47: an AI could request as author.kind 'human' and spend the
  human weekly ledger. E48: new_evidence was never validated - ['trust me', 42] reopened a REFUTED family.
  E61: caller text in REFUSED.why reached readers as trusted fields. E68: the person-only doors trusted
  `sys.stdin.isatty()`, and on Windows the NUL device answers True. Also E15.
- tv-core E1: checklog accepted "PASSED" as an argument, so anyone could record a pass. E15. tv-tests E4: the
  CONFIRM gate was honest only for an honest caller. tv-harvest E1: the store took known_time from the caller.
engineering:security-review reads a diff for generic security bugs; it does not know this workspace's actor model.

## Procedure
1. `scan` the package (tests are skipped). Each finding names the attack it allows.
2. For each one write the hostile test FIRST, from `params` (the 12 inputs) plus the two procedures it prints
   (call twice; run a person door with stdin from NUL). Red = REAL: fix with an exact id compare, the `allowed`
   field, a kind derived from the verified actor (never declared), ids looked up on the chain, the writer's own
   fields, `append_if` for once-only acts, GetConsoleMode for person doors.
3. Green on the hostile test = the finding was safe: keep the test anyway (it pins the guard).
4. Report each finding REAL / SAFE with the test name.

## The tool
```
python hostile_caller.py scan tv-forge/forge tv-core/tv_core     # H-SUBSTR H-TRUTHY H-CLAIM H-TTY H-EVIDENCE H-ECHO H-REPLAY
python hostile_caller.py params                                   # HOSTILE = [...] for pytest.mark.parametrize
python hostile_caller.py --selftest                               # 11 PASS lines, SELFTEST PASS
```

## First real run (2026-10-16, read-only, seven projects)
12 findings, all after the old fixes landed (no H-SUBSTR, H-TRUTHY, H-TTY or H-ECHO left: E1/E20/E61/E68 hold).
Worth a hostile test first:
- `tv-screener/screener/intraday/lab.py:153 propose()` stores `dict(evidence)` from the caller unchecked into the
  proposals chain - the E48 shape in a second project.
- `tv-forge/forge/lifecycle.py:176 method_problems()` accepts a caller-declared method "human" - check that the
  method is cross-checked against the verified actor (E47's shape).
- H-REPLAY on `tv-lens unmask()` (2) and `grant()` in tv-core / tv-forge: call twice; a grant is likely idempotent.
The draft flagged 31; the guards it learned: a dict built in the function (`owner[name] = ...`) is not an identity
string; `revealed()` / `_grantable()` are queries, not acts; passing evidence to `evidence_problems()` is delegation;
a loop that looks each item up counts as checking; "max"/"pass" are too common (max(), grades) to be trust words.

## Proof the selftest can fail
Planted 7, caught 7 (module dicts treated as id strings; dict returners emptied; "human" dropped; isatty
ignored; any call counted as an evidence check; trusted keys emptied; replay memory matching anything). One
planted change survived at first - a CONTAINERISH filter that could never fire (dead code); it was removed.

Pairs with self-attacking-referee, code-kaleidoscope, windows-port-audit (W-ISATTY), vacuous-success-audit
(truthy dicts), time-semantics-contract (caller-supplied times) and engineering:security-review.
