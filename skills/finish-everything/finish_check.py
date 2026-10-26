"""finish_check - prove every ask in the user's prompt is done before stopping, and flag what wasn't asked
(backs the finish-everything skill).

Asks come from literal-execution's parser (or a list you pass). The ledger maps each ask to evidence - a commit,
a file path, a command output line. The report says DONE / NOT DONE per ask, and lists EXTRA work that maps to no
ask (token-thrift: drop it, or say why it improves the software). Exit 1 while anything is NOT DONE, so it can gate
the final reply. Ledger keys and asks meet on a normalised form (whitespace collapsed, trailing punctuation dropped,
casefolded), so a key typed without the sentence's period still finds its ask.

    from finish_check import finish_report
    finish_report(prompt_or_asks, ledger={"Sync it to the repo.": "pushed e94a307", ...}, extras=["..."])
    python finish_check.py --selftest
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "literal-execution"))
from literal_parse import parse  # noqa: E402


def _key(s) -> str:
    """The form on which ledger keys and asks meet: inner whitespace collapsed, outer whitespace and trailing
    punctuation dropped, casefolded - so the key 'fix the 3 gaps you found' finds the ask 'Fix the 3 gaps you found.'
    (survey 2026-10-24: a sentence prompt became 3 asks, all NOT DONE, because the keys lacked the period)."""
    return " ".join(str(s).split()).rstrip(" .!?;:,").casefold()


def finish_report(prompt_or_asks, ledger: dict, extras=None) -> dict:
    if isinstance(prompt_or_asks, str):
        p = parse(prompt_or_asks)
        asks = p["asks"] + p["questions"]
    else:
        asks = list(prompt_or_asks)
    if not asks:
        raise ValueError("no asks to check")
    by_key = {}
    for k, v in ledger.items():                       # keys are normalised on the way in (the write side) ...
        if str(v or "").strip() or _key(k) not in by_key:
            by_key[_key(k)] = v
    rows = []
    for a in asks:                                    # ... and every ask on lookup, so either spelling matches
        ev = str(by_key.get(_key(a), "") or "").strip()
        rows.append({"ask": a, "status": "DONE" if ev else "NOT DONE", "evidence": ev or None})
    ask_keys = {_key(a) for a in asks}
    unknown = sorted(k for k in ledger if _key(k) not in ask_keys)
    return {"rows": rows, "not_done": [r["ask"] for r in rows if r["status"] == "NOT DONE"],
            "extra": list(extras or []) + unknown, "finished": all(r["status"] == "DONE" for r in rows)}


def _selftest() -> bool:
    ok = {}
    prompt = "Fix the 3 gaps you found. Tell me what inspired the nature skills?"
    asks = parse(prompt)["asks"] + parse(prompt)["questions"]
    ok["asks come from literal-execution's parser (statements and questions)"] = len(asks) == 2
    full = {asks[0]: "selftests strengthened; full mutation audit: all 3 lines killed",
            asks[1]: "timeline from the transcripts, 7 quoted prompts"}
    r = finish_report(prompt, full)
    ok["every ask with evidence -> finished"] = r["finished"] and r["not_done"] == []
    part = finish_report(prompt, {asks[0]: "done"})
    ok["planted missing ask -> NOT DONE, not finished"] = (not part["finished"]) and part["not_done"] == [asks[1]]
    blank = finish_report(prompt, {asks[0]: "  ", asks[1]: "x"})
    ok["empty evidence does not count as done"] = blank["not_done"] == [asks[0]]
    ext = finish_report(prompt, full, extras=["ran 28 coin-prediction tests"])
    ok["unasked work is listed as extra"] = ext["extra"] == ["ran 28 coin-prediction tests"] and ext["finished"]
    loose = finish_report(prompt, {"fix the 3 gaps you found": "mutation audit, 3/3 killed",
                                   asks[1].rstrip("?").upper() + "  ": "timeline, 7 quoted prompts"})
    ok["keys without the trailing period, in other case or spacing, still meet their asks (survey 2026-10-24)"] = (
        loose["finished"] and loose["extra"] == [])
    try:
        finish_report([], {})
        ok["planted bad input (no asks) is rejected"] = False
    except ValueError:
        ok["planted bad input (no asks) is rejected"] = True
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    import json
    data = json.loads(open(argv[0], encoding="utf-8-sig").read())      # {"prompt": ..., "ledger": {...}, "extras": [...]}
    # -sig: PowerShell 5.1's Set-Content -Encoding utf8 writes a BOM, which plain utf-8 json refuses
    r = finish_report(data["prompt"], data.get("ledger", {}), data.get("extras"))
    for row in r["rows"]:
        print(f"{row['status']:<9} {row['ask']}" + (f"  <- {row['evidence']}" if row["evidence"] else ""))
    for e in r["extra"]:
        print(f"EXTRA     {e}")
    return 0 if r["finished"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
