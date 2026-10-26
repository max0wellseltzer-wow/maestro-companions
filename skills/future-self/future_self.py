"""future-self - a plan's irreversible steps and deferred costs as next-week and next-year regrets (backs future-self).

Two horizons. NEXT WEEK: one-way doors - steps whose verb cannot be undone (delete, push, publish, send, drop,
overwrite, rebuild, land, sell...) unless the same step names its undo (backup, archive, tag, snapshot, dry-run).
NEXT YEAR: deferred costs - shortcuts that accrue interest (later, TODO, temporary, hack, skip, for now, manual,
without tests) and things that grow on their own (append, log, cache, nightly, cron). Each regret is written in the
future self's voice with the step it comes from. Heuristic verb lists.

    python future_self.py plan.md
    python future_self.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import load_subject, view, run_cli, report, PROBES, sentences  # noqa: E402

KINDS = {"plan", "text"}
ONE_WAY = re.compile(r"\b(delete|remove|rm|drop|truncate|purge|wipe|overwrite|rebuild|replace|push|force|land|merge|"
                     r"publish|post|send|email|tell|announce|deploy|release|migrate|rename|sell|buy|pay|cancel|"
                     r"close|retire|squash|reset)\w*", re.I)
UNDO = re.compile(r"\b(backup|back up|archive|tag|snapshot|dry[- ]run|copy first|revert|rollback|staging|draft|"
                  r"reversible|undo|keep the old)\b", re.I)
DEFER = re.compile(r"\b(later|todo|temporary|temp|hack|skip|for now|quick|workaround|manual(?:ly)?|someday|"
                   r"without tests|ignore|defer|postpone|hardcode\w*|fix it next)\b", re.I)
GROWS = re.compile(r"\b(append|log|logs|cache|nightly|cron|schedule\w*|accumulat\w*|every day|daily|forever|record)\b", re.I)


def apply(subject, kind=None, **opts) -> dict:
    kind, value = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"future-self reads {sorted(KINDS)}, not {kind}")
    steps = [s for s in (value if kind == "plan" else sentences(value)) if s.strip()]
    if not steps:
        raise ValueError("empty plan")
    findings, week, year, guarded = [], 0, 0, 0
    for i, s in enumerate(steps, 1):
        ow, undo = ONE_WAY.search(s), UNDO.search(s)
        if ow and undo:
            guarded += 1
            findings.append({"what": f"guarded door  step {i} '{ow[0]}' has its undo '{undo[0]}': {s[:80]}",
                             "step": i, "horizon": "none"})
        elif ow:
            week += 1
            findings.append({"what": f"NEXT WEEK  step {i}: 'once I ran \"{ow[0].lower()}\" there was no way back' - {s[:80]}",
                             "step": i, "horizon": "week", "door": ow[0].lower()})
        d, g = DEFER.search(s), GROWS.search(s)
        if d:
            year += 1
            findings.append({"what": f"NEXT YEAR  step {i}: 'the \"{d[0].lower()}\" was never paid back' - {s[:80]}",
                             "step": i, "horizon": "year", "debt": d[0].lower()})
        elif g:
            year += 1
            findings.append({"what": f"NEXT YEAR  step {i}: 'the {g[0].lower()} kept growing and nobody owned it' - {s[:80]}",
                             "step": i, "horizon": "year", "debt": g[0].lower()})
    first_door = next((f["step"] for f in findings if f["horizon"] == "week"), None)
    findings.sort(key=lambda f: {"week": 0, "year": 1, "none": 2}[f["horizon"]])
    summary = (f"{week} next-week regret(s) (unguarded one-way doors), {year} next-year regret(s) (deferred or growing "
               f"costs), {guarded} guarded door(s); " +
               (f"point of no return at step {first_door} of {len(steps)}" if first_door else "no one-way door"))
    return view("future-self", kind, findings, summary, next_week=week, next_year=year, guarded=guarded,
                point_of_no_return=first_door)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["plan"])
    weeks = {f["step"] for f in v["findings"] if f["horizon"] == "week"}
    ok["probe plan: rebuild, land and tell are one-way doors"] = weeks == {2, 5, 6}
    ok["probe plan: the forward record is a growing next-year cost"] = any(
        f["step"] == 4 and f["horizon"] == "year" for f in v["findings"])
    ok["probe plan: point of no return is step 2"] = v["stats"]["point_of_no_return"] == 2
    p = apply(["delete the old branch after an archive tag", "delete the scratch folder", "hardcode the path for now"])
    ph = [(f["step"], f["horizon"]) for f in p["findings"]]
    ok["planted: delete with archive tag is guarded, bare delete is a regret"] = (1, "none") in ph and (2, "week") in ph
    ok["planted: 'hardcode for now' is a next-year debt"] = (3, "year") in ph
    ok["a read-only plan has no door"] = apply(["read the log file", "count the rows"])["stats"]["next_week"] == 0
    try:
        apply(PROBES["items"])
        ok["planted bad input (items) refused"] = False
    except ValueError:
        ok["planted bad input (items) refused"] = True
    return report(ok)


def main(argv):
    return run_cli("future-self", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
