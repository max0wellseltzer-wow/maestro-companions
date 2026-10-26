"""live_sync.py - bring a LIVE repo (C:\\Autotrade, where scheduled jobs keep appending to chain/log files) up to its
origin after a landing, without losing a byte the jobs wrote meanwhile. Dry run by default.

    python live_sync.py --live <workspace> --files data/forward/screen_picks.jsonl shared/bus.chain.jsonl \
        [--branch main] [--unstage experiments] [--backup DIR] [--go]
    python live_sync.py --selftest

Steps (with --go): back up each job-written file (default backup dir: a fresh timestamped folder in the system temp
dir), `git restore --staged` each --unstage path (a peer's half-staged work must not ride the rebase), then
`git pull --rebase --autostash origin <branch>`, then the size check: each file must still START with its backed-up
bytes (append-only: same or longer). Prints KEPT / GREW / LOST per file and SYNCED or HOLD. Exit 0 SYNCED (or dry
run), 1 HOLD (pull failed, conflict markers, or a file LOST - the backup stays, nothing is deleted), 2 bad arguments.
From session max-24 2026-10-23 (transcript L11991): the same steps were typed as one shell line after a landing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)


def compare(backup: Path, now: Path) -> str:
    """KEPT (identical), GREW (backup is a prefix), LOST (shorter or rewritten), MISSING."""
    if not now.exists():
        return "MISSING"
    a, b = backup.read_bytes(), now.read_bytes()
    if a == b:
        return "KEPT"
    return "GREW" if b.startswith(a) else "LOST"


def sync(live: Path, files: list[str], branch: str, unstage: list[str], backup: Path | None, go: bool) -> int:
    bdir = backup or Path(tempfile.gettempdir()) / f"live_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    print(f"live {live}  branch {branch}  backup {bdir}  {'GO' if go else 'DRY RUN (add --go)'}")
    for f in files:
        print(f"  back up {f} ({(live / f).stat().st_size if (live / f).exists() else 'absent'} bytes)")
    for u in unstage:
        print(f"  git restore --staged {u}")
    print(f"  git pull --rebase --autostash origin {branch}")
    if not go:
        return 0
    bdir.mkdir(parents=True, exist_ok=False)
    for f in files:
        if (live / f).exists():
            dst = bdir / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live / f, dst)
    for u in unstage:
        git(live, "restore", "--staged", "--", u)
    r = git(live, "pull", "--rebase", "--autostash", "origin", branch)
    hold = False
    if r.returncode != 0:
        print("  PULL FAILED: " + (r.stderr or r.stdout).strip().splitlines()[-1:][0] if (r.stderr or r.stdout).strip()
              else "  PULL FAILED")
        hold = True
    marks = git(live, "diff", "--check")
    if "conflict marker" in marks.stdout:
        print("  CONFLICT MARKERS in the working tree (autostash pop): " + marks.stdout.splitlines()[0])
        hold = True
    for f in files:
        if (bdir / f).exists():
            v = compare(bdir / f, live / f)
            print(f"  {v:<8}{f}")
            hold = hold or v in ("LOST", "MISSING")
    print(("HOLD - backup kept at " + str(bdir)) if hold else "SYNCED")
    return 1 if hold else 0


def _selftest() -> int:
    ok: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        t = Path(td)
        origin, live, peer = t / "origin.git", t / "live", t / "peer"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        for d in (live, peer):
            subprocess.run(["git", "clone", "-q", str(origin), str(d)], check=True, capture_output=True)
            git(d, "config", "user.email", "t@t")
            git(d, "config", "user.name", "t")
            git(d, "checkout", "-q", "-b", "main")
        (live / "chain.jsonl").write_text('{"a":1}\n', encoding="utf-8")
        (live / "code.py").write_text("x = 1\n", encoding="utf-8")
        git(live, "add", "chain.jsonl", "code.py")
        git(live, "commit", "-qm", "base")
        git(live, "push", "-q", "origin", "main")
        git(peer, "pull", "-q", "origin", "main")
        (peer / "code.py").write_text("x = 2\n", encoding="utf-8")
        git(peer, "commit", "-qam", "landed")
        git(peer, "push", "-q", "origin", "main")
        with (live / "chain.jsonl").open("a", encoding="utf-8") as fh:      # the job appended meanwhile
            fh.write('{"b":2}\n')
        (live / "half.py").write_text("y\n", encoding="utf-8")
        git(live, "add", "half.py")                                           # a peer's half-staged file
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc_dry = sync(live, ["chain.jsonl"], "main", ["half.py"], t / "b0", go=False)
        ok["dry run writes nothing"] = rc_dry == 0 and not (t / "b0").exists() and "DRY RUN" in out.getvalue()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = sync(live, ["chain.jsonl"], "main", ["half.py"], t / "b1", go=True)
        s = out.getvalue()
        ok["sync pulls the landed commit and keeps the job's appended line"] = (
            rc == 0 and (live / "code.py").read_text(encoding="utf-8") == "x = 2\n"
            and '{"b":2}' in (live / "chain.jsonl").read_text(encoding="utf-8") and "SYNCED" in s)
        ok["the unstaged path is left untracked, not rebased"] = "half.py" not in git(live, "diff", "--cached",
                                                                                     "--name-only").stdout
        (t / "bk.txt").write_bytes(b"line1\nline2\n")
        (t / "now.txt").write_bytes(b"line1\n")
        ok["planted shrink is LOST"] = compare(t / "bk.txt", t / "now.txt") == "LOST"
        (t / "now.txt").write_bytes(b"line1\nline2\nline3\n")
        ok["an append is GREW"] = compare(t / "bk.txt", t / "now.txt") == "GREW"
        (t / "now.txt").write_bytes(b"lineX\nline2\nline3\n")
        ok["a rewritten old line is LOST even when the file grew"] = compare(t / "bk.txt", t / "now.txt") == "LOST"
        with contextlib.redirect_stdout(io.StringIO()):
            rc_exist = 0
            try:
                sync(live, ["chain.jsonl"], "main", [], t / "b1", go=True)
            except FileExistsError:
                rc_exist = 1
        ok["an existing backup folder is refused (never overwritten)"] = rc_exist == 1
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    print(f"selftest {sum(ok.values())}/{len(ok)}")
    return 0 if all(ok.values()) else 1


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--selftest" in argv:
        return _selftest()
    opts: dict[str, list[str]] = {}
    key = None
    for a in argv:
        if a.startswith("--"):
            key = a
            opts.setdefault(a, [])
        elif key:
            opts[key].append(a)
    if "--live" not in opts or len(opts["--live"]) != 1 or not opts.get("--files"):
        print(__doc__)
        return 2
    bk = opts.get("--backup")
    return sync(Path(opts["--live"][0]), opts["--files"], (opts.get("--branch") or ["main"])[0],
                opts.get("--unstage", []), Path(bk[0]) if bk else None, "--go" in opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
