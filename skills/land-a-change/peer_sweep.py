"""peer_sweep - did a peer's commit carry MY unfinished work? (read-only on the live tree)

On 2026-10-21 a peer session's commit (tv-screener 6717641, "D180: design rules become design hints") staged my new
test and its tests.json entry, but not the code the test needs: main was red until I pushed ad704a5. A peer that runs
`git add -A` or `git commit -a` in a shared tree commits whatever is lying there.

After every fetch, run this on each repo you are editing:
  SWEPT    a peer commit holds a file whose content equals your working copy: your work landed under its name
  TOUCHED  a peer commit changed a file you have uncommitted edits in: merge before you commit
  With --run: the commands run in a clean detached worktree of UPTO ({files} = the swept/touched test files) and
  each is GREEN or RED there, so a half-landed change is caught before anyone builds on it.

    python peer_sweep.py --repo R --since REF [--upto origin/master] [--run -- python -m pytest -q {files}]
    python peer_sweep.py --selftest
Exit: 0 nothing overlaps (or all runs GREEN), 1 a RED run, 3 SWEPT/TOUCHED files found (merge first), 2 bad args.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _git(repo, *args, check=True, raw=False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout if raw else r.stdout.decode("utf-8", "replace")


def dirty_files(repo) -> list:
    """Files with uncommitted edits or untracked, as repo-relative paths."""
    out = []
    for ln in _git(repo, "status", "--porcelain", "--untracked-files=all").splitlines():
        p = ln[3:].strip().strip('"')
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        out.append(p.replace("\\", "/"))
    return out


def sweep(repo, since: str, upto: str) -> dict:
    """-> {"commits": [(sha, subject)], "rows": [{"file", "kind", "commit"}]}"""
    commits = [ln.split(" ", 1) for ln in _git(repo, "log", "--format=%h %s", f"{since}..{upto}").splitlines() if ln]
    mine = set(dirty_files(repo))
    rows, seen = [], set()
    for sha, _subj in commits:
        for f in _git(repo, "show", "--name-only", "--format=", sha).splitlines():
            f = f.strip()
            if not f or f not in mine or f in seen:
                continue
            seen.add(f)
            work = Path(repo, f)
            at_upto = _git(repo, "show", f"{upto}:{f}", check=False, raw=True)
            same = work.is_file() and work.read_bytes().replace(b"\r\n", b"\n") == at_upto.replace(b"\r\n", b"\n")
            rows.append({"file": f, "kind": "SWEPT" if same else "TOUCHED", "commit": sha})
    return {"commits": commits, "rows": rows}


def run_in_clean_tree(repo, upto: str, cmd: list, files: list) -> tuple:
    """Run cmd in a detached worktree of `upto`; {files} expands to the files. -> (GREEN|RED, output tail)"""
    d = tempfile.mkdtemp(prefix="peer_sweep_")
    try:
        _git(repo, "worktree", "add", "--detach", d, upto)
        argv = []
        for a in cmd:
            argv.extend(files) if a == "{files}" else argv.append(a)
        r = subprocess.run(argv, cwd=d, capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        return ("GREEN" if r.returncode == 0 else "RED"), " | ".join(tail)
    finally:
        _git(repo, "worktree", "remove", "--force", d, check=False)
        shutil.rmtree(d, ignore_errors=True)


def _selftest() -> int:
    ok = {}
    tmp = Path(tempfile.mkdtemp(prefix="peer_sweep_st_"))
    try:
        env_cfg = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false"]
        origin, mine, peer = tmp / "origin.git", tmp / "mine", tmp / "peer"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(mine)], check=True, capture_output=True)
        (mine / "a.py").write_text("def old():\n    return 1\n", encoding="utf-8")
        (mine / "test_a.py").write_text("import a\nassert a.old() == 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(mine), *env_cfg, "add", "."], check=True)
        subprocess.run(["git", "-C", str(mine), *env_cfg, "commit", "-qm", "base"], check=True)
        subprocess.run(["git", "-C", str(mine), "push", "-q", "origin", "HEAD:main"], check=True, capture_output=True)
        base = _git(mine, "rev-parse", "HEAD").strip()
        # my unfinished work: new code AND its test, both uncommitted
        (mine / "a.py").write_text("def old():\n    return 1\n\n\ndef new():\n    return 2\n", encoding="utf-8")
        (mine / "test_a.py").write_text("import a\nassert a.old() == 1\nassert a.new() == 2\n", encoding="utf-8")
        # the peer commits my test (same bytes) but not the code, plus a file of its own
        (mine / "test_b.py").write_text("import a\nassert a.new() == 2\n", encoding="utf-8")   # brand new, untracked
        subprocess.run(["git", "clone", "-q", str(origin), str(peer)], check=True, capture_output=True)
        shutil.copy(mine / "test_a.py", peer / "test_a.py")
        shutil.copy(mine / "test_b.py", peer / "test_b.py")
        (peer / "notes.md").write_text("peer\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(peer), *env_cfg, "add", "."], check=True)
        subprocess.run(["git", "-C", str(peer), *env_cfg, "commit", "-qm", "D180 design hints"], check=True)
        subprocess.run(["git", "-C", str(peer), "push", "-q", "origin", "HEAD:main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(mine), "fetch", "-q"], check=True)
        rep = sweep(mine, base, "origin/main")
        kinds = {r["file"]: r["kind"] for r in rep["rows"]}
        ok["my tests committed by the peer are SWEPT (an untracked new file too); its own file is not listed"] = kinds == {"test_a.py": "SWEPT", "test_b.py": "SWEPT"}
        state, _ = run_in_clean_tree(mine, "origin/main", [sys.executable, "{files}"], ["test_a.py"])
        ok["--run in a clean worktree of origin shows the half-landed change RED"] = state == "RED"
        state2, _ = run_in_clean_tree(mine, base, [sys.executable, "{files}"], ["test_a.py"])
        ok["the same run on the base is GREEN (the probe can pass)"] = state2 == "GREEN"
        (mine / "test_a.py").write_text("import a\nassert a.new() == 2\n", encoding="utf-8")
        ok["a peer change to a file I edited differently is TOUCHED"] = (
            {r["file"]: r["kind"] for r in sweep(mine, base, "origin/main")["rows"]}["test_a.py"] == "TOUCHED")
        ok["the live tree is untouched (no stash, no checkout)"] = "a.new()" in (mine / "test_a.py").read_text()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(ok.values()) else 1


def main(argv) -> int:
    if argv[:1] == ["--selftest"]:
        return _selftest()
    args, cmd = list(argv), []
    if "--" in args:
        i = args.index("--")
        args, cmd = args[:i], args[i + 1:]
    o = {"--repo": ".", "--since": None, "--upto": None}
    while args:
        a = args.pop(0)
        if a == "--run":
            continue
        if a not in o or not args:
            print(__doc__)
            return 2
        o[a] = args.pop(0)
    if not o["--since"]:
        print(__doc__)
        return 2
    repo = o["--repo"]
    try:
        upto = o["--upto"] or _git(repo, "rev-parse", "--abbrev-ref", "@{u}").strip()
        rep = sweep(repo, o["--since"], upto)
    except RuntimeError as e:
        print(f"ERROR {e}")
        return 2
    print(f"{len(rep['commits'])} commit(s) {o['--since']}..{upto}")
    for r in rep["rows"]:
        print(f"  {r['kind']:<8} {r['file']}  (in {r['commit']})")
    if not rep["rows"]:
        print("  nothing of yours in them")
        return 0
    if cmd:
        tests = [r["file"] for r in rep["rows"] if Path(r["file"]).name.startswith("test")] or [r["file"] for r in rep["rows"]]
        state, tail = run_in_clean_tree(repo, upto, cmd, tests)
        print(f"{state} on a clean {upto}: {tail}")
        return 1 if state == "RED" else 3
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
