---
name: riffle-order
description: Card-magic test hygiene - shuffle a test suite's order k times (seeded), run every test alone as the reference, and classify each test STABLE, VICTIM (fails after some other test - the polluter is named by bisection), BRITTLE (passes only after a state-setting test - the setter is named), FLAKY or NO-RESULT; also computes how many shuffled orders see every ordered pair of tests with probability 1 - delta (k >= log2(n(n-1)/delta)). Works with any runner printing per-test PASSED/FAILED lines (pytest -v). Use this whenever a test passes alone but fails in the suite (or the reverse), when a suite is green only in one order, before trusting a suite that shares files, globals, caches or a database, or when the user asks whether tests leak state into each other. Pairs with brittle-test-audit, live-root-pollution-guard, check-under-concurrent-writers and plant-the-bug.
---
# riffle-order

## Pitch [IMAGINED]
A magician knows a deck is not mixed until it has been riffled about seven times. A test suite run in one fixed
order is an unshuffled deck: a test that passes only because an earlier test left state behind (or fails only
because one did) stays hidden until the order changes - on another machine, under xdist, after a rename.

## Mechanism [REAL]
In a uniform random permutation a given ordered pair (p before v) appears with probability 1/2, so k orders miss it
with probability 2**-k and, by the union bound over n(n-1) ordered pairs, k >= log2(n(n-1)/delta) orders see every
pair at least once with probability >= 1 - delta. Polluter search is delta debugging on the prefix before the victim
(bisect halves, then single candidates; a polluter that needs two tests together is reported as such).

## Procedure
1. `python riffle_order.py --plan N` - how many orders for N tests (10 tests: 11; 100 tests: 18 at 5%).
2. Write the ids, one per line (`pytest --collect-only -q > ids.txt`, keep the `file::name` lines).
3. `python riffle_order.py --ids ids.txt --k K -- {python} -m pytest -q -v -p no:randomly -p no:cacheprovider {tests}`.
4. For each VICTIM: make the polluter clean up (fixture teardown, tmp dirs, monkeypatch) - not the victim reset.
   For each BRITTLE test: give it its own setup. FLAKY goes to doubt-mind; it is not an order bug.

## Usage
```
python riffle_order.py --plan 40
python riffle_order.py --ids ids.txt --k 12 --seed 1 -- {python} -m pytest -q -v -p no:randomly {tests}
VICTIM    pass       4    6  t_victim  (polluter: t_polluter)
BRITTLE   fail       6    4  t_needy  (setter: t_setter)
python riffle_order.py --selftest          # 14 PASS lines
```
Exit: 0 all STABLE, 1 order dependence found, 2 bad input.

## A/B: did my change break it, or is the machine loaded? (added 2026-10-21)
A test that fails in a full check but not alone may be a load flake, not an order bug. `--ab N` runs one test command
N times on a clean detached worktree of HEAD (nothing in the live tree is stashed: a peer session may own files there)
and N times on your working tree, interleaved so a load spike hits both, then gives one verdict:
```
python riffle_order.py --ab 3 --repo <workspace>\tv-harvest -- python -m pytest -q -p no:cacheprovider tests/test_live.py::test_x
VERDICT LOAD_SUSPECT: base 3/3 pass, change 2/4 pass: the change's failures were slow (mean 9.6 s ...)
```
CAUSED (clean tree always passes, change fails at normal speed, or always), LOAD_SUSPECT (the change's failures ran
slower than 1.5 x the median pass), FLAKY_BOTH (the clean tree fails too), BOTH_FAIL, PASS_BOTH, FIXED_OR_FLAKY. Exit 1
only for CAUSED. Earned on 2026-10-21: tv-harvest's reconnect test failed 2 of 3 runs on a change that only added a
poller (14.2 s and 5.0 s against 3.4 s clean passes), then passed 5 of 5 once the machine was quiet.

## Evidence
Selftest world (a fake runner with a polluter, a victim, a setter and a needy test among 8): with seed 0 and k=10 both
pairs are found and named. While building it, seed 3 with k=10 never once put the setter before the needy test (a
1-in-1024 miss) - exactly the risk the --plan bound prices: for n=8 at 5% it asks for k=11. Planted 3 (FLAKY check
removed, pair bound using n instead of n(n-1), setter searched with the wrong outcome): caught 3 of 3.


## Provenance
skill-foundry dry run 2026-10-16: "riffle-order: PASSES ALL GATES" (finder top hit markov-chain norm 0.18; metaphor
BUILD - nearest metamorphic-test at 0.32 checks input relations, not test-order dependence).

Pairs with brittle-test-audit, live-root-pollution-guard (writes into live records), check-under-concurrent-writers,
plant-the-bug, mise-en-place (what each test reads).
