"""adversary_eye - walk a plan as the attacker: for each step name what an adversary controls there (the outside data
source, the store at rest, the code and its dependencies, the metric, the branch and credentials, the message channel),
how they would tamper with it, and the check that would catch it; then find the first outside input no later step
verifies and how many steps it poisons (backs the adversary-eye skill). Verb and noun classes are a heuristic.

    python adversary_eye.py <plan> [--json]
    python adversary_eye.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, report, run_cli, view, words  # noqa: E402

KINDS = {"plan"}
SURFACE = [  # (class, trigger words, what the adversary controls, tamper, check)
    ("ingest", "download fetch pull scrape import ingest receive feed api prices bars quotes data",
     "the outside source and the wire", "serve revised, stale or poisoned rows", "hash and row-count against a second source"),
    ("at-rest", "cache rebuild store save write db database file disk snapshot",
     "the stored copy between runs", "edit or swap files at rest", "content hash recorded at write, checked at read"),
    ("execute", "run execute schedule install job script screener build compile",
     "the code, its dependencies and environment", "inject via a dependency, env var or path", "pinned deps and a clean-env run"),
    ("measure", "score evaluate measure rank backtest grade forward record metric",
     "the metric and its inputs", "game the metric or leak future data", "pre-registered metric and a holdout"),
    ("publish", "land push merge deploy commit main branch release tag",
     "the branch, the credentials and the review gate", "push unreviewed code with stolen credentials",
     "protected branch, signed commits, secret scan"),
    ("message", "tell send email post notify report message announce",
     "the channel and the message", "spoof or suppress the message", "message tied to a run id and a receipt"),
]
VERIFY = re.compile(r"\b(verify|check|validate|hash|compare|diff|audit|test|reconcile|second source|cross-check)\b", re.I)


def classify(step: str) -> list:
    ws = set(words(step))
    return [s for s in SURFACE if ws & set(s[1].split())]


def apply(subject, kind=None, **opts) -> dict:
    kind, steps = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"adversary-eye reads a plan (step list), not {kind}")
    if not steps:
        raise ValueError("empty plan")
    f, surface = [], []
    for i, st in enumerate(steps, 1):
        cls = classify(st)
        surface.append(len(cls))
        for c, _, ctrl, tamper, check in cls:
            f.append({"what": f"step {i} [{c}] {st}: adversary controls {ctrl}; could {tamper}; caught by {check}",
                      "step": i, "class": c})
        if not cls:
            f.append({"what": f"step {i} {st}: no attack surface named by the heuristic", "step": i, "class": None})
    ingest = [i for i, st in enumerate(steps, 1) if any(c[0] == "ingest" for c in classify(st))]
    first_bad = next((i for i in ingest if not any(VERIFY.search(steps[j - 1]) for j in range(i, len(steps) + 1))), None)
    if first_bad:
        poisoned = len(steps) - first_bad
        f.append({"what": f"FIRST UNVERIFIED INPUT step {first_bad}: {steps[first_bad - 1]} - nothing after it verifies "
                          f"the data, so {poisoned} later step(s) inherit whatever it serves", "step": first_bad,
                  "class": "unverified"})
    worst = max(range(len(steps)), key=lambda k: surface[k]) + 1
    summary = (f"{sum(surface)} attack surface(s) over {len(steps)} steps; widest step {worst} ({surface[worst - 1]}); "
               + (f"first unverified input at step {first_bad}" if first_bad else "every outside input is verified later"
                  if ingest else "no outside input named"))
    return view("adversary-eye", kind, f, summary, surfaces=sum(surface), widest_step=worst,
                first_unverified=first_bad)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["plan"])
    cls = {(x["step"], x["class"]) for x in v["findings"]}
    ok["probe plan: download is ingest, cache is at-rest, land is publish, tell is message"] = {
        (1, "ingest"), (2, "at-rest"), (5, "publish"), (6, "message")} <= cls
    ok["probe plan: the downloaded bars are the first unverified input (5 steps poisoned)"] = (
        v["stats"]["first_unverified"] == 1 and "5 later step(s)" in v["findings"][-1]["what"])
    ok["probe plan: 'score the forward record' is a measure surface"] = (4, "measure") in cls
    safe = apply(["download the prices", "hash and compare the prices with a second source", "run the screener"])
    ok["planted verify step clears the unverified input"] = safe["stats"]["first_unverified"] is None
    bare = apply(["think about it", "rest"])
    ok["planted plan with no surface names none and no unverified input"] = (
        bare["stats"]["surfaces"] == 0 and bare["stats"]["first_unverified"] is None)
    ok["a multi-surface step counts every class it touches"] = len(classify("download bars and push to main")) == 2
    try:
        apply(PROBES["text"])
        ok["planted bad input (prose text) is refused"] = False
    except ValueError:
        ok["planted bad input (prose text) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("adversary-eye", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
