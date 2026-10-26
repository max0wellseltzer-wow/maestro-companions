"""Mechanical checker for the restriction-matrix Tier 5 receipt and the Tier 2 locks that can be read from text.

Given the text of a reply (its receipt block included), it checks: all six receipt sections are present (INTAKE, BUILT,
RAN, NOT RUN, CYST, DEBTS); INTAKE lists at least three readings and marks at least two BURNED and one TAKEN; CYST
answers all five numbered questions; BUILT names at least one PASS selftest line; the deferral lock (every "later",
"next step", "could", "would", "should be built", "if the user wants" outside DEBTS must be matched by a DEBTS entry, or
DEBTS must say zero and there must be no deferrals); and the prose-to-code lock (prose lines about the work <= lines of
code shipped, the code count given on the command line or as `CODE_LINES: N` in the text). It checks form, not
honesty: a reviewer still reads the answers.

Usage:
    python matrix_receipt_check.py reply.md [--code-lines N]   # prints PROBLEMS; exit 1 if any
    python matrix_receipt_check.py --selftest
Library:
    from matrix_receipt_check import check_reply
    problems = check_reply(text, code_lines=120)
"""
import re
import sys

SECTIONS = ("INTAKE", "BUILT", "RAN", "NOT RUN", "CYST", "DEBTS")
DEFERRALS = ("later", "next step", "could", "would", "should be built", "if max wants")
_HEAD = re.compile(r"^[ \t#*`]*(INTAKE|BUILT|RAN|NOT RUN|CYST|DEBTS)\b[ \t:*`]*", re.MULTILINE)


def split_sections(text):
    """Return (prose_before_receipt, {SECTION: body})."""
    marks = [(m.start(), m.end(), m.group(1)) for m in _HEAD.finditer(text)]
    if not marks:
        return text, {}
    out = {}
    for i, (s, e, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.setdefault(name, text[e:end].strip())
    return text[:marks[0][0]], out


def count_deferrals(text):
    """One hit per sentence that contains any deferral word (the word list of the first match is reported)."""
    hits = []
    for sent in re.split(r"(?<=[.!?;])\s+|\n", text.lower()):
        for w in DEFERRALS:
            if re.search(r"\b" + re.escape(w) + r"\b", sent):
                hits.append(w)
                break
    return hits


def check_reply(text, code_lines=None):
    probs = []
    prose, secs = split_sections(text)
    for s in SECTIONS:
        if s not in secs:
            probs.append("receipt section missing: " + s)
    intake = secs.get("INTAKE", "")
    readings = re.findall(r"(?im)^\s*(?:\d+[.)]|-|\*)\s+\S", intake)
    if len(readings) < 3:
        probs.append("INTAKE lists %d readings (need >= 3)" % len(readings))
    if len(re.findall(r"\bBURNED\b", intake)) < 2:
        probs.append("INTAKE marks fewer than two readings BURNED")
    if not re.search(r"\bTAKEN\b", intake):
        probs.append("INTAKE does not say which reading is TAKEN")
    if "BUILT" in secs and not re.search(r"\bPASS\b", secs["BUILT"]):
        probs.append("BUILT has no PASS selftest line")
    cyst = secs.get("CYST", "")
    answered = {int(n) for n in re.findall(r"(?m)^\s*([1-5])[.)]\s+\S", cyst)}
    for n in range(1, 6):
        if n not in answered:
            probs.append("CYST question %d not answered" % n)
    body_wo_debts = "\n".join(v for k, v in secs.items() if k not in ("DEBTS", "CYST")) + "\n" + prose
    defs = count_deferrals(body_wo_debts)
    debts = secs.get("DEBTS", "")
    debt_entries = re.findall(r"(?m)^\s*(?:-|\*|\d+[.)])\s+\S", debts)
    zero = re.match(r"\s*(zero|none|0)\b", debts, re.IGNORECASE) is not None
    if defs and len(debt_entries) < len(defs):
        probs.append("deferral lock: %d deferral words (%s) but %d DEBTS entries"
                     % (len(defs), ", ".join(sorted(set(defs))), len(debt_entries)))
    if zero and defs:
        probs.append("DEBTS says zero but the reply defers: " + ", ".join(sorted(set(defs))))
    if code_lines is None:
        m = re.search(r"CODE_LINES:\s*(\d+)", text)
        code_lines = int(m.group(1)) if m else None
    prose_lines = [l for l in prose.splitlines() if l.strip() and not l.lstrip().startswith(("```", "    "))]
    if code_lines is None:
        probs.append("prose-to-code lock: no code line count given (--code-lines or CODE_LINES: N)")
    elif len(prose_lines) > code_lines:
        probs.append("prose-to-code lock: %d prose lines > %d code lines" % (len(prose_lines), code_lines))
    return probs


GOOD = """Built the half-life fitter.
CODE_LINES: 140
INTAKE
1. explain half-lives in prose - BURNED
2. write a plan - BURNED
3. build and run a fitter on real data - TAKEN
BUILT
halflife.py: PASS 7/7, planted bugs caught 3/3
RAN
python -I halflife.py --selftest
NOT RUN
nothing skipped
CYST
1. ran, quoted above
2. real input: the fills file
3. no hard part deferred
4. every number from the run
5. the hard version
DEBTS
zero
"""


def _selftest():
    ok = True

    def check(cond, desc):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + desc)
        ok = ok and bool(cond)

    check(check_reply(GOOD) == [], "a complete receipt passes")
    no_cyst = GOOD.replace("4. every number from the run\n", "")
    check(check_reply(no_cyst) == ["CYST question 4 not answered"], "catches an unanswered CYST question")
    lazy = GOOD.replace("Built the half-life fitter.", "Built the fitter; a GUI could come later.")
    p = check_reply(lazy)
    check(any(s.startswith("DEBTS says zero") for s in p), "catches a deferral hidden behind DEBTS: zero")
    one_burn = GOOD.replace("2. write a plan - BURNED", "2. write a plan")
    check("INTAKE marks fewer than two readings BURNED" in check_reply(one_burn), "catches only one burned reading")
    check(any("prose-to-code" in s for s in check_reply(GOOD, code_lines=0)), "prose-to-code lock fires at 0 code lines")
    check(any("section missing: NOT RUN" in s for s in check_reply(GOOD.replace("NOT RUN\nnothing skipped\n", ""))),
          "catches a missing NOT RUN section")
    paid = lazy.replace("DEBTS\nzero\n", "DEBTS\n- GUI: out of this prompt's words (burned reading)\n")
    check(check_reply(paid) == [], "a deferral matched by a DEBTS entry passes")
    return ok


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    code_lines = int(argv[argv.index("--code-lines") + 1]) if "--code-lines" in argv else None
    with open(argv[0], encoding="utf-8") as f:
        probs = check_reply(f.read(), code_lines)
    print("PROBLEMS: none" if not probs else "PROBLEMS:")
    for p in probs:
        print("- " + p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
