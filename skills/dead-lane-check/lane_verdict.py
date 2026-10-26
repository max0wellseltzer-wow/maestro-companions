"""lane_verdict - before spending on a trading idea, look the lane up in the verdict record and print its standing
verdict with sources (backs the dead-lane-check skill, candidate #63).

Searches the record files and folders you give (memory notes, receipts/, GRAVEYARD.md, kill logs, DECISIONS.md,
PREREG files) for lines that mention the lane (every query word, matched on its first 5 letters, so "predict"
finds "prediction") AND carry a verdict word:
  DEAD   refuted, falsified, killed, cost-killed, dead, no edge, NO_PREMIUM, failed, rejected
  OPEN   untested, underpowered, unresolvable, not dead, inconclusive, open
  ALIVE  replicates, survives, passes, calibrated, real edge, premium
Each hit is dated (a YYYY-MM-DD or "10-07"-style date in the line, else the file's date). The STANDING verdict is
the newest hit; on the same date a line saying CORRECTED / SUPERSEDED wins. Every hit is printed so a reader can
overrule the tool.

    python lane_verdict.py "<lane words>" --record <file-or-dir> [--record ...] [--year 2026] [--different "<what is new>"] [--json]
    python lane_verdict.py --selftest
Exit 0 lane not dead (or a --different reason given), 3 standing verdict DEAD and nothing named as different,
1 no verdict found (look by hand before assuming it is new), 2 bad args. Reads only. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

KINDS = [
    ("OPEN", re.compile(r"\b(untested|underpowered|unresolvable|not dead|inconclusive|not yet tested)\b", re.I)),
    ("DEAD", re.compile(r"\b(refuted|falsified|cost[- ]killed|killed|dead|no edge|no_premium|no premium|failed|"
                        r"rejected)\b", re.I)),
    ("ALIVE", re.compile(r"\b(replicates?|survives?|passes|calibrated|real edge|premium)\b", re.I)),
]
OVERRIDE = re.compile(r"\b(CORRECTED|SUPERSEDED|REVISED|re-?labell?ed)\b", re.I)
FULL_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
SHORT_DATE = re.compile(r"(?<![\d-])(1[0-2]|0[1-9])-([0-3]\d)(?![\d-])")
TEXT_EXT = {".md", ".txt", ".json", ".jsonl", ".csv"}


def _files(paths: list) -> list:
    out = []
    for s in paths:
        p = Path(s)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += [q for q in sorted(p.rglob("*")) if q.is_file() and q.suffix.lower() in TEXT_EXT
                    and not any(x.startswith(".") for x in q.relative_to(p).parts)]
    return out


def _date(line: str, fallback: dt.date, year: int) -> dt.date:
    dates = []
    for m in FULL_DATE.finditer(line):
        try:
            dates.append(dt.date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    if not dates:
        for m in SHORT_DATE.finditer(line):
            try:
                dates.append(dt.date(year, int(m[1]), int(m[2])))
            except ValueError:
                pass
    return max(dates) if dates else fallback


def _kind(line: str) -> str | None:
    for k, rx in KINDS:          # OPEN first: "UNTESTED, NOT DEAD" must not read as DEAD
        if rx.search(line):
            return k
    return None


def lookup(query: str, records: list, year: int = 2026) -> dict:
    stems = [w.lower()[:5] for w in re.findall(r"[A-Za-z0-9]+", query) if len(w) > 1]
    if not stems:
        raise ValueError("empty lane query")
    hits = []
    for f in _files(records):
        fallback = dt.date.fromtimestamp(f.stat().st_mtime)
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            low = line.lower()
            if not all(s in low for s in stems):
                continue
            k = _kind(line)
            if k:
                hits.append({"kind": k, "date": _date(line, fallback, year).isoformat(), "override": bool(OVERRIDE.search(line)),
                             "src": f"{f}:{i}", "text": re.sub(r"\s+", " ", line).strip()[:240]})
    hits.sort(key=lambda h: (h["date"], h["override"]), reverse=True)
    return {"lane": query, "standing": hits[0] if hits else None, "hits": hits}


def decide(r: dict, different: str = "") -> int:
    if r["standing"] is None:
        return 1
    if r["standing"]["kind"] == "DEAD" and not different.strip():
        return 3
    return 0


def _selftest() -> bool:
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        mem = t / "memory"
        mem.mkdir()
        (mem / "strategy-state.md").write_text(
            "- 2026-10-05: coin prediction lane DEAD after 12 experiments\n"
            "- PREDICTION IS UNTESTED, NOT DEAD (CORRECTED 2026-10-07 by the power relabel)\n"
            "- trend following on crypto: replicates (10-13)\n"
            "- trend premium on LTC: NO_PREMIUM at 0.80%/side (2026-10-10)\n", encoding="utf-8")
        (t / "GRAVEYARD.md").write_text("short-term reversal: cost-killed 10-13\n", encoding="utf-8")
        (t / "receipts").mkdir()
        (t / "receipts" / ".hidden").mkdir()
        (t / "receipts" / ".hidden" / "x.md").write_text("reversal replicates 2026-10-20\n", encoding="utf-8")
        r = lookup("coin prediction", [str(mem)])
        ok["every query word must appear: 'coin prediction' finds only the 10-05 DEAD line"] = \
            r["standing"]["kind"] == "DEAD" and len(r["hits"]) == 1
        r2 = lookup("predictions", [str(mem)])
        ok["newest line wins: prediction is OPEN (corrected 10-07), not DEAD (10-05)"] = len(r2["hits"]) == 2 and \
            r2["standing"]["date"] == "2026-10-07" and r2["standing"]["kind"] == "OPEN"
        r3 = lookup("reversal", [str(t / "GRAVEYARD.md"), str(t / "receipts")])
        ok["cost-killed reversal -> DEAD, exit 3 unless something new is named"] = r3["standing"]["kind"] == "DEAD" and \
            decide(r3) == 3 and decide(r3, "intraday bars, not daily") == 0
        ok["hidden folders are not read"] = len(r3["hits"]) == 1
        r4 = lookup("trend", [str(mem)])
        ok["trend: newest is replicates 10-13 -> ALIVE, exit 0"] = r4["standing"]["kind"] == "ALIVE" and decide(r4) == 0
        ok["unknown lane -> no verdict, exit 1"] = decide(lookup("kalshi weather", [str(mem)])) == 1
        (t / "same.md").write_text("momentum: dead 2026-10-09\nmomentum: SUPERSEDED, underpowered 2026-10-09\n",
                                   encoding="utf-8")
        ok["same date: the CORRECTED/SUPERSEDED line wins"] = lookup("momentum", [str(t / "same.md")])["standing"]["kind"] == "OPEN"
        try:
            lookup("  ", [str(mem)])
            ok["empty query refused"] = False
        except ValueError:
            ok["empty query refused"] = True
        ok["a line with two dates takes the later one"] = _date("reviewed 2026-10-07, revisited 2026-10-12", dt.date(2000, 1, 1), 2026) == dt.date(2026, 10, 12)
        ok["main exit codes 3 / 0 / 2"] = main(["reversal", "--record", str(t / "GRAVEYARD.md")]) == 3 and \
            main(["trend", "--record", str(mem)]) == 0 and main(["--bogus"]) == 2
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv: list) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1
    query, records, different, year, as_json = "", [], "", 2026, False
    it = iter(argv)
    for x in it:
        if x == "--record":
            records.append(next(it, ""))
        elif x == "--different":
            different = next(it, "")
        elif x == "--year":
            year = int(next(it, "2026"))
        elif x == "--json":
            as_json = True
        elif x.startswith("--"):
            print(f"unknown argument {x}", file=sys.stderr)
            return 2
        else:
            query = (query + " " + x).strip()
    if not query or not records:
        print("give the lane words and at least one --record", file=sys.stderr)
        return 2
    r = lookup(query, records, year)
    code = decide(r, different)
    if as_json:
        print(json.dumps({**r, "exit": code}, indent=1))
        return code
    s = r["standing"]
    if s is None:
        print(f"lane '{query}': no verdict found in the record - search by hand before treating it as new")
    else:
        print(f"lane '{query}': STANDING {s['kind']} ({s['date']})  <- {s['src']}\n  {s['text']}")
        for h in r["hits"][1:12]:
            print(f"  earlier {h['kind']:<5} {h['date']}  {h['src']}  {h['text'][:120]}")
        if code == 3:
            print("DEAD lane: do not re-run it. Name what is different (--different \"...\") or stop.")
        elif s["kind"] == "DEAD":
            print(f"DEAD lane re-opened because: {different}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
