"""merge3 - three-way merge of a skill file whose global copy and repo copy BOTH changed (skill-sync-audit).

The recipe that worked on 2026-10-21 (skill-maestro, transcript L2653-L2814):
  1. base = the repo commit whose version of the file is CLOSEST to the archived global copy (the global copy
     before its own edits), found by diff size over the file's history - not the newest commit, not a guess;
  2. git merge-file -L global -L base -L repo <merged=copy of global> <base> <repo>, with Windows paths;
  3. read every conflict, resolve by hand (or a small resolve script with an assert per block), run the selftest.
Calling git from Python with a list of arguments sidesteps both Git Bash traps hit that day (MSYS path conversion
turning `origin/main:path` into `origin\\main;...`, and git.exe not reading /c/... paths).

    python merge3.py base REPO PATH_IN_REPO ARCHIVED_GLOBAL_COPY [--last 25]
        -> one line per commit "sha date subject | diff=N", then "BASE sha (diff N)"
    python merge3.py merge GLOBAL BASE REPO --out MERGED
        -> writes MERGED only (refuses if it exists), prints "conflicts: N" and each conflict's line and size
    python merge3.py --selftest
Reads repos only; never writes into a repo or a skills folder unless you name that path as --out.
"""
from __future__ import annotations

import difflib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def _norm(text: str) -> list[str]:
    return text.replace("\r\n", "\n").splitlines()


def diff_size(a: str, b: str) -> int:
    """Lines added plus removed between two texts (CRLF ignored), like `diff | grep -c '^[<>]'`."""
    return sum(1 for ln in difflib.unified_diff(_norm(a), _norm(b), lineterm="", n=0)
               if ln[:1] in "+-" and not ln.startswith(("+++", "---")))


def find_base(repo, path: str, archived: str, last: int = 25) -> list[tuple[str, str, int]]:
    """[(sha, 'date subject', diff)] for the last N commits touching path, in log order (newest first)."""
    shas = _git(repo, "log", f"-{last}", "--format=%h", "--", path).stdout.split()
    out = []
    for c in shas:
        r = _git(repo, "show", f"{c}:{path}", check=False)
        if r.returncode != 0:
            continue
        info = _git(repo, "log", "-1", "--format=%cs %s", c).stdout.strip()[:70]
        out.append((c, info, diff_size(r.stdout, archived)))
    return out


def conflicts(text: str) -> list[tuple[int, int, int]]:
    """[(line, ours_lines, theirs_lines)] for each <<<<<<< ... ======= ... >>>>>>> block."""
    res, start, side, a, b = [], 0, None, 0, 0
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("<<<<<<< "):
            start, side, a, b = i, "a", 0, 0
        elif ln == "=======" and side == "a":
            side = "b"
        elif ln.startswith(">>>>>>> ") and side == "b":
            res.append((start, a, b))
            side = None
        elif side == "a" and not re.match(r"^\|\|\|\|\|\|\| ", ln):
            a += 1
        elif side == "b":
            b += 1
    return res


def merge(global_copy, base, repo_copy, out) -> tuple[int, list]:
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")
    shutil.copyfile(global_copy, out)
    r = subprocess.run(["git", "merge-file", "-L", "global", "-L", "base", "-L", "repo",
                        str(out), str(base), str(repo_copy)], capture_output=True, text=True)
    if r.returncode < 0 or r.returncode > 127:
        raise RuntimeError(f"git merge-file failed: {r.stderr.strip()}")
    return r.returncode, conflicts(out.read_text(encoding="utf-8", errors="replace"))


def _selftest() -> bool:
    ok = {}
    if shutil.which("git") is None:
        print("FAIL git not found on PATH")
        return False
    tmp = Path(tempfile.mkdtemp(prefix="merge3_selftest_"))
    try:
        repo = tmp / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "<email>")
        _git(repo, "config", "user.name", "t")
        f = repo / "skill" / "tool.py"
        f.parent.mkdir()
        lines = [f"line {i}\n" for i in range(40)]
        versions = []
        for k in range(4):                                  # v0..v3; each commit edits a different region
            if k:
                lines[k * 10] = f"repo edit {k}\n"
            f.write_bytes("".join(lines).encode())
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", f"v{k}")
            versions.append("".join(lines))
        # the archived global copy = v1 plus one global-only line far from the repo's later edits
        g = versions[1].replace("line 35\n", "global edit\n")
        rows = find_base(repo, "skill/tool.py", g)
        best = min(rows, key=lambda r: r[2])
        ok["base finder lists every commit of the file, newest first"] = (
            len(rows) == 4 and [r[1].split(" ", 1)[1] for r in rows] == ["v3", "v2", "v1", "v0"])
        ok["base = the commit closest to the archived global copy (v1), not the newest"] = (
            best[1].endswith("v1") and best[0] != rows[0][0])
        ok["diff_size ignores CRLF vs LF"] = diff_size("a\nb\n", "a\r\nb\r\n") == 0 and diff_size("a\n", "b\n") == 2
        base_f, glob_f, repo_f = tmp / "base.py", tmp / "global.py", tmp / "repo.py"
        base_f.write_text(versions[1], encoding="utf-8", newline="\n")
        glob_f.write_text(g, encoding="utf-8", newline="\n")
        repo_f.write_text(versions[3], encoding="utf-8", newline="\n")
        code, cf = merge(glob_f, base_f, repo_f, tmp / "merged.py")
        merged = (tmp / "merged.py").read_text(encoding="utf-8")
        ok["non-overlapping edits merge clean and keep both sides"] = (
            code == 0 and cf == [] and "global edit" in merged and "repo edit 3" in merged)
        # planted: the repo also edited the global-only line -> exactly one conflict, sizes 1 and 1
        repo_f.write_text(versions[3].replace("line 35\n", "repo took 35\n"), encoding="utf-8", newline="\n")
        code, cf = merge(glob_f, base_f, repo_f, tmp / "merged2.py")
        ok["a planted overlapping edit is reported as 1 conflict with its sizes"] = code == 1 and cf == [(36, 1, 1)]
        try:
            merge(glob_f, base_f, repo_f, tmp / "merged2.py")
            ok["an existing --out is refused"] = False
        except FileExistsError:
            ok["an existing --out is refused"] = True
        # planted: a naive base (the newest commit) makes the repo's own edits look like global ones
        newest = versions[3]
        ok["planted wrong base (newest) has a bigger diff than the right one"] = diff_size(newest, g) > best[2]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    if argv[:1] == ["base"] and len(argv) >= 4:
        last = 25
        if "--last" in argv:
            i = argv.index("--last")
            last = int(argv[i + 1])
            argv = argv[:i] + argv[i + 2:]
        archived = Path(argv[3]).read_text(encoding="utf-8-sig", errors="replace")
        rows = find_base(argv[1], argv[2].replace("\\", "/"), archived, last)
        if not rows:
            print("no commits touch that path")
            return 1
        for c, info, d in rows:
            print(f"{c} {info} | diff={d}")
        c, _, d = min(rows, key=lambda r: r[2])
        print(f"BASE {c} (diff {d})")
        return 0
    if argv[:1] == ["merge"] and len(argv) == 6 and argv[4] == "--out":
        code, cf = merge(argv[1], argv[2], argv[3], argv[5])
        print(f"conflicts: {len(cf)}")
        for line, a, b in cf:
            print(f"  conflict at {line}: global {a} lines, repo {b} lines")
        return 0 if code == 0 else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
