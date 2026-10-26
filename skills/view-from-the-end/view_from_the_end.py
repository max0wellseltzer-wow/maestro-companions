"""view_from_the_end - stand at the goal and walk backwards: back-chain the preconditions the goal step needs through
the earlier steps that deliver them, list the preconditions nobody delivers, the steps the goal never reaches, and
any step that needs something only a LATER step makes (backs the view-from-the-end skill).

Heuristic step parsing: the first word is the verb; making verbs (download, build, write ...) deliver their objects,
other verbs need their objects; every step also delivers 'its result', which 'the result/change/output' refers to.

    python view_from_the_end.py <plan> [--opt goal=STEP_NO] [--json]
    python view_from_the_end.py --selftest
"""
from __future__ import annotations

import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, view, words  # noqa: E402

KINDS = {"plan"}
MAKE = set("""download build rebuild create make write generate compute fetch produce draft collect gather export
save record derive train fit pull render compile""".split())
VAGUE = {"result", "results", "output", "it", "change", "this", "that", "answer", "outcome"}


def contract(i: int, step: str):
    """(needs, delivers) for step i (1-based) as sets of tokens."""
    ws = words(step)
    names = {w.lower() for w in words(step, lower=False)[1:] if w[:1].isupper()}   # people are not preconditions
    verb, objs = (ws[0] if ws else ""), {w for w in ws[1:] if w not in STOP and len(w) > 2 and w not in names}
    needs = set() if verb in MAKE else objs - VAGUE
    if objs & VAGUE and i > 1:
        needs.add(f"result#{i - 1}")
    if verb in MAKE and "from" in ws:                      # 'build X from Y' needs Y
        needs |= {w for w in ws[ws.index("from") + 1:] if w not in STOP and len(w) > 2}
    delivers = ((objs - VAGUE) if verb in MAKE else set()) | {f"result#{i}"}
    if verb in MAKE and "from" in ws:
        delivers -= needs
    return needs, delivers


def apply(subject, kind=None, goal=None, **opts) -> dict:
    kind, steps = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"view-from-the-end reads a plan (step list), not {kind}")
    if not steps:
        raise ValueError("empty plan")
    g = int(goal) if goal is not None else len(steps)
    if not 1 <= g <= len(steps):
        raise ValueError(f"goal step {g} outside 1..{len(steps)}")
    c = {i: contract(i, s) for i, s in enumerate(steps, 1)}
    need, chain, findings = set(c[g][0]), [g], []
    findings.append({"what": f"GOAL step {g}: {steps[g - 1]} needs {sorted(need) or 'nothing named'}", "step": g})
    for i in range(g - 1, 0, -1):
        hit = c[i][1] & need
        if hit:
            chain.append(i)
            need = (need - hit) | c[i][0]
            findings.append({"what": f"<- step {i}: {steps[i - 1]} delivers {sorted(hit)}; it needs "
                                     f"{sorted(c[i][0]) or 'nothing named'}", "step": i, "delivers": sorted(hit)})
    unmet = sorted(need)
    off = [i for i in range(1, g) if i not in chain]
    for n in unmet:
        findings.append({"what": f"UNMET precondition '{n}': no earlier step delivers it - must already exist "
                                 f"or a link is missing", "need": n})
    for i in off:
        findings.append({"what": f"OFF-CHAIN step {i}: {steps[i - 1]} - the goal never needs what it delivers",
                         "step": i})
    late = []
    for i in range(1, len(steps) + 1):
        for n in c[i][0]:
            if not any(n in c[j][1] for j in range(1, i)) and any(n in c[j][1] for j in range(i + 1, len(steps) + 1)):
                late.append((i, n))
                findings.append({"what": f"ORDER step {i} needs '{n}' which only a later step makes", "step": i, "need": n})
    summary = (f"back from step {g}: {len(chain)} step(s) on the chain {sorted(chain)}, {len(off)} off-chain, "
               f"{len(unmet)} unmet precondition(s), {len(late)} ordering violation(s)")
    return view("view-from-the-end", kind, findings, summary, goal=g, chain=sorted(chain), off_chain=off,
                unmet=unmet, order_violations=len(late))


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["plan"])
    ok["probe plan: chain from 'tell the user the result' is steps 4-6"] = v["stats"]["chain"] == [4, 5, 6]
    ok["probe plan: download, rebuild and run are off-chain"] = v["stats"]["off_chain"] == [1, 2, 3]
    ok["probe plan: 'forward' 'record' and 'main' are unmet preconditions"] = {"forward", "record", "main"} <= set(
        v["stats"]["unmet"])
    good = apply(["download the bars", "build the cache from the bars", "run the screener on the cache",
                  "send the result to the user"])
    ok["planted linked plan: every step on the chain, only the screener tool is unmet"] = (
        good["stats"]["chain"] == [1, 2, 3, 4] and good["stats"]["unmet"] == ["screener"])
    bad_order = apply(["fetch the prices", "send the report to the user", "build the report from the prices"])
    ok["planted ordering violation: report sent before it is built"] = bad_order["stats"]["order_violations"] == 1
    ok["goal option moves the end point"] = apply(PROBES["plan"], goal=2)["stats"]["chain"] == [2]
    refused = []
    for bad, kw in ((PROBES["series"], {}), (PROBES["plan"], {"goal": 9})):
        try:
            apply(bad, **kw)
            refused.append(False)
        except ValueError:
            refused.append(True)
    ok["planted bad inputs (a series, goal step 9 of 6) are refused"] = all(refused)
    return report(ok)


def main(argv):
    return run_cli("view-from-the-end", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
