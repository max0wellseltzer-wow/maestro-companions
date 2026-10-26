"""skill_sync - compare skill libraries (user ~/.claude/skills, a project's .claude/skills, a repo copy) by name and
content hash; list skills missing from a root and copies that drifted, and propose the copy direction
(backs the skill-sync-audit skill, candidate #61).

Per skill name across the roots:
  SAME       identical content everywhere it exists (line endings normalized; __pycache__ / *.pyc / evals runs ignored)
  EOL-ONLY   differs only in CRLF vs LF
  DRIFTED    content differs: lists the differing files and the first differing SKILL.md line; the copy with the newest
             file is proposed as the source (a proposal - read both before copying)
  MISSING    absent from some roots: proposes copying from a root that has it
Nothing is copied. `--plan` prints PowerShell Copy-Item lines for the user/Claude to run after reading them.

    python skill_sync.py <root> <root> [<root> ...] [--names a,b] [--plan] [--json]
    python skill_sync.py --selftest
Exit 0 all in sync, 1 something missing or drifted, 2 bad args. Reads only. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

IGNORE_DIRS = {"__pycache__", ".git", ".pytest_cache", "runs"}
IGNORE_SUFFIX = {".pyc", ".pyo"}


def _files(d: Path) -> dict:
    out = {}
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.suffix not in IGNORE_SUFFIX and not (set(p.relative_to(d).parts) & IGNORE_DIRS):
            out[p.relative_to(d).as_posix()] = p
    return out


def _digest(p: Path, eol: bool) -> str:
    b = p.read_bytes()
    if eol:
        b = b.replace(b"\r\n", b"\n")
    return hashlib.sha256(b).hexdigest()


def skill_state(d: Path) -> dict:
    fs = _files(d)
    return {"raw": {k: _digest(v, False) for k, v in fs.items()}, "norm": {k: _digest(v, True) for k, v in fs.items()},
            "newest": max((v.stat().st_mtime for v in fs.values()), default=0.0)}


def _first_diff(a: Path, b: Path) -> str:
    try:
        la = a.read_text(encoding="utf-8", errors="replace").splitlines()
        lb = b.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for i, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return f"line {i}: {x[:80]!r} vs {y[:80]!r}"
    return f"length {len(la)} vs {len(lb)} lines" if len(la) != len(lb) else ""


def audit(roots: list, names: list | None = None) -> list:
    roots = [Path(r) for r in roots]
    found = {r: {d.name for d in r.iterdir() if d.is_dir() and (d / "SKILL.md").exists()} if r.is_dir() else set()
             for r in roots}
    all_names = sorted(set().union(*found.values()))
    if names:
        all_names = [n for n in all_names if n in names]
    rows = []
    for n in all_names:
        have = [r for r in roots if n in found[r]]
        st = {r: skill_state(r / n) for r in have}
        missing = [str(r) for r in roots if r not in have]
        norms = {json.dumps(st[r]["norm"], sort_keys=True) for r in have}
        raws = {json.dumps(st[r]["raw"], sort_keys=True) for r in have}
        src = max(have, key=lambda r: st[r]["newest"])
        row = {"name": n, "have": [str(r) for r in have], "missing": missing, "source": str(src)}
        if len(norms) > 1:
            row["state"] = "DRIFTED"
            keys = set().union(*(st[r]["norm"] for r in have))
            row["files"] = sorted(k for k in keys if len({st[r]["norm"].get(k) for r in have}) > 1)
            other = next(r for r in have if r != src)
            row["skill_md"] = _first_diff(src / n / "SKILL.md", other / n / "SKILL.md")
        elif len(raws) > 1:
            row["state"] = "EOL-ONLY"
        else:
            row["state"] = "SAME"
        if missing and row["state"] == "SAME":
            row["state"] = "MISSING"
        rows.append(row)
    return rows


def plan_lines(rows: list) -> list:
    out = []
    for r in rows:
        targets = list(r["missing"]) + ([h for h in r["have"] if h != r["source"]] if r["state"] == "DRIFTED" else [])
        for t in targets:
            out.append(f'Copy-Item -Recurse -Force "{Path(r["source"]) / r["name"]}" "{Path(t)}\\"   # {r["state"]}')
    return out


def _selftest() -> bool:
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        a, b = t / "user", t / "proj"
        for root in (a, b):
            (root / "same").mkdir(parents=True)
            (root / "same" / "SKILL.md").write_text("---\nname: same\n---\nbody\n", encoding="utf-8")
            (root / "same" / "__pycache__").mkdir()
        (a / "same" / "__pycache__" / "x.pyc").write_bytes(b"1")
        (a / "same" / "__pycache__" / "note.txt").write_bytes(b"run 1")
        (b / "same" / "__pycache__" / "x.pyc").write_bytes(b"2")
        (a / "onlyuser").mkdir()
        (a / "onlyuser" / "SKILL.md").write_text("x", encoding="utf-8")
        for root, desc in ((a, "Files are ground truth"), (b, "How to write the final report")):
            (root / "receipt-report").mkdir()
            (root / "receipt-report" / "SKILL.md").write_text(f"---\nname: receipt-report\ndescription: {desc}\n---\n",
                                                              encoding="utf-8")
        import os
        os.utime(b / "receipt-report" / "SKILL.md", (1, 1))
        (a / "eol").mkdir()
        (b / "eol").mkdir()
        (a / "eol" / "SKILL.md").write_bytes(b"a\r\nb\r\n")
        (b / "eol" / "SKILL.md").write_bytes(b"a\nb\n")
        (b / "notaskill").mkdir()
        rows = {r["name"]: r for r in audit([str(a), str(b)])}
        ok["identical copies (pycache ignored) -> SAME"] = rows["same"]["state"] == "SAME"
        ok["skill in one root only -> MISSING with the root named"] = rows["onlyuser"]["state"] == "MISSING" and \
            rows["onlyuser"]["missing"] == [str(b)]
        r = rows["receipt-report"]
        ok["different descriptions -> DRIFTED, SKILL.md named, line 3 shown"] = r["state"] == "DRIFTED" and \
            r["files"] == ["SKILL.md"] and r["skill_md"].startswith("line 3")
        ok["newest copy proposed as source"] = r["source"] == str(a)
        ok["CRLF vs LF only -> EOL-ONLY, not DRIFTED"] = rows["eol"]["state"] == "EOL-ONLY"
        ok["folder without SKILL.md is not a skill"] = "notaskill" not in rows
        pl = plan_lines(list(rows.values()))
        ok["plan copies missing and drifted only, from the source"] = len(pl) == 2 and all(str(a) in x.split('" "')[0] for x in pl)
        ok["main: drift -> exit 1, synced subset -> 0, bad arg -> 2"] = (main([str(a), str(b)]) == 1 and
                                                                         main([str(a), str(b), "--names", "same"]) == 0
                                                                         and main(["--bogus"]) == 2)
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
    roots, names, plan, as_json = [], None, False, False
    it = iter(argv)
    for x in it:
        if x == "--names":
            names = [s.strip() for s in next(it, "").split(",") if s.strip()]
        elif x == "--plan":
            plan = True
        elif x == "--json":
            as_json = True
        elif x.startswith("--"):
            print(f"unknown argument {x}", file=sys.stderr)
            return 2
        else:
            roots.append(x)
    if len(roots) < 2:
        print("give at least two skill roots", file=sys.stderr)
        return 2
    rows = audit(roots, names)
    bad = [r for r in rows if r["state"] != "SAME"]
    if as_json:
        print(json.dumps(rows, indent=1))
    else:
        for r in bad:
            extra = f" missing from {', '.join(r['missing'])}" if r["missing"] else ""
            if r["state"] == "DRIFTED":
                extra += f" files {', '.join(r['files'][:6])}; SKILL.md {r['skill_md']}; newest in {r['source']}"
            print(f"{r['state']:<9} {r['name']}{extra}")
        counts = {s: sum(r["state"] == s for r in rows) for s in ("SAME", "EOL-ONLY", "DRIFTED", "MISSING")}
        print(f"{len(rows)} skills: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        if plan:
            print("\n".join(plan_lines(bad)))
    return 1 if any(r["state"] in ("DRIFTED", "MISSING") for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
