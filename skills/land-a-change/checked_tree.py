"""checked_tree.py - commit only what the check actually checked, and only when the check itself passed.

    python checked_tree.py run [--repo R] -- check.bat          # record the working tree, run the check, record ITS exit code
    python checked_tree.py start [--repo R]                     # (or by hand) record the tree before you run the check
    python checked_tree.py done --rc N [--repo R]               # ... and the check's own exit code after it
    python checked_tree.py verify [--repo R]                    # pre-commit: exit 2 unless every staged change is in the
                                                                # checked tree, the check exited 0 and nothing moved meanwhile
    python checked_tree.py --selftest

The record lives in .git/checked_tree.json. "The tree" = the working tree as `git add -A` would see it (built in a
throwaway index, so your real index is untouched; git stores the blobs as loose objects, which is harmless).
verify fails (exit 2) when: there is no record; the check's exit code was not 0; the tree changed while the check
ran; or a staged file's content differs from the checked tree (a stash pop, an edit, a restore after the green check:
tv-forge E36). Exit 0 = commit what was checked.

Pre-commit hook (one line; NOT installed by this tool - activation is the user's call):
    .git/hooks/pre-commit:   python "<path>/checked_tree.py" verify
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RECORD = "checked_tree.json"


def git(repo: Path, *args: str, env: dict | None = None, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def git_dir(repo: Path) -> Path:
    d = Path(git(repo, "rev-parse", "--git-dir").strip())
    return d if d.is_absolute() else repo / d


def worktree_tree(repo: Path) -> str:
    """The tree `git add -A` would commit, built in a temporary index (the real index is not touched)."""
    fd, idx = tempfile.mkstemp(prefix="checked_idx_")
    os.close(fd)
    os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        if git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False).strip():
            git(repo, "read-tree", "HEAD", env=env)
        git(repo, "add", "-A", env=env)
        return git(repo, "write-tree", env=env).strip()
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def blobs_of_tree(repo: Path, tree: str | None) -> dict[str, str]:
    if not tree:
        return {}
    out = {}
    for line in git(repo, "ls-tree", "-r", "-z", tree).split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            out[path] = meta.split()[2]
    return out


def blobs_of_index(repo: Path) -> dict[str, str]:
    out = {}
    for line in git(repo, "ls-files", "-s", "-z").split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            out[path] = meta.split()[1]
    return out


def _head(repo: Path) -> str | None:
    return git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False).strip() or None


def start(repo: Path, cmd: str = "") -> dict:
    rec = {"tree": worktree_tree(repo), "head": _head(repo), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "cmd": cmd, "rc": None, "end_tree": None}
    (git_dir(repo) / RECORD).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def done(repo: Path, rc: int) -> dict:
    f = git_dir(repo) / RECORD
    rec = json.loads(f.read_text(encoding="utf-8"))
    rec["rc"], rec["end_tree"] = rc, worktree_tree(repo)
    f.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def run(repo: Path, cmd: list[str]) -> int:
    start(repo, " ".join(cmd))
    rc = subprocess.run(cmd, cwd=repo, shell=(sys.platform == "win32" and cmd[0].lower().endswith((".bat", ".cmd"))
                                              )).returncode
    rec = done(repo, rc)
    print(f"check exit {rc}; tree {rec['tree'][:10]}" + ("" if rec["end_tree"] == rec["tree"]
                                                         else " - the tree CHANGED while it ran"))
    return rc


def verify(repo: Path) -> tuple[int, list[str]]:
    f = git_dir(repo) / RECORD
    if not f.exists():
        return 2, ["no checked-tree record: run `checked_tree.py run -- <check>` before committing"]
    rec = json.loads(f.read_text(encoding="utf-8"))
    why = []
    if rec.get("rc") is None:
        why.append("the check never reported its exit code (start without done)")
    elif rec["rc"] != 0:
        why.append(f"the check's own exit code was {rec['rc']} (not 0) - a green tail does not count")
    if rec.get("end_tree") and rec["end_tree"] != rec["tree"]:
        why.append("the working tree changed while the check ran: it checked a moving target")
    checked = blobs_of_tree(repo, rec["tree"])
    head = blobs_of_tree(repo, _head(repo))
    index = blobs_of_index(repo)
    for p in sorted(set(index) | set(head)):
        if index.get(p) == head.get(p):
            continue                                            # not a staged change
        if checked.get(p) != index.get(p):
            state = "deleted" if p not in index else "content"
            why.append(f"staged {state} of {p} is not what the check saw")
    return (2 if why else 0), why


# ----------------------------------------------------------------------------------------------------- selftest
def _selftest() -> bool:
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    py = sys.executable
    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "repo"
        r.mkdir()
        g = lambda *a, **k: git(r, *a, **k)  # noqa: E731
        g("init", "-q")
        g("config", "user.email", "<email>")
        g("config", "user.name", "selftest")
        g("config", "core.autocrlf", "false")
        (r / "a.py").write_text("x = 1\n", encoding="utf-8")
        g("add", "a.py")
        g("commit", "-q", "-m", "base")
        check("verify with no record exits 2", verify(r)[0] == 2)
        (r / "a.py").write_text("x = 2\n", encoding="utf-8")
        rc = run(r, [py, "-c", "raise SystemExit(0)"])
        g("add", "a.py")
        code, why = verify(r)
        check("a green check on the staged content: verify exits 0", rc == 0 and code == 0)
        (r / "a.py").write_text("x = 3  # restored from a stash after the check\n", encoding="utf-8")
        g("add", "a.py")
        code, why = verify(r)
        check("an edit staged AFTER the green check: exit 2 (tv-forge E36)", code == 2 and any("a.py" in w for w in why))
        run(r, [py, "-c", "raise SystemExit(1)"])
        code, why = verify(r)
        check("the check's own exit code 1: exit 2 even with the same tree (tv-forge E23)",
              code == 2 and any("exit code was 1" in w for w in why))
        run(r, [py, "-c", "open('a.py','a').write('# moved\\n')"])
        g("add", "a.py")
        code, why = verify(r)
        check("a tree that changed while the check ran: exit 2", code == 2 and any("changed while" in w for w in why))
        run(r, [py, "-c", "pass"])
        g("rm", "-q", "--cached", "a.py")
        code, why = verify(r)
        check("a staged deletion the check never saw: exit 2", code == 2 and any("deleted" in w for w in why))
        g("add", "a.py")
        (r / "b.py").write_text("y = 1\n", encoding="utf-8")
        run(r, [py, "-c", "pass"])
        g("add", "b.py")
        check("only part of the checked tree staged (git add by name): exit 0", verify(r)[0] == 0)
        # the hook itself, installed only inside this throwaway repo
        hook = r / ".git" / "hooks" / "pre-commit"
        hook.write_text(f'#!/bin/sh\n"{Path(py).as_posix()}" "{Path(__file__).resolve().as_posix()}" verify\n',
                        encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        p = subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "checked"], capture_output=True, text=True)
        check("hook: a commit of the checked tree goes through", p.returncode == 0)
        (r / "b.py").write_text("y = 2\n", encoding="utf-8")
        g("add", "b.py")
        p = subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "unchecked"], capture_output=True, text=True)
        check("hook: a commit of an unchecked edit is refused", p.returncode != 0 and "not what the check saw" in p.stdout + p.stderr)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argv[0] == "--selftest":
        return 0 if _selftest() else 1
    head = argv[:argv.index("--")] if "--" in argv else argv
    repo = Path(head[head.index("--repo") + 1]) if "--repo" in head else Path.cwd()
    if argv[0] == "run":
        if "--" not in argv:
            print("run needs the check command after --")
            return 2
        return run(repo, argv[argv.index("--") + 1:])
    if argv[0] == "start":
        print("recorded tree", start(repo)["tree"][:10])
        return 0
    if argv[0] == "done":
        rec = done(repo, int(head[head.index("--rc") + 1]))
        print(f"recorded check exit {rec['rc']}")
        return 0
    if argv[0] == "verify":
        code, why = verify(repo)
        for w in why:
            print("checked-tree: " + w)
        print("checked-tree: " + ("REFUSED" if code else "OK - committing what the check saw"))
        return code
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
