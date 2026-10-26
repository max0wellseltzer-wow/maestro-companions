"""bench.py: declare a benchmark before the candidate exists, measure it, and compare answers and CPU seconds.

    python bench.py declare bench.json --tree DIR [--repeat 5] --out bench/baseline.json
    python bench.py measure bench.json --tree DIR [--repeat 5] --out bench/candidate.json
    python bench.py pair    bench.json --old DIR --new DIR [--repeat 5] --out-dir bench/     # interleaved old/new runs
    python bench.py compare bench/baseline.json bench/candidate.json [--target 3]
    python bench.py sources bench/baseline.json --tree DIR                                 # were these the sources measured?

bench.json:
    {"target": 3,
     "commands": {"report": ["python", "report.py", "data.csv"],
                  "build":  {"argv": ["python", "build.py"], "target": null}},     # null: must stay identical, no speed target
     "strip": {"report": ["^generated: .*$"]},                                     # regexes; matching LINES are dropped
     "drop_json_keys": {"api": ["seconds", "source"]}}                             # if stdout is JSON, drop these top-level keys

What is recorded, per command: CPU seconds (user+system of the child, measured INSIDE the child with time.process_time() at
exit, because on Windows a parent cannot read a child's CPU time), min and median of N after one untimed warm-up; wall seconds;
exit code; a fingerprint (sha256 of stdout after the strips); and the full stdout/stderr, so a mismatch is diffable. Per file:
the tree's git head and the sha256 of every *.py under it, the target, and when it was declared. Only "python ..." commands get
CPU seconds; anything else is timed by wall clock only (cpu = null).

compare exits 0 when every fingerprint and exit code match and every command with a target meets it; 1 on a different answer,
2 on a missed target, 3 on a different exit code. It is a test, and a plant-the-bug oracle. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WRAP = ("import atexit, runpy, sys, time\n"
        "atexit.register(lambda: sys.__stderr__.write('\\n@@CPU=%.6f\\n' % time.process_time()))\n"
        "args = sys.argv[1:]\n"
        "if args and args[0] == '-m':\n"
        "    sys.argv = args[1:]\n"
        "    runpy.run_module(args[1], run_name='__main__', alter_sys=True)\n"
        "elif args and args[0] == '-c':\n"
        "    sys.argv = ['-c'] + args[2:]\n"
        "    exec(compile(args[1], '<string>', 'exec'), {'__name__': '__main__'})\n"
        "else:\n"
        "    sys.argv = args\n"
        "    runpy.run_path(args[0], run_name='__main__')\n")
CPU_MARK = re.compile(r"\n?@@CPU=([0-9.]+)\n?")


def load_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    cmds: dict[str, dict[str, Any]] = {}
    for name, c in spec["commands"].items():
        if isinstance(c, list):
            c = {"argv": c}
        cmds[name] = {"argv": list(c["argv"]), "target": c.get("target", spec.get("target"))}
    return {"commands": cmds, "strip": spec.get("strip", {}), "drop_json_keys": spec.get("drop_json_keys", {}),
            "target": spec.get("target")}


def fingerprint(stdout: str, strips: list[str], drop_keys: list[str]) -> str:
    text = stdout.replace("\r\n", "\n")
    if drop_keys:
        try:
            rep = json.loads(text)
            if isinstance(rep, dict):
                for k in drop_keys:
                    rep.pop(k, None)
                text = json.dumps(rep, sort_keys=True)
        except ValueError:
            pass
    if strips:
        pats = [re.compile(p) for p in strips]
        text = "\n".join(ln for ln in text.split("\n") if not any(p.search(ln) for p in pats))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_once(argv: list[str], tree: Path) -> dict[str, Any]:
    """One execution: wall seconds, CPU seconds (python commands only), exit code, stdout, stderr."""
    is_py = argv and argv[0] in ("python", "python3", sys.executable)
    cmd = [sys.executable, "-c", WRAP, *argv[1:]] if is_py else list(argv)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"} if is_py else None   # the child writes UTF-8 (Windows would use cp1252)
    t0 = time.perf_counter()
    r = subprocess.run(cmd, cwd=tree, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, env=env)
    wall = time.perf_counter() - t0
    err = r.stderr
    cpu = None
    if is_py:
        marks = CPU_MARK.findall(err)
        cpu = float(marks[-1]) if marks else None
        err = CPU_MARK.sub("\n", err)
    return {"wall": wall, "cpu": cpu, "exit": r.returncode, "stdout": r.stdout, "stderr": err}


def sources_of(tree: Path) -> dict[str, str]:
    out = {}
    for p in sorted(tree.rglob("*.py")):
        if any(part in (".git", "__pycache__", "bench") for part in p.parts):
            continue
        out[p.relative_to(tree).as_posix()] = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return out


def git_head(tree: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def measure_tree(spec: dict[str, Any], tree: Path, repeat: int, say: Any = print) -> dict[str, Any]:
    """Every command, one warm-up then `repeat` timed runs; the record described in the module docstring."""
    out: dict[str, Any] = {"meta": {"tree": str(tree.resolve()), "git_head": git_head(tree), "sources": sources_of(tree),
                                    "python": sys.version.split()[0], "repeat": repeat, "target": spec["target"],
                                    "declared_utc": datetime.now(UTC).isoformat(timespec="seconds")}, "commands": {}}
    for name, c in spec["commands"].items():
        run_once(c["argv"], tree)
        runs = [run_once(c["argv"], tree) for _ in range(repeat)]
        out["commands"][name] = _summarise(name, c, spec, runs)
        say(_line(name, out["commands"][name]))
    return out


def _summarise(name: str, c: dict[str, Any], spec: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    last = runs[-1]
    cpus = [r["cpu"] for r in runs if r["cpu"] is not None]
    fps = {fingerprint(r["stdout"], spec["strip"].get(name, []), spec["drop_json_keys"].get(name, [])) for r in runs}
    return {"argv": c["argv"], "target": c["target"],
            "cpu_min_s": round(min(cpus), 4) if cpus else None, "cpu_median_s": round(statistics.median(cpus), 4) if cpus else None,
            "cpu_runs": [round(x, 4) for x in cpus], "wall_min_s": round(min(r["wall"] for r in runs), 4),
            "wall_runs": [round(r["wall"], 4) for r in runs], "exit": sorted({r["exit"] for r in runs}),
            "fingerprint": sorted(fps), "stdout": last["stdout"], "stderr": last["stderr"]}


def _line(name: str, rec: dict[str, Any]) -> str:
    cpu = f"cpu min {rec['cpu_min_s']:.3f} med {rec['cpu_median_s']:.3f}" if rec["cpu_min_s"] is not None else "cpu n/a"
    fp = rec["fingerprint"][0][:12] + ("" if len(rec["fingerprint"]) == 1 else " UNSTABLE")
    return f"{name:<24} {cpu}  wall min {rec['wall_min_s']:.3f}  exit {rec['exit']}  answer {fp}"


def measure_pair(spec: dict[str, Any], old: Path, new: Path, repeat: int, say: Any = print) -> tuple[dict, dict]:
    """Old and new interleaved (old, new, old, new ...) so a drift in the machine's load hits both alike."""
    recs = {k: {"meta": {"tree": str(t.resolve()), "git_head": git_head(t), "sources": sources_of(t),
                         "python": sys.version.split()[0], "repeat": repeat, "target": spec["target"],
                         "declared_utc": datetime.now(UTC).isoformat(timespec="seconds")}, "commands": {}}
            for k, t in (("old", old), ("new", new))}
    for name, c in spec["commands"].items():
        runs: dict[str, list[dict[str, Any]]] = {"old": [], "new": []}
        for k, t in (("old", old), ("new", new)):
            run_once(c["argv"], t)
        for _ in range(repeat):
            for k, t in (("old", old), ("new", new)):
                runs[k].append(run_once(c["argv"], t))
        for k in ("old", "new"):
            recs[k]["commands"][name] = _summarise(name, c, spec, runs[k])
            say(f"{k:<4} " + _line(name, recs[k]["commands"][name]))
    return recs["old"], recs["new"]


def compare(base: dict[str, Any], cand: dict[str, Any], target: float | None = None, say: Any = print) -> int:
    code = 0
    say(f"{'command':<24} {'before':>9} {'after':>9} {'ratio':>7}  answers")
    for name, b in base["commands"].items():
        c = cand["commands"].get(name)
        if c is None:
            say(f"{name:<24} {'':>9} {'':>9} {'':>7}  MISSING from the candidate")
            code = max(code, 1)
            continue
        same = b["fingerprint"] == c["fingerprint"] and len(c["fingerprint"]) == 1
        if b["exit"] != c["exit"]:
            code = max(code, 3)
        if not same:
            code = max(code, 1)
        want = target if target is not None else b.get("target")
        bm, cm = b["cpu_min_s"] if b["cpu_min_s"] is not None else b["wall_min_s"], \
            c["cpu_min_s"] if c["cpu_min_s"] is not None else c["wall_min_s"]
        ratio = (bm / cm) if cm else float("inf")
        met = "" if want is None else (" target met" if ratio >= want else f" TARGET {want}x MISSED")
        if want is not None and ratio < want:
            code = max(code, 2)
        say(f"{name:<24} {bm:>9.3f} {cm:>9.3f} {ratio:>6.2f}x  "
            + ("IDENTICAL" if same else "DIFFERENT") + ("" if b["exit"] == c["exit"] else f" exit {b['exit']}->{c['exit']}") + met)
    unit = "CPU seconds, min of N" if all(v["cpu_min_s"] is not None for v in base["commands"].values()) else "wall seconds"
    say(f"({unit}; before N={base['meta']['repeat']} after N={cand['meta']['repeat']}; "
        f"before declared {base['meta']['declared_utc']})")
    return code


def _selftest() -> bool:
    """Hermetic: two tiny temp trees (slow vs fast, same answer) plus planted wrong-answer and wrong-exit trees."""
    import shutil
    import tempfile
    ok: dict[str, bool] = {}
    root = Path(tempfile.mkdtemp(prefix="bench_selftest_"))
    quiet = lambda *_: None
    try:
        progs = {"old": "s = 0\nfor i in range(300000):\n    s += i\nprint('generated: now')\nprint(s)\n",
                 "new": "print('generated: later')\nprint(sum(range(300000)))\n",
                 "wrong": "print('generated: x')\nprint(sum(range(300001)))\n",
                 "crash": "print('generated: x')\nprint(sum(range(300000)))\nraise SystemExit(4)\n"}
        trees = {}
        for k, src in progs.items():
            trees[k] = root / k
            trees[k].mkdir()
            (trees[k] / "job.py").write_text(src, encoding="utf-8")
        spec = {"commands": {"job": {"argv": ["python", "job.py"], "target": None}},
                "strip": {"job": ["^generated: .*$"]}, "drop_json_keys": {}, "target": None}
        ok["strip regexes remove volatile lines from the answer"] = (
            fingerprint("generated: a\n42\n", ["^generated: .*$"], []) == fingerprint("generated: b\n42\n", ["^generated: .*$"], []))
        ok["drop_json_keys ignores the named keys only"] = (
            fingerprint('{"v": 1, "seconds": 3}', [], ["seconds"]) == fingerprint('{"v": 1, "seconds": 9}', [], ["seconds"])
            and fingerprint('{"v": 1}', [], ["seconds"]) != fingerprint('{"v": 2}', [], ["seconds"]))
        old, new = measure_pair(spec, trees["old"], trees["new"], 1, say=quiet)
        ok["same answer, no target: compare exits 0"] = compare(old, new, say=quiet) == 0
        ok["python commands get CPU seconds measured in the child"] = old["commands"]["job"]["cpu_min_s"] is not None
        ok["an unmeetable target exits 2"] = compare(old, new, target=1e9, say=quiet) == 2
        wrong = measure_tree(spec, trees["wrong"], 1, say=quiet)
        ok["planted different answer exits 1"] = compare(old, wrong, say=quiet) == 1
        crash = measure_tree(spec, trees["crash"], 1, say=quiet)
        ok["planted different exit code exits 3"] = compare(old, crash, say=quiet) == 3
        before = sources_of(trees["new"])
        (trees["new"] / "job.py").write_text(progs["new"] + "# edited\n", encoding="utf-8")
        ok["sources_of notices an edited file"] = sources_of(trees["new"]) != before
    finally:
        shutil.rmtree(root, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1
    ap = argparse.ArgumentParser(prog="bench.py", description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("declare", "measure"):
        p = sub.add_parser(name)
        p.add_argument("spec", type=Path)
        p.add_argument("--tree", type=Path, default=Path("."))
        p.add_argument("--repeat", type=int, default=5)
        p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("pair")
    p.add_argument("spec", type=Path)
    p.add_argument("--old", type=Path, required=True)
    p.add_argument("--new", type=Path, required=True)
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--out-dir", type=Path, required=True)
    p = sub.add_parser("compare")
    p.add_argument("baseline", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--target", type=float, default=None, help="override the declared target ratio")
    p = sub.add_parser("sources")
    p.add_argument("record", type=Path)
    p.add_argument("--tree", type=Path, default=Path("."))
    a = ap.parse_args(argv)
    if a.cmd in ("declare", "measure"):
        spec = load_spec(a.spec)
        rec = measure_tree(spec, a.tree, a.repeat)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"wrote {a.out} ({a.cmd}; {len(rec['commands'])} commands; sources hashed: {len(rec['meta']['sources'])})")
        return 0
    if a.cmd == "pair":
        spec = load_spec(a.spec)
        old, new = measure_pair(spec, a.old, a.new, a.repeat)
        a.out_dir.mkdir(parents=True, exist_ok=True)
        (a.out_dir / "old.json").write_text(json.dumps(old, indent=1), encoding="utf-8")
        (a.out_dir / "new.json").write_text(json.dumps(new, indent=1), encoding="utf-8")
        return compare(old, new)
    if a.cmd == "compare":
        return compare(json.loads(a.baseline.read_text(encoding="utf-8")), json.loads(a.candidate.read_text(encoding="utf-8")),
                       a.target)
    rec = json.loads(a.record.read_text(encoding="utf-8"))
    now = sources_of(a.tree)
    diff = sorted(k for k in set(rec["meta"]["sources"]) | set(now) if rec["meta"]["sources"].get(k) != now.get(k))
    print("the recorded sources equal this tree" if not diff else f"these sources differ from the record: {diff}")
    return 0 if not diff else 1


if __name__ == "__main__":
    raise SystemExit(main())
