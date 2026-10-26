"""resurrect - which DEAD lanes have gone STALE and deserve a re-judge? (backs the lane-resurrection skill; the
reverse of dead-lane-check).

dead-lane-check's reader (lane_verdict.py) gives every lane whose STANDING verdict is DEAD, with its source line.
For each, this reads what the verdict DEPENDED ON from that line:
    data end    "through/to/until/ending <date>" in the line, else the verdict's own date (marked assumed)
    sample      n=..., "<N> trades/bars/stocks/events/obs/days", underpowered / power <x>
    null/test   named nulls and tests (per_stock_scatter, random_timing, permutation, bootstrap, t-test, ...)
    bug         erratum ids (E77) and the word bug
and compares it with what has CHANGED since:
    newer data      {lane words: "YYYY-MM-DD"} and/or the newest file date under --data-dir whose name carries a lane word
    flawed nulls    names you pass, plus null-shaped PER_ITEM_DRAW functions that self-attacking-referee's
                    null_audit_sweep.find() lists in --null-code (the per-stock shape that failed on clusters, E77/E81)
    fixed errata    ids you pass, plus ids on lines saying fixed/landed/closed/resolved in --errata files
Verdict per lane: STILL DEAD, or RE-JUDGE with the changed input and the reproduce-before-rejudge step to run FIRST.

    python resurrect.py --record <file-or-dir> [--record ...] [--lane "words"]... [--data "lane words=YYYY-MM-DD"]...
                        [--data-dir DIR] [--flawed-null NAME]... [--null-code DIR] [--fixed-erratum E77]...
                        [--errata FILE] [--json]
    python resurrect.py --selftest
Exit 0 nothing to re-judge, 1 at least one RE-JUDGE, 2 bad args. Reads only. Stdlib + sibling imports.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "dead-lane-check"))
import lane_verdict as lv  # noqa: E402

try:
    sys.path.insert(0, str(SK / "self-attacking-referee" / "scripts"))
    import null_audit_sweep as nas  # noqa: E402
except ImportError:          # the null sweep is optional: --flawed-null still works without it
    nas = None

END_RX = re.compile(r"\b(?:through|thru|to|until|ending|end(?:ing)? (?:at|on)?|data end)\s*:?\s*(20\d\d-\d\d-\d\d)", re.I)
N_RX = re.compile(r"\b[nN]\s*=\s*([\d,]+)|\b([\d,]{2,})\s+(trades|bars|stocks|events|obs|observations|samples|days|"
                  r"coins|weeks|months)\b", re.I)
POWER_RX = re.compile(r"\b(underpowered|low power|power\s*[=:]?\s*0?\.\d+)", re.I)
NULL_RX = re.compile(r"\b(\w*_null\w*|null_\w+|per[-_ ]stock\w*|random_timing|date[-_ ]blocked|matched[-_ ]null|"
                     r"permutation|shuffle|bootstrap|placebo|t-test|block[-_ ]bootstrap)\b", re.I)
BUG_RX = re.compile(r"\b(E\d{2,3})\b|\b(bug)\b")
FIXED_RX = re.compile(r"\b(fixed|landed|closed|resolved)\b", re.I)
STOP = {"the", "and", "for", "with", "from", "lane", "daily", "max", "same", "question", "on"}
GENERIC = {"description", "test", "text", "evidence", "verdict", "failed", "done", "detector", "result", "results",
           "note", "notes", "status", "why", "lesson", "proof", "idea", "verdicts"}


def _norm(s: str) -> str:
    return re.sub(r"[-_ ]+", "_", s.lower())


def _iso(s: str) -> dt.date:
    try:
        return dt.date.fromisoformat(s.strip())
    except ValueError:
        raise ValueError(f"bad date {s!r}: want YYYY-MM-DD") from None


def discover(records: list) -> list:
    """Candidate lane names from DEAD-verdict lines: a table row's first cell, or the text before ': ' / ' - '."""
    seen, out = set(), []
    for f in lv._files(records):
        if f.suffix.lower() != ".md":                  # receipts' json/txt rows are tickers and fields, not lanes
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if lv._kind(line) != "DEAD" or s.startswith("#") or "---" in s or re.match(r"[a-z_]+:", s):
                continue                               # headings, table rules, YAML keys
            if s.startswith("|"):
                name = s.strip("|").split("|")[0]
            else:
                m = re.match(r"[-*\s\d.]*([^:]{3,60}?)(?:: | - | -- )", s)
                name = m.group(1) if m else ""
            words = re.findall(r"[A-Za-z][A-Za-z0-9]+", name)[:6]
            low = {w.lower() for w in words}
            if not words or low <= STOP or (len(words) == 1 and low <= GENERIC):
                continue
            key = " ".join(words).lower()
            if key not in seen:
                seen.add(key)
                out.append(" ".join(words))
    return out


def _line(src: str) -> str:
    path, _, no = src.rpartition(":")
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[int(no) - 1]
    except (OSError, ValueError, IndexError):
        return ""


def depends(text: str, verdict_date: str) -> dict:
    m = END_RX.search(text)
    ns = [int((a or b).replace(",", "")) for a, b, _ in N_RX.findall(text)]
    return {"data_end": m.group(1) if m else verdict_date, "data_end_assumed": not m,
            "n": max(ns) if ns else None, "power": [p for p in POWER_RX.findall(text)],
            "nulls": sorted({x for x in NULL_RX.findall(text)}) or
                     (["unnamed (p-value given; read its receipt for the null)"] if re.search(r"\bp\s*[=<]?\s*0?\.\d", text) else []),
            "bugs": sorted({a or b for a, b in BUG_RX.findall(text)})}


def _stems(lane: str) -> list:
    return [w.lower()[:5] for w in re.findall(r"[A-Za-z0-9]+", lane) if len(w) > 2 and w.lower() not in STOP]


def newest_data(lane: str, data: dict, data_dir=None):
    stems, best = _stems(lane), None
    for k, v in (data or {}).items():
        ks = _stems(k)
        if k == "*" or (ks and all(s in stems for s in ks)):
            d = _iso(v)
            best = max(best, (d, f"--data {k}={v}")) if best else (d, f"--data {k}={v}")
    if data_dir:
        for p in Path(data_dir).rglob("*"):
            if p.is_file() and any(s in p.name.lower() for s in stems if len(s) >= 3):
                d = dt.date.fromtimestamp(p.stat().st_mtime)
                if not best or d > best[0]:
                    best = (d, f"file {p}")
    return best


def flawed_from_code(code_dir) -> set:
    if nas is None or not code_dir:
        return set()
    return {name.rsplit(":", 1)[1] for name, _, _, shape in nas.find(Path(code_dir)) if shape == "PER_ITEM_DRAW"}


def fixed_from_files(paths) -> set:
    out = set()
    for f in lv._files(list(paths or [])):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if FIXED_RX.search(line):
                out |= set(re.findall(r"\bE\d{2,3}\b", line))
    return out


def judge(records: list, lanes=None, data=None, data_dir=None, flawed_nulls=(), fixed_errata=(), year=2026) -> list:
    flawed = {_norm(x) for x in flawed_nulls if x.strip()}
    fixed = {x.strip().upper() for x in fixed_errata if x.strip()}
    rows = []
    for lane in (lanes or discover(records)):
        r = lv.lookup(lane, records, year)
        s = r["standing"]
        if not s or s["kind"] != "DEAD":
            continue
        text = _line(s["src"]) or s["text"]
        dep = depends(text, s["date"])
        changes = []
        nd = newest_data(lane, data, data_dir)
        if nd and nd[0] > _iso(dep["data_end"]):
            changes.append(f"newer data to {nd[0]} ({nd[1]}) - verdict used data through {dep['data_end']}"
                           + (" (assumed = verdict date)" if dep["data_end_assumed"] else ""))
        low = _norm(text)
        bad = sorted(n for n in flawed if n in low)
        if bad:
            changes.append(f"null flagged flawed by null_audit_sweep: {', '.join(bad)}")
        fx = sorted(b for b in dep["bugs"] if b.upper() in fixed)
        if fx:
            changes.append(f"erratum fixed since: {', '.join(fx)}")
        step = None
        if changes:
            step = (f"FIRST reproduce the DEAD result like-for-like (reproduce-before-rejudge: rerun the original method on "
                    f"data through {dep['data_end']}" + (f" with {', '.join(dep['nulls'])}" if dep["nulls"] else "")
                    + "; expect its saved numbers within tolerance), THEN change only: " + changes[0].split(" (")[0])
        rows.append({"lane": lane, "verdict": "RE-JUDGE" if changes else "STILL DEAD", "src": s["src"],
                     "date": s["date"], "text": re.sub(r"\s+", " ", text).strip()[:200], "depends": dep,
                     "changes": changes, "step": step})
    return rows


def _selftest() -> bool:
    import contextlib
    import io
    import os
    import tempfile
    import time
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        g = t / "GRAVEYARD.md"
        g.write_text(
            "| idea | verdict | evidence |\n|---|---|---|\n"
            "| RSI dip on LTC | REFUTED | 2,472 bars through 2026-09-30, p 0.695 |\n"
            "| volume spike stocks | no edge | 45,096 trades, per_stock_scatter null, p 0.080 (2026-10-10) |\n"
            "| gap fade | dead | killed by E77 bug in the scan (2026-10-11) |\n"
            "| calendar effect | dead | 300 days, power 0.31 (2026-10-05) |\n"
            "- trend following: replicates on crypto (2026-10-13)\n", encoding="utf-8")
        rec = [str(g)]
        lanes = discover(rec)
        ok["discover finds the 4 DEAD lanes from table rows, not the ALIVE trend lane"] = (
            len(lanes) == 4 and not any("trend" in x.lower() for x in lanes))
        rows = {r["lane"]: r for r in judge(rec, data={"LTC": "2026-10-14"})}
        rsi = rows["RSI dip on LTC"]
        ok["newer LTC data than the verdict's 'through 2026-09-30' -> RE-JUDGE, reproduce step first"] = (
            rsi["verdict"] == "RE-JUDGE" and rsi["depends"]["data_end"] == "2026-09-30"
            and rsi["depends"]["n"] == 2472 and rsi["step"].startswith("FIRST reproduce"))
        ok["no change named -> the other lanes stay STILL DEAD"] = all(
            rows[k]["verdict"] == "STILL DEAD" for k in ("volume spike stocks", "gap fade", "calendar effect"))
        old = {r["lane"]: r for r in judge(rec, data={"LTC": "2026-09-01"})}
        ok["data no newer than the verdict -> STILL DEAD"] = old["RSI dip on LTC"]["verdict"] == "STILL DEAD"
        r2 = {r["lane"]: r for r in judge(rec, flawed_nulls=["per-stock-scatter"], fixed_errata=["E77"])}
        ok["flawed null named in the verdict -> RE-JUDGE (names normalised)"] = (
            r2["volume spike stocks"]["verdict"] == "RE-JUDGE" and "null" in r2["volume spike stocks"]["changes"][0])
        ok["fixed erratum E77 -> RE-JUDGE; a low-power lane has its power read but stays dead"] = (
            r2["gap fade"]["verdict"] == "RE-JUDGE" and r2["calendar effect"]["verdict"] == "STILL DEAD"
            and r2["calendar effect"]["depends"]["power"] == ["power 0.31"])
        dd = t / "data"
        dd.mkdir()
        f = dd / "calendar_daily.csv"
        f.write_text("x\n", encoding="utf-8")
        ts = time.mktime((2026, 10, 15, 12, 0, 0, 0, 0, -1))
        os.utime(f, (ts, ts))
        r3 = {r["lane"]: r for r in judge(rec, data_dir=str(dd))}
        ok["--data-dir file date newer than the assumed data end -> RE-JUDGE"] = (
            r3["calendar effect"]["verdict"] == "RE-JUDGE" and r3["calendar effect"]["depends"]["data_end_assumed"])
        code = t / "code"
        code.mkdir()
        (code / "nulls.py").write_text("def random_timing(per, reps, rng):\n    out = []\n    for s in per:\n"
                                       "        out.append(rng.sample(s, 2))\n    return out\n", encoding="utf-8")
        (t / "ERRATA.md").write_text("- E77 per-stock null: FIXED 2026-10-15\n- E90 open\n", encoding="utf-8")
        ok["null_audit_sweep.find flags a PER_ITEM_DRAW null; errata file gives fixed ids"] = (
            (nas is None or "random_timing" in flawed_from_code(code)) and fixed_from_files([t / "ERRATA.md"]) == {"E77"})
        try:
            judge(rec, data={"LTC": "last tuesday"})
            ok["planted bad input (malformed data date) is refused"] = False
        except ValueError:
            ok["planted bad input (malformed data date) is refused"] = True
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            codes = (main(["--record", str(g), "--data", "LTC=2026-10-14"]), main(["--record", str(g)]),
                     main(["--bogus"]))
        ok["main exit codes 1 re-judge / 0 all still dead / 2 bad args"] = codes == (1, 0, 2)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    rec, lanes, data, nulls, errata, efiles = [], [], {}, [], [], []
    data_dir = code_dir = None
    as_json = False
    it = iter(argv)
    try:
        for a in it:
            if a == "--record":
                rec.append(next(it))
            elif a == "--lane":
                lanes.append(next(it))
            elif a == "--data":
                k, _, v = next(it).rpartition("=")
                data[k] = v
            elif a == "--data-dir":
                data_dir = next(it)
            elif a == "--flawed-null":
                nulls.append(next(it))
            elif a == "--null-code":
                code_dir = next(it)
            elif a == "--fixed-erratum":
                errata.append(next(it))
            elif a == "--errata":
                efiles.append(next(it))
            elif a == "--json":
                as_json = True
            else:
                raise ValueError(f"unknown argument {a}")
        if not rec:
            raise ValueError("give at least one --record")
        nulls += sorted(flawed_from_code(code_dir))
        errata += sorted(fixed_from_files(efiles))
        rows = judge(rec, lanes, data, data_dir, nulls, errata)
    except (ValueError, StopIteration) as e:
        print(f"bad args: {e or 'missing value'}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(rows, indent=1))
    else:
        print(f"checked {len(rows)} DEAD lane(s); flawed nulls: {', '.join(nulls) or 'none given'}; "
              f"fixed errata: {', '.join(errata) or 'none given'}")
        for r in rows:
            d = r["depends"]
            print(f"{r['verdict']:<10} {r['lane']}  (DEAD {r['date']} <- {r['src']})")
            print(f"           depended on: data through {d['data_end']}{' (assumed)' if d['data_end_assumed'] else ''}"
                  f", n {d['n']}, power {d['power'] or '-'}, nulls {d['nulls'] or '-'}, bugs {d['bugs'] or '-'}")
            for c in r["changes"]:
                print(f"           changed: {c}")
            if r["step"]:
                print(f"           step: {r['step']}")
    return 1 if any(r["verdict"] == "RE-JUDGE" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
