"""pyc_fresh - run a test command so Python can neither READ nor WRITE a stale bytecode cache (plant-the-bug).

Python trusts a cached .pyc whose header matches the source's SIZE and whole-second MTIME. A planted bug that keeps
the file the same size, applied and restored within the same second, can therefore run the OLD code: a false
KILLED or a false SURVIVED (errata E26, 2026-10-15). PYTHONDONTWRITEBYTECODE=1 alone stops new writes but still
READS a .pyc left by an earlier run. This wrapper points PYTHONPYCACHEPREFIX at a fresh empty folder (reads and
writes both go there) and sets PYTHONDONTWRITEBYTECODE=1, then deletes the folder.

    python plant_runner.py cases.json --cwd . -- python pyc_fresh.py -- python -m pytest tests/test_x.py -q -x
    python pyc_fresh.py -- <any command>         # exit code is the command's
    python pyc_fresh.py --selftest               # reproduces the stale-pyc false verdict, then shows the fix
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile


def fresh_env(base: dict | None = None) -> tuple[dict, str]:
    prefix = tempfile.mkdtemp(prefix="pyc_fresh_")
    env = {**(os.environ if base is None else base), "PYTHONPYCACHEPREFIX": prefix, "PYTHONDONTWRITEBYTECODE": "1"}
    return env, prefix


def run(cmd: list[str], cwd: str | None = None) -> int:
    env, prefix = fresh_env()
    try:
        return subprocess.run(cmd, cwd=cwd, env=env).returncode
    finally:
        shutil.rmtree(prefix, ignore_errors=True)


def _selftest() -> bool:
    from pathlib import Path
    ok: dict[str, bool] = {}
    d = Path(tempfile.mkdtemp(prefix="pyc_fresh_selftest_"))
    try:
        mod = d / "m.py"
        mod.write_bytes(b"VALUE = 1\n")
        st = os.stat(mod)
        probe = [sys.executable, "-c", "import m; print(m.VALUE)"]
        plain = {k: v for k, v in os.environ.items() if k not in ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")}
        first = subprocess.run(probe, cwd=d, env=plain, capture_output=True, text=True).stdout.strip()
        ok["baseline import writes a cache and prints 1"] = first == "1" and any((d / "__pycache__").glob("m.*.pyc"))
        mod.write_bytes(b"VALUE = 2\n")                      # the planted bug: same size ...
        os.utime(mod, ns=(st.st_atime_ns, st.st_mtime_ns))   # ... and the same mtime (same second, as in E26)
        stale = subprocess.run(probe, cwd=d, env=plain, capture_output=True, text=True).stdout.strip()
        ok["hazard reproduced: a plain run still prints 1 (stale cache)"] = stale == "1"
        dont_write = {**plain, "PYTHONDONTWRITEBYTECODE": "1"}
        half = subprocess.run(probe, cwd=d, env=dont_write, capture_output=True, text=True).stdout.strip()
        ok["PYTHONDONTWRITEBYTECODE alone is NOT enough (still prints 1)"] = half == "1"
        env, prefix = fresh_env(plain)
        try:
            fixed = subprocess.run(probe, cwd=d, env=env, capture_output=True, text=True).stdout.strip()
            ok["fresh cache prefix runs the planted code (prints 2)"] = fixed == "2"
            ok["nothing written into the fresh prefix"] = not any(Path(prefix).rglob("*.pyc"))
        finally:
            shutil.rmtree(prefix, ignore_errors=True)
        ok["run() passes the command's exit code through"] = run([sys.executable, "-c", "raise SystemExit(3)"]) == 3
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        print(__doc__)
        return 2
    return run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
