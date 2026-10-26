"""Land commits from a scratch clone into a live repo that another session may be committing to, without losing either
side's work: pen -> fetch -> fast-forward or cherry-pick (tests.json conflicts merged by union) -> full check whenever the
result differs from what was checked -> push -> bump the root pointer -> release the pen. Every step prints one line.

    python land.py --live <root>\\tv-screener --clone <scratch clone> [--branch master] [--root <root>]
                   [--check check.bat] [--checked <sha the clone's check passed on>] [--label "..."] [--dry-run]
    python land.py --selftest      (hermetic: temp repos with a temp bare "origin"; never the pen, never a real remote)

Exit codes: 0 landed (or nothing to land), 2 bad arguments, 3 pen held by someone else, 4 a conflict other than
tests.json (nothing landed; live tree restored), 5 check failed (commits are in the live repo but NOT pushed), 6 push failed.
Stdlib only. The pen is tv_core.writer, run from the root folder; the claim id is used for the release.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

Run = Callable[[Sequence[str], Path], tuple[int, str]]


def run(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def git(cwd: Path, *args: str, runner: Run = run) -> str:
    code, out = runner(["git", *args], cwd)
    if code:
        raise RuntimeError(f"git {' '.join(args)} failed: {out[-300:]}")
    return out


# ---- tests.json union ------------------------------------------------------------------------------------------------

def union_tests_json(ours: str, theirs: str) -> str:
    """Our registry plus every entry of theirs whose test is not registered yet. An id that collides gets a suffix.
    The format (indent) of ours is kept. Raises ValueError when either side is not a registry."""
    a, b = json.loads(ours), json.loads(theirs)
    key = "checks" if "checks" in a else "tests"
    have_tests = {e.get("test") for e in a[key]}
    have_ids = {e.get("id") for e in a[key]}
    for e in b.get(key, []):
        if e.get("test") in have_tests:
            continue
        e = dict(e)
        base, n = e.get("id"), 1
        while e.get("id") in have_ids:
            n += 1
            e["id"] = f"{base}_{n}"
        a[key].append(e)
        have_tests.add(e.get("test"))
        have_ids.add(e.get("id"))
    indent = 2 if ours.startswith('{\n  "') else 1
    return json.dumps(a, indent=indent, ensure_ascii=False) + "\n"


# ---- the pen ---------------------------------------------------------------------------------------------------------

@dataclass
class Pen:
    root: Path
    runner: Run = run
    claim_id: str | None = None

    def holder(self) -> str | None:
        _, out = self.runner([sys.executable, "-m", "tv_core.writer", "status"], self.root)
        first = out.splitlines()[0] if out else ""
        return None if first.strip() == "Writer: NONE" else first.removeprefix("Writer: ")

    def claim(self, label: str) -> bool:
        code, out = self.runner([sys.executable, "-m", "tv_core.writer", "claim", label], self.root)
        m = re.search(r"claim id: ([0-9a-f]{16,})", out)
        self.claim_id = m.group(1) if m else None
        return code == 0

    def release(self) -> None:
        args = [sys.executable, "-m", "tv_core.writer", "release"] + ([self.claim_id] if self.claim_id else [])
        self.runner(args, self.root)


class NoPen(Pen):
    """For a repo with no pen (tests, other projects)."""

    def holder(self) -> str | None:
        return None

    def claim(self, label: str) -> bool:
        return True

    def release(self) -> None:
        return None


# ---- landing ---------------------------------------------------------------------------------------------------------

@dataclass
class Result:
    code: int
    lines: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)
        print(line, flush=True)


def bring_in(live: Path, clone: Path, branch: str, res: Result, runner: Run = run) -> tuple[str, bool | None] | None:
    """Fetches the clone's branch and applies its new commits. Returns (new HEAD, moved_under_us) or None on a conflict
    that is not tests.json (the live tree is then restored). moved_under_us: the live tree had commits the clone lacked (None: there was nothing to land)."""
    before = git(live, "rev-parse", "HEAD", runner=runner)
    git(live, "fetch", "-q", str(clone), branch, runner=runner)
    theirs = git(live, "rev-parse", "FETCH_HEAD", runner=runner)
    base = git(live, "merge-base", before, theirs, runner=runner)
    if base == theirs:
        res.say("nothing to land: the live tree already has every commit of the clone")
        return before, None
    if base == before:
        git(live, "merge", "-q", "--ff-only", theirs, runner=runner)
        res.say(f"fast-forwarded {before[:7]} -> {theirs[:7]}")
        return theirs, False
    picks = [ln[2:] for ln in git(live, "cherry", before, theirs, runner=runner).splitlines() if ln.startswith("+ ")]
    res.say(f"live tree moved ({before[:7]} is not in the clone): cherry-picking {len(picks)} commit(s)")
    for sha in picks:
        code, out = runner(["git", "cherry-pick", sha], live)
        if code == 0:
            continue
        conflicted = git(live, "diff", "--name-only", "--diff-filter=U", runner=runner).split()
        if conflicted == ["tests.json"]:
            ours = git(live, "show", "HEAD:tests.json", runner=runner)
            mine = git(live, "show", f"{sha}:tests.json", runner=runner)
            (live / "tests.json").write_text(union_tests_json(ours, mine), encoding="utf-8", newline="\n")
            git(live, "add", "tests.json", runner=runner)
            git(live, "-c", "core.editor=true", "cherry-pick", "--continue", runner=runner)
            res.say(f"  {sha[:7]}: tests.json merged by union")
            continue
        runner(["git", "cherry-pick", "--abort"], live)
        git(live, "reset", "-q", "--hard", before, runner=runner)
        res.say(f"STOP: {sha[:7]} conflicts in {conflicted or 'unknown files'}; live tree restored to {before[:7]}")
        return None
    return git(live, "rev-parse", "HEAD", runner=runner), True


def land(live: Path, clone: Path, branch: str = "master", root: Path | None = None, check: str | None = "check.bat",
         checked: str | None = None, label: str = "race-lander", dry_run: bool = False, pen: Pen | None = None,
         runner: Run = run) -> Result:
    res = Result(0)
    pen = pen or (Pen(root, runner) if root else NoPen(live, runner))
    held = pen.holder()
    if held:
        res.say(f"pen held by: {held} - build on in the clone and try again later")
        res.code = 3
        return res
    if dry_run:
        res.say(f"dry run: would land {clone} -> {live} ({branch}), check {'when moved' if checked else 'always'}, "
                f"{'bump the pointer in ' + str(root) if root else 'no root pointer'}")
        return res
    if not pen.claim(label):
        res.say("could not claim the pen")
        res.code = 3
        return res
    try:
        got = bring_in(live, clone, branch, res, runner)
        if got is None:
            res.code = 4
            return res
        head, moved = got
        if moved is None:
            return res
        must_check = check and checked != head            # a cherry-picked head is always new, so it is always checked
        if must_check:
            res.say(f"running {check} on {head[:7]} (the result differs from what was checked)")
            code, out = runner(["cmd", "/c", str(live / check) if check.endswith(".bat") else check], live)
            tail = "\n".join(out.splitlines()[-3:])
            if code or "CHECK PASSED" not in out:
                res.say(f"CHECK FAILED - not pushed. Last lines:\n{tail}")
                res.code = 5
                return res
            res.say(f"check passed: {tail.splitlines()[0] if tail else ''}")
        elif check:
            res.say(f"check skipped: {head[:7]} is exactly the commit the clone's check passed on")
        code, out = runner(["git", "push", "-q", "origin", branch], live)
        if code:
            res.say(f"PUSH FAILED: {out[-300:]}")
            res.code = 6
            return res
        res.say(f"pushed {live.name} {head[:7]}")
        if root:
            rel = live.resolve().relative_to(root.resolve()).as_posix()
            git(root, "add", rel, runner=runner)
            code, _ = runner(["git", "diff", "--cached", "--quiet"], root)
            if code:
                git(root, "commit", "-q", "-m", f"{rel} pointer -> {head[:7]} ({label})", runner=runner)
                code, out = runner(["git", "push", "-q", "origin", "HEAD"], root)
                if code:
                    res.say(f"ROOT PUSH FAILED: {out[-300:]}")
                    res.code = 6
                    return res
                res.say(f"root pointer bumped and pushed ({rel} -> {head[:7]})")
        return res
    finally:
        pen.release()


def _rmtree(path: Path) -> None:
    """shutil.rmtree that also removes git's read-only object files on Windows."""
    import os
    import shutil
    import stat

    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


def _selftest() -> bool:
    """Hermetic. Landing is tested only against a temp bare repo as "origin" (root=None, so NoPen: tv_core.writer is
    never run); the real Pen class is tested with a fake runner that executes nothing. Prints PASS/FAIL per check."""
    import io
    import tempfile
    from contextlib import redirect_stdout

    ok: dict[str, bool] = {}
    ours = '{\n  "tests": [\n    {"id": "a", "test": "t_a"}\n  ]\n}\n'
    theirs = json.dumps({"tests": [{"id": "a", "test": "t_a"}, {"id": "a", "test": "t_b"}, {"id": "c", "test": "t_c"}]})
    merged = json.loads(union_tests_json(ours, theirs))["tests"]
    ok["tests.json union: dedup by test, colliding id suffixed, new kept"] = (
        [(e["id"], e["test"]) for e in merged] == [("a", "t_a"), ("a_2", "t_b"), ("c", "t_c")])
    try:
        union_tests_json(ours, "not json {")
        ok["planted: a non-registry tests.json is refused"] = False
    except ValueError:
        ok["planted: a non-registry tests.json is refused"] = True

    calls: list[list[str]] = []

    def fake(reply: str, code: int = 0) -> Run:
        def r(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
            calls.append(list(cmd))
            return code, reply
        return r
    pen = Pen(Path("."), fake("Writer: other-session (since 10:00)"))
    with redirect_stdout(io.StringIO()):
        res = land(Path("unused-live"), Path("unused-clone"), pen=pen, runner=fake("", 1))
    ok["planted: pen held by someone else -> exit 3, no git run"] = (
        res.code == 3 and not any(c and c[0] == "git" for c in calls))
    calls.clear()
    pen = Pen(Path("."), fake("claimed. claim id: 0123456789abcdef0123"))
    ok["Pen parses the claim id and releases with it (fake runner)"] = (
        pen.claim("x") and pen.claim_id == "0123456789abcdef0123" and (pen.release() or True)
        and calls[-1][-2:] == ["release", "0123456789abcdef0123"])
    ok["Pen reads 'Writer: NONE' as free"] = Pen(Path("."), fake("Writer: NONE")).holder() is None
    with redirect_stdout(io.StringIO()):
        ok["no --live/--clone -> usage, exit 2"] = main([]) == 2

    tmp = Path(tempfile.mkdtemp(prefix="race_lander_selftest_"))
    try:
        def g(cwd: Path, *args: str) -> str:
            return git(cwd, *args)

        def commit(repo: Path, name: str, text: str) -> str:
            (repo / name).write_text(text, encoding="utf-8", newline="\n")
            g(repo, "add", name)
            g(repo, "commit", "-q", "-m", f"edit {name}")
            return g(repo, "rev-parse", "HEAD")

        def world(tag: str) -> tuple[Path, Path, Path]:
            w = tmp / tag
            w.mkdir()
            origin, seed = w / "origin.git", w / "seed"
            g(w, "init", "-q", "--bare", "-b", "master", str(origin))
            g(w, "init", "-q", "-b", "master", str(seed))
            for repo in (seed,):
                g(repo, "config", "user.name", "selftest")
                g(repo, "config", "user.email", "selftest@invalid")
            commit(seed, "f.txt", "base\n")
            g(seed, "remote", "add", "origin", str(origin))
            g(seed, "push", "-q", "origin", "master")
            live, clone = w / "live", w / "clone"
            for repo in (live, clone):
                g(w, "clone", "-q", str(origin), str(repo))
                g(repo, "config", "user.name", "selftest")
                g(repo, "config", "user.email", "selftest@invalid")
            return origin, live, clone

        origin, live, clone = world("ff")
        new = commit(clone, "g.txt", "mine\n")
        with redirect_stdout(io.StringIO()):
            res = land(live, clone, "master", check=None)
        ok["temp repos: fast-forward lands and pushes to the temp origin"] = (
            res.code == 0 and g(origin, "rev-parse", "master") == new)

        origin, live, clone = world("fail")
        before = g(origin, "rev-parse", "master")
        commit(clone, "g.txt", "mine\n")
        seen: list[list[str]] = []

        def failing_check(cmd: Sequence[str], cwd: Path) -> tuple[int, str]:
            seen.append(list(cmd))
            return (1, "boom") if cmd[0] == "cmd" else run(cmd, cwd)
        with redirect_stdout(io.StringIO()):
            res = land(live, clone, "master", check="check.bat", runner=failing_check)
        ok["planted: a failing check -> exit 5 and nothing pushed"] = (
            res.code == 5 and g(origin, "rev-parse", "master") == before
            and not any("push" in c for c in seen))

        origin, live, clone = world("conflict")
        live_head = commit(live, "f.txt", "live side\n")
        commit(clone, "f.txt", "clone side\n")
        with redirect_stdout(io.StringIO()):
            res = land(live, clone, "master", check=None)
        ok["planted: a real conflict -> exit 4, live tree restored"] = (
            res.code == 4 and g(live, "rev-parse", "HEAD") == live_head
            and (live / "f.txt").read_text(encoding="utf-8") == "live side\n")
    except Exception as e:  # a crash is a FAIL line, not a traceback
        ok[f"temp-repo checks ran ({type(e).__name__}: {e})"] = False
    finally:
        _rmtree(tmp)
    for name, passed in ok.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return all(ok.values())


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1

    def opt(name: str, default: str | None = None) -> str | None:
        return argv[argv.index(name) + 1] if name in argv else default
    live, clone = opt("--live"), opt("--clone")
    if not live or not clone:
        print(__doc__)
        return 2
    root = opt("--root")
    res = land(Path(live), Path(clone), opt("--branch", "master") or "master", Path(root) if root else None,
               opt("--check", "check.bat"), opt("--checked"), opt("--label", "race-lander") or "race-lander",
               "--dry-run" in argv)
    return res.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
