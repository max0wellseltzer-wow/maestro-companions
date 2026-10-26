"""riffle_order - shuffle a test suite's order k times, find tests whose outcome depends on order, and name the
polluter (or the state-setter) by delta debugging.

[IMAGINED pitch] A card magician knows a deck is not mixed until it has been riffled about seven times
(Bayer-Diaconis 1992). A test suite run in one fixed order is an unshuffled deck: a test that only passes because an
earlier test left state behind (or only fails because one did) hides there forever.
[REAL mechanism] For n tests, a specific ordered pair (p before v) appears in a uniform random permutation with
probability 1/2, so k independent orders miss it with probability 2**-k; to see every one of the n(n-1) ordered
pairs at least once with probability >= 1 - delta (union bound) you need k >= log2(n(n-1)/delta). The tool prints
that k for your n, runs each test ALONE (the reference outcome), then k seeded permutations, and classifies:
  STABLE   same outcome alone and in every order
  VICTIM   passes alone, fails in some order    -> POLLUTER found by bisecting the prefix before it
  BRITTLE  fails alone, passes in some order    -> SETTER found the same way (it depends on another test's state)
  FLAKY    the outcome changes with the same order (seen when a rerun of the failing order disagrees)

    python riffle_order.py --plan 40 --delta 0.05                         # how many orders to run
    python riffle_order.py --ids ids.txt --k 8 --seed 1 -- {python} -m pytest -q -v -p no:randomly {tests}
    python riffle_order.py --selftest
The command after `--` runs the given test ids in the given order; `{tests}` expands to the ids, `{python}` to this
interpreter. Per-test outcomes are read from its output with --result-re (default: a line starting with the id
followed by PASSED / FAILED / ERROR - pytest -v prints exactly that).
Exit: 0 every test STABLE, 1 order dependence found, 2 bad input.
"""
from __future__ import annotations

import math
import random
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_RE = r"^(?P<id>\S+)\s+(?P<outcome>PASSED|FAILED|ERROR)\b"


def orders_needed(n: int, delta: float = 0.05) -> int:
    """Smallest k with n(n-1) * 2**-k <= delta: every ordered pair seen at least once w.p. >= 1 - delta."""
    if n < 2:
        return 1
    return max(1, math.ceil(math.log2(n * (n - 1) / delta)))


def make_runner(cmd: list, result_re: str = DEFAULT_RE, timeout: float = 600):
    rx = re.compile(result_re, re.M)

    def run(order):
        args = []
        for c in cmd:
            if c == "{tests}":
                args.extend(order)
            else:
                args.append(sys.executable if c == "{python}" else c)
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL)
        got = {}
        for m in rx.finditer(r.stdout):
            got[m.group("id")] = m.group("outcome") == "PASSED"
        return got
    return run


def _search(run, prefix, victim, want_pass: bool):
    """Smallest culprit p in prefix such that run([p, victim]) gives victim the outcome `want_pass`. Bisection when
    a half alone reproduces it, then a linear scan of single candidates (interactions of 2+ tests are reported as
    None)."""
    cand = list(prefix)
    while len(cand) > 1:
        half = len(cand) // 2
        a, b = cand[:half], cand[half:]
        if run(a + [victim]).get(victim) is want_pass:
            cand = a
        elif run(b + [victim]).get(victim) is want_pass:
            cand = b
        else:
            break
    for p in cand:
        if run([p, victim]).get(victim) is want_pass:
            return p
    return None


def riffle(tests: list, run, k: int = 8, seed: int = 0) -> dict:
    alone = {t: run([t]).get(t) for t in tests}
    rng = random.Random(seed)
    perms, outcomes = [], {t: [] for t in tests}
    for _ in range(k):
        order = list(tests)
        rng.shuffle(order)
        got = run(order)
        perms.append((order, got))
        for t in tests:
            outcomes[t].append(got.get(t))
    rows = []
    for t in tests:
        seen = {o for o in outcomes[t] if o is not None}
        row = {"test": t, "alone": alone[t], "passes": sum(o is True for o in outcomes[t]),
               "fails": sum(o is False for o in outcomes[t]), "kind": "STABLE", "culprit": None}
        if alone[t] is True and False in seen:
            order, _ = next((o, g) for o, g in perms if g.get(t) is False)
            if run(order).get(t) is True:
                row["kind"] = "FLAKY"
            else:
                row["kind"] = "VICTIM"
                row["culprit"] = _search(run, order[:order.index(t)], t, want_pass=False)
        elif alone[t] is False and True in seen:
            order, _ = next((o, g) for o, g in perms if g.get(t) is True)
            if run(order).get(t) is False:
                row["kind"] = "FLAKY"
            else:
                row["kind"] = "BRITTLE"
                row["culprit"] = _search(run, order[:order.index(t)], t, want_pass=True)
        elif alone[t] is None:
            row["kind"] = "NO-RESULT"
        rows.append(row)
    return {"rows": rows, "k": k, "n": len(tests), "pair_miss_bound": len(tests) * (len(tests) - 1) * 2.0 ** -k}


def format_report(res: dict) -> str:
    out = [f"{'kind':<10}{'alone':<7}{'pass':>5}{'fail':>5}  test  (culprit)"]
    for r in sorted(res["rows"], key=lambda r: (r["kind"] == "STABLE", r["test"])):
        a = {True: "pass", False: "fail", None: "-"}[r["alone"]]
        role = {"VICTIM": "polluter", "BRITTLE": "setter"}.get(r["kind"])
        c = f"  ({role}: {r['culprit'] or 'needs 2+ tests together'})" if role else ""
        out.append(f"{r['kind']:<10}{a:<7}{r['passes']:>5}{r['fails']:>5}  {r['test']}{c}")
    bad = sum(r["kind"] != "STABLE" for r in res["rows"])
    out.append(f"{res['n']} tests x {res['k']} orders: {bad} order-dependent; chance some ordered pair was never "
               f"tried <= {min(1.0, res['pair_miss_bound']):.3g} (run k={orders_needed(res['n'])} for 5%)")
    return "\n".join(out)


# ---------------------------------------------------------------- A/B: my change, or the machine?
def ab_run(run_base, run_change, n: int = 5, clock=None) -> list:
    """Run the same failing test n times on the clean tree (base) and n times on my change, INTERLEAVED
    (base, change, base, change ...) so a load spike hits both sides alike. run_x() -> bool (passed).
    Returns rows {"side", "ok", "s"}."""
    import time as _t
    clock = clock or _t.perf_counter
    rows = []
    for _ in range(n):
        for side, run in (("base", run_base), ("change", run_change)):
            t0 = clock()
            ok = bool(run())
            rows.append({"side": side, "ok": ok, "s": round(clock() - t0, 3)})
    return rows


def ab_verdict(rows: list, slow: float = 1.5) -> tuple:
    """(VERDICT, why). CAUSED: base always passes, change fails at speed. LOAD_SUSPECT: change fails only on runs
    slower than `slow` x the median passing run (the 2026-10-21 tv-harvest case: 5-14 s failures vs 3.5 s passes).
    FLAKY_BOTH: base fails too (it was flaky before you). BOTH_FAIL, PASS_BOTH, FIXED_OR_FLAKY."""
    base = [r for r in rows if r["side"] == "base"]
    chg = [r for r in rows if r["side"] == "change"]
    if not base or not chg:
        return "NO_DATA", "need runs on both sides"
    bp, cp = sum(r["ok"] for r in base), sum(r["ok"] for r in chg)
    rate = f"base {bp}/{len(base)} pass, change {cp}/{len(chg)} pass"
    if bp == len(base) and cp == len(chg):
        return "PASS_BOTH", rate + ": the failure did not reproduce"
    if bp == 0 and cp == 0:
        return "BOTH_FAIL", rate + ": broken before your change"
    if bp < len(base) and cp < len(chg):
        return "FLAKY_BOTH", rate + ": the clean tree fails too, so it is not your change"
    if cp == len(chg):
        return "FIXED_OR_FLAKY", rate
    passing = sorted(r["s"] for r in rows if r["ok"])
    median = passing[len(passing) // 2] if passing else 0.0
    bad = [r["s"] for r in chg if not r["ok"]]
    if cp > 0 and median and sum(bad) / len(bad) > slow * median:
        return "LOAD_SUSPECT", (rate + f": the change's failures were slow (mean {sum(bad) / len(bad):.1f} s, runs "
                                f"{', '.join(map(str, bad))} s, vs median pass {median} s); rerun interleaved when the "
                                f"machine is quiet before blaming the change")
    return "CAUSED", rate + ": the clean tree always passes and the change fails at normal speed"


def _git_base_tree(repo: str) -> str:
    """A detached worktree of HEAD (the clean tree) beside the repo, so nothing in the live tree is stashed:
    another session may own files there."""
    import tempfile
    d = tempfile.mkdtemp(prefix="riffle_ab_")
    subprocess.run(["git", "-C", repo, "worktree", "add", "--detach", d, "HEAD"], check=True, capture_output=True)
    return d


# ---------------------------------------------------------------- selftest
FAKE = '''import sys
state = {"polluted": False, "ready": False}
for t in sys.argv[1:]:
    ok = True
    if t == "t_polluter":
        state["polluted"] = True
    elif t == "t_victim":
        ok = not state["polluted"]
    elif t == "t_setter":
        state["ready"] = True
    elif t == "t_needy":
        ok = state["ready"]
    print(t, "PASSED" if ok else "FAILED")
'''


def _selftest() -> int:
    import shutil
    import tempfile
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(("PASS " if cond else "FAIL ") + name)
        fails += 0 if cond else 1

    check("orders needed: 10 tests at 5% -> 11", orders_needed(10, 0.05) == 11)
    check("orders needed grows like log n", orders_needed(100, 0.05) == 18 and orders_needed(2, 0.5) == 2)
    tmp = Path(tempfile.mkdtemp(prefix="riffle_st_"))
    try:
        (tmp / "fake.py").write_text(FAKE, encoding="utf-8")
        tests = ["t_a", "t_polluter", "t_b", "t_victim", "t_setter", "t_c", "t_needy", "t_d"]
        run = make_runner(["{python}", str(tmp / "fake.py"), "{tests}"])
        res = riffle(tests, run, k=10, seed=0)   # seed 3 never puts setter before needy: 1 in 1024 bad luck
        v = {r["test"]: r for r in res["rows"]}
        check("victim found with its polluter", v["t_victim"]["kind"] == "VICTIM"
              and v["t_victim"]["culprit"] == "t_polluter")
        check("brittle test found with its setter", v["t_needy"]["kind"] == "BRITTLE"
              and v["t_needy"]["culprit"] == "t_setter")
        check("independent tests are STABLE", all(v[t]["kind"] == "STABLE" for t in ("t_a", "t_b", "t_c", "t_d",
                                                                                    "t_polluter", "t_setter")))
        check("report names roles", "polluter: t_polluter" in format_report(res)
              and "setter: t_setter" in format_report(res))
        calls = {"n": 0}

        def flaky(order):
            calls["n"] += 1
            return {t: (calls["n"] % 2 == 1) if t == "t_f" else True for t in order}
        r2 = riffle(["t_f", "t_g"], flaky, k=6, seed=0)
        check("an outcome that changes on an identical rerun is FLAKY, not a victim",
              {r["test"]: r["kind"] for r in r2["rows"]}["t_f"] == "FLAKY"
              and {r["test"]: r["kind"] for r in r2["rows"]}["t_f"] != "VICTIM")
        r3 = riffle(["x"], lambda order: {}, k=2)
        check("a test the runner never reports is NO-RESULT", r3["rows"][0]["kind"] == "NO-RESULT")

        def rows(base, chg):
            return ([{"side": "base", "ok": o, "s": s} for o, s in base] +
                    [{"side": "change", "ok": o, "s": s} for o, s in chg])
        # the real 2026-10-21 tv-harvest numbers: base 3/3 at ~3.4 s; change failed at 14.2 s and 5.0 s, passed at 7.6
        live = rows([(True, 3.6), (True, 3.4), (True, 3.2)], [(False, 14.2), (False, 5.0), (True, 7.6), (True, 3.6)])
        check("A/B: slow-only failures on the change are LOAD_SUSPECT", ab_verdict(live)[0] == "LOAD_SUSPECT")
        check("A/B: fast failures with a clean base are CAUSED",
              ab_verdict(rows([(True, 3.5)] * 3, [(False, 3.4), (False, 3.6), (True, 3.5)]))[0] == "CAUSED")
        check("A/B: a change that ALWAYS fails is CAUSED even when its runs are slow",
              ab_verdict(rows([(True, 3.5)] * 3, [(False, 14.0), (False, 12.0)]))[0] == "CAUSED")
        check("A/B: a failing base is FLAKY_BOTH, never the change's fault",
              ab_verdict(rows([(False, 3.5), (True, 3.5)], [(False, 3.5), (True, 3.4)]))[0] == "FLAKY_BOTH")
        check("A/B: PASS_BOTH / BOTH_FAIL / NO_DATA", ab_verdict(rows([(True, 1)], [(True, 1)]))[0] == "PASS_BOTH"
              and ab_verdict(rows([(False, 1)], [(False, 1)]))[0] == "BOTH_FAIL" and ab_verdict([])[0] == "NO_DATA")
        seq = []
        ab_run(lambda: seq.append("b") or True, lambda: seq.append("c") or True, n=2)
        check("A/B runs interleave base and change", seq == ["b", "c", "b", "c"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest:", "ALL PASS" if not fails else f"{fails} FAILED")
    return 0 if not fails else 1


def main(argv) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return _selftest()
    args = list(argv)
    cmd = []
    if "--" in args:
        i = args.index("--")
        cmd, args = args[i + 1:], args[:i]

    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return default
    try:
        if "--ab" in args:
            n, repo = int(opt("--ab")), opt("--repo", ".")
            if not cmd:
                raise ValueError("--ab needs the test command after --")
            base_dir = _git_base_tree(repo)
            try:
                def runner(cwd):
                    return lambda: subprocess.run(cmd, cwd=cwd, capture_output=True).returncode == 0
                res_rows = ab_run(runner(base_dir), runner(repo), n)
            finally:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", base_dir], capture_output=True)
            for r in res_rows:
                print(f"  {r['side']:<6} {'pass' if r['ok'] else 'FAIL'}  {r['s']} s")
            verdict, why = ab_verdict(res_rows)
            print(f"VERDICT {verdict}: {why}")
            return 1 if verdict == "CAUSED" else 0
        if "--plan" in args:
            n, d = int(opt("--plan")), float(opt("--delta", "0.05"))
            print(f"{n} tests: run k = {orders_needed(n, d)} shuffled orders to try every ordered pair at least once "
                  f"with probability >= {1 - d:.3g}")
            return 0
        ids = [x.strip() for x in Path(opt("--ids")).read_text(encoding="utf-8").splitlines() if x.strip()]
        k, seed = int(opt("--k", "8")), int(opt("--seed", "0"))
        if "{tests}" not in cmd:
            raise ValueError("the command after -- must contain {tests}")
        res = riffle(ids, make_runner(cmd, opt("--result-re", DEFAULT_RE)), k, seed)
    except (ValueError, TypeError, OSError, IndexError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(format_report(res))
    return 0 if all(r["kind"] == "STABLE" for r in res["rows"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
