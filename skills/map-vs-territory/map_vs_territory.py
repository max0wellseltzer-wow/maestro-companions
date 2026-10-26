"""map_vs_territory - hold a module's documented numbers against what its code measures (backs the map-vs-territory
skill). EPISTEMIC lens of the point-of-view family. The docstrings and comments are the map; the ast is the territory.

Claims read from the module docstring, every function docstring and every # comment:
  "<N> lines" / "about N lines" / "A-B lines"   vs the module's (or that function's) line count
  "<N> functions|defs"                          vs the number of def statements
  "<N> checks|tests"                            vs the count of ok[...] = assignments (or test_ functions)
  "<N> args|arguments|parameters"               vs that function's parameter count
  "<param> defaults to N" / "<param>=N"         vs that parameter's literal default in any def
An exact number must match; "about N" passes within 25%; a range passes inside it. Then the reverse direction: the
numeric literals in function bodies and defaults (other than 0, 1, 2, -1) that no docstring or comment mentions are
listed as undocumented magic numbers. Text-pattern claims only; prose like "a few lines" is not a number.

    python map_vs_territory.py --selftest
    python map_vs_territory.py <file.py> [--json]
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, load_subject, report, run_cli, view  # noqa: E402

NAME = "map-vs-territory"
KINDS = {"code"}
CLAIM = re.compile(r"(about\s+|~)?(\d+)(?:\s*-\s*(\d+))?\s+(lines|functions|defs|checks|tests|args|arguments|parameters)\b", re.I)
DEFAULT = re.compile(r"\b([a-z_]\w*)\s*(?:defaults?\s+(?:to\s+|is\s+)?|=\s*)(-?\d+(?:\.\d+)?)\b")


def apply(subject, kind=None, **opts) -> dict:
    kd, src = load_subject(subject, kind or "code")
    if kd not in KINDS:
        raise ValueError(f"map-vs-territory reads python code, not {kd}")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise ValueError(f"not parseable python: {e}") from None
    defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    checks = max(sum(1 for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "ok" for t in n.targets)),
        sum(d.name.startswith("test_") for d in defs))
    defaults = {}
    for d in defs:
        args = d.args.args[len(d.args.args) - len(d.args.defaults):] + d.args.kwonlyargs
        for a, v in zip(args, d.args.defaults + [x for x in d.args.kw_defaults]):
            if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) and not isinstance(v.value, bool):
                defaults[a.arg] = v.value
    docs = [("module", ast.get_docstring(tree) or "", src.count("\n") + 1, None)]
    docs += [(d.name, ast.get_docstring(d) or "", d.end_lineno - d.lineno + 1, len(d.args.args)) for d in defs]
    comments = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT]
    docs.append(("comments", "\n".join(comments), src.count("\n") + 1, None))
    f, drift, n_claims = [], 0, 0
    for where, doc, lines, nargs in docs:
        for m in CLAIM.finditer(doc):
            about, a, b, unit = m.group(1), int(m.group(2)), m.group(3), m.group(4).lower()
            measured = {"lines": lines, "functions": len(defs), "defs": len(defs), "checks": checks, "tests": checks,
                        "args": nargs, "arguments": nargs, "parameters": nargs}[unit]
            if measured is None:
                continue
            n_claims += 1
            good = (a <= measured <= int(b)) if b else (abs(measured - a) <= 0.25 * a) if about else measured == a
            drift += not good
            f.append({"what": f"{'OK   ' if good else 'DRIFT'} {where}: says '{m.group(0).strip()}', measures {measured} {unit}",
                      "where": where, "claim": m.group(0).strip(), "measured": measured, "ok": good})
        for m in DEFAULT.finditer(doc):
            p, said = m.group(1), float(m.group(2))
            if p in defaults:
                n_claims += 1
                good = float(defaults[p]) == said
                drift += not good
                f.append({"what": f"{'OK   ' if good else 'DRIFT'} {where}: says {p} = {said:g}, the def has {defaults[p]}",
                          "where": where, "claim": m.group(0), "measured": defaults[p], "ok": good})
    alldoc = " ".join(d[1] for d in docs)
    said_nums = {float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", alldoc)}
    lits = [n for d in defs for n in ast.walk(d) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            and not isinstance(n.value, bool) and n.value not in (0, 1, 2, -1)]
    magic = sorted({n.value for n in lits if float(n.value) not in said_nums}, key=float)
    for v in magic:
        line = next(n.lineno for n in lits if n.value == v)
        f.append({"what": f"undocumented magic number {v!r} (first at line {line})", "magic": v})
    return view(NAME, "code", f, f"{n_claims} documented numbers checked: {drift} drifted from the code; "
                f"{len(magic)} undocumented magic numbers", claims=n_claims, drift=drift, magic=magic,
                measured={"functions": len(defs), "checks": checks, "lines": src.count("\n") + 1})


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["code"])
    ok["probe code: no docstring claims, magic numbers 3, 3.7 and 42 found"] = (
        p["stats"]["claims"] == 0 and p["stats"]["magic"] == [3, 3.7, 42])
    planted = ('"""tool - 2 functions, about 12 lines, 1 checks."""\n'
               'def score(rows, k=42):\n    """Sum rows. k defaults to 10. Takes 3 args."""\n    return sum(rows) / k\n\n'
               'def main():\n    ok = {}\n    ok["a"] = score([1]) > 0\n    ok["b"] = True\n    return ok\n')
    q = apply(planted)
    by = {x.get("claim"): x for x in q["findings"] if "claim" in x}
    ok["planted: '2 functions' matches 2 defs"] = by["2 functions"]["ok"]
    ok["planted: 'about 12 lines' passes within 25% of 10 lines"] = by["about 12 lines"]["ok"]
    ok["planted: '1 checks' drifts (2 ok[...] assignments)"] = not by["1 checks"]["ok"] and by["1 checks"]["measured"] == 2
    ok["planted: 'k defaults to 10' drifts from k=42"] = any(not x["ok"] and x["measured"] == 42 for x in q["findings"] if "claim" in x)
    ok["planted: 'Takes 3 args' drifts (score has 2)"] = not by["3 args"]["ok"]
    ok["planted: 42 is magic only when no doc says 42"] = q["stats"]["magic"] == [42]
    for label, bad in (("plain text", "We will launch next week."), ("series", PROBES["series"])):
        try:
            apply(bad, kind="text" if label == "plain text" else None)
            ok[f"planted bad input ({label}) is refused"] = False
        except ValueError:
            ok[f"planted bad input ({label}) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli(NAME, apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
