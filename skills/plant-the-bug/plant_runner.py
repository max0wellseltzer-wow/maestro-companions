"""Portable plant-the-bug runner: apply hand-written mutation cases one at a time, run a test command, report verdicts.

Each case is {"file": "path/relative/to/cwd", "old": "exact text", "new": "replacement"}. The case is applied to the
FIRST occurrence only, byte for byte (line endings survive because the file is read and written as bytes), the test
command runs with the given cwd, and the original bytes are put back in a `finally:` block even if the run is
interrupted. Verdicts: KILLED (test command exited non-zero), SURVIVED (exited 0), MISSING (old text not in the file),
TIMEOUT (counted as killed but reported separately). This is the generic, repo-free version; inside the Autotrade repo the
repo tool `tools/plant.py` remains the in-repo option.

Usage:
    python plant_runner.py cases.json [--cwd DIR] [--timeout SEC] -- <test command ...>
    python plant_runner.py --selftest
Library:
    from plant_runner import run_cases
    results = run_cases(cases, ["python", "-m", "pytest", "-q", "-x"], cwd=".")
"""
import json
import os
import subprocess
import sys
import tempfile


def apply_case(path, old, new):
    """Return (original_bytes, mutated_bytes) or (original_bytes, None) when old is not present."""
    with open(path, "rb") as f:
        original = f.read()
    old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
    idx = original.find(old_b)
    if idx < 0 or not old_b:
        return original, None
    return original, original[:idx] + new_b + original[idx + len(old_b):]


def run_cases(cases, command, cwd=".", timeout=300):
    """Run every case; return a list of dicts {i, file, old, new, verdict, rc}."""
    results = []
    for i, case in enumerate(cases):
        path = os.path.join(cwd, case["file"])
        row = {"i": i, "file": case["file"], "old": case["old"], "new": case["new"], "rc": None}
        if not os.path.isfile(path):
            row["verdict"] = "MISSING"
            results.append(row)
            continue
        original, mutated = apply_case(path, case["old"], case["new"])
        if mutated is None:
            row["verdict"] = "MISSING"
            results.append(row)
            continue
        try:
            with open(path, "wb") as f:
                f.write(mutated)
            try:
                proc = subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      timeout=timeout)
                row["rc"] = proc.returncode
                row["verdict"] = "KILLED" if proc.returncode != 0 else "SURVIVED"
            except subprocess.TimeoutExpired:
                row["verdict"] = "TIMEOUT"
        finally:
            with open(path, "wb") as f:
                f.write(original)
        results.append(row)
    return results


def summarize(results):
    n = len(results)
    k = sum(r["verdict"] in ("KILLED", "TIMEOUT") for r in results)
    s = sum(r["verdict"] == "SURVIVED" for r in results)
    m = sum(r["verdict"] == "MISSING" for r in results)
    return "%d planted bugs: %d killed, %d survived, %d missing" % (n, k, s, m)


def format_report(results):
    lines = []
    for r in results:
        lines.append("%-8s #%d %s: %r -> %r" % (r["verdict"], r["i"], r["file"], r["old"][:40], r["new"][:40]))
    lines.append(summarize(results))
    return "\n".join(lines)


def load_cases(path):
    """Cases from a plant file: a bare list, or {"how_to_run": "...", "run": [argv], "cwd": "...", "cases": [...]}
    (the HEADER says how to run it - 2026-10-21 L5834: a session had to grep the repo to find which runner and test
    a plants/*.json belonged to). List elements without "file" (e.g. {"_header": "..."}) are headers, not cases.
    Returns (cases, header_dict)."""
    with open(path, encoding="utf-8-sig") as f:
        doc = json.load(f)
    header = {}
    if isinstance(doc, dict):
        header = {k: v for k, v in doc.items() if k != "cases"}
        doc = doc.get("cases", [])
    cases = []
    for c in doc:
        if isinstance(c, dict) and "file" in c:
            cases.append(c)
        elif isinstance(c, dict):
            header.update(c)
    return cases, header


def red_on_old(source, command, cwd=".", ref="HEAD", old_bytes=None, timeout=300):
    """Prove a NEW test catches the OLD bug: swap ONLY the source file to its old version (git show REF:path, or
    old_bytes), run the test (must FAIL), restore the new bytes exactly, run again (must PASS).
    Never `git stash` for this: 2026-10-21 (L7139) the stash took the new test with it and the red was invalid."""
    path = os.path.join(cwd, source)
    with open(path, "rb") as f:
        new = f.read()
    if old_bytes is None:
        rel = subprocess.run(["git", "-C", cwd, "ls-files", "--full-name", source], capture_output=True,
                             text=True).stdout.strip()
        r = subprocess.run(["git", "-C", cwd, "show", f"{ref}:{rel or source}"], capture_output=True)
        if r.returncode != 0 or not rel:
            return {"verdict": "NO_OLD_VERSION", "why": r.stderr.decode("utf-8", "replace").strip()[:200]}
        old_bytes = r.stdout
    if old_bytes == new:
        return {"verdict": "SAME_AS_OLD", "why": f"{source} at {ref} equals the working file - nothing to prove"}
    try:
        with open(path, "wb") as f:
            f.write(old_bytes)
        try:
            rc_old = subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc_old = "TIMEOUT"
    finally:
        with open(path, "wb") as f:
            f.write(new)
    rc_new = subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=timeout).returncode
    with open(path, "rb") as f:
        restored = f.read() == new
    if not restored:
        v = "RESTORE_FAILED"
    elif rc_old == 0:
        v = "NOT_RED_ON_OLD"
    elif rc_new != 0:
        v = "NOT_GREEN_ON_NEW"
    else:
        v = "RED_ON_OLD_GREEN_ON_NEW"
    return {"verdict": v, "rc_old": rc_old, "rc_new": rc_new}


def compare(prev, results):
    """Re-score after each rule change (2026-10-20 L2073: a new rule moved 35/1/4 to 33/2/5 and one planted bug
    survived unseen). Cases are matched by (file, old, new); KILLED/TIMEOUT -> SURVIVED/MISSING is a REGRESSION."""
    key = lambda r: (r["file"], r["old"], r["new"])  # noqa: E731
    before = {key(r): r["verdict"] for r in prev}
    good = ("KILLED", "TIMEOUT")
    out = []
    for r in results:
        b = before.get(key(r))
        if b is None:
            out.append(("NEW", r, None))
        elif b in good and r["verdict"] not in good:
            out.append(("REGRESSION", r, b))
        elif b not in good and r["verdict"] in good:
            out.append(("FIXED", r, b))
    return out


def _selftest():
    ok = True

    def check(cond, desc):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + desc)
        ok = ok and bool(cond)

    with tempfile.TemporaryDirectory() as d:
        mod = os.path.join(d, "mod.py")
        src = b"def clamp(x):\r\n    if x < 0:\r\n        return 0\r\n    return x\r\n\r\ndef unused():\r\n    return 1\r\n"
        with open(mod, "wb") as f:
            f.write(src)
        with open(os.path.join(d, "t.py"), "w") as f:
            f.write("import mod\nassert mod.clamp(-5) == 0\nassert mod.clamp(3) == 3\n")
        cmd = [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); import runpy; runpy.run_path('t.py')"]
        cases = [
            {"file": "mod.py", "old": "x < 0", "new": "x > 0"},           # breaks clamp(-5) and clamp(3)
            {"file": "mod.py", "old": "return 0", "new": "return -1"},     # breaks clamp(-5)
            {"file": "mod.py", "old": "return 1", "new": "return 2"},      # unused(): nothing checks it
            {"file": "mod.py", "old": "x <= 0 and", "new": "x"},           # not in file
            {"file": "nope.py", "old": "a", "new": "b"},                   # no such file
        ]
        res = run_cases(cases, cmd, cwd=d, timeout=60)
        v = [r["verdict"] for r in res]
        check(v[0] == "KILLED", "flipped comparison is KILLED")
        check(v[1] == "KILLED", "changed constant return is KILLED")
        check(v[2] == "SURVIVED", "mutation in unchecked code is reported SURVIVED (tool can say a test is missing)")
        check(v[3] == "MISSING", "case whose old text is absent is reported MISSING, not skipped")
        check(v[4] == "MISSING", "case naming a missing file is reported MISSING")
        with open(mod, "rb") as f:
            after = f.read()
        check(after == src, "file restored byte-exact including CRLF line endings")
        _, mutated = apply_case(mod, "return", "RET")
        check(mutated is not None and mutated.count(b"RET") == 1, "only the first occurrence is mutated")
        check(summarize(res) == "5 planted bugs: 2 killed, 1 survived, 2 missing", "summary line counts are exact")
        # ---- header, compare, red-on-old (2026-10-24)
        pf = os.path.join(d, "plants.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump({"how_to_run": "python plant_runner.py plants.json -- python t.py", "cwd": ".",
                       "cases": cases[:2]}, f)
        c2, h2 = load_cases(pf)
        with open(pf, "w", encoding="utf-8") as f:
            json.dump([{"_header": "run with tools/plant.py"}] + cases[:2], f)
        c3, h3 = load_cases(pf)
        check(c2 == cases[:2] and "how_to_run" in h2 and c3 == cases[:2] and h3.get("_header"),
              "plant file header (object or header element) is read and never run as a case")
        prev = [dict(r) for r in res]
        prev[2]["verdict"] = "KILLED"                  # pretend case 2 was killed before the rule change
        cmp_ = compare(prev, res)
        check([(k, r["i"]) for k, r, _ in cmp_] == [("REGRESSION", 2)], "compare flags KILLED -> SURVIVED as REGRESSION")
        g = os.path.join(d, "g")
        os.makedirs(os.path.join(g, "tests"))
        subprocess.run(["git", "init", "-q", g], check=True, capture_output=True)
        env_cfg = ["-c", "user.email=<email>", "-c", "user.name=t"]
        with open(os.path.join(g, "mod.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("def is_html(b):\n    return False\n")
        subprocess.run(["git", "-C", g, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", g, *env_cfg, "commit", "-qm", "old"], check=True, capture_output=True)
        with open(os.path.join(g, "mod.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("def is_html(b):\n    return b.lstrip().lower().startswith(b'<html')\n")
        with open(os.path.join(g, "tests", "t_new.py"), "w", encoding="utf-8") as f:       # NEW, untracked test
            f.write("import sys\nsys.path.insert(0, '.')\nimport mod\nassert mod.is_html(b'<html>x')\n")
        tcmd = [sys.executable, "-I", "tests/t_new.py"]
        new_src = open(os.path.join(g, "mod.py"), "rb").read()
        ro = red_on_old("mod.py", tcmd, cwd=g)
        check(ro["verdict"] == "RED_ON_OLD_GREEN_ON_NEW" and os.path.isfile(os.path.join(g, "tests", "t_new.py"))
              and open(os.path.join(g, "mod.py"), "rb").read() == new_src,
              "red-on-old: only the source swapped; new test kept; red on old, green on new; source restored")
        weak = [sys.executable, "-I", "-c", "pass"]
        check(red_on_old("mod.py", weak, cwd=g)["verdict"] == "NOT_RED_ON_OLD",
              "planted: a test that cannot see the old bug reads NOT_RED_ON_OLD")
        subprocess.run(["git", "-C", g, *env_cfg, "commit", "-qam", "new"], check=True, capture_output=True)
        check(red_on_old("mod.py", tcmd, cwd=g)["verdict"] == "SAME_AS_OLD",
              "red-on-old against HEAD after committing the fix says SAME_AS_OLD (use --ref HEAD~1)")
        check(red_on_old("mod.py", tcmd, cwd=g, ref="HEAD~1")["verdict"] == "RED_ON_OLD_GREEN_ON_NEW",
              "--ref HEAD~1 reaches the old version")
    return ok


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    sep = argv.index("--") if "--" in argv else len(argv)
    opts, command = argv[:sep], argv[sep + 1:]

    def opt(name, default=None):
        return opts[opts.index(name) + 1] if name in opts else default
    cwd, timeout = opt("--cwd", "."), float(opt("--timeout", 300))
    if opts[:1] == ["red-on-old"]:
        if not opt("--source") or not command:
            print("usage: plant_runner.py red-on-old --source FILE [--ref HEAD] [--cwd DIR] -- <test command>")
            return 2
        r = red_on_old(opt("--source"), command, cwd=cwd, ref=opt("--ref", "HEAD"), timeout=timeout)
        print(r["verdict"], {k: v for k, v in r.items() if k != "verdict"})
        return 0 if r["verdict"] == "RED_ON_OLD_GREEN_ON_NEW" else 1
    if not opts:
        print("usage: plant_runner.py cases.json [--cwd DIR] [--timeout SEC] [--out R.json] [--compare PREV.json] "
              "[-- <test command>]   (the command may come from the plant file's header 'run')")
        return 2
    cases, header = load_cases(opts[0])
    if header.get("how_to_run"):
        print("header:", header["how_to_run"])
    if not command and isinstance(header.get("run"), list):
        command = header["run"]
        cwd = opt("--cwd", header.get("cwd", "."))
    if not command:
        print("no test command: pass one after -- or put \"run\": [argv] in the plant file header")
        return 2
    results = run_cases(cases, command, cwd=cwd, timeout=timeout)
    print(format_report(results))
    if opt("--out"):
        with open(opt("--out"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
    regress = False
    if opt("--compare"):
        with open(opt("--compare"), encoding="utf-8") as f:
            for kind, r, b in compare(json.load(f), results):
                print(f"{kind:<10} #{r['i']} {r['file']}: {b} -> {r['verdict']}  {r['old'][:40]!r}")
                regress = regress or kind == "REGRESSION"
    return 0 if all(r["verdict"] in ("KILLED", "TIMEOUT") for r in results) and not regress else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
