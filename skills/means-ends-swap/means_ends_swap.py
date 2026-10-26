"""means_ends_swap - swap the means and ends of a plan and inspect what changes (backs means-ends-swap).

Each step's OBJECTS are its content words after the leading verb (a plural -s folded). Step i FEEDS a later step j
when they share an object: i is a means to j. Then the roles are swapped:
  the goal as a means     what does the last step feed? Nothing in the plan - so what is it for? (the unstated end)
  dead-end means          non-final steps that feed no later step - if they are ends in themselves, say so
  unmotivated steps       non-first steps no earlier step feeds - nothing in the plan makes them necessary
  unforced order          adjacent steps with no link between them - swapping them reads just as sensibly
A plan whose steps never name a shared artifact gets every step flagged; that is the finding (the links live only
in the writer's head), not a bug.

    python means_ends_swap.py <plan file|"- a\\n- b"> [--json]
    python means_ends_swap.py --selftest
"""
from __future__ import annotations

import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, sentences, view, words  # noqa: E402

KINDS = {"plan", "text"}


def _objects(step):
    ws = words(step)[1:]
    return {(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w) for w in ws if w not in STOP and len(w) > 2}


def apply(subject, kind=None, **opts) -> dict:
    k, val = load_subject(subject, kind)
    if k not in KINDS:
        raise ValueError(f"means-ends-swap reads a plan, not {k}")
    steps = list(val) if k == "plan" else sentences(val)
    if len(steps) < 2:
        raise ValueError("a plan needs 2+ steps")
    obj = [_objects(s) for s in steps]
    n = len(steps)
    feeds = {i: [j for j in range(i + 1, n) if obj[i] & obj[j]] for i in range(n)}
    fed = {j: [i for i in range(j) if obj[i] & obj[j]] for j in range(n)}
    dead = [i for i in range(n - 1) if not feeds[i]]
    unmot = [j for j in range(1, n) if not fed[j]]
    unforced = [i for i in range(n - 1) if not (obj[i] & obj[i + 1])]
    findings = [{"what": f"goal as a means: '{steps[-1]}' feeds nothing in the plan - its purpose is unstated",
                 "goal": steps[-1]}]
    findings += [{"what": f"dead-end means: '{steps[i]}' feeds no later step - an end in itself?", "dead_end": steps[i]} for i in dead]
    findings += [{"what": f"unmotivated: '{steps[j]}' - no earlier step makes it necessary", "unmotivated": steps[j]} for j in unmot]
    findings += [{"what": f"unforced order: '{steps[i]}' <-> '{steps[i + 1]}' share nothing - the swap reads as well",
                  "swap": [steps[i], steps[i + 1]]} for i in unforced]
    chain = [f"{steps[i]} -> {steps[j]}" for i in range(n) for j in feeds[i]]
    if chain:
        findings.append({"what": "means->end links: " + "; ".join(chain)[:250], "links": chain})
    return view("means-ends-swap", k, findings, f"{n} steps, {len(chain)} means->end links; {len(dead)} dead-end means, "
                f"{len(unmot)} unmotivated, {len(unforced)} unforced adjacent orders", links=len(chain),
                dead_ends=len(dead), unmotivated=len(unmot), unforced=len(unforced))


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["plan"])
    ok["probe: the 6-step plan names no shared artifact (0 links, 5 unforced)"] = v["stats"]["links"] == 0 and v["stats"]["unforced"] == 5
    ok["probe: 'tell the user the result' is the goal that feeds nothing"] = v["findings"][0]["goal"] == "tell the user the result"
    plan = ["fetch the prices", "clean the prices", "fit a model on the clean prices", "write the model report", "buy lunch"]
    p = apply(plan)
    ok["planted: 4 links fetch->clean->fit->report; the report is the one dead end before lunch"] = (
        p["stats"]["links"] == 4 and [f["dead_end"] for f in p["findings"] if "dead_end" in f] == ["write the model report"])
    ok["planted: buy lunch is unmotivated and its order unforced"] = (
        any(f.get("unmotivated") == "buy lunch" for f in p["findings"]) and any(f.get("swap") == ["write the model report", "buy lunch"] for f in p["findings"]))
    d = apply(["download bars", "email the landlord", "rebuild bars cache"])
    ok["planted: a step that feeds nothing mid-plan is a dead-end means"] = any(f.get("dead_end") == "email the landlord" for f in d["findings"])
    try:
        apply(["only one step"])
        ok["planted bad input (a 1-step plan) is refused"] = False
    except ValueError:
        ok["planted bad input (a 1-step plan) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("means-ends-swap", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
