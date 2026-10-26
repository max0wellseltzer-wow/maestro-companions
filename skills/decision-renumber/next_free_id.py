"""next_free_id - the next D / E / GT (any prefix) id that NO branch claims, and the ids two branches both claim.

Scans the base ref, every ref under --refs (default refs/remotes/origin/), optionally the work tree, for files that
match --file globs (defaults: D -> DECISIONS.md, E -> **/errata.md, anything else -> **/*.md). A CLAIM is a line
that DEFINES an id: it starts (after optional "|", "-", "*", "#", "**" and spaces) with the id, e.g.
"| D159 | ...", "- E72 [WIN] ...", "## GT35 ...". A mention elsewhere is not a claim. A SOFT claim is an id named in
a commit message of an unlanded branch (base..ref), e.g. "errata E77 to write".

CLASH  = one id defined with different text on two refs (or twice on one ref).
NEXT_FREE = 1 + the highest id claimed anywhere (hard or soft), so it is free on every branch at once.

    python next_free_id.py --repo R --kind E [--base origin/main] [--refs refs/remotes/origin/] [--file GLOB]...
                           [--worktree] [--no-fetch-hint] [--json]
    python next_free_id.py --headings plans/PLAN.md [--under 31]   # numbered headings as ids: clashes + next free
    python next_free_id.py --selftest
Exit: 0 no clash, 1 a clash exists (NEXT_FREE is still printed), 2 bad args / git error.
Read-only: it never writes, fetches or reserves anything; announce the id you take (mailbox #41) yourself.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_FILES = {"D": ["DECISIONS.md"], "E": ["errata.md", "*/errata.md"]}


class GitError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8", "replace")


def def_pattern(kind: str) -> re.Pattern:
    return re.compile(r"^[ \t]*(?:[-*|#]+[ \t]*)*(?:\*\*)?" + re.escape(kind) + r"(\d+)\b")


def claims_in_text(text: str, kind: str) -> dict:
    """-> {number: [defining line, ...]}"""
    pat, out = def_pattern(kind), {}
    for ln in text.splitlines():
        m = pat.match(ln)
        if m:
            out.setdefault(int(m.group(1)), []).append(ln.strip())
    return out


def _match(path: str, globs: list) -> bool:
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(Path(path).name, g) for g in globs)


def ref_claims(repo: Path, ref: str, kind: str, globs: list) -> dict:
    files = [f for f in _git(repo, "ls-tree", "-r", "--name-only", "-z", ref).split("\0") if f and _match(f, globs)]
    out = {}
    for f in files:
        for n, lines in claims_in_text(_git(repo, "show", f"{ref}:{f}"), kind).items():
            out.setdefault(n, []).extend((f, ln) for ln in lines)
    return out


def worktree_claims(repo: Path, kind: str, globs: list) -> dict:
    top = Path(_git(repo, "rev-parse", "--show-toplevel").strip())
    out = {}
    for p in top.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        rel = p.relative_to(top).as_posix()
        if _match(rel, globs):
            for n, lines in claims_in_text(p.read_text(encoding="utf-8", errors="replace"), kind).items():
                out.setdefault(n, []).extend((rel, ln) for ln in lines)
    return out


def soft_claims(repo: Path, base: str, ref: str, kind: str) -> set:
    msgs = _git(repo, "log", "--format=%B", f"{base}..{ref}")
    return {int(x) for x in re.findall(r"\b" + re.escape(kind) + r"(\d+)\b", msgs)}


def scan(repo: Path, kind: str, base: str, refs_prefix: str, globs: list, worktree: bool = False) -> dict:
    refs = [r for r in _git(repo, "for-each-ref", "--format=%(refname)", refs_prefix).split()
            if not r.endswith("/HEAD")]
    hard = {}                                   # n -> {ref: [(file, line)]}
    soft = {}                                   # n -> [ref]
    names = [base] + [r for r in refs if _git(repo, "rev-parse", r).strip() != _git(repo, "rev-parse", base).strip()
                      or r == base]
    for ref in dict.fromkeys(names):
        for n, where in ref_claims(repo, ref, kind, globs).items():
            hard.setdefault(n, {})[ref] = where
        if ref != base:
            for n in soft_claims(repo, base, ref, kind):
                soft.setdefault(n, []).append(ref)
    if worktree:
        for n, where in worktree_claims(repo, kind, globs).items():
            hard.setdefault(n, {})["(worktree)"] = where
    clashes = {}
    for n, by in hard.items():
        texts = {ln for where in by.values() for _, ln in where}
        dup_in_one = any(len(where) > 1 and len({ln for _, ln in where}) > 1 for where in by.values())
        if len(texts) > 1 or dup_in_one:
            clashes[n] = {ref: [ln for _, ln in where] for ref, where in by.items()}
    soft_only = {n: refs_ for n, refs_ in soft.items() if n not in hard}
    base_ids = [n for n, by in hard.items() if base in by]
    top = max(list(hard) + list(soft_only) + [0])
    return {"kind": kind, "base": base, "refs_scanned": len(dict.fromkeys(names)),
            "max_on_base": f"{kind}{max(base_ids)}" if base_ids else None,
            "clashes": {f"{kind}{n}": v for n, v in sorted(clashes.items())},
            "soft_only": {f"{kind}{n}": v for n, v in sorted(soft_only.items())},
            "branch_only": {f"{kind}{n}": sorted(by) for n, by in sorted(hard.items()) if base not in by},
            "next_free": f"{kind}{top + 1}"}


# ---------------------------------------------------------------- numbered headings --------------------------------
HEADING = re.compile(r"^(#{2,6})[ \t]+(\d+(?:\.\d+)*)\.?[ \t]+(.*)$")


def heading_report(text: str, under: str | None = None) -> dict:
    """Numbered markdown headings as ids ("### 31.7 ...", "## 32. ..."). Two sessions both wrote "### 31.7" on
    2026-10-21; a section number is an id like D177 and clashes the same way.
    -> {"clashes": {id: [lines]}, "next_free": "31.9" (under `under`) or None}"""
    seen: dict = {}
    for ln in text.splitlines():
        m = HEADING.match(ln.rstrip())
        if m:
            seen.setdefault(m.group(2), []).append(ln.strip())
    clashes = {k: v for k, v in seen.items() if len(v) > 1}
    nxt = None
    if under is not None:
        kids = [int(k.rsplit(".", 1)[1]) for k in seen if "." in k and k.rsplit(".", 1)[0] == under]
        nxt = f"{under}.{max(kids, default=0) + 1}"
    return {"clashes": clashes, "next_free": nxt}


# ---------------------------------------------------------------- selftest ----------------------------------------

def _rmtree(p: Path) -> None:
    def onerr(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=onerr)
    else:
        shutil.rmtree(p, onerror=onerr)


def _sandbox() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="freeid_selftest_"))
    cfg = tmp / "gitconfig"
    cfg.write_text("[user]\n\tname = selftest\n\temail = \n[core]\n\tautocrlf = false\n[init]\n\tdefaultBranch = main\n",
                   encoding="utf-8")
    os.environ["GIT_CONFIG_GLOBAL"] = str(cfg)
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    return tmp


def _selftest() -> bool:
    ok = {}
    c = claims_in_text("| D159 | row |\n- E72 [WIN] x\n## GT35 card\nsee D160 later\n**E9** bold\n", "E")
    ok["defining lines only (a mention is not a claim)"] = sorted(c) == [9, 72]
    ok["table row and heading forms"] = (list(claims_in_text("| D159 | row |\nsee D160\n", "D")) == [159]
                                         and list(claims_in_text("## GT35 card\n", "GT")) == [35])
    plan = ("## 31. Gemini toolkit\n### 31.6 FRED\n### 31.7 Alpha Vantage built (max-10)\ntext 31.7 mention\n"
            "### 31.7 P31.3 terms pass done\n## 32. Trading plans\n### 31.10 later\n")
    h = heading_report(plan, under="31")
    ok["two sessions' ### 31.7 headings -> heading CLASH (the 2026-10-21 case)"] = list(h["clashes"]) == ["31.7"]
    ok["next free section counts numerically (31.11 after 31.10, not 31.8)"] = h["next_free"] == "31.11"
    ok["a mention in body text and '## 32.' are not clashes"] = heading_report(plan)["clashes"].keys() == {"31.7"}
    ok["two '## 33.' top-level sections clash too"] = list(heading_report("## 33. a\n## 33. b\n")["clashes"]) == ["33"]
    tmp = _sandbox()
    try:
        r = tmp / "repo"
        r.mkdir()
        _git(r, "init", "-q")
        (r / "tv-x").mkdir()
        (r / "tv-x" / "errata.md").write_text("- E70 a\n- E71 b\n", encoding="utf-8")
        _git(r, "add", ".")
        _git(r, "commit", "-qm", "base")
        _git(r, "branch", "w3")
        _git(r, "branch", "lamport")
        _git(r, "checkout", "-q", "w3")
        (r / "tv-x" / "errata.md").write_text("- E70 a\n- E71 b\n- E72 [NA] prims.Window fix\n", encoding="utf-8")
        _git(r, "commit", "-qam", "W3: three tests not registered, errata E77 to write")
        _git(r, "checkout", "-q", "lamport")
        (r / "tv-x" / "errata.md").write_text("- E70 a\n- E71 b\n- E72 [CRASH] other thing\n", encoding="utf-8")
        _git(r, "commit", "-qam", "lamport")
        _git(r, "checkout", "-q", "main")
        rep = scan(r, "E", "main", "refs/heads/", ["errata.md", "*/errata.md"])
        ok["E72 claimed by two branches with different text -> CLASH"] = list(rep["clashes"]) == ["E72"]
        ok["E77 named only in a commit message -> soft claim"] = list(rep["soft_only"]) == ["E77"]
        ok["NEXT_FREE skips the soft claim (E78, not E73)"] = rep["next_free"] == "E78"
        ok["max on base reported"] = rep["max_on_base"] == "E71"
        _git(r, "checkout", "-q", "lamport")
        (r / "tv-x" / "errata.md").write_text("- E70 a\n- E71 b\n- E73 [CRASH] other thing\n", encoding="utf-8")
        _git(r, "commit", "-qam", "renumber to E73")
        _git(r, "checkout", "-q", "main")
        rep = scan(r, "E", "main", "refs/heads/", ["errata.md", "*/errata.md"])
        ok["after the renumber: no clash"] = rep["clashes"] == {}
        ok["identical inherited rows are not a clash"] = "E70" not in rep["clashes"]
        (r / "tv-x" / "errata.md").write_text("- E70 a\n- E71 b\n- E90 uncommitted\n", encoding="utf-8")
        rep = scan(r, "E", "main", "refs/heads/", ["*/errata.md"], worktree=True)
        ok["--worktree sees an uncommitted claim"] = rep["next_free"] == "E91"
        rc = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--repo", str(r), "--kind", "E",
                             "--base", "main", "--refs", "refs/heads/"], capture_output=True, text=True)
        ok["CLI prints NEXT_FREE and exits 0 without clash"] = rc.returncode == 0 and "NEXT_FREE: E78" in rc.stdout
    finally:
        _rmtree(tmp)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv: list) -> int:
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    if argv[:1] == ["--headings"] and len(argv) >= 2:
        under = argv[argv.index("--under") + 1] if "--under" in argv else None
        try:
            rep = heading_report(Path(argv[1]).read_text(encoding="utf-8"), under)
        except OSError as e:
            print(f"ERROR {e}")
            return 2
        for idn, lines in rep["clashes"].items():
            print(f"CLASH section {idn}:")
            for ln in lines:
                print(f"    {ln[:110]}")
        if rep["next_free"]:
            print(f"NEXT_FREE section: {rep['next_free']}")
        return 1 if rep["clashes"] else 0
    o = {"--repo": ".", "--kind": None, "--base": "origin/main", "--refs": "refs/remotes/origin/"}
    globs, flags, i = [], set(), 0
    while i < len(argv):
        a = argv[i]
        if a in o or a == "--file":
            if i + 1 >= len(argv):
                print(f"{a} needs a value")
                return 2
            if a == "--file":
                globs.append(argv[i + 1])
            else:
                o[a] = argv[i + 1]
            i += 2
            continue
        if a in ("--worktree", "--json"):
            flags.add(a)
        else:
            print(f"unknown argument {a}")
            return 2
        i += 1
    if not o["--kind"]:
        print(__doc__)
        return 2
    kind = o["--kind"]
    globs = globs or DEFAULT_FILES.get(kind, ["*.md"])
    try:
        rep = scan(Path(o["--repo"]), kind, o["--base"], o["--refs"], globs, "--worktree" in flags)
    except GitError as e:
        print(f"ERROR {e}")
        return 2
    if "--json" in flags:
        print(json.dumps(rep, indent=1))
    else:
        print(f"kind {kind}  files {globs}  refs scanned {rep['refs_scanned']}  max on {rep['base']}: "
              f"{rep['max_on_base']}")
        for idn, by in rep["clashes"].items():
            print(f"CLASH {idn}:")
            for ref, lines in by.items():
                for ln in lines:
                    print(f"    {ref}: {ln[:100]}")
        for idn, refs in rep["soft_only"].items():
            print(f"SOFT  {idn}: named in unlanded commit message(s) of {', '.join(refs)} (not written yet)")
        for idn, refs in rep["branch_only"].items():
            print(f"BRANCH_ONLY {idn}: {', '.join(refs)}")
        print(f"NEXT_FREE: {rep['next_free']}")
    return 1 if rep["clashes"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
