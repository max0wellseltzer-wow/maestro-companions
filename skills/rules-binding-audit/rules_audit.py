"""rules_audit - audit rule FILES (not errata, not prompts): who each rule binds, what enforces it, whether the user can
override it, whether it cites a retired decision, and whether it repeats another rule.

    python rules_audit.py <rule file> [<rule file> ...] [--decisions DECISIONS.md] [--retired D70,D87] [--dup 0.6]
    python rules_audit.py --selftest

A rule line is a bullet, numbered item or table row (outside code fences) carrying a rule word (never, always, must,
do not, only, no, every, refuse, required, forbidden). For each it prints
    file:line | BINDS=CLAUDE/MAX/CODE | MECH=HOOK/TEST/PROSE | OVERRIDE=MAX/NONE | RETIRED=D.. | DUP=file:line
then a SUMMARY with counts of PROSE_ONLY (nothing enforces it), NO_OVERRIDE, CITES_RETIRED, DUPLICATE pairs, and
META_CLAUSE: whether any file says the rules bind Claude and that the user can override them (absent on 2026-10-15).

Retired ids come from --retired and from --decisions rows whose text says REMOVED / SUPERSEDED / RETIRED / REVOKED
(their own id; an id they supersede is named as "supersedes D87" and is also taken as retired).
The tags are keyword heuristics: read the table, do not quote it as a ruling. Stdlib only; reads only.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

RULE_WORD = re.compile(r"\b(never|always|must|do not|don't|only|no|every|refuse[sd]?|required?|forbid\w*|"
                       r"not allowed|may not|cannot)\b", re.I)
ITEM = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\|)")
BINDS = {
    "MAX": re.compile(r"\bMax\s+(must|should|has to|needs to|may not|cannot|never|always)\b", re.I),
    "CODE": re.compile(r"\b(the (code|tool|script|checker|function|module|harness)|tests?\s+must|every test|"
                       r"\.py\b|exit code)", re.I),
    "CLAUDE": re.compile(r"\b(Claude|session|instance|agent|you|your)\b", re.I),
}
MECH = [("HOOK", re.compile(r"\b(hook|PreToolUse|guard|blocked by|classifier|escape-proof)\b", re.I)),
        ("TEST", re.compile(r"(\btests?\b|pytest|check_all|checker|\w+_check\.py|selftest|\bCI\b|verify|"
                            r"prints? `?[A-Z_]{4,}|`python )", re.I))]
OVERRIDE = re.compile(r"(unless (the user|he|commanded)|the user'?s? (OK|go-?ahead|approval|order|command|say)|"
                      r"the user (can|may) override|override[sd]? by the user|only (with|on) the user|the user decides|asks? the user|"
                      r"without the user)", re.I)
META = re.compile(r"(rules? (here )?bind (Claude|you|the session)|the user (can|may) override (any|these|the) rules?|"
                  r"the user'?s (literal )?order outranks)", re.I)
DREF = re.compile(r"\bD\d{1,3}\b")
RETIRING = re.compile(r"\b(REMOVED|SUPERSEDED|RETIRED|REVOKED)\b", re.I)
STOP = set("the a an and or of to in on for is be it this that with by as at from not no never always must only "
           "do does any every you your we our are was were".split())


def retired_from(decisions: Path) -> set:
    """Ids a decision log retires: a row whose status cell starts REMOVED/SUPERSEDED/...; 'D70 is REMOVED';
    'supersedes/replaces/removes/retires D87'. A row that merely USES the word (D161 'ceremonies retired as RULES')
    does not retire itself."""
    out = set()
    for line in decisions.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(D\d+)\s*\|\s*\**\s*(\w+)", line)
        if not m:
            continue
        if RETIRING.fullmatch(m[2]):
            out.add(m[1])
        out.update(re.findall(r"\b(D\d+)\s+(?:is|was)\s+(?:now\s+)?(?:REMOVED|SUPERSEDED|RETIRED|REVOKED)\b", line, re.I))
        out.update(re.findall(r"\b(?:supersedes|replaces|removes|retires)\s+(D\d+)", line, re.I))
    return out


BOLD_RULE = re.compile(r"^\*\*[A-Z]?\d+[a-z]?\.")          # DESIGN_HINTS v3 shape: **A1. Run it or label it.** ...


def rules(path: Path) -> list:
    """(line, text) per rule: rule-worded bullets/items/table rows, and whole **A1.**-style paragraphs (the
    paragraph, including its *Mechanism:* line, is the rule's text)."""
    out, fence, para = [], False, None
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if para is not None:
            if line.strip() and not BOLD_RULE.match(line) and not line.startswith("#"):
                para[1] += " " + line.strip()
                continue
            out.append(tuple(para))
            para = None
        if fence:
            continue
        if BOLD_RULE.match(line):
            para = [n, line.strip()]
            continue
        if not ITEM.match(line) or re.match(r"^\s*\|[\s|:-]+\|?\s*$", line):
            continue
        if RULE_WORD.search(line):
            out.append((n, line.strip()))
    if para is not None:
        out.append(tuple(para))
    return out


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 2}


def audit(files: list, retired: set, dup: float = 0.6) -> dict:
    rows, meta = [], False
    for f in files:
        text = Path(f).read_text(encoding="utf-8")
        meta = meta or bool(META.search(text))
        for n, line in rules(Path(f)):
            binds = [k for k, rx in BINDS.items() if rx.search(line)] or ["CLAUDE(implied)"]
            mech = next((k for k, rx in MECH if rx.search(line)), "PROSE")
            over = "MAX" if OVERRIDE.search(line) else "NONE"
            ret = sorted(set(DREF.findall(line)) & retired)
            rows.append({"file": Path(f).name, "line": n, "text": line, "binds": binds, "mech": mech,
                         "override": over, "retired": ret, "dup": None, "words": _words(line)})
    pairs = 0
    for i, a in enumerate(rows):
        for b in rows[:i]:
            if len(a["words"]) >= 4 and len(b["words"]) >= 4:
                j = len(a["words"] & b["words"]) / len(a["words"] | b["words"])
                if j >= dup:
                    a["dup"] = f"{b['file']}:{b['line']}"
                    pairs += 1
                    break
    return {"rows": rows, "meta": meta, "dup_pairs": pairs,
            "prose_only": sum(r["mech"] == "PROSE" for r in rows),
            "no_override": sum(r["override"] == "NONE" for r in rows),
            "cites_retired": sum(bool(r["retired"]) for r in rows)}


def print_audit(rep: dict) -> None:
    for r in rep["rows"]:
        print(f"{r['file']}:{r['line']} | BINDS={'/'.join(r['binds'])} | MECH={r['mech']} | OVERRIDE={r['override']}"
              + (f" | RETIRED={','.join(r['retired'])}" if r["retired"] else "")
              + (f" | DUP={r['dup']}" if r["dup"] else "") + f" | {r['text'][:90]}")
    print(f"SUMMARY rules={len(rep['rows'])} PROSE_ONLY={rep['prose_only']} NO_OVERRIDE={rep['no_override']} "
          f"CITES_RETIRED={rep['cites_retired']} DUPLICATE_PAIRS={rep['dup_pairs']} "
          f"META_CLAUSE={'present' if rep['meta'] else 'ABSENT (no file says the rules bind Claude and the user can override them)'}")


def main(argv: list) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")      # a cp1252 console must not crash on a Greek letter
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    files, retired, dup, i = [], set(), 0.6, 0
    while i < len(argv):
        a = argv[i]
        if a == "--decisions":
            retired |= retired_from(Path(argv[i + 1]))
            i += 2
        elif a == "--retired":
            retired |= {x.strip() for x in argv[i + 1].split(",") if x.strip()}
            i += 2
        elif a == "--dup":
            dup = float(argv[i + 1])
            i += 2
        else:
            files.append(Path(a))
            i += 1
    if not files:
        print(__doc__)
        return 2
    print_audit(audit(files, retired, dup))
    return 0


def _selftest() -> bool:
    ok = {}
    t = Path(tempfile.mkdtemp(prefix="rulesaudit_"))
    (t / "DECISIONS.md").write_text("| D70 | REMOVED 2026-10-15 by D160 |\n| D159 | supersedes D87 |\n| D71 | ok |\n"
                                    "| D161 | Process ceremonies retired as RULES |\n| D160 | **D74 is REMOVED.** |\n",
                                    encoding="utf-8")
    card = t / "RULES_CARD.md"
    card.write_text(
        "# Rules\n"
        "- Never edit DECISIONS.md: a correction is a new entry.\n"                      # 2 prose, no override
        "- Never script a Kraken pull (D74(c), D70).\n"                                   # 3 cites retired D70
        "- Commit only after `python tools/secretscan.py` prints `0 possible secret(s)`.\n"  # 4 TEST
        "- The guard hook blocks any write to settings.json.\n"                           # 5 HOOK (no rule word? 'any' -> no)
        "- Never place a real order unless the user says so in that prompt.\n"                 # 6 override MAX
        "```\n- never inside a fence\n```\n"
        "Plain prose line that never counts.\n"
        "| D87 rule | only ETF-holdings scripts |\n", encoding="utf-8")                   # 11 table row, retired D87
    other = t / "CLAUDE.md"
    other.write_text("1. You must never edit the DECISIONS.md file: any correction is a new entry.\n"
                     "2. Every test must be registered in tests.json.\n", encoding="utf-8")
    ret = retired_from(t / "DECISIONS.md")
    ok["retired ids: a REMOVED status cell, 'D74 is REMOVED', 'supersedes D87'; not a row using the word"] = (
        ret == {"D70", "D87", "D74"})
    ret = {"D70", "D87"}
    (t / "V3.md").write_text("## A\n\n**A1. Run it or label it.** Every number comes from a run.\n"
                             "*Mechanism:* the escape-proof hook.\n\n**A2. Plain.** Say it plainly.\n",
                             encoding="utf-8")
    v3 = {r["line"]: r for r in audit([t / "V3.md"], ret)["rows"]}
    ok["**A1.**-style paragraphs are rules, their *Mechanism:* line counts"] = (
        sorted(v3) == [3, 6] and v3[3]["mech"] == "HOOK" and v3[6]["mech"] == "PROSE")
    rep = audit([card, other], ret)
    by = {(r["file"], r["line"]): r for r in rep["rows"]}
    ok["rule lines found; fenced and plain prose lines skipped"] = (
        ("RULES_CARD.md", 8) not in by and ("RULES_CARD.md", 10) not in by and ("RULES_CARD.md", 2) in by)
    ok["a rule with nothing enforcing it is PROSE"] = by[("RULES_CARD.md", 2)]["mech"] == "PROSE"
    ok["a rule naming its checker is TEST"] = by[("RULES_CARD.md", 4)]["mech"] == "TEST"
    ok["'unless the user says' is OVERRIDE=MAX; others NONE"] = (
        by[("RULES_CARD.md", 6)]["override"] == "MAX" and by[("RULES_CARD.md", 2)]["override"] == "NONE")
    ok["citations of retired D70 and D87 are flagged"] = (
        by[("RULES_CARD.md", 3)]["retired"] == ["D70"] and by[("RULES_CARD.md", 11)]["retired"] == ["D87"])
    ok["the same rule in two files is a DUPLICATE"] = by[("CLAUDE.md", 1)]["dup"] == "RULES_CARD.md:2"
    ok["'Every test must' binds CODE; 'You must' binds CLAUDE"] = (
        "CODE" in by[("CLAUDE.md", 2)]["binds"] and "CLAUDE" in by[("CLAUDE.md", 1)]["binds"])
    ok["no file states the meta clause -> META_CLAUSE absent"] = rep["meta"] is False
    (t / "META.md").write_text("These rules bind Claude; the user can override any rule.\n", encoding="utf-8")
    ok["a file that states it -> META_CLAUSE present"] = audit([card, t / "META.md"], ret)["meta"] is True
    shutil.rmtree(t, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
