"""opponent-lawyer - find exploitable ambiguity in a rule or contract text (backs the opponent-lawyer skill).

Reads every sentence as opposing counsel would, hunting for the words that let a hostile party do less, do
something else, or do it never: permissive may / should where shall was meant; any (one is enough) versus all
(one missing defeats it); an inclusive "or" (both, or the cheaper one); elastic terms (reasonable, promptly,
material, as needed, best effort, etc.); obligations with no deadline; exceptions (unless, except, subject to)
that swallow the rule. Each hit comes with the hostile reading. Exposure = hits weighted by how much they loosen.
Regex patterns - it reads words, not intent.

    python opponent_lawyer.py DECISIONS.md
    python opponent_lawyer.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import load_subject, view, run_cli, report, PROBES, sentences  # noqa: E402

KINDS = {"text", "plan"}
# (label, pattern, weight, hostile reading template - {m} is the matched words)
TRAPS = [
    ("permissive", r"\b(may|can|is allowed to|is permitted to)\b", 3,
     "'{m}' grants a right, not a duty - I may simply not do it"),
    ("soft duty", r"\b(should|ought to|is expected to|aims? to|tries to|tr(?:y|ies) to)\b", 2,
     "'{m}' is advice; nothing happens when I don't"),
    ("any", r"\bany\b", 2, "'any' - one instance of my choosing satisfies it"),
    ("all", r"\b(all|every|each)\b", 1, "'{m}' - one missing case and the whole clause fails, so it never binds"),
    ("inclusive or", r"\b(\w+) or (\w+)\b", 2, "'{m}' - I pick whichever side is cheaper, or claim both"),
    ("and/or", r"\band/or\b", 3, "'and/or' - every combination is allowed, including the empty one in spirit"),
    ("elastic", r"\b(reasonabl[ey]|appropriate(?:ly)?|promptly|timely|material(?:ly)?|significant(?:ly)?|"
                r"substantial(?:ly)?|as needed|where possible|if possible|best efforts?|normally|generally|"
                r"small|large|fast|soon|again|etc\.?|and so on|similar)\b", 2,
     "'{m}' has no number - I decide what it means"),
    ("exception", r"\b(unless|except|subject to|notwithstanding|other than|provided that)\b", 3,
     "'{m}' - I will argue my case falls in the exception"),
    ("undefined actor", r"\b(they|someone|somebody|it is|will be \w+ed|are \w+ed)\b", 1,
     "'{m}' - no named party, so nobody is bound"),
]
DUTY = re.compile(r"\b(will|must|shall|should|need to|has to|we stop|we \w+)\b", re.I)
WHEN = re.compile(r"\b(by|before|within|after|until|daily|nightly|weekly|every|next|tomorrow|today|\d+\s*(?:h|d|days?|"
                  r"hours?|min)|\d{4}-\d\d-\d\d|monday|tuesday|wednesday|thursday|friday|week|month)\b", re.I)


def apply(subject, kind=None, **opts) -> dict:
    kind, value = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"opponent-lawyer reads {sorted(KINDS)}, not {kind}")
    clauses = [c for c in (value if kind == "plan" else sentences(value)) if re.search(r"[A-Za-z]{3}", c)]
    if not clauses:
        raise ValueError("no clauses to read")
    findings, per, total = [], {}, 0
    for i, c in enumerate(clauses, 1):
        for label, pat, w, tmpl in TRAPS:
            for m in re.finditer(pat, c, re.I):
                if label == "inclusive or" and re.search(r"\beither\b|\bbut not both\b", c, re.I):
                    continue
                findings.append({"what": f"[{label}] clause {i}: {tmpl.format(m=m[0])} - \"{c[:70]}\"",
                                 "clause": i, "trap": label, "weight": w})
                per[i] = per.get(i, 0) + w
                total += w
        if DUTY.search(c) and not WHEN.search(c):
            findings.append({"what": f"[no deadline] clause {i}: '{DUTY.search(c)[0]}' with no time bound - "
                                     f"I comply eventually, i.e. never - \"{c[:70]}\"", "clause": i,
                             "trap": "no deadline", "weight": 2})
            per[i] = per.get(i, 0) + 2
            total += 2
    findings.sort(key=lambda f: (-per.get(f["clause"], 0), f["clause"], -f["weight"]))
    worst = max(per, key=per.get) if per else None
    traps = sorted({f["trap"] for f in findings})
    summary = (f"{len(findings)} exploitable reading(s) across {len(per)}/{len(clauses)} clause(s), exposure {total}; "
               + (f"weakest clause {worst} (exposure {per[worst]}); traps: {', '.join(traps)}" if worst else "airtight on these patterns"))
    return view("opponent-lawyer", kind, findings, summary, exposure=total, clauses_hit=len(per),
                weakest=worst)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["text"])
    tr = {(f["clause"], f["trap"]) for f in v["findings"]}
    ok["probe: 'small' and 'again' are elastic terms"] = (4, "elastic") in tr and (5, "elastic") in tr
    ok["probe: 'They say' has an undefined actor"] = any(t == "undefined actor" and c == 7 for c, t in tr)
    p = apply("The operator may run the backup. Any failed job shall be reported within 2 hours. "
              "Costs must be reasonable unless the job is urgent.")
    pt = {(f["clause"], f["trap"]) for f in p["findings"]}
    ok["planted: 'may run the backup' is permissive"] = (1, "permissive") in pt
    ok["planted: 'any failed job' is an any-trap with a deadline present"] = (2, "any") in pt and (2, "no deadline") not in pt
    ok["planted: 'unless urgent' exception + elastic 'reasonable' make clause 3 weakest"] = (
        (3, "exception") in pt and p["stats"]["weakest"] == 3)
    ok["either ... or is not an inclusive-or trap"] = not any(
        f["trap"] == "inclusive or" for f in apply("Pick either red or blue by 5 pm.")["findings"])
    try:
        apply([1.0, 2.0])
        ok["planted bad input (series) refused"] = False
    except ValueError:
        ok["planted bad input (series) refused"] = True
    return report(ok)


def main(argv):
    return run_cli("opponent-lawyer", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
