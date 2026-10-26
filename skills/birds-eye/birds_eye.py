"""birds-eye - the dependency map of a plan or python code seen from above: roots, sinks, hubs, cycles (backs birds-eye).

    python birds_eye.py --selftest
    python birds_eye.py <file.py|plan|code> [--kind code|plan] [--json]
Code: edge f -> g when f calls g (both defined in the file).  Plan: edge i -> j (i < j) when steps share a noun stem;
a step linked to nothing earlier is 'loose' (only the order connects it).
"""
from __future__ import annotations

import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, code_functions, load_subject, report, run_cli, view, words  # noqa: E402

NAME = "birds-eye"


def graph(k: str, v):
    if k == "code":
        try:
            fns = code_functions(v)
        except SyntaxError as e:
            raise ValueError(f"birds-eye cannot parse the code: {e}") from e
        names = [fn["name"] for fn in fns]
        return names, {fn["name"]: sorted(set(fn["calls"]) & set(names) - {fn["name"]}) for fn in fns}, \
            {fn["name"] for fn in fns if fn["name"] in fn["calls"]}
    stems = [{w[:5] for w in words(s) if w not in STOP and len(w) > 2} for s in v]
    names = [f"{i + 1}. {s[:40]}" for i, s in enumerate(v)]
    return names, {names[i]: [names[j] for j in range(i + 1, len(v)) if stems[i] & stems[j]] for i in range(len(v))}, set()


def cycles(names, out) -> list:
    color, found = {n: 0 for n in names}, []

    def dfs(n, stack):
        color[n] = 1
        stack.append(n)
        for m in out[n]:
            if color[m] == 1:
                found.append(stack[stack.index(m):] + [m])
            elif color[m] == 0:
                dfs(m, stack)
        stack.pop()
        color[n] = 2
    for n in names:
        if color[n] == 0:
            dfs(n, [])
    return found


def apply(subject, kind=None, **opts) -> dict:
    k, v = load_subject(subject, kind)
    if k not in ("code", "plan"):
        raise ValueError(f"birds-eye reads code or a plan, not {k}")
    names, out, selfloops = graph(k, v)
    if len(names) < 2:
        raise ValueError("birds-eye needs at least 2 functions or steps")
    inn = {n: [m for m in names if n in out[m]] for n in names}
    roots = [n for n in names if not inn[n]]
    sinks = [n for n in names if not out[n]]
    deg = {n: len(inn[n]) + len(out[n]) for n in names}
    hub = max(names, key=lambda n: deg[n])
    cyc = cycles(names, out) + [[n, n] for n in sorted(selfloops)]
    f = [{"what": f"{n}: calls/feeds {', '.join(out[n]) or '-'}; fed by {', '.join(inn[n]) or '-'}", "node": n} for n in names]
    f.append({"what": f"roots (nothing above them): {', '.join(roots)}", "role": "roots"})
    f.append({"what": f"sinks (nothing below them): {', '.join(sinks)}", "role": "sinks"})
    f.append({"what": f"hub: {hub} with {deg[hub]} links", "role": "hub"})
    if k == "plan":
        loose = [n for i, n in enumerate(names) if i and not inn[n]]
        f.append({"what": f"loose steps (only the order links them): {', '.join(loose) or 'none'}", "role": "loose"})
    f += [{"what": "cycle: " + " -> ".join(c), "role": "cycle"} for c in cyc]
    edges = sum(len(o) for o in out.values())
    return view(NAME, k, f, f"{len(names)} nodes, {edges} edges; {len(roots)} roots, {len(sinks)} sinks, hub {hub}, "
                f"{len(cyc)} cycles", roots=roots, sinks=sinks, hub=hub, cycles=cyc, edges=edges)


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["code"], kind="code")
    ok["probe code: main is the only root"] = p["stats"]["roots"] == ["main"]
    ok["probe code: load and score are sinks, main is the hub"] = p["stats"]["sinks"] == ["load", "score"] and p["stats"]["hub"] == "main"
    q = apply(PROBES["plan"])
    ok["probe plan: 6 steps mapped, loose steps reported"] = sum("node" in d for d in q["findings"]) == 6 and any(d.get("role") == "loose" for d in q["findings"])
    cyc = "def a():\n    b()\n\ndef b():\n    c()\n\ndef c():\n    a()\n\ndef d():\n    d()\n"
    c = apply(cyc, kind="code")
    ok["planted a->b->c->a cycle and d self-call are found"] = (
        any(set(x) == {"a", "b", "c"} for x in c["stats"]["cycles"]) and ["d", "d"] in c["stats"]["cycles"])
    plan = ["fetch prices", "clean the prices", "fit model on clean prices", "report the model"]
    r = apply(plan)
    ok["planted plan: step 1 is the root and step 4 the sink"] = r["stats"]["roots"] == ["1. fetch prices"] and r["stats"]["sinks"] == ["4. report the model"]
    try:
        apply("def broken(:\n  pass", kind="code")
        ok["planted bad input (unparseable code) is refused"] = False
    except ValueError:
        ok["planted bad input (unparseable code) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
