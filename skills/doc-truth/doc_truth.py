"""doc_truth - documented commands must match the scripts they name (backs doc-truth).

For every line of a doc (SKILL.md, README, any .md) that invokes `python ... X.py ...`, check:
  MISSING_SCRIPT   X.py does not exist (resolved against the doc's folder, then as given, then by basename in the
                   doc's folder tree)
  UNKNOWN_FLAG     a --flag written after X.py appears nowhere in X.py as a quoted literal ('--flag' / "--flag"),
                   so neither argparse nor a hand-rolled argv loop can accept it (--help/-h pass when argparse is used)
  UNKNOWN_COMMAND  the first bare word after X.py is not a quoted literal in X.py although X.py dispatches on
                   sub-commands (add_parser / argv[0] / argv[1] comparisons)
Text after a ' #' on the line is a comment and ignored; '<...>' placeholders, '...' and all-caps script names (X.py, TOOL.py) are ignored.
--run-selftest also runs every documented `X.py --selftest` (timeout 120 s each) and checks a claimed "N PASS"
count on the same line against the real number of PASS lines.

    python doc_truth.py PATH [PATH...] [--run-selftest] [--quiet]
PATH is a doc or a folder (every SKILL.md below it; --all-md for every .md). Exit 0 clean, 1 problems, 2 bad args.
    python doc_truth.py --selftest
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

INVOKE = re.compile(r"\bpython[0-9.]*(?:\s+-[A-Za-z]+)*\s+(\"[^\"]+\.py\"|'[^']+\.py'|\S+\.py)\b(.*)")
FLAG = re.compile(r"(?<![\w-])(--[A-Za-z][\w-]*)")
WORD = re.compile(r"^\s*([a-z][a-z0-9_-]*)\b")
DISPATCH = re.compile(r"add_parser\(|argv\[[01]\]\s*(?:==|in)\s*[(\[{]?\s*[\"'][a-z]|args\.(?:cmd|command)\b")
STRIPS = re.compile(r"\[2:\]|lstrip\(\s*[\"']-|removeprefix\(\s*[\"']--|[\"']--[\"']\s*\+|f[\"']--\{")  # flags keyed by bare name
CLAIM = re.compile(r"(\d+)\s+PASS")


def resolve(doc: Path, name: str) -> Path | None:
    name = name.strip("\"'")
    cands = [doc.parent / name, Path(name).expanduser()]
    for c in cands:
        if c.is_file():
            return c
    base = Path(name).name
    hits = sorted(doc.parent.rglob(base)) if doc.parent.is_dir() else []
    return hits[0] if hits else None


IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_]\w*)\s+import|import\s+([A-Za-z_]\w*))", re.M)


def source_with_helpers(path: Path, depth: int = 2) -> str:
    """The script's source plus the local modules it imports (its own folder, or a sibling folder of its parent -
    the skills library's sys.path pattern), so flags parsed by a shared CLI helper count as known."""
    seen, out, todo = set(), [], [(path, 0)]
    while todo:
        p, d = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        try:
            s = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append(s)
        if d >= depth:
            continue
        for m in IMPORT.finditer(s):
            name = m.group(1) or m.group(2)
            if name in STDLIB:
                continue
            c = _find_module(p.parent, name + ".py")
            if c is not None:
                todo.append((c, d + 1))
    return "\n".join(out)


STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
_MOD_CACHE: dict = {}


def _find_module(folder: Path, mod: str):
    """mod in the script's folder, else in a sibling folder of that folder (cached per parent)."""
    own = folder / mod
    if own.is_file():
        return own
    parent = folder.parent
    if parent not in _MOD_CACHE:
        idx = {}
        if parent.is_dir():
            for f in sorted(parent.glob("*/*.py")):
                idx.setdefault(f.name, f)
        _MOD_CACHE[parent] = idx
    return _MOD_CACHE[parent].get(mod)


def check_doc(doc: Path, run_selftest=False) -> list:
    rows = []
    try:
        lines = doc.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return [{"doc": str(doc), "line": 0, "status": "UNREADABLE", "detail": str(e)}]
    src_cache = {}
    for n, raw in enumerate(lines, 1):
        matches = [m for seg in raw.split("`") for s in re.finditer(r"\bpython", seg)
                   for m in [INVOKE.match(seg, s.start())] if m]      # every python start, nested ones too
        for m in matches:
            script, rest = m.group(1), m.group(2)
            rest = re.split(r"\s#\s|\s#$", rest)[0]
            rest = re.split(r"\s--(?=\s|$)|\spython[0-9.]*\s", rest)[0]   # after ' -- ' or a nested python: another command
            rest = re.sub(r"<[^>]*>", " ", rest)
            rest = re.sub(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'', " ", rest)   # quoted args hold OTHER commands' flags
            if Path(script.strip("\"'")).stem.isupper():      # X.py, TOOL.py, MODULE.py are placeholders
                continue
            path = resolve(doc, script)
            if path is None:
                rows.append({"doc": str(doc), "line": n, "status": "MISSING_SCRIPT", "detail": script.strip("\"'")})
                continue
            if path not in src_cache:
                src_cache[path] = source_with_helpers(path)
            src = src_cache[path]
            argparse_used = "argparse" in src
            for flag in FLAG.findall(rest):
                if flag in ("--help",) and argparse_used:
                    continue
                bare = flag[2:]
                stripped = STRIPS.search(src) and (f'"{bare}"' in src or f"'{bare}'" in src)
                if f'"{flag}"' not in src and f"'{flag}'" not in src and not stripped:
                    rows.append({"doc": str(doc), "line": n, "status": "UNKNOWN_FLAG",
                                 "detail": f"{path.name} {flag}"})
            w = WORD.match(rest)
            nxt = rest.strip()[len(w.group(1)):][:1] if w else ""
            if w and DISPATCH.search(src) and nxt not in (".", "/", ":", "\\"):
                word = w.group(1)
                if f'"{word}"' not in src and f"'{word}'" not in src:
                    rows.append({"doc": str(doc), "line": n, "status": "UNKNOWN_COMMAND",
                                 "detail": f"{path.name} {word}"})
            if run_selftest and "--selftest" in rest:
                try:
                    r = subprocess.run([sys.executable, "-B", "-I", str(Path(path).resolve()), "--selftest"], capture_output=True,
                                       text=True, timeout=120, cwd=tempfile.gettempdir())
                    passes = sum(ln.startswith("PASS") for ln in r.stdout.splitlines())
                    if r.returncode != 0:
                        rows.append({"doc": str(doc), "line": n, "status": "SELFTEST_FAILS",
                                     "detail": f"{path.name} exit {r.returncode}"})
                    c = CLAIM.search(raw)
                    if c and int(c.group(1)) != passes:
                        rows.append({"doc": str(doc), "line": n, "status": "STALE_COUNT",
                                     "detail": f"{path.name} doc says {c.group(1)} PASS, run printed {passes}"})
                except subprocess.TimeoutExpired:
                    rows.append({"doc": str(doc), "line": n, "status": "SELFTEST_TIMEOUT", "detail": path.name})
    return rows


def docs_under(p: Path, all_md=False) -> list:
    if p.is_file():
        return [p]
    pat = "*.md" if all_md else "SKILL.md"
    return sorted(x for x in p.rglob(pat) if "__pycache__" not in x.parts)


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    flags = {a for a in argv if a.startswith("--")}
    bad = flags - {"--run-selftest", "--quiet", "--all-md"}
    paths = [Path(a) for a in argv if not a.startswith("--")]
    if bad or not paths or any(not p.exists() for p in paths):
        print(__doc__)
        return 2
    docs = [d for p in paths for d in docs_under(p, "--all-md" in flags)]
    rows = [r for d in docs for r in check_doc(d, "--run-selftest" in flags)]
    for r in rows:
        print(f"{r['status']:<16} {r['doc']}:{r['line']}  {r['detail']}")
    kinds = {}
    for r in rows:
        kinds[r["status"]] = kinds.get(r["status"], 0) + 1
    print(f"{len(docs)} doc(s) checked, {len(rows)} problem(s)" +
          ("" if not kinds else ": " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))))
    return 1 if rows else 0


def _selftest() -> bool:
    ok = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sk = td / "demo"
        sk.mkdir()
        (sk / "tool.py").write_text(
            "import sys\n"
            "def _selftest():\n    print('PASS a')\n    print('PASS b')\n    return True\n"
            "def main(argv):\n"
            "    if argv[:1] == ['--selftest']:\n        return 0 if _selftest() else 1\n"
            "    if argv[0] == 'scan':\n        pass\n"
            "    if '--alpha' in argv or \"--beta\" in argv:\n        pass\n    return 0\n"
            "if __name__ == '__main__':\n    sys.exit(main(sys.argv[1:]))\n", encoding="utf-8")
        (sk / "ap.py").write_text("import argparse\np = argparse.ArgumentParser()\np.add_argument('--gamma')\n",
                                  encoding="utf-8")
        doc = sk / "SKILL.md"
        doc.write_text(
            "# demo\n```\n"
            "python tool.py scan --alpha 1 --beta    # comment --ignored\n"           # 3 clean
            "python tool.py scan --delta             # delta is not in the tool\n"   # 4 UNKNOWN_FLAG
            "python tool.py sacn --alpha             # misspelt command\n"           # 5 UNKNOWN_COMMAND
            "python gone.py --x\n"                                                   # 6 MISSING_SCRIPT
            "python ap.py --gamma 2 --help\n"                                        # 7 clean (argparse help)
            "python tool.py <FILE> --alpha\n"                                        # 8 placeholder ignored
            "python tool.py --selftest     # 3 PASS lines\n"                         # 9 STALE_COUNT with --run
            "```\nInline: `python -I tool.py --alpha` and `python gone2.py --zeta`.\n"  # 11
            "python shared.py --json --nope\n"                                       # 12 helper flag ok, --nope not
            "python loop.py --hours 3 --nada\n"                                      # 13 bare-key argv loop
            "python built.py --base 1 --cmd \"other.py --data x\" --zzz\n"            # 14
            "python tool.py scan --alpha -- python -B ap.py --gamma --qqq\n", encoding="utf-8")  # 15 wrapped command
        (sk / "built.py").write_text("import argparse\nap = argparse.ArgumentParser()\nap.add_argument('--cmd')\n"
                                     "for k, v in {'base': 1}.items():\n    ap.add_argument('--' + k, default=v)\n",
                                     encoding="utf-8")
        (sk / "loop.py").write_text("import sys\na = {'hours': '1'}\nit = iter(sys.argv[1:])\nfor x in it:\n"
                                    "    if x[2:] in a:\n        a[x[2:]] = next(it)\n", encoding="utf-8")
        (td / "helper").mkdir()
        (td / "helper" / "clihelp.py").write_text("FLAGS = ['--json']\n", encoding="utf-8")
        (sk / "shared.py").write_text("import sys\nfrom clihelp import FLAGS\n", encoding="utf-8")
        rows = check_doc(doc)
        got = {(r["line"], r["status"]) for r in rows}
        ok["flags parsed by an imported sibling helper count as known"] = (
            [r["detail"] for r in rows if r["line"] == 12] == ["shared.py --nope"])
        ok["a command wrapped after ' -- ' is checked against its own script"] = (
            [r["detail"] for r in rows if r["line"] == 15] == ["ap.py --qqq"])
        ok["'--' + name flags count, flags inside a quoted argument are not this script's"] = (
            [r["detail"] for r in rows if r["line"] == 14] == ["built.py --zzz"])
        ok["an argv loop keyed by the bare name (x[2:]) knows its flags"] = (
            [r["detail"] for r in rows if r["line"] == 13] == ["loop.py --nada"])
        ok["an undocumented-in-code flag is UNKNOWN_FLAG"] = (4, "UNKNOWN_FLAG") in got
        ok["a misspelt sub-command is UNKNOWN_COMMAND"] = (5, "UNKNOWN_COMMAND") in got
        ok["a script that does not exist is MISSING_SCRIPT"] = (6, "MISSING_SCRIPT") in got
        ok["flags after ' #' comments are ignored"] = not any("--ignored" in r["detail"] for r in rows)
        ok["argparse --help and add_argument flags pass"] = not any(r["line"] == 7 for r in rows)
        ok["a clean line with hand-rolled argv flags passes"] = not any(r["line"] == 3 for r in rows)
        ok["placeholders are not read as commands"] = not any(r["line"] == 8 for r in rows)
        ok["each inline backtick command is checked on its own"] = (
            [r["status"] for r in rows if r["line"] == 11] == ["MISSING_SCRIPT"])
        rows2 = check_doc(doc, run_selftest=True)
        ok["--run-selftest catches a stale PASS count"] = any(r["status"] == "STALE_COUNT" and r["line"] == 9
                                                             for r in rows2)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main([str(td)])
            (doc).write_text("python tool.py scan --alpha\n", encoding="utf-8")
            rc0 = main([str(td)])
            rcb = main([str(td), "--bogus"])
        ok["exit 1 on problems, 0 when clean, 2 on a bad flag"] = (rc, rc0, rcb) == (1, 0, 2)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
