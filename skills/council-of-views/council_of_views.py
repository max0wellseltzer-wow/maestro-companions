"""council_of_views - seat N sibling lenses around one subject and tally, element by element, which of them named it
(backs the council-of-views skill). PLURAL lens of the point-of-view family.

Elements are what the subject is made of: its top content keywords (text, plan, code) or its item labels (items).
A lens "names" an element when the element appears as a whole word in that lens's summary or findings. Each element
lands in one bin: agreed (named by at least half the council), contested (by 2 or more but under half), lone (by
exactly one lens - the dissent, with the dissenter named) or ignored (by none - the council's shared blind spot).
The council is fixed: N seats spread evenly over the sorted family, each taking the next lens that can read the kind;
--opt lenses=a,b,c names it. Meta lenses never sit on a council.

    python council_of_views.py --selftest
    python council_of_views.py <subject> [--opt n=7 | --opt lenses=spotlight,squint] [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, keywords, label_of, load_subject, report, run_cli, view  # noqa: E402

NAME = "council-of-views"
KINDS = {"text", "plan", "code", "items"}
META = {"lens-carousel", "random-lens", "council-of-views"}


def family() -> dict:
    from ratify import members
    return {n: p for n, p in members(SK).items() if n not in META}


def elements(kd, val) -> list:
    if kd == "items":
        return [label_of(it, i).lower() for i, it in enumerate(val)]
    text = "\n".join(val) if kd == "plan" else val
    return [w for w, _ in keywords(text, 25)]


def seat(pool, kd, subject, n, want):
    from ratify import _load
    names, views, tried = sorted(pool), {}, set()
    starts = want or [names[(i * len(names)) // n] for i in range(n)]
    sys._pov_meta_depth = 1
    try:
        for s in starts:
            i = names.index(s)
            for j in range(len(names)):
                nm = names[(i + j) % len(names)]
                if nm in tried:
                    continue
                tried.add(nm)
                mod = pool[nm] if hasattr(pool[nm], "apply") else _load(nm, pool[nm])
                v = None
                if kd in getattr(mod, "KINDS", {kd}):
                    try:
                        v = mod.apply(subject, kind=kd)
                    except Exception:      # a sibling that cannot read this subject leaves its seat empty
                        v = None
                if isinstance(v, dict) and v.get("findings"):
                    views[nm] = v
                    break
                if want:
                    break
    finally:
        sys._pov_meta_depth = 0
    return views


def apply(subject, kind=None, n=7, lenses=None, _mods=None, **opts) -> dict:
    if getattr(sys, "_pov_meta_depth", 0):
        raise ValueError("council-of-views cannot sit inside another meta lens")
    kd, val = load_subject(subject, kind)
    if kd not in KINDS:
        raise ValueError(f"council-of-views has no elements to tally in a {kd} subject")
    pool = dict(_mods) if _mods is not None else family()
    want = [x.strip() for x in str(lenses).split(",")] if lenses else None
    if want and any(w not in pool for w in want):
        raise ValueError(f"unknown lens in {want}")
    if (len(want) if want else int(n)) < 3:
        raise ValueError("a council needs at least 3 seats")
    views = seat(pool, kd, subject, int(n), want)
    if len(views) < 3:
        raise ValueError(f"fewer than 3 lenses could read this {kd} subject")
    said = {nm: (v["summary"] + " " + " ".join(json.dumps(f, default=str) for f in v["findings"])).lower()
            for nm, v in views.items()}
    tally = {e: [nm for nm in views if re.search(rf"(?<![a-z0-9]){re.escape(e)}(?![a-z0-9])", said[nm])]
             for e in elements(kd, val)}
    half = len(views) / 2
    bins = {e: ("agreed" if len(w) >= half else "contested" if len(w) >= 2 else "lone" if w else "ignored")
            for e, w in tally.items()}
    f = []
    for b in ("agreed", "contested", "lone", "ignored"):
        for e in sorted((e for e in bins if bins[e] == b), key=lambda e: -len(tally[e])):
            who = ", ".join(tally[e]) if b != "ignored" else "nobody"
            f.append({"what": f"{b}: '{e}' named by {len(tally[e])}/{len(views)} ({who})", "element": e, "bin": b,
                      "votes": len(tally[e])})
    cnt = {b: sum(v == b for v in bins.values()) for b in ("agreed", "contested", "lone", "ignored")}
    return view(NAME, kd, f, f"council of {len(views)} on {len(tally)} elements: {cnt['agreed']} agreed, "
                f"{cnt['contested']} contested, {cnt['lone']} lone dissent, {cnt['ignored']} ignored",
                council=list(views), bins=cnt, tally={e: len(w) for e, w in tally.items()})


def _selftest() -> bool:
    from types import SimpleNamespace as NS

    from pov_core import view as mk
    ok = {}
    p = apply(PROBES["text"], n=4)
    ok["probe text with the live family: 3-4 seats and every keyword binned"] = (
        3 <= len(p["stats"]["council"]) <= 4 and sum(p["stats"]["bins"].values()) == len(p["stats"]["tally"]))
    ok["probe text: the council is fixed (same run, same seats)"] = apply(PROBES["text"], n=4)["stats"]["council"] == p["stats"]["council"]
    say = lambda words: (lambda s, kind=None: mk("t", "items", [{"what": words}], "said"))  # noqa: E731
    mods = {"a": NS(apply=say("trend and carry look fine"), KINDS={"items"}),
            "b": NS(apply=say("trend wins, carry ok"), KINDS={"items"}),
            "c": NS(apply=say("trend again; reversion is cost-killed"), KINDS={"items"}),
            "d": NS(apply=say("nothing here"), KINDS={"series"})}
    q = apply(PROBES["items"], lenses="a,b,c,d", _mods=mods)
    ok["planted items: trend agreed 3/3, carry agreed 2/3, reversion lone"] = (
        q["stats"]["tally"]["trend"] == 3 and q["stats"]["tally"]["carry"] == 2 and q["stats"]["tally"]["reversion"] == 1)
    ok["planted items: momentum and pm-calibration are ignored, the series lens holds no seat"] = (
        q["stats"]["bins"]["ignored"] == 2 and "d" not in q["stats"]["council"])
    ok["planted: 'trend' is not counted inside 'trendy'"] = apply(
        PROBES["items"], lenses="a,b,e", _mods={**mods, "e": NS(apply=say("trendy names"), KINDS={"items"})})["stats"]["tally"]["trend"] == 2
    for label, bad in (("series subject", lambda: apply(PROBES["series"], _mods=mods)),
                       ("two seats", lambda: apply(PROBES["items"], lenses="a,b", _mods=mods)),
                       ("unknown lens", lambda: apply(PROBES["items"], lenses="a,b,zz", _mods=mods))):
        try:
            bad()
            ok[f"planted bad input ({label}) is refused"] = False
        except ValueError:
            ok[f"planted bad input ({label}) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
