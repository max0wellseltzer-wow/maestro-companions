"""Shared helpers for the speed-proof eval checkers (check_e1.py, check_e2.py, check_e3.py).

A checker gets the directory a subagent worked in (a copy of a fixture repo it modified) and prints a JSON list of
{"text": assertion, "passed": bool, "evidence": str} for the assertions a script can decide. The grader subagent merges these
with its own reading of the transcript for the rest. Nothing here edits the run directory: every mutation happens on a copy.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import bench

STDLIB = set(getattr(sys, "stdlib_module_names", set()))


def fresh_fixture(which: str, tmp: Path, **kw: Any) -> Path:
    """The ORIGINAL fixture, regenerated into tmp/orig (same seed, same sizes) - the reference the candidate is held to."""
    out = tmp / "orig"
    args = [sys.executable, str(HERE / "make_fixtures.py"), which, str(out)]
    for k, v in kw.items():
        args += [f"--{k}", str(v)]
    subprocess.run(args, check=True, capture_output=True)
    return out


def copy_repo(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return dst


def run(argv: list[str], cwd: Path, timeout: float = 300) -> dict[str, Any]:
    """stdout/stderr/exit of one command (python commands get CPU seconds, as bench.py measures them)."""
    return bench.run_once(argv, cwd) if argv and argv[0] == "python" else _plain(argv, cwd, timeout)


def _plain(argv: list[str], cwd: Path, timeout: float) -> dict[str, Any]:
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                       timeout=timeout)
    return {"wall": None, "cpu": None, "exit": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


def cpu_min(argv: list[str], cwd: Path, n: int = 3) -> float:
    bench.run_once(argv, cwd)
    return min(bench.run_once(argv, cwd)["cpu"] or float("inf") for _ in range(n))


def same_stdout(a: dict[str, Any], b: dict[str, Any], drop_first_line: bool = False) -> bool:
    x, y = a["stdout"].replace("\r\n", "\n"), b["stdout"].replace("\r\n", "\n")
    if drop_first_line:
        x, y = x.partition("\n")[2], y.partition("\n")[2]
    return x == y


def git_commits(repo: Path) -> list[dict[str, Any]]:
    """Commits oldest first with the files each touched (empty list when the directory is not a git repo)."""
    r = subprocess.run(["git", "log", "--reverse", "--format=%H%x00%s", "--name-only"], cwd=repo, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", check=False)
    if r.returncode != 0:
        return []
    out: list[dict[str, Any]] = []
    for ln in r.stdout.splitlines():                     # a header line (hash NUL subject) starts a commit; the rest are files
        if "\x00" in ln:
            h, _, subject = ln.partition("\x00")
            out.append({"hash": h, "subject": subject, "files": []})
        elif ln.strip() and out:
            out[-1]["files"].append(ln.strip().replace("\\", "/"))
    return out


def first_commit_touching(commits: list[dict[str, Any]], pred: Any) -> int | None:
    for i, c in enumerate(commits):
        if i == 0:
            continue                                     # the fixture commit itself
        if any(pred(f) for f in c["files"]):
            return i
    return None


def sha_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sha_raw(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_text(repo: Path, patterns: tuple[str, ...] = ("*.md", "*.txt", "*.json", "*.py", "*.toml", "*.cfg")) -> str:
    chunks = []
    for pat in patterns:
        for p in sorted(repo.rglob(pat)):
            if any(part in (".git", "__pycache__") for part in p.parts):
                continue
            try:
                chunks.append(f"\n### {p.relative_to(repo).as_posix()}\n" + p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(chunks)


def transcript_text(run_dir: Path) -> str:
    """Whatever the subagent left as its account: outputs/TRANSCRIPT.md, REPORT.md, user_notes.md, plus the repo's text."""
    parts = []
    for p in sorted(run_dir.glob("*")):                 # the subagent's own files beside repo/: REPORT, TRANSCRIPT, plant runs ...
        if p.is_file() and p.suffix.lower() in (".md", ".txt", ".json", ".log"):
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def non_stdlib_imports(repo: Path) -> list[str]:
    import ast
    local = {p.stem for p in repo.rglob("*.py")} | {p.name for p in repo.iterdir() if p.is_dir()}
    bad = []
    for p in sorted(repo.rglob("*.py")):
        if any(part in (".git", "__pycache__") for part in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            bad.append(f"{p.name}: syntax error")
            continue
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for n in names:
                top = n.split(".")[0]
                if top not in STDLIB and top not in local and top not in ("__future__",):
                    bad.append(f"{p.relative_to(repo).as_posix()}: {n}")
    return sorted(set(bad))


def planted_bug_lines(text: str) -> list[str]:
    """Lines that report a planted bug's fate: KILLED/SURVIVED/MISSING verdicts, or prose ('planted ... turned the suite red')."""
    return [ln.strip() for ln in text.splitlines()
            if re.search(r"\b(KILLED|SURVIVED|MISSING)\b", ln, re.IGNORECASE)
            or (re.search(r"plant", ln, re.IGNORECASE) and re.search(r"\b(red|fail|kill|caught|revert)", ln, re.IGNORECASE))]


def result(text: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {"text": text, "passed": bool(passed), "evidence": evidence[:600]}


def emit(results: list[dict[str, Any]]) -> int:
    print(json.dumps(results, indent=1))
    return 0 if all(r["passed"] for r in results) else 1


def tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="speedproof-check-"))
