"""ratify - the point-of-view family's ratification gate (ships with pov-core).

A lens is RATIFIED by the machine when all four hold (the user's own sign-off is the fifth, recorded with --max):
  R1 member     its tool imports pov_core and defines apply()  (the family roster is discovered, never hand-kept)
  R2 selftest   `python -B <tool> --selftest` exits 0, prints >= 6 PASS and no FAIL, and names a planted case
  R3 health     skill-health --only <name> gives 0 FAIL / 0 WARN
  R4 distinct   on every shared probe kind it reads, its view overlaps no sibling's at >= 0.8 (pov_core.distinctness)

    python ratify.py --all           # ratify every family member, write RATIFIED.jsonl beside this file, print a table
    python ratify.py --only a,b      # just these
    python ratify.py --max a,b       # record the user's sign-off on lenses that already passed R1-R4
    python ratify.py --selftest
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SK = HERE.parent
sys.path.insert(0, str(HERE))
from pov_core import PROBES, distinctness, report   # noqa: E402

LEDGER = HERE / "RATIFIED.jsonl"


def members(root: Path = SK) -> dict:
    """{name: tool_path} for every skill whose tool imports pov_core and defines apply()."""
    out = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "pov-core"):
        for py in sorted(d.glob("*.py")):
            src = py.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*from pov_core import|^\s*import pov_core", src, re.M) and re.search(r"^def apply\(", src, re.M):
                out[d.name] = py
                break
    return out


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"lens_{name.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(path.parent))
    return mod


def selftest_ok(path: Path, timeout: int = 60) -> tuple:
    try:
        p = subprocess.run([sys.executable, "-B", str(path), "--selftest"], capture_output=True, text=True,
                           timeout=timeout, cwd=tempfile.gettempdir(), encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "timeout"
    passes = len(re.findall(r"^PASS ", p.stdout, re.M))
    fails = len(re.findall(r"^FAIL ", p.stdout, re.M))
    planted = bool(re.search(r"^PASS .*(planted|bad input|refus|reject)", p.stdout, re.M | re.I))
    ok = p.returncode == 0 and passes >= 6 and fails == 0 and planted
    return ok, f"exit {p.returncode}, {passes} PASS, {fails} FAIL, planted={planted}"


def health_ok(names: list, timeout: int = 900) -> dict:
    tool = SK / "skill-health" / "skill_health.py"
    if not tool.exists():
        return {n: (False, "skill-health missing") for n in names}
    p = subprocess.run([sys.executable, "-B", str(tool), "--only", ",".join(names)], capture_output=True, text=True,
                       timeout=timeout, cwd=tempfile.gettempdir(), encoding="utf-8", errors="replace")
    bad = set(re.findall(r"^(?:FAIL|WARN) (\S+)", p.stdout, re.M))
    return {n: (n not in bad, "0 FAIL / 0 WARN" if n not in bad else "flagged") for n in names}


def probe_views(mods: dict) -> dict:
    """{kind: {lens: view}} - every lens run on each shared probe it can read (errors = cannot read that kind)."""
    out = {}
    for kind, subject in PROBES.items():
        for name, mod in mods.items():
            kinds = getattr(mod, "KINDS", None)
            if kinds is not None and kind not in kinds:
                continue
            try:
                v = mod.apply(subject, kind=kind)
            except Exception:
                continue
            if isinstance(v, dict) and "findings" in v:
                out.setdefault(kind, {})[name] = v
    return out


def ratify(only=None, root: Path = SK, ledger: Path = LEDGER, threshold: float = 0.8) -> list:
    fam = members(root)
    names = [n for n in fam if not only or n in only]
    mods = {}
    for n, p in fam.items():
        try:
            mods[n] = _load(n, p)
        except Exception:
            pass
    views = probe_views(mods)
    twins = {}
    for kind, vs in views.items():
        for a, b, j in distinctness(vs, threshold):
            twins.setdefault(a, []).append(f"{b}@{kind}:{j}")
            twins.setdefault(b, []).append(f"{a}@{kind}:{j}")
    health = health_ok(names) if names else {}
    rows = []
    for n in names:
        st = selftest_ok(fam[n])
        r = {"lens": n, "R1_member": n in mods, "R2_selftest": st[0], "R2_detail": st[1],
             "R3_health": health.get(n, (False, ""))[0],
             "R4_distinct": n not in twins, "R4_detail": twins.get(n, []),
             "probe_kinds": sorted(k for k, vs in views.items() if n in vs)}
        r["machine_ratified"] = r["R1_member"] and r["R2_selftest"] and r["R3_health"] and r["R4_distinct"]
        r["ts"] = time.strftime("%Y-%m-%d %H:%M")
        rows.append(r)
    with open(ledger, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return rows


def max_signoff(names: list, ledger: Path = LEDGER) -> list:
    latest = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if "lens" in r:
                latest[r["lens"]] = r
    done = []
    with open(ledger, "a", encoding="utf-8") as fh:
        for n in names:
            if latest.get(n, {}).get("machine_ratified"):
                fh.write(json.dumps({"lens": n, "max_ratified": True, "ts": time.strftime("%Y-%m-%d %H:%M")}) + "\n")
                done.append(n)
    return done


def _selftest() -> bool:
    import shutil
    ok = {}
    tmp = Path(tempfile.mkdtemp(prefix="pov_ratify_"))
    try:
        lib = tmp / "lib"
        (lib / "pov-core").mkdir(parents=True)
        shutil.copy(HERE / "pov_core.py", lib / "pov-core" / "pov_core.py")
        lens_src = ('import sys\nfrom pathlib import Path\nsys.dont_write_bytecode = True\n'
                    'sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pov-core"))\n'
                    'from pov_core import load_subject, view, report, run_cli\nKINDS = {"text"}\n'
                    'def apply(subject, kind=None, **o):\n    k, t = load_subject(subject, "text")\n'
                    '    return view(NAME, k, [{"what": w} for w in WORDS(t)], "s")\n'
                    'def _selftest():\n    ok = {f"check {i}": True for i in range(5)}\n'
                    '    ok["planted bad input rejected"] = PLANTED\n    return report(ok)\n'
                    'def main(a): return run_cli(NAME, apply, a, _selftest)\n'
                    'if __name__ == "__main__": sys.exit(main(sys.argv[1:]))\n')
        for name, words, planted in [("lens-a", "lambda t: t.split()[:5]", "True"),
                                     ("lens-b", "lambda t: t.split()[:5]", "True"),
                                     ("lens-c", "lambda t: [str(len(t)) + ' characters counted']", "False")]:
            (lib / name).mkdir()
            (lib / name / "lens.py").write_text(lens_src.replace("NAME", repr(name)).replace("WORDS", f"({words})")
                                                .replace("PLANTED", planted), encoding="utf-8")
        (lib / "not-a-lens").mkdir()
        (lib / "not-a-lens" / "tool.py").write_text("def apply(x): return x\n", encoding="utf-8")
        fam = members(lib)
        ok["members() finds exactly the lenses (imports pov_core + defines apply)"] = sorted(fam) == ["lens-a", "lens-b", "lens-c"]
        mods = {n: _load(n, p) for n, p in fam.items()}
        views = probe_views(mods)
        pairs = distinctness(views["text"])
        ok["R4 flags the renamed twins a/b and passes the different lens c"] = [(a, b) for a, b, _ in pairs] == [("lens-a", "lens-b")]
        ok["R2 passes a lens with >=6 PASS and a planted check"] = selftest_ok(fam["lens-a"])[0]
        ok["R2 refuses a lens whose planted check FAILs (planted bad input)"] = not selftest_ok(fam["lens-c"])[0]
        ledger = tmp / "R.jsonl"
        with open(ledger, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"lens": "lens-a", "machine_ratified": True}) + "\n")
            fh.write(json.dumps({"lens": "lens-b", "machine_ratified": False}) + "\n")
        ok["the user sign-off is recorded only on machine-ratified lenses"] = max_signoff(["lens-a", "lens-b"], ledger) == ["lens-a"]
        ok["probe views carry the lens kinds it reads (text only)"] = sorted(views) == ["text"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return report(ok)


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "--max":
        print("the user sign-off recorded:", ", ".join(max_signoff(argv[1].split(","))) or "none (not machine-ratified)")
        return 0
    if argv[0] not in ("--all", "--only"):
        print(__doc__)
        return 2
    only = set(argv[1].split(",")) if argv[0] == "--only" and len(argv) > 1 else None
    rows = ratify(only)
    good = [r for r in rows if r["machine_ratified"]]
    for r in rows:
        if not r["machine_ratified"]:
            print(f"NOT RATIFIED {r['lens']}: member={r['R1_member']} selftest={r['R2_detail']} "
                  f"health={r['R3_health']} twins={r['R4_detail']}")
    print(f"family: {len(rows)} lenses, {len(good)} machine-ratified, {len(rows) - len(good)} not")
    return 0 if len(good) == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
