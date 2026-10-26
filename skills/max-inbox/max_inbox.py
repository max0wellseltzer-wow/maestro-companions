"""max_inbox - harvest every item waiting on the user from the workspace's files and the mailbox, deduplicated, numbered
(backs the max-inbox skill, candidate #60).

Scans the files and folders you give (SESSION_LEDGER_*.md, plans/, YOUR_TASKS_*, MAX_ONLY_*, DECISIONS_PROPOSED_*)
plus an issue export (`gh issue view 41 --json body,comments,title > issue41.json`) for lines that put an item on the user:
  NEEDS_MAX / NEEDS: the user / needs the user / waits on the user / the user's call / the user decides / only the user / pending the user /
  OPEN until the user / held pending the user / "for the user to"; and every unchecked "- [ ]" box in a YOUR_TASKS / MAX_ONLY file.
Lines that say the item is closed (answered, the user said, resolved, closed, DONE, ~~struck~~) are dropped (shown with
--all). Near-duplicates (same D/E/GT id, or 60%+ shared words) merge into one item that lists every source.

    python max_inbox.py <file-or-dir> [...] [--issue issue41.json] [--since YYYY-MM-DD] [--skip DIRNAME]... [--all] [--json]
                        [--env-check]   # per item: is each key-shaped variable NAME set (Process/User/Machine)? names only
    python max_inbox.py --selftest
Exit 0 inbox empty, 1 items waiting, 2 bad args. Reads only. Stdlib only. Lines are cut at 220 characters and
key-shaped strings are masked before printing.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

CUE = re.compile(r"NEEDS[_ :-]*MAX|needs max\b|wait(s|ing)? (on|for) max|max'?s (call|decision|answer|choice)|"
                 r"max decides|only max|pending max|open until max|held pending max|for max to|ask max|"
                 r"decisions only max|BLOCKED_ON_MAX|\[MAX\]", re.I)
CLOSED = re.compile(r"\banswered\b|\bmax said\b|\bresolved\b|\bclosed\b|\bDONE\b|~~.+~~|max (chose|approved|answered)",
                    re.I)
BOX = re.compile(r"^\s*[-*] \[ \]\s+(.*)")
TASK_FILE = re.compile(r"YOUR_TASKS|MAX_ONLY|MAX_TODO", re.I)
IDS = re.compile(r"\b(?:D|E|GT|M|V)\d{1,4}\b")
SECRETISH = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
TEXT_EXT = {".md", ".txt"}


def _clean(s: str) -> str:
    return SECRETISH.sub("<masked>", re.sub(r"\s+", " ", s).strip())[:220]


SKIP_DIRS = {"node_modules", "__pycache__", "data", "venv", "cache", "archive", "transcripts"}


def _files(paths: list, since: str = "", skip: set | None = None) -> list:
    """Files given, plus .md/.txt under folders given - pruning dot-folders, SKIP_DIRS and --skip names while
    walking, so a private or huge folder is never opened."""
    import datetime as dt
    import os
    skip = SKIP_DIRS | set(skip or ())
    out = []
    for s in paths:
        p = Path(s)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in skip)
                out += [Path(root) / f for f in sorted(files) if Path(f).suffix.lower() in TEXT_EXT]
    if since:
        out = [q for q in out if dt.date.fromtimestamp(q.stat().st_mtime).isoformat() >= since]
    return out


def harvest_text(text: str, where: str, task_file: bool) -> list:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = BOX.match(line)
        if line.lstrip().startswith("#"):
            continue
        if (task_file and m) or CUE.search(line):
            out.append({"text": _clean(line), "src": f"{where}:{i}", "closed": bool(CLOSED.search(line))})
    return out


def harvest(paths: list, issue: str | None = None, since: str = "") -> list:
    items = []
    for f in _files(paths, since):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        items += harvest_text(text, str(f), bool(TASK_FILE.search(f.name)))
    if issue:
        d = json.loads(Path(issue).read_text(encoding="utf-8"))
        posts = [("body", d.get("body", ""))] + [(c.get("createdAt", f"comment{n}"), c.get("body", ""))
                                                 for n, c in enumerate(d.get("comments", []))]
        for when, body in posts:
            if since and when[:4].isdigit() and when[:10] < since:
                continue
            items += harvest_text(body or "", f"#issue {when}", False)
    return items


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2} - {"max", "needs", "the", "and", "for"}


def dedupe(items: list) -> list:
    groups = []
    for it in items:
        ids, w = set(IDS.findall(it["text"])), _words(it["text"])
        for g in groups:
            j = len(w & g["words"]) / max(1, len(w | g["words"]))
            if (ids and ids & g["ids"]) or j >= 0.6:
                g["srcs"].append(it["src"])
                g["closed"] = g["closed"] or it["closed"]
                break
        else:
            groups.append({"text": it["text"], "srcs": [it["src"]], "ids": ids, "words": w, "closed": it["closed"]})
    return groups


ENV_NAME = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:API_KEY|KEY|TOKEN|SECRET|CONTACT|PASSWORD|ID)\b")


def _reg_names(scope: str) -> set:
    """Environment variable NAMES stored for User or Machine (Windows registry); values are never read."""
    try:
        import winreg
    except ImportError:
        return set()
    hive, sub = ((winreg.HKEY_CURRENT_USER, "Environment") if scope == "User" else
                 (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"))
    names = set()
    try:
        with winreg.OpenKey(hive, sub) as k:
            i = 0
            while True:
                try:
                    names.add(winreg.EnumValue(k, i)[0].upper())
                except OSError:
                    break
                i += 1
    except OSError:
        pass
    return names


def env_status(text: str, scopes: dict | None = None) -> list:
    """For each key-shaped variable NAME the item mentions (ALPHAVANTAGE_API_KEY, HARVEST_CONTACT ...), where it is
    set: Process / User / Machine, or NOT SET. Names only - an item "the user must set X" whose X is already set is
    probably done (2026-10-22: keys were asked for after the user had set them). `scopes` maps scope -> set of names."""
    if scopes is None:
        import os
        scopes = {"Process": {k.upper() for k in os.environ}, "User": _reg_names("User"),
                  "Machine": _reg_names("Machine")}
    out = []
    for name in dict.fromkeys(ENV_NAME.findall(text)):
        where = [s for s, names in scopes.items() if name.upper() in names]
        out.append(f"{name} {'SET(' + ','.join(where) + ')' if where else 'NOT SET'}")
    return out


def inbox(paths: list, issue: str | None = None, show_all: bool = False, since: str = "") -> list:
    g = dedupe(harvest(paths, issue, since))
    return [x for x in g if show_all or not x["closed"]]


def _selftest() -> bool:
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "SESSION_LEDGER_a.md").write_text(
            "- P23 branch deletes: D153 OPEN until the user chooses.\n- task 10 DONE\n"
            "- GT35 test-weakening hook: NEEDS_MAX\n- W2: the user said yes, needs the user no more (answered)\n", encoding="utf-8")
        plans = t / "plans"
        plans.mkdir()
        (plans / "PC_FEED.md").write_text("7. **GT35: test-weakening hook + judges without Bash. NEEDS MAX.**\n"
                                          "running it needs the user's HARVEST_CONTACT string\n", encoding="utf-8")
        (t / "YOUR_TASKS_x.md").write_text("- [ ] rotate the paper key\n- [x] create the repo\n", encoding="utf-8")
        (t / "data").mkdir()
        (t / "data" / "big.md").write_text("NEEDS_MAX inside a skipped folder", encoding="utf-8")
        (t / "notes.md").write_text("- [ ] a box outside a task file is not the user's\n", encoding="utf-8")
        iss = t / "issue41.json"
        key = "PK" + "FAKE0SENTINEL" + "9f3a1c2b7d04e5f6a7b8c9d0"
        iss.write_text(json.dumps({"title": "mailbox", "body": "Anything that needs the user: put NEEDS: the user",
                                   "comments": [{"createdAt": "2026-10-15T01:00:00Z",
                                                 "body": "- M4 (deleting 43 branches) still needs the user. key " + key}]}),
                       encoding="utf-8")
        got = inbox([str(t)], str(iss))
        texts = [g["text"] for g in got]
        ok["GT35 in two files merges into one item with two sources"] = sum("GT35" in x for x in texts) == 1 and \
            len(next(g for g in got if "GT35" in g["text"])["srcs"]) == 2
        ok["closed line (answered / the user said) is dropped"] = not any("W2" in x for x in texts)
        ok["unchecked box in YOUR_TASKS is an item, checked box is not"] = any("rotate the paper key" in x for x in texts) \
            and not any("create the repo" in x for x in texts)
        ok["skipped folder (data) is never read"] = not any("skipped folder" in x for x in texts)
        ok["box outside a task file is not an item"] = not any("outside a task file" in x for x in texts)
        ok["issue comments are harvested with their date"] = any(g["srcs"][0].startswith("#issue 2026-10-15") for g in got)
        ok["key-shaped strings are masked"] = not any(key in x for x in texts) and any("<masked>" in x for x in texts)
        ok["--all shows the closed item"] = any("W2" in g["text"] for g in inbox([str(t)], str(iss), True))
        ok["--since drops older issue comments"] = not any(g["srcs"][0].startswith("#issue 2026") for g in inbox([], str(iss), False, "2026-10-16"))
        ok["the user's call wording is caught"] = any("HARVEST_CONTACT" in x for x in texts)
        ok["main: items -> exit 1, empty dir -> exit 0, bad arg -> 2"] = (
            main([str(t / "YOUR_TASKS_x.md")]) == 1 and main([str(plans / "none")]) == 0 and main(["--bogus"]) == 2)
        sc = {"Process": set(), "User": {"HARVEST_CONTACT"}, "Machine": set()}
        st = env_status("running it needs the user's HARVEST_CONTACT string and an ALPACA_API_KEY", sc)
        ok["--env-check: names found, User scope seen, missing one NOT SET"] = st == ["HARVEST_CONTACT SET(User)",
                                                                                    "ALPACA_API_KEY NOT SET"]
        ok["planted: a plain word in capitals (NEEDS_MAX, DONE) is not taken as a key name"] = \
            env_status("GT35 NEEDS_MAX DONE PLAN_V3", sc) == []
        import contextlib
        import io
        import os
        os.environ["ZZ_SELFTEST_TOKEN"] = "value-that-must-never-print-7f3a"
        (t / "YOUR_TASKS_y.md").write_text("- [ ] set ZZ_SELFTEST_TOKEN for the feed\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main([str(t / "YOUR_TASKS_y.md"), "--env-check"])
        os.environ.pop("ZZ_SELFTEST_TOKEN")
        ok["--env-check prints the name and scope, never the value"] = "ZZ_SELFTEST_TOKEN SET(Process" in \
            buf.getvalue() and "value-that-must-never-print" not in buf.getvalue()
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
    paths, issue, show_all, as_json, since, envc = [], None, False, False, "", False
    it = iter(argv)
    for a in it:
        if a == "--env-check":
            envc = True
        elif a == "--issue":
            issue = next(it, None)
        elif a == "--skip":
            SKIP_DIRS.add(next(it, ""))
        elif a == "--since":
            since = next(it, "")
        elif a == "--all":
            show_all = True
        elif a == "--json":
            as_json = True
        elif a.startswith("--"):
            print(f"unknown argument {a}", file=sys.stderr)
            return 2
        else:
            paths.append(a)
    got = inbox(paths, issue, show_all, since)
    if envc:
        for g in got:
            g["env"] = env_status(g["text"])
    if as_json:
        print(json.dumps([{k: v for k, v in g.items() if k not in ("ids", "words")} for g in got], indent=1))
    else:
        for n, g in enumerate(got, 1):
            more = f" (+{len(g['srcs']) - 1} more)" if len(g["srcs"]) > 1 else ""
            print(f"{n:>3}. {'[closed] ' if g['closed'] else ''}{g['text']}\n       <- {g['srcs'][0]}{more}")
            if g.get("env"):
                print(f"       env: {'; '.join(g['env'])}")
        print(f"{len(got)} item(s) waiting on the user")
    return 1 if got else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
