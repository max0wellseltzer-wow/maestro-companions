"""stop_hook_open_asks - a Claude Code Stop hook that refuses to let a turn end while an ask is open and unblocked
(backs finish-everything, candidate #58).

Reads one or more ask ledgers and blocks the stop (exit 2, reason on stderr - Claude reads it and keeps working)
when any ask is NOT DONE and names no blocker. Ledger formats:

  JSON (finish_check's ledger, extended):
      {"asks": ["...", ...], "ledger": {"<ask>": "<evidence>"}, "blockers": {"<ask>": "pen held by max-a1"}}
      (without "asks", the asks are the keys of ledger + blockers)
  Markdown: any table whose header has an "ask" column and a "status" column (optional "blocker" / "blocked on"
      column). A row is DONE when its status starts with DONE; it is BLOCKED when the blocker cell is non-empty or
      the status names a blocker (pen, check running, the user, waiting, BLOCKED).

Loop safety: the hook remembers, per session, how many times in a row it blocked with the SAME open list. A changed
list (progress) resets the count; after --max-blocks unchanged blocks (default 3) it lets the stop through with a
note, so it can never trap a session that is truly stuck.

    python stop_hook_open_asks.py --ledger <file-or-glob> [--ledger ...] [--max-blocks 3] [--state-dir DIR] < event.json
    python stop_hook_open_asks.py --list --ledger <file>       # print the open asks, exit 1 if any
    python stop_hook_open_asks.py --selftest
Exit: 0 allow stop, 2 block (open asks), 1 with --list when something is open. A missing or unreadable ledger never
blocks (exit 0 with a note): a broken hook must not wedge every turn. Stdlib only, reads only (plus its state file).
"""
from __future__ import annotations

import glob
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

BLOCKER_WORDS = re.compile(r"\b(blocked|pen\b|check running|running|waits? on|waiting|max('s)? (call|decision|answer)|"
                           r"needs[_ ]max|only max|pending max)", re.I)


def _cells(line: str) -> list:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return []
    return [c.strip() for c in s[1:-1].split("|")]


def asks_from_markdown(text: str) -> list:
    """[(ask, status, blocker)] from every table with ask + status columns."""
    out, header = [], None
    for line in text.splitlines():
        cells = _cells(line)
        if not cells:
            header = None
            continue
        if header is None:
            low = [c.lower() for c in cells]
            if any("ask" in c for c in low) and any("status" in c for c in low):
                header = low
            continue
        if all(re.fullmatch(r":?-{2,}:?", c or "--") for c in cells):
            continue
        row = dict(zip(header, cells))
        ask = next((v for k, v in row.items() if "ask" in k), "")
        status = next((v for k, v in row.items() if "status" in k), "")
        blocker = next((v for k, v in row.items() if "block" in k), "")
        if ask:
            out.append((ask, status, blocker))
    return out


def _key(s) -> str:
    """Ledger keys and asks meet on the same normalised form finish_check uses: whitespace collapsed, trailing
    punctuation dropped, casefolded (a key without the sentence's period still finds its ask)."""
    return " ".join(str(s).split()).rstrip(" .!?;:,").casefold()


def asks_from_json(data: dict) -> list:
    raw_ledger = data.get("ledger", {}) or {}
    raw_blockers = data.get("blockers", {}) or {}
    ledger = {_key(k): v for k, v in raw_ledger.items()}
    blockers = {_key(k): v for k, v in raw_blockers.items()}
    asks = data.get("asks")
    if not asks:
        first = {}
        for k in list(raw_ledger) + list(raw_blockers):
            first.setdefault(_key(k), k)
        asks = list(first.values())
    out = []
    for a in asks:
        ev = str(ledger.get(_key(a), "") or "").strip()
        out.append((a, "DONE " + ev if ev else "NOT DONE", str(blockers.get(_key(a), "") or "").strip()))
    return out


def open_asks(paths: list) -> tuple:
    """(open_unblocked, blocked, notes)."""
    rows, notes = [], []
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            notes.append(f"unreadable ledger {p}: {e}")
            continue
        if p.lower().endswith(".json"):
            try:
                rows += asks_from_json(json.loads(text))
            except (ValueError, AttributeError) as e:
                notes.append(f"bad JSON ledger {p}: {e}")
        else:
            rows += asks_from_markdown(text)
    open_, blocked = [], []
    for ask, status, blocker in rows:
        if status.strip().upper().startswith("DONE"):
            continue
        if blocker or BLOCKER_WORDS.search(status):
            blocked.append((ask, blocker or status))
        else:
            open_.append(ask)
    return open_, blocked, notes


def _expand(specs: list) -> list:
    out = []
    for s in specs:
        hits = sorted(glob.glob(s))
        out += hits if hits else [s]
    return out


def decide(event: dict, ledgers: list, state_dir: Path, max_blocks: int = 3) -> tuple:
    """(exit_code, message)."""
    open_, blocked, notes = open_asks(_expand(ledgers))
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(event.get("session_id", "nosession")))[:80]
    state = state_dir / f"open_asks_stop_{sid}.json"
    if not open_:
        try:
            state.unlink()
        except OSError:
            pass
        return 0, "; ".join(notes)
    h = hashlib.sha256("\n".join(open_).encode("utf-8")).hexdigest()
    try:
        st = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    count = st.get("count", 0) + 1 if st.get("hash") == h else 1
    if count > max_blocks:
        return 0, (f"open asks unchanged after {max_blocks} blocks - letting the stop through; report them as "
                   f"NOT DONE with the reason: " + "; ".join(open_))
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"hash": h, "count": count}), encoding="utf-8")
    except OSError:
        pass
    lines = [f"{len(open_)} ask(s) NOT DONE with no named blocker (finish-everything). Keep working, or write the "
             f"blocker (pen, check running, the user's decision) into the ledger:"]
    lines += [f"  {i}. {a}" for i, a in enumerate(open_, 1)]
    if blocked:
        lines.append(f"({len(blocked)} more are blocked and may wait: " + "; ".join(f"{a} [{b}]" for a, b in blocked) + ")")
    return 2, "\n".join(lines)


def _selftest() -> bool:
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        md = t / "SESSION_LEDGER_x.md"
        md.write_text("# ledger\n\n| # | ask | status | blocker |\n|---|---|---|---|\n"
                      "| 1 | land W3 | DONE root 7005b5b | |\n| 2 | write E77 | NOT DONE | |\n"
                      "| 3 | delete branches | OPEN | the user's decision (D153) |\n| 4 | rerun check | waiting on check running | |\n",
                      encoding="utf-8")
        o, b, _ = open_asks([str(md)])
        ok["markdown: only the unblocked NOT DONE row is open"] = o == ["write E77"]
        ok["markdown: blocker column and blocker words both count as blocked"] = len(b) == 2
        js = t / "asks.json"
        js.write_text(json.dumps({"asks": ["a", "b", "c"], "ledger": {"a": "sha 1f55eb6"},
                                  "blockers": {"c": "pen held by max-a1"}}), encoding="utf-8")
        o, b, _ = open_asks([str(js)])
        ok["json: evidence -> done, blocker -> blocked, else open"] = o == ["b"] and [x[0] for x in b] == ["c"]
        js2 = t / "asks2.json"
        js2.write_text(json.dumps({"asks": ["Sync it to the repo.", "Tell me why?"],
                                   "ledger": {"sync it to the repo": "pushed e94a307"},
                                   "blockers": {"TELL ME WHY": "the user's answer"}}), encoding="utf-8")
        o, b, _ = open_asks([str(js2)])
        ok["json: keys without the trailing period or in other case still meet their asks (survey 2026-10-24)"] = (
            o == [] and [x[0] for x in b] == ["Tell me why?"])
        sd = t / "state"
        ev = {"session_id": "s1", "stop_hook_active": False}
        code, msg = decide(ev, [str(t / "SESSION_LEDGER_*.md")], sd, 2)
        ok["glob ledger + open ask -> exit 2 naming the ask"] = code == 2 and "write E77" in msg
        code2, _ = decide(ev, [str(md)], sd, 2)
        code3, msg3 = decide(ev, [str(md)], sd, 2)
        ok["loop cap: unchanged list lets the stop through after max blocks"] = code2 == 2 and code3 == 0 and "unchanged" in msg3
        md.write_text(md.read_text(encoding="utf-8").replace("| 2 | write E77 | NOT DONE | |",
                                                             "| 2 | write E77 | NOT DONE | |\n| 5 | push | NOT DONE | |"),
                      encoding="utf-8")
        code4, _ = decide(ev, [str(md)], sd, 2)
        ok["progress (changed list) resets the cap -> blocks again"] = code4 == 2
        done = t / "done.md"
        done.write_text("| ask | status |\n|---|---|\n| x | DONE a1b2c3 |\n", encoding="utf-8")
        code5, _ = decide(ev, [str(done)], sd, 2)
        ok["benign: everything DONE -> exit 0"] = code5 == 0
        code6, msg6 = decide(ev, [str(t / "missing.md")], sd, 2)
        ok["missing ledger never blocks"] = code6 == 0 and "unreadable" in msg6
        code7, _ = decide(ev, [str(t / "SESSION_LEDGER_x.md")], sd, 2)  # end-to-end through main below
        r = _run_main(["--ledger", str(done), "--state-dir", str(sd)], {"session_id": "s2"})
        r2 = _run_main(["--ledger", str(t / "SESSION_LEDGER_x.md"), "--state-dir", str(sd)], {"session_id": "s3"})
        ok["main: benign event exits 0, violating event exits 2"] = r == 0 and r2 == 2 and code7 in (0, 2)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def _run_main(argv: list, event: dict) -> int:
    import io
    old_in, old_err = sys.stdin, sys.stderr
    sys.stdin, sys.stderr = io.StringIO(json.dumps(event)), io.StringIO()
    try:
        return main(argv)
    finally:
        sys.stdin, sys.stderr = old_in, old_err


def main(argv: list) -> int:
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1
    ledgers, max_blocks, state_dir, listing = [], 3, Path(tempfile.gettempdir()), False
    it = iter(argv)
    for a in it:
        if a == "--ledger":
            ledgers.append(next(it, ""))
        elif a == "--max-blocks":
            max_blocks = int(next(it, "3"))
        elif a == "--state-dir":
            state_dir = Path(next(it, "."))
        elif a == "--list":
            listing = True
        else:
            print(f"unknown argument {a}", file=sys.stderr)
            return 0 if not listing else 2
    if listing:
        o, b, notes = open_asks(_expand(ledgers))
        for a in o:
            print(f"OPEN     {a}")
        for a, why in b:
            print(f"BLOCKED  {a}  [{why}]")
        for n in notes:
            print(f"NOTE     {n}")
        return 1 if o else 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        event = {}
    if not ledgers:
        return 0
    code, msg = decide(event, ledgers, state_dir, max_blocks)
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
