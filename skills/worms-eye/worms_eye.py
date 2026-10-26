"""worms-eye - from the bottom step up, what each foundation step must assume about everything above it (backs worms-eye).

    python worms_eye.py --selftest
    python worms_eye.py <file.py|plan> [--kind code|plan] [--json]
Code: functions ordered by height (leaves first); each one's assumptions are read off its AST (args iterated, opened,
divided by, indexed, attribute-read; globals it reads) and paired with every caller above that must honour them.
Plan: step 1 is the bottom; each step's verb precondition plus the hand-offs later steps take from it.
"""
from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, view, words  # noqa: E402

NAME = "worms-eye"
VERB = {"download": "the source is reachable and returns complete data", "fetch": "the source is reachable",
        "pull": "the source is reachable", "rebuild": "every input from below is complete and there is disk room",
        "build": "inputs from below are complete", "run": "what it runs on is fresh, not left from an older pass",
        "score": "the outcomes being scored have settled", "land": "every check above passed on this exact tree",
        "merge": "every check passed on this exact tree", "push": "checks passed and the remote is the right one",
        "tell": "the result is final and will not change after it is told", "report": "the numbers are final",
        "clean": "the raw data arrived whole", "fit": "the cleaned data is representative", "delete": "a backup exists"}


def _assumptions(fn: ast.FunctionDef) -> list:
    args = {a.arg for a in fn.args.args}
    local = args | {t.id for n in ast.walk(fn) for t in ([n.target] if isinstance(n, (ast.For, ast.AugAssign)) else
                    getattr(n, "targets", [])) if isinstance(t, ast.Name)}
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id in args:
            out.append(f"'{n.iter.id}' is iterable")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open" and n.args \
                and isinstance(n.args[0], ast.Name):
            out.append(f"'{n.args[0].id}' names a readable file")
        elif isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod)) and isinstance(n.right, ast.Name):
            out.append(f"'{n.right.id}' is never 0")
        elif isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id in args:
            out.append(f"'{n.value.id}' supports indexing")
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in args:
            out.append(f"'{n.value.id}' has .{n.attr}")
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in local and not hasattr(builtins, n.id):
            out.append(f"global '{n.id}' exists")
    return list(dict.fromkeys(out))


def _code(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise ValueError(f"worms-eye cannot parse the code: {e}") from e
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    calls = {k: {c.func.id for c in ast.walk(v) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)} & set(fns) - {k}
             for k, v in fns.items()}
    height = {}

    def h(k, seen=()):
        if k not in height:
            height[k] = 0 if not calls[k] or k in seen else 1 + max(h(c, seen + (k,)) for c in calls[k])
        return height[k]
    callers = {k: sorted(m for m in fns if k in calls[m]) for k in fns}
    defined = {f"global '{n}' exists" for n in fns}
    assume = {k: [a for a in _assumptions(v) if a not in defined] for k, v in fns.items()}
    f = []
    for k in sorted(fns, key=lambda n: (h(n), fns[n].lineno)):
        ups = callers[k]
        for a in assume[k] or ["nothing visible in its body"]:
            f.append({"what": f"level {h(k)} {k} assumes {a}; " +
                      (f"above it {', '.join(ups)} must honour that" if ups else "top level, only the outside caller can break it"),
                      "fn": k, "level": h(k)})
    leaves = [k for k in fns if h(k) == 0]
    return view(NAME, "code", f, f"{len(leaves)} bottom functions ({', '.join(leaves)}) carry {sum(d['level'] == 0 for d in f)} "
                f"assumptions up to {len(fns) - len(leaves)} callers", leaves=leaves, assumptions=assume)


def _plan(steps: list):
    stems = [{w[:5] for w in words(s) if w not in STOP and len(w) > 2} for s in steps]
    f, implicit = [], 0
    for i, s in enumerate(steps):
        verb = next((VERB[w] for w in words(s) if w in VERB), None)
        if verb:
            f.append({"what": f"step {i + 1} '{s}' assumes {verb}", "step": i + 1})
        later = [(j, sorted(stems[i] & stems[j])) for j in range(i + 1, len(steps)) if stems[i] & stems[j]]
        for j, shared in later:
            f.append({"what": f"step {i + 1} hands '{', '.join(shared)}' up to step {j + 1}, which assumes it is still valid",
                      "step": i + 1})
        if not later and i + 1 < len(steps):
            implicit += 1
            f.append({"what": f"step {i + 1} hands up nothing named; step {i + 2} must assume it finished and left its output "
                              f"where it looks", "step": i + 1})
    return view(NAME, "plan", f, f"{len(steps)} steps from the bottom; {implicit} hand-offs are implicit (no shared noun)",
                implicit=implicit)


def apply(subject, kind=None, **opts) -> dict:
    k, v = load_subject(subject, kind)
    if k not in ("code", "plan"):
        raise ValueError(f"worms-eye reads code or a plan, not {k}")
    return _code(v) if k == "code" else _plan(v)


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["code"], kind="code")
    a = p["stats"]["assumptions"]
    ok["probe code: leaves are load and score"] = sorted(p["stats"]["leaves"]) == ["load", "score"]
    ok["probe code: load assumes path is a readable file"] = "'path' names a readable file" in a["load"]
    ok["probe code: score assumes rows iterable and k never 0"] = {"'rows' is iterable", "'k' is never 0"} <= set(a["score"])
    g = apply("LIMIT = 3\ndef cap(x):\n    return min(x.size, LIMIT)\n\ndef top():\n    return cap(1)\n", kind="code")
    ok["planted: global LIMIT and x.size are found, top must honour them"] = (
        {"global 'LIMIT' exists", "'x' has .size"} <= set(g["stats"]["assumptions"]["cap"])
        and any("top must honour" in d["what"] for d in g["findings"]))
    q = apply(PROBES["plan"])
    ok["probe plan: download assumes a reachable source; hand-offs are implicit"] = (
        "reachable" in q["findings"][0]["what"] and q["stats"]["implicit"] >= 3)
    try:
        apply(PROBES["text"])
        ok["planted bad input (text) is refused"] = False
    except ValueError:
        ok["planted bad input (text) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
