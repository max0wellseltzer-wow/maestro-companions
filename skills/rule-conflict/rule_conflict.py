"""rule_conflict - find where a SET of standing rules collides (backs the rule-conflict skill; reverses rule-miner).

rule-miner turns prompts INTO rules; this reads the rules already standing and reports where they fight:

  still-cited     rule X was REMOVED / SUPERSEDED / RETIRED / replaced (by Y), yet a later rule still invokes X
  contradiction   two live rules, same subject (shared key terms), opposite modality (always/never, must/must not,
                  allowed/forbidden) - and neither rule cites the other (an explicit amendment is not a conflict)
  duplicate       two rules whose content-word sets overlap >= --dup (default 0.8)
  dangling        a cited rule id (same prefix as the defined ids) that no rule defines
  id-collision    the same id defined twice (only possible across files or by a copy-paste slip)

Input: a markdown file (table rows `| D71 | text | ... |` or list rows `- D71: text` / `**D1. text**`) or a folder of
*.md rule files. Read-only: every file is opened for reading.

    python rule_conflict.py <rules.md | folder> [more files...] [--top 30] [--dup 0.8] [--jac 0.12] [--shared 4] [--common 0.15]
    python rule_conflict.py --selftest
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "skill-finder"))
from find_skill import _tokens  # noqa: E402  (sibling skill)

TABLE_ROW = re.compile(r"^\s*\|\s*\**([A-Z]{1,3}\d{1,4})\**\s*\|(.*)$")
LIST_ROW = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?([A-Z]{1,3}\d{1,4})(?:\*\*)?\s*[.:)]\s*(.+)$")
ID = re.compile(r"\b([A-Z]{1,3})(\d{1,4})\b")
UPPER_KILL = re.compile(r"(?:\b([A-Z]{1,3}\d{1,4})\b[^|.;]{0,25}?)?\b(SUPERSEDED|REMOVED|RETIRED|REVERSED)\b(?!\s+IN\s+PART)")
VERB_KILL = re.compile(r"\b(supersedes|replaces|retires|removes|reverses|overrides)\s+(?:the\s+old\s+|the\s+)?"
                       r"([A-Z]{1,3}\d{1,4})\b(['’(]?)", re.I)
BY_KILL = re.compile(r"\b(?:superseded|replaced|retired|removed|reversed)\s+(?:in\s+part\s+)?by\s+(?:main\s+)?"
                     r"([A-Z]{1,3}\d{1,4})\b", re.I)
HISTORY = re.compile(r"\b(supersed\w*|replac\w*|retir\w*|remov\w*|revers\w*|was|history|historical|formerly|"
                     r"old|instead of|no longer|dropped|in part|struck|renumber\w*)\b|->|→", re.I)
PROVENANCE = re.compile(r"\((?:was|see|cf\.?|from|on)\b[^)]*\)", re.I)
NEG = re.compile(r"\b(never|must not|mustn't|do not|don't|dont|forbidden|banned|not allowed|prohibited|may not|"
                 r"cannot|can't|no longer allowed|is not permitted)\b", re.I)
POS = re.compile(r"\b(always|must|required|allowed|may|permitted|ok to|should|is the)\b", re.I)
MODAL = set(_tokens("never must not mustn't don't dont forbidden banned allowed prohibited may cannot always "
                    "required permitted should longer only"))
SENT = re.compile(r"(?<=[.!?;])\s+")


def _num(rid):
    m = ID.match(rid)
    return int(m.group(2)) if m else 0


def parse_text(text: str, source: str = "") -> list:
    rules = []
    for i, ln in enumerate(text.splitlines(), 1):
        m = TABLE_ROW.match(ln)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            cells = [c for c in cells if c]
            rules.append({"id": m.group(1), "text": " | ".join(cells), "status": cells[-1] if len(cells) > 1 else "",
                          "file": source, "line": i})
            continue
        m = LIST_ROW.match(ln)
        if m and len(m.group(2).split()) >= 3:
            rules.append({"id": m.group(1), "text": m.group(2).strip(), "status": "", "file": source, "line": i})
    return rules


def load(paths) -> list:
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(p.glob("*.md"))
        elif p.is_file():
            files.append(p)
        else:
            raise ValueError(f"no such rules file or folder: {p}")
    rules = []
    for f in files:
        rules += parse_text(f.read_text(encoding="utf-8", errors="replace"), f.name)
    if not rules:
        raise ValueError("no rule rows found (want '| D71 | text |' or '- D71: text' rows)")
    return rules


def _key(text, common=frozenset()):
    text = PROVENANCE.sub(" ", text)
    return {t for t in _tokens(re.sub(r"\b[A-Z]{1,3}\d{1,4}\b", " ", text))
            if t not in MODAL and t not in common and not t.isdigit()}


def _jac(a, b):
    return len(a & b) / len(a | b) if a or b else 0.0


def _snip(text, at, w=70):
    return "..." + " ".join(text[max(0, at - w): at + w].split()) + "..."


def analyse(rules, dup: float = 0.8, min_shared: int = 4, min_jac: float = 0.12, common_frac: float = 0.15) -> dict:
    """common_frac: in sets of >= 30 rules, words in that share of rules are boilerplate, not a shared subject."""
    prefix = Counter(ID.match(r["id"]).group(1) for r in rules).most_common(1)[0][0]
    by_id = defaultdict(list)
    for r in rules:
        by_id[r["id"]].append(r)
    items = []
    for rid, rs in sorted(by_id.items(), key=lambda kv: _num(kv[0])):
        if len(rs) > 1:
            items.append({"kind": "id-collision", "ids": [rid],
                          "reason": "defined %d times: %s" % (len(rs), ", ".join(f"{r['file']}:{r['line']}" for r in rs))})
    # 1. who killed whom
    dead = {}                                   # dead id -> (killer id or None, evidence)
    partial = set()
    for r in rules:
        for m in UPPER_KILL.finditer(r["text"]):
            victim = m.group(1) if m.group(1) and m.group(1) != r["id"] else r["id"]
            self_ok = (m.start(2) < 40 or r["text"].endswith(r["status"]) and m.start(2) >= len(r["text"]) - len(r["status"])
                       or BY_KILL.match(r["text"], m.start(2)))
            if victim == r["id"] and not self_ok:
                continue                        # 'SHADOW -> RETIRED' mid-text is a state name, not this rule's death
                k = BY_KILL.search(r["text"][m.start():m.start() + 120])
                dead.setdefault(victim, (k.group(1) if k else None, _snip(r["text"], m.start())))
            else:
                dead.setdefault(victim, (r["id"], _snip(r["text"], m.start())))
        for m in VERB_KILL.finditer(r["text"]):
            if m.group(3):
                partial.add(m.group(2))
            elif m.group(2) != r["id"]:
                dead.setdefault(m.group(2), (r["id"], _snip(r["text"], m.start())))
        for m in BY_KILL.finditer(r["text"]):
            near = ID.findall(r["text"][max(0, m.start() - 35):m.start()])
            victim = near[-1][0] + near[-1][1] if near else r["id"]     # "D70 was replaced by D71" names its victim
            if "in part" in m.group(0).lower():
                partial.add(victim)
            elif m.group(1) != victim:
                dead.setdefault(victim, (m.group(1), _snip(r["text"], m.start())))
    # 2. dead but still cited by a later rule, outside a history/retirement sentence
    for x, (killer, ev) in sorted(dead.items(), key=lambda kv: _num(kv[0])):
        after = max(_num(x), _num(killer) if killer else 0)
        for r in rules:
            if r["id"] in (x, killer) or _num(r["id"]) <= after:
                continue
            for s in SENT.split(r["text"]):
                if re.search(rf"\b{re.escape(x)}\b(?!\()", s) and not HISTORY.search(s):
                    items.append({"kind": "still-cited", "ids": [x, r["id"]] + ([killer] if killer else []),
                                  "reason": f"{x} is dead ({'by ' + killer if killer else 'self-marked'}: {ev}) "
                                            f"but {r['id']} still invokes it: \"{' '.join(s.split())[:160]}\""})
                    break
    # 3. contradictions: opposite modality on the same subject, between live rules that do not cite each other
    cites = {r["id"]: {a + b for a, b in ID.findall(r["text"])} for r in rules}
    df = Counter(t for r in rules for t in _key(r["text"]))
    common = frozenset(t for t, c in df.items() if len(rules) >= 30 and c >= common_frac * len(rules))
    sents = []
    for r in rules:
        if r["id"] in dead:
            continue
        for s in SENT.split(r["text"]):
            pol = -1 if NEG.search(s) else (1 if POS.search(s) else 0)
            k = _key(s, common)
            if pol and len(k) >= min_shared:
                sents.append((r["id"], pol, k, " ".join(s.split())))
    inv = defaultdict(set)
    for i, (_, _, k, _) in enumerate(sents):
        for t in k:
            inv[t].add(i)
    seen = set()
    for i, (ra, pa, ka, sa) in enumerate(sents):
        cand = Counter(j for t in ka for j in inv[t] if j > i)
        for j, shared in cand.items():
            rb, pb, kb, sb = sents[j]
            if shared < min_shared or pa == pb or ra == rb or (ra, rb) in seen:
                continue
            if rb in cites[ra] or ra in cites[rb] or _jac(ka, kb) < min_jac:
                continue
            seen.add((ra, rb))
            neg, pos = (sa, sb) if pa < 0 else (sb, sa)
            items.append({"kind": "contradiction", "ids": [ra, rb],
                          "reason": f"shared terms {sorted(ka & kb)[:6]}; NO: \"{neg[:110]}\" vs YES: \"{pos[:110]}\""})
    # 4. duplicates
    keys = [(r["id"], _key(r["text"])) for r in rules]
    for i, (a, ka) in enumerate(keys):
        for b, kb in keys[i + 1:]:
            replaced = dead.get(a, (None,))[0] == b or dead.get(b, (None,))[0] == a   # old rule vs its replacement
            if a != b and not replaced and len(ka) >= 4 and _jac(ka, kb) >= dup:
                items.append({"kind": "duplicate", "ids": [a, b], "reason": f"content Jaccard {_jac(ka, kb):.2f}"})
    # 5. dangling references
    defined = set(by_id)
    for r in rules:
        for p, n in ID.findall(r["text"]):
            rid = p + n
            if p == prefix and rid not in defined and rid not in dead:   # a removed rule cited as removed is fine
                at = r["text"].find(rid)
                items.append({"kind": "dangling", "ids": [rid, r["id"]],
                              "reason": f"{r['id']} cites {rid}, which no rule defines: {_snip(r['text'], at, 50)}"})
                defined.add(rid)                # report each missing id once
    counts = Counter(it["kind"] for it in items)
    return {"items": items, "counts": dict(counts), "n_rules": len(rules), "dead": sorted(dead, key=_num),
            "partial": sorted(partial, key=_num), "prefix": prefix}


ORDER = {"still-cited": 0, "contradiction": 1, "dangling": 2, "duplicate": 3, "id-collision": 4}


def render(r, top: int = 30) -> str:
    out = [f"rule-conflict (read-only) - {r['n_rules']} rules, prefix {r['prefix']}, "
           f"{len(r['dead'])} dead ({', '.join(r['dead'][:12])}{' ...' if len(r['dead']) > 12 else ''}), "
           f"{len(r['partial'])} partly superseded",
           "counts: " + (", ".join(f"{k}={v}" for k, v in sorted(r["counts"].items())) or "none - the rules agree")]
    for it in sorted(r["items"], key=lambda it: ORDER[it["kind"]])[:top]:
        out.append(f"  [{it['kind']}] {' / '.join(it['ids'])}: {it['reason']}")
    if len(r["items"]) > top:
        out.append(f"  ... {len(r['items']) - top} more (raise --top)")
    return "\n".join(out)


def _selftest() -> bool:
    import random
    import tempfile
    rng = random.Random("rule_conflict/selftest")
    filler = " ".join(rng.choice(["ledger", "report", "branch", "cache", "panel"]) for _ in range(3))
    planted = "\n".join([
        "| id | decision | status |", "|---|---|---|",
        "| D1 | Never use the Kraken trading API for scripted price pulls | FIXED |",
        "| D2 | Reports lead with the result and list open items in full | FIXED |",
        "| D3 | Use Python 3.12 for every project venv | SUPERSEDED by D4 |",
        "| D4 | Use Python 3.13 for every project venv | FIXED |",
        "| D5 | Per D3, the nightly job builds its venv first | FIXED |",
        "| D6 | Reports lead with the result and list the open items in full | FIXED |",
        "| D7 | Always use the Kraken trading API for scripted price pulls on weekends | FIXED |",
        "| D8 | Follow D99 for the pen order " + filler + " | FIXED |",
        "| D9 | Supersedes D2's wording: reports may skip the preamble entirely | FIXED |",
    ])
    clean = "\n".join(["- R1: Never push to main without the checks passing",
                       "- R2: Always archive-tag a branch before deleting it",
                       "- R3: Write the decision log after R1 and R2 are satisfied"])
    ok = {}
    res = analyse(parse_text(planted, "planted.md"))
    kinds = Counter(it["kind"] for it in res["items"])
    ok["superseded D3 still invoked by later D5 is flagged"] = any(
        it["kind"] == "still-cited" and it["ids"][:2] == ["D3", "D5"] for it in res["items"])
    ok["the killing rule D4 is not itself reported as still citing D3"] = not any(
        it["kind"] == "still-cited" and "D4" in it["ids"][1:2] for it in res["items"])
    ok["never vs always on the Kraken API (D1/D7) is a contradiction"] = any(
        it["kind"] == "contradiction" and set(it["ids"]) == {"D1", "D7"} for it in res["items"])
    ok["near-identical D2/D6 flagged as duplicate"] = any(
        it["kind"] == "duplicate" and set(it["ids"]) == {"D2", "D6"} for it in res["items"])
    ok["D99 is dangling; partial supersede of D2 does not kill it"] = (
        any(it["kind"] == "dangling" and it["ids"][0] == "D99" for it in res["items"])
        and "D2" in res["partial"] and "D2" not in res["dead"])
    rc = analyse(parse_text(clean, "clean.md"))
    ok["a consistent rule set reports nothing"] = rc["items"] == []
    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "a.md", Path(td) / "b.md"
        a.write_text(planted, encoding="utf-8")
        b.write_text("| D1 | Duplicate id row for the collision check here | FIXED |", encoding="utf-8")
        before = (a.read_bytes(), b.read_bytes())
        rf = analyse(load([td]))
        ok["folder input finds the cross-file id collision and leaves files untouched"] = (
            any(it["kind"] == "id-collision" and it["ids"] == ["D1"] for it in rf["items"])
            and before == (a.read_bytes(), b.read_bytes()))
        empty = Path(td) / "empty.md"
        empty.write_text("just prose, no rule rows\n", encoding="utf-8")
        try:
            load([empty])
            ok["planted bad input (file with no rule rows) is rejected"] = False
        except ValueError:
            ok["planted bad input (file with no rule rows) is rejected"] = True
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    print(f"  planted: {dict(kinds)}; dead={res['dead']} partial={res['partial']}")
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    opts = {"--top": 30, "--dup": 0.8, "--jac": 0.12, "--shared": 4, "--common": 0.15}
    paths, i = [], 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = type(opts[argv[i]])(argv[i + 1])
            i += 2
        else:
            paths.append(argv[i])
            i += 1
    r = analyse(load(paths), dup=opts["--dup"], min_shared=opts["--shared"], min_jac=opts["--jac"],
                common_frac=opts["--common"])
    print(render(r, top=opts["--top"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
