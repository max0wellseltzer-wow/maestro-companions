"""brittle_audit - which tests break when NOTHING that matters changed? (backs the brittle-test-audit skill;
mutation-audit reversed).

mutation-audit plants real bugs and asks "did a test notice?". This tool makes changes that should NOT matter and
asks "did a test notice anyway?". A test that fails under a semantics-preserving change is brittle: it pins an
accident (dict repr order, definition order, line numbers, hash seed, local time zone, the current directory)
instead of the behaviour. Each perturbation runs the test command once, in a fresh subprocess, with the target
module's CHANGED source compiled under its original path and installed in sys.modules first. The file on disk is
never written.

Source perturbations (target module only):
    reformat      ast round-trip (comments gone, line numbers shift)
    noop-line     a `pass` inserted at the top of the module (every later line number +1)
    reorder-defs  each run of adjacent top-level undecorated function definitions reversed
    rename-locals function locals renamed _bt0, _bt1... (skips functions using locals/vars/eval/exec/nested defs)
    dict-order    dict literals with 2+ unique constant keys, and set literals, written in reverse order
Environment perturbations (unchanged source):
    hashseed=1/2/3   PYTHONHASHSEED (the baseline pins 0, so string-set order is reproducible)
    tz=UTC0 / tz=IST-5:30   TZ (POSIX string, also read by the Windows C runtime)
    cwd=temp      run from a fresh empty directory instead of the baseline cwd

Per-test results are parsed from the output: house `PASS name` / `FAIL name` lines, unittest -v
(`name (id) ... ok|FAIL|ERROR`) and pytest -v (`file::test PASSED|FAILED|ERROR`). Without any, the whole command
is one test judged by its exit code.

    python brittle_audit.py --target mod.py --test test_mod.py [--module NAME] [--cwd DIR] [--timeout 60] [-- args]
    python brittle_audit.py --target mod.py --test -m pytest -- -v test_mod.py
    python brittle_audit.py --selftest
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_PERTURBATIONS = ["reformat", "noop-line", "reorder-defs", "rename-locals", "dict-order"]
ENV_PERTURBATIONS = ["hashseed=1", "hashseed=2", "hashseed=3", "tz=UTC0", "tz=IST-5:30", "cwd=temp"]
BASE_HASHSEED = "0"
_DYNAMIC = {"locals", "vars", "eval", "exec", "dir", "globals"}

LOADER = r"""
import os, runpy, sys, types
sys.dont_write_bytecode = True
sys.path.insert(0, %r)
from brittle_audit import perturb_source
target, modname, pert, test = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
rest = sys.argv[5:]
sys.path.insert(0, os.path.dirname(target))
src = open(target, encoding='utf-8').read()
if pert != 'none':
    src = perturb_source(src, pert)
mod = types.ModuleType(modname)
mod.__file__ = target
sys.modules[modname] = mod
exec(compile(src, target, 'exec'), mod.__dict__)
if test == '-m':
    sys.argv = [rest[0]] + rest[1:]
    runpy.run_module(rest[0], run_name='__main__', alter_sys=True)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(test)))
    sys.argv = [test] + rest
    runpy.run_path(test, run_name='__main__')
"""


# ---------------------------------------------------------------- source perturbations (pure: str -> str)
def _after_header(body):
    """Index after the module docstring and `from __future__` imports (a statement may not precede those)."""
    i = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        i = 1
    while i < len(body) and isinstance(body[i], ast.ImportFrom) and body[i].module == "__future__":
        i += 1
    return i


def _reorder_defs(tree):
    out, run = [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.decorator_list:
            run.append(node)
            continue
        out += run[::-1] + [node]
        run = []
    tree.body = out + run[::-1]


def _rename_in(fn):
    nodes = list(ast.walk(fn))
    if any(isinstance(n, (ast.Lambda, ast.ClassDef, ast.Match)) or
           (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn) or
           (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _DYNAMIC) for n in nodes):
        return
    params = {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}
    params |= {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
    declared = {name for n in nodes if isinstance(n, (ast.Global, ast.Nonlocal)) for name in n.names}
    stored = []
    for n in nodes:
        name = (n.id if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) else
                n.name if isinstance(n, ast.ExceptHandler) and n.name else None)
        if name and name not in params and name not in declared and name not in stored:
            stored.append(name)
    new = {old: f"_bt{i}" for i, old in enumerate(stored)}
    for n in nodes:
        if isinstance(n, ast.Name) and n.id in new:
            n.id = new[n.id]
        elif isinstance(n, ast.ExceptHandler) and n.name in new:
            n.name = new[n.name]


def _dict_order(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict) and len(n.keys) >= 2 and all(isinstance(k, ast.Constant) for k in n.keys):
            ks = [k.value for k in n.keys]
            if len(set(map(repr, ks))) == len(ks):
                n.keys, n.values = n.keys[::-1], n.values[::-1]
        elif isinstance(n, ast.Set) and len(n.elts) >= 2:
            n.elts = n.elts[::-1]


def perturb_source(src: str, name: str) -> str:
    """Apply one named semantics-preserving source perturbation; returns the new source."""
    if name not in SOURCE_PERTURBATIONS:
        raise ValueError(f"unknown source perturbation {name!r}")
    tree = ast.parse(src)
    if name == "noop-line":
        tree.body.insert(_after_header(tree.body), ast.Pass())
    elif name == "reorder-defs":
        _reorder_defs(tree)
    elif name == "rename-locals":
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _rename_in(n)
    elif name == "dict-order":
        _dict_order(tree)
    return ast.unparse(ast.fix_missing_locations(tree))   # unparse renumbers lines, so the `pass` shifts them


# ---------------------------------------------------------------- running and parsing
_LINE_RES = [
    (re.compile(r"^(PASS|FAIL)\s+(.+?)\s*$"), lambda m: (m.group(2), m.group(1) == "PASS")),
    (re.compile(r"^(.+?) \.\.\. (ok|FAIL|ERROR)\s*$"), lambda m: (m.group(1), m.group(2) == "ok")),
    (re.compile(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR)\b"), lambda m: (m.group(1), m.group(2) == "PASSED")),
]


def parse_results(text: str) -> dict:
    """{test name: passed?} from house PASS/FAIL lines, unittest -v and pytest -v output."""
    out = {}
    for line in text.splitlines():
        for rx, f in _LINE_RES:
            m = rx.match(line)
            if m:
                k, v = f(m)
                out[k] = out.get(k, True) and v
                break
    return out


def _run(loader, target, modname, pert, test, args, cwd, env, timeout):
    try:
        r = subprocess.run([sys.executable, "-B", "-c", loader, str(target), modname, pert, *test, *args],
                           cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        res = parse_results(r.stdout + "\n" + r.stderr)
        return r.returncode, res, (r.stdout + r.stderr)[-600:]
    except subprocess.TimeoutExpired:
        return "timeout", {}, ""


def audit(target, test, args=(), module=None, cwd=None, timeout=60, perturbations=None) -> dict:
    """target: the module file to perturb; test: a test script path, or ['-m', 'pytest'] style list."""
    target = Path(target).resolve()
    if not target.is_file():
        raise ValueError(f"target module not found: {target}")
    test = list(test) if isinstance(test, (list, tuple)) else [str(Path(test).resolve())]
    if test[0] == "-m":
        test, args = ["-m"], [test[1], *args]
    modname = module or target.stem
    cwd = str(Path(cwd or os.getcwd()).resolve())
    loader = LOADER % str(Path(__file__).resolve().parent)
    base_env = {**os.environ, "PYTHONHASHSEED": BASE_HASHSEED, "PYTHONDONTWRITEBYTECODE": "1"}
    base_env.pop("TZ", None)
    rc, base, tail = _run(loader, target, modname, "none", test, args, cwd, base_env, timeout)
    if not base:
        base = {"<whole command>": rc == 0}
    if not any(base.values()):
        raise ValueError(f"no test passes at baseline (exit {rc}); fix the tests first:\n{tail}")
    whole = list(base) == ["<whole command>"]
    rows, tmp = [], tempfile.mkdtemp(prefix="brittle_")
    try:
        for p in perturbations or SOURCE_PERTURBATIONS + ENV_PERTURBATIONS:
            env, run_cwd, pert = dict(base_env), cwd, p
            if p.startswith("hashseed="):
                env["PYTHONHASHSEED"], pert = p.split("=", 1)[1], "none"
            elif p.startswith("tz="):
                env["TZ"], pert = p.split("=", 1)[1], "none"
            elif p == "cwd=temp":
                run_cwd, pert = tmp, "none"
            prc, res, ptail = _run(loader, target, modname, pert, test, args, run_cwd, env, timeout)
            if whole:
                res = {"<whole command>": prc == 0}
            broke = sorted(t for t, ok in base.items() if ok and not res.get(t, False))
            rows.append({"perturbation": p, "exit": prc, "broke": broke, "tail": ptail if broke else ""})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    by_test = {}
    for r in rows:
        for t in r["broke"]:
            by_test.setdefault(t, []).append(r["perturbation"])
    return {"target": target.name, "baseline": base, "baseline_failing": sorted(t for t, v in base.items() if not v),
            "rows": rows, "brittle": by_test,
            "robust": sorted(t for t, v in base.items() if v and t not in by_test)}


def report(rep) -> str:
    n_ok = sum(rep["baseline"].values())
    lines = [f"{rep['target']}: {len(rep['brittle'])} of {n_ok} passing tests are BRITTLE "
             f"({len(rep['rows'])} semantics-preserving perturbations)"]
    for t, ps in sorted(rep["brittle"].items()):
        lines.append(f"  BRITTLE {t}  <- {', '.join(ps)}")
    if rep["baseline_failing"]:
        lines.append(f"  (failing at baseline, not judged: {', '.join(rep['baseline_failing'])})")
    lines.append(f"  robust: {len(rep['robust'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------- selftest
_MOD = '''"""synthetic target"""
import time

def config():
    rate, name = 2, "x"
    return {"alpha": 1, "beta": rate, "gamma": name}

def tags():
    return {"red", "green", "blue", "cyan", "plum"}

def scale(values, k=2):
    total = 0
    for i, v in enumerate(values):
        try:
            total += v * k
        except TypeError as err:
            total += 0
    return total

def noon_hour():
    return time.localtime(43200).tm_hour
'''

_TEST = '''import os, sys, types
import synth

def run():
    ok = {}
    ok["robust config equality"] = synth.config() == {"gamma": "x", "beta": 2, "alpha": 1}
    ok["robust tags as a set"] = synth.tags() == {"plum", "cyan", "blue", "green", "red"}
    ok["robust scale"] = synth.scale([1, 2, 3]) == 12
    ok["brittle dict repr"] = repr(synth.config()) == "{'alpha': 1, 'beta': 2, 'gamma': 'x'}"
    ok["brittle set order"] = ",".join(synth.tags()) == EXPECTED_ORDER
    fns = [k for k, v in vars(synth).items() if isinstance(v, types.FunctionType)]
    ok["brittle definition order"] = fns[:2] == ["config", "tags"]
    ok["brittle local time"] = synth.noon_hour() == EXPECTED_HOUR
    ok["brittle relative fixture"] = os.path.exists("fixture.txt")
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())

sys.exit(0 if run() else 1)
'''


def _selftest() -> bool:
    ok = {}
    d = Path(tempfile.mkdtemp(prefix="brittle_selftest_"))
    try:
        mod, test = d / "synth.py", d / "test_synth.py"
        mod.write_text(_MOD, encoding="utf-8")
        (d / "fixture.txt").write_text("fixture", encoding="utf-8")
        env0 = {**os.environ, "PYTHONHASHSEED": BASE_HASHSEED}
        env0.pop("TZ", None)
        probe = subprocess.run([sys.executable, "-B", "-c",
                                "import synth;print(','.join(synth.tags()));print(synth.noon_hour())"],
                               cwd=d, env=env0, capture_output=True, text=True, timeout=30).stdout.split()
        test.write_text(f"EXPECTED_ORDER = {probe[0]!r}\nEXPECTED_HOUR = {int(probe[1])}\n" + _TEST, encoding="utf-8")

        # the perturbations really are semantics-preserving on the synthetic module
        g0 = {}
        exec(compile(_MOD, "synth", "exec"), g0)
        same = True
        for p in SOURCE_PERTURBATIONS:
            g = {}
            exec(compile(perturb_source(_MOD, p), "synth", "exec"), g)
            same &= (g["config"]() == g0["config"]() and g["tags"]() == g0["tags"]()
                     and g["scale"]([1, 2, "z"]) == g0["scale"]([1, 2, "z"]) == 6)
        renamed = perturb_source(_MOD, "rename-locals")
        ok["every source perturbation preserves the module's values (rename-locals did rename)"] = (
            same and "_bt0" in renamed and "except TypeError as _bt" in renamed)

        rep = audit(mod, test, cwd=d, timeout=30)
        br = rep["brittle"]
        print(report(rep))
        ok["baseline: all 8 tests pass"] = len(rep["baseline"]) == 8 and all(rep["baseline"].values())
        ok["robust tests are never flagged"] = all(not t.startswith("robust") for t in br) and len(rep["robust"]) == 3
        ok["planted dict-repr test is broken by dict-order (and by no env change)"] = (
            "dict-order" in br.get("brittle dict repr", []) and
            not any(p in ENV_PERTURBATIONS for p in br.get("brittle dict repr", [])))
        ok["planted set-order test is broken by a hash seed"] = any(
            p.startswith("hashseed") for p in br.get("brittle set order", []))
        ok["planted definition-order test is broken by reorder-defs"] = br.get("brittle definition order") == ["reorder-defs"]
        ok["local-time and relative-path tests are broken by TZ and cwd"] = (
            any(p.startswith("tz=") for p in br.get("brittle local time", []))
            and br.get("brittle relative fixture") == ["cwd=temp"])
        ok["the target file on disk is never modified"] = mod.read_text(encoding="utf-8") == _MOD
        try:
            audit(d / "missing.py", test, cwd=d)
            ok["planted bad input (missing target module) is rejected"] = False
        except ValueError:
            ok["planted bad input (missing target module) is rejected"] = True
        ok["unittest -v and pytest -v lines are parsed"] = parse_results(
            "test_a (m.T.test_a) ... ok\ntest_b (m.T.test_b) ... FAIL\nt.py::test_c PASSED\n") == {
            "test_a (m.T.test_a)": True, "test_b (m.T.test_b)": False, "t.py::test_c": True}
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    opt = lambda k, dflt=None: argv[argv.index(k) + 1] if k in argv else dflt
    if "--target" not in argv or "--test" not in argv:
        print(__doc__)
        return 2
    t = opt("--test")
    test = ["-m", argv[argv.index("--test") + 2]] if t == "-m" else t
    rep = audit(opt("--target"), test, extra, module=opt("--module"), cwd=opt("--cwd"),
                timeout=int(opt("--timeout", 60)))
    print(report(rep))
    return 1 if rep["brittle"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
