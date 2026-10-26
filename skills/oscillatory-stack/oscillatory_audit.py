"""oscillatory_audit - audit an Oscillatory Fire log against the stack's hardenings (backs oscillatory-stack).

A log is JSONL, one record per cycle (alpha fascination -> beta Controlled Fire attack -> gamma residue):
  {"cycle": 1, "object": "...", "intensity": 3,
   "lock": {"text": "...", "sha256": "<sha of text>", "t": "2026-10-16T10:00:00Z"}, "audit_t": "2026-10-16T10:05:00Z",
   "rejection_set": [{"object": "...", "intensity": 4, "breaks": "the constraint it breaks"}],
   "near_wall": [{"claim": "...", "strength": 0.9, "standard": 0.6, "stated": 0.7,
                  "surplus_fate": "future-use|future-attack|undecided", "previous_fate": "...", "consistency_cost": "..."}],
   "pivot": {"to": "...", "distance": 0.4, "cost_paid": 0.3},
   "softenings": ["a softening found by the Rule-omega audit"]}
Checks (hardening numbers from FULL_OSCILLATORY_HISTORY_AND_CURRENT_STACK.md):
  LOCK_AFTER_AUDIT       the fascination lock is not timestamped before the audit (8)
  LOCK_EDITED            the lock text no longer matches its recorded sha256 (8: the sentence cannot be revised)
  NO_REJECTION_SET       no rivals were locked (10)
  REJECTION_NOT_HOTTER   a rival's intensity is not above the current object's (11)
  NO_BROKEN_CONSTRAINT   a rival names no constraint it breaks (12: verbosity is not intensity)
  TAX_UNPAID             a near-wall claim's stated strength exceeds strength - tax x (strength - standard) (15-16)
  SURPLUS_NO_FATE        unclaimed surplus without a declared fate (17)
  FATE_CHANGED_FREE      a surplus fate changed with no consistency cost (17)
  PIVOT_UNDERPAID        cost_paid < rate x distance (18-19); distance defaults to the word-set Jaccard distance
                         between the objects - one measurable answer to the open residue "how is distance measured"
  SOFTENING_DROPPED      a cycle found softenings and the next cycle's object is none of them (6, Rule omega)
    python oscillatory_audit.py LOG.jsonl [--tax 0.5] [--rate 1.0]
    python oscillatory_audit.py distance "object A" "object B"
    python oscillatory_audit.py --selftest
Exit 0 every cycle clean, 1 findings, 2 bad arguments.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

FATES = {"future-use", "future-attack", "undecided"}
STOP = set("the a an of to in on for and or is are be by with as at from that this it its".split())


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP}


def distance(a: str, b: str) -> float:
    A, B = words(a), words(b)
    if not A and not B:
        return 0.0
    return 1.0 - len(A & B) / len(A | B)


def _t(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def audit(cycles: list, tax=0.5, rate=1.0) -> list:
    out = []
    cycles = sorted(cycles, key=lambda c: c.get("cycle", 0))
    for i, c in enumerate(cycles):
        f = []
        n = c.get("cycle", i + 1)
        lock = c.get("lock") or {}
        try:
            if not lock.get("t") or not c.get("audit_t") or _t(lock["t"]) >= _t(c["audit_t"]):
                f.append("LOCK_AFTER_AUDIT")
        except ValueError:
            f.append("LOCK_AFTER_AUDIT (unparseable time)")
        if lock.get("sha256") and hashlib.sha256(lock.get("text", "").encode("utf-8")).hexdigest() != lock["sha256"]:
            f.append("LOCK_EDITED")
        cur = float(c.get("intensity", 0))
        rs = c.get("rejection_set") or []
        if not rs:
            f.append("NO_REJECTION_SET")
        for r in rs:
            if float(r.get("intensity", 0)) <= cur:
                f.append(f"REJECTION_NOT_HOTTER {r.get('object', '?')!r} ({r.get('intensity')} <= {cur:g})")
            if not (r.get("breaks") or "").strip():
                f.append(f"NO_BROKEN_CONSTRAINT {r.get('object', '?')!r}")
        for w in c.get("near_wall") or []:
            s, std, st = float(w["strength"]), float(w["standard"]), float(w["stated"])
            if s > std:
                cap = s - tax * (s - std)
                if st > cap + 1e-12:
                    f.append(f"TAX_UNPAID {w.get('claim', '?')!r} stated {st:g} > allowed {cap:g}")
            if s - st > 1e-12:
                fate = w.get("surplus_fate")
                if fate not in FATES:
                    f.append(f"SURPLUS_NO_FATE {w.get('claim', '?')!r}")
                elif w.get("previous_fate") and w["previous_fate"] != fate and not w.get("consistency_cost"):
                    f.append(f"FATE_CHANGED_FREE {w.get('claim', '?')!r} {w['previous_fate']} -> {fate}")
        pv = c.get("pivot")
        if pv:
            d = pv.get("distance")
            d = distance(c.get("object", ""), pv.get("to", "")) if d is None else float(d)
            need = rate * d
            if float(pv.get("cost_paid", 0)) + 1e-12 < need:
                f.append(f"PIVOT_UNDERPAID distance {d:.2f} needs {need:.2f}, paid {float(pv.get('cost_paid', 0)):g}")
        soft = c.get("softenings") or []
        if soft and i + 1 < len(cycles):
            nxt = cycles[i + 1].get("object", "")
            if not any(s.strip().lower() == nxt.strip().lower() or distance(s, nxt) <= 0.5 for s in soft):
                f.append(f"SOFTENING_DROPPED next object {nxt!r} is none of {soft}")
        out.append({"cycle": n, "findings": f})
    return out


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    if argv[:1] == ["distance"] and len(argv) == 3:
        print(f"{distance(argv[1], argv[2]):.3f}")
        return 0
    args, o = list(argv), {}
    try:
        for fl in ("--tax", "--rate"):
            if fl in args:
                i = args.index(fl)
                o[fl] = float(args[i + 1])
                del args[i:i + 2]
        if len(args) != 1 or not Path(args[0]).is_file():
            raise ValueError("need one LOG.jsonl")
        cycles = [json.loads(ln) for ln in Path(args[0]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (ValueError, IndexError, OSError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    rep = audit(cycles, o.get("--tax", 0.5), o.get("--rate", 1.0))
    for r in rep:
        print(f"cycle {r['cycle']}: {'CLEAN' if not r['findings'] else str(len(r['findings'])) + ' finding(s)'}")
        for x in r["findings"]:
            print("  - " + x)
    n = sum(len(r["findings"]) for r in rep)
    print(f"{len(rep)} cycle(s), {n} finding(s)")
    return 1 if n else 0


def _selftest() -> bool:
    ok = {}
    lock_text = "The residue matters because it predicts which gate fails first."
    sha = hashlib.sha256(lock_text.encode("utf-8")).hexdigest()
    good = [
        {"cycle": 1, "object": "gate failure prediction", "intensity": 3,
         "lock": {"text": lock_text, "sha256": sha, "t": "2026-10-16T10:00:00Z"}, "audit_t": "2026-10-16T10:05:00Z",
         "rejection_set": [{"object": "proof of all gates", "intensity": 5, "breaks": "finite gate"}],
         "near_wall": [{"claim": "c1", "strength": 0.9, "standard": 0.5, "stated": 0.7, "surplus_fate": "future-attack"}],
         "pivot": {"to": "gate failure order prediction", "cost_paid": 0.3},
         "softenings": ["distance between objects"]},
        {"cycle": 2, "object": "distance between objects", "intensity": 4,
         "lock": {"text": "x", "t": "2026-10-16T11:00:00Z"}, "audit_t": "2026-10-16T11:10:00Z",
         "rejection_set": [{"object": "y", "intensity": 6, "breaks": "sacred four placement"}]},
    ]
    r = audit(good)
    ok["a log that follows every hardening is clean"] = all(not c["findings"] for c in r)
    ok["Jaccard distance: same words 0, disjoint 1"] = distance("a b c", "c b a") == 0.0 and distance("x", "y") == 1.0
    bad = json.loads(json.dumps(good))
    bad[0]["audit_t"] = "2026-10-16T09:00:00Z"
    bad[0]["lock"]["text"] += " (revised)"
    bad[0]["rejection_set"] = [{"object": "milder", "intensity": 2, "breaks": ""}]
    bad[0]["near_wall"] = [{"claim": "c1", "strength": 0.9, "standard": 0.5, "stated": 0.85},
                           {"claim": "c2", "strength": 0.8, "standard": 0.4, "stated": 0.5, "surplus_fate": "undecided",
                            "previous_fate": "future-use"}]
    bad[0]["pivot"] = {"to": "something entirely unrelated", "cost_paid": 0.1}
    bad[1]["object"] = "a fresh shiny topic"
    bad[1]["rejection_set"] = []
    rb = audit(bad)
    k0 = " | ".join(rb[0]["findings"])
    for name in ("LOCK_AFTER_AUDIT", "LOCK_EDITED", "REJECTION_NOT_HOTTER", "NO_BROKEN_CONSTRAINT", "TAX_UNPAID",
                 "SURPLUS_NO_FATE", "FATE_CHANGED_FREE", "PIVOT_UNDERPAID", "SOFTENING_DROPPED"):
        ok[f"{name} is caught"] = name in k0
    eq = audit([dict(good[1], rejection_set=[{"object": "z", "intensity": 4, "breaks": "b"}])])[0]["findings"]
    ok["a rival at the same intensity is not hotter"] = any("REJECTION_NOT_HOTTER" in x for x in eq)
    ok["an empty rejection set is NO_REJECTION_SET"] = "NO_REJECTION_SET" in rb[1]["findings"]
    ok["the tax scales with the excess (0.9 vs 0.5 at tax 0.5 allows 0.7)"] = not any(
        "TAX_UNPAID" in x for x in audit([dict(good[0], near_wall=[{"claim": "z", "strength": 0.9, "standard": 0.5,
                                                                    "stated": 0.7, "surplus_fate": "undecided"}])])[0]["findings"])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "log.jsonl"
        p.write_text("\n".join(json.dumps(c) for c in good) + "\n", encoding="utf-8")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc0 = main([str(p)])
            p.write_text("\n".join(json.dumps(c) for c in bad) + "\n", encoding="utf-8")
            rc1 = main([str(p)])
        ok["exit 0 clean, 1 with findings"] = (rc0, rc1) == (0, 1)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
