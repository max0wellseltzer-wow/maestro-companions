"""exaptation - the skill library's FUNCTION INDEX, and a search over it (backs the exaptation-finder skill).

Exaptation: a trait evolved for one job gets co-opted for another (feathers grew for warmth, then carried flight).
Code is the same: a function written inside one skill is often exactly what another job needs. This module walks
every shipped tool .py in the library with `ast` (skipping test_* files, evals/ fixtures, synced/ and
__pycache__), records each top-level function - skill, file, name, args with defaults, docstring first line,
return hints, line span - and ranks them against a plain-language need by TF-IDF over name tokens (snake_case
split), argument names and the docstring, using skill-finder's tokeniser. Search here BEFORE writing new code.

The same index answers the reverse question (merged from pleiotropy-map - pleiotropy: one gene, many traits):
`impact("skill:module.func")` is the blast radius of changing a function - tier 1 direct callers (same module or
importers, resolved per file by import so a same-named local function is not a caller), tier 2+ transitive
callers, the _selftest / test_* units that exercise it, the SKILL.md files that mention it, and the distinct
skills touched.

It is also the shared index the other library-anatomy tools import (convergence-detector, peacock-tail,
skill-finder's salvage): one walker, no copies.

    python exaptation.py "moving average over a window"        # top 10 functions for a need
    python exaptation.py "invert a matrix" --top 5 --root DIR
    python exaptation.py --impact matrix-lite:matrix_lite.inv  # who breaks if this changes
    python exaptation.py --stats                                # how big is the index
    python exaptation.py --selftest
"""
from __future__ import annotations

import ast
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "skill-finder"))
from find_skill import _tokens  # noqa: E402

SKIP_DIRS = {"synced", "__pycache__"}
DEFAULT_ROOT = Path.home() / ".claude" / "skills"


def skill_dirs(root) -> list:
    """Every skill folder under root (any non-hidden dir except synced/ and __pycache__)."""
    root = Path(root)
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."))


def tool_files(root, include_tests: bool = False) -> list:
    """(skill_name, path) for every tool .py; test_* files only when include_tests, evals/ never."""
    out = []
    for d in skill_dirs(root):
        for p in sorted(d.rglob("*.py")):
            rel = p.relative_to(d).parts
            if "__pycache__" in rel or "evals" in rel:
                continue
            if p.name.startswith("test_") and not include_tests:
                continue
            out.append((d.name, p))
    return out


def parse(path: Path, errors: list | None = None):
    """ast tree of a file, or None (appending 'file: reason' to errors) when it does not parse."""
    try:
        return ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError) as e:
        if errors is not None:
            errors.append(f"{path}: {type(e).__name__} {getattr(e, 'msg', e)}")
        return None


def render_args(a: ast.arguments) -> list:
    """['x', 'window=5', '*rest', 'flag=True', '**kw'] - positional defaults aligned right, as Python does."""
    pos = list(a.posonlyargs) + list(a.args)
    defs = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    out = [p.arg + ("" if d is None else "=" + ast.unparse(d)) for p, d in zip(pos, defs)]
    if a.vararg:
        out.append("*" + a.vararg.arg)
    for k, d in zip(a.kwonlyargs, a.kw_defaults):
        out.append(k.arg + ("" if d is None else "=" + ast.unparse(d)))
    if a.kwarg:
        out.append("**" + a.kwarg.arg)
    return out


def return_hints(fn) -> list:
    """The annotation if there is one, else a sketch of what the return statements hand back."""
    if fn.returns is not None:
        return [ast.unparse(fn.returns)]
    hints = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        v = node.value
        if isinstance(v, ast.Dict):
            keys = [k.value for k in v.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            h = "dict{" + ",".join(keys[:6]) + "}" if keys else "dict"
        elif isinstance(v, ast.Tuple):
            h = f"tuple({len(v.elts)})"
        elif isinstance(v, (ast.List, ast.ListComp)):
            h = "list"
        elif isinstance(v, ast.Constant):
            h = type(v.value).__name__
        elif isinstance(v, (ast.Compare, ast.BoolOp)) or (isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.Not)):
            h = "bool"
        elif isinstance(v, ast.Name):
            h = v.id
        elif isinstance(v, ast.Call):
            h = ast.unparse(v.func) + "(...)"
        else:
            h = type(v).__name__.lower()
        if h not in hints:
            hints.append(h)
    return hints[:4]


def index_functions(root=DEFAULT_ROOT, include_private: bool = False, keep_ast: bool = False,
                    errors: list | None = None) -> list:
    """One record per top-level function of every tool .py: skill, file (relative), module, name, args,
    arg_names, doc (first line), returns (hints), lines (start, end). Private (_x) names only when asked;
    keep_ast attaches the FunctionDef as 'node'. Files that do not parse are skipped (and noted in errors)."""
    root = Path(root)
    recs = []
    for skill, p in tool_files(root):
        tree = parse(p, errors)
        if tree is None:
            continue
        for fn in tree.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name.startswith("_") and not include_private:
                continue
            doc = (ast.get_docstring(fn) or "").strip().splitlines()
            rec = {"skill": skill, "file": p.relative_to(root).as_posix(), "module": p.stem, "name": fn.name,
                   "args": render_args(fn.args),
                   "arg_names": [x.arg for x in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs)],
                   "doc": doc[0] if doc else "", "returns": return_hints(fn),
                   "lines": (fn.lineno, getattr(fn, "end_lineno", fn.lineno))}
            if keep_ast:
                rec["node"] = fn
            recs.append(rec)
    return recs


def _doc_tokens(r: dict):
    name_toks = set(_tokens(r["name"].replace("_", " ")))
    toks = _tokens(" ".join([r["name"].replace("_", " "), " ".join(r["arg_names"]).replace("_", " "), r["doc"]]))
    return name_toks, toks


def find(need: str, root=DEFAULT_ROOT, top: int = 10, index: list | None = None) -> list:
    """Rank functions for a plain-language need: TF-IDF over name/arg/docstring tokens, name hits count double,
    damped by (distinct tokens)^0.25 so a long docstring cannot win on bulk. Empty list when nothing matches."""
    idx = index if index is not None else index_functions(root)
    q = set(_tokens(need))
    if not q or not idx:
        return []
    docs = [(_doc_tokens(r), r) for r in idx]
    n = len(docs)
    df = {}
    for (_, toks), _r in docs:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    scored = []
    for (name_toks, toks), r in docs:
        ts = set(toks)
        hit = q & ts
        # abbreviated names: 'inv' answers 'invert', 'std' answers 'standard' (name tokens only, >= 3 chars)
        short = {t for t in name_toks - hit if len(t) >= 3 and any(w != t and (w.startswith(t) or t.startswith(w))
                                                                   for w in q if len(w) >= 3)}
        if not hit and not short:
            continue
        s = sum(math.log((n + 1) / (df[t] + 0.5)) * (2.0 if t in name_toks else 1.0) for t in hit)
        s += sum(math.log((n + 1) / (df[t] + 0.5)) * 1.5 for t in short)
        s /= max(len(ts), 1) ** 0.25
        scored.append((s, r))
    scored.sort(key=lambda x: (-x[0], x[1]["skill"], x[1]["name"]))
    return [{**{k: v for k, v in r.items() if k != "node"}, "score": round(s, 3)} for s, r in scored[:top]]


# ---- blast radius (merged from pleiotropy-map) ---------------------------------------------------------------

MODULE = "<module>"


def _units(tree):
    """(qualname, node) for each top-level function, each class method, and the module-level remainder."""
    rest = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{node.name}.{sub.name}", sub
        else:
            rest.append(node)
    yield MODULE, ast.Module(body=rest, type_ignores=[])


def _bound(fn) -> set:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return set()
    out = {a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg)}
    return out | {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def build_graph(root=DEFAULT_ROOT, errors: list | None = None) -> dict:
    """Function-level reference graph of the library, test_* files included:
    {'edges': {(file, unit): {(file, name), ...}}, 'skill_of': {file: skill}, 'files': {stem: [file]},
    'defs': {file: {top-level names}}}. Files are root-relative posix paths."""
    root = Path(root)
    by_stem, skill_of, trees = {}, {}, {}
    for s, p in tool_files(root, include_tests=True):
        rel = p.relative_to(root).as_posix()
        by_stem.setdefault(p.stem, []).append(rel)
        skill_of[rel] = s
        t = parse(p, errors)
        if t is not None:
            trees[rel] = (t, p.read_text(encoding="utf-8", errors="replace"))

    def resolve(mod, rel):
        cands = by_stem.get(mod.split(".")[-1], [])
        if len(cands) <= 1:
            return cands[0] if cands else None
        same = [c for c in cands if skill_of[c] == skill_of[rel]]
        if same:
            return same[0]
        src = trees[rel][1]
        named = [c for c in cands if f'"{skill_of[c]}"' in src or f"'{skill_of[c]}'" in src]
        return (named or cands)[0]

    edges, defs = {}, {}
    for rel, (tree, _src) in trees.items():
        local = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        defs[rel] = local
        fimports, mimports = {}, {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                f = resolve(node.module, rel)
                if f:
                    for a in node.names:
                        fimports[a.asname or a.name] = (f, a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    f = resolve(a.name, rel)
                    if f:
                        mimports[a.asname or a.name.split(".")[0]] = f
        for qual, unit in _units(tree):
            shadow = _bound(unit)
            refs = set()
            for n in ast.walk(unit):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in shadow:
                    if n.id in fimports:
                        refs.add(fimports[n.id])
                    elif n.id in local and n.id != qual:
                        refs.add((rel, n.id))
                elif (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                      and n.value.id in mimports and n.value.id not in shadow):
                    refs.add((mimports[n.value.id], n.attr))
            if refs:
                edges[(rel, qual)] = refs
    return {"edges": edges, "skill_of": skill_of, "files": by_stem, "defs": defs}


def _parse_ref(ref: str, graph: dict):
    """'skill:module.func' or 'module.func' -> (file, func), or None when no such module defines func."""
    skill = None
    if ":" in ref:
        skill, ref = ref.split(":", 1)
    if "." not in ref:
        return None
    mod, func = ref.rsplit(".", 1)
    for f in graph["files"].get(mod, []):
        if (skill is None or graph["skill_of"][f] == skill) and func in graph["defs"].get(f, ()):
            return f, func
    return None


def _mentions(root: Path, module: str, func: str) -> list:
    pat = re.compile(rf"\b{re.escape(module)}\.{re.escape(func)}\b|(?<![\w.]){re.escape(func)}\(")
    word = re.compile(rf"\b{re.escape(func)}\b")
    out = []
    for d in skill_dirs(root):
        md = d / "SKILL.md"
        if md.exists():
            t = md.read_text(encoding="utf-8", errors="replace")
            if pat.search(t) or (module in t and word.search(t)):
                out.append(d.name)
    return out


def impact(func_ref: str, root=DEFAULT_ROOT, graph: dict | None = None) -> dict:
    """Blast radius of changing one function: tiers of callers (1 = direct), tests that exercise it, SKILL.md
    mentions, distinct skills touched. Raises ValueError for a ref the library does not define."""
    root = Path(root)
    g = graph or build_graph(root)
    t = _parse_ref(func_ref, g)
    if t is None:
        raise ValueError(f"{func_ref!r} not found (use skill:module.func or module.func)")
    rev = {}
    for src, refs in g["edges"].items():
        for r in refs:
            rev.setdefault(r, set()).add(src)
    tiers, seen, frontier = [], {t}, {t}
    while frontier:
        nxt = {c for node in frontier for c in rev.get(node, ()) if c not in seen}
        seen |= nxt
        if nxt:
            tiers.append(sorted(nxt))
        frontier = {n for n in nxt if n[1] != MODULE}         # module-level code has no callers

    def fmt(n):
        return f"{g['skill_of'][n[0]]}:{Path(n[0]).name}:{n[1]}"
    everyone = [n for tier in tiers for n in tier]
    tests = sorted(fmt(n) for n in everyone
                   if Path(n[0]).name.startswith("test_") or n[1].split(".")[-1].startswith(("_selftest", "test")))
    docs = _mentions(root, Path(t[0]).stem, t[1])
    skills = {g["skill_of"][t[0]]} | {g["skill_of"][n[0]] for n in everyone} | set(docs)
    shown = [[fmt(n) for n in tier if n[1] not in (MODULE, "main")] for tier in tiers]   # entry points: noise
    return {"target": fmt(t), "tiers": [x for x in shown if x], "tests": tests, "docs": docs,
            "skills": sorted(skills), "blast_radius": len(skills)}


def _selftest_impact(ok: dict) -> None:
    root = Path(tempfile.mkdtemp(prefix="exapt_impact_"))

    def put(rel, src):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    try:
        put("core/core_mod.py", "def inv(a):\n    return a\ndef solve(a, b):\n    return inv(a)\n"
            "def _selftest():\n    return solve(1, 2) == 1\n")
        put("fit/SKILL.md", "---\nname: fit\n---\nUses core_mod.inv for the normal equations.\n")
        put("fit/fit_mod.py", "from core_mod import inv as I\ndef fit(x):\n    return I(x)\n")
        put("chain/chain_mod.py", "from fit_mod import fit\ndef pipeline(x):\n    return fit(x)\n")
        put("attr/attr_mod.py", "import core_mod as cm\ndef run(x):\n    return cm.solve(x, 1)\n")
        put("twin/twin_mod.py", "def inv(a):\n    return -a\ndef use(a):\n    return inv(a)\n")    # false friend
        put("shadow/shadow_mod.py", "from core_mod import inv\ndef g(inv):\n    return inv(1)\n")   # param shadows
        put("tests/test_core.py", "from core_mod import inv\ndef test_inv():\n    assert inv(2) == 2\n")
        g = build_graph(root)
        rep = impact("core:core_mod.inv", root, g)
        flat = [x for tier in rep["tiers"] for x in tier]
        ok["impact: direct callers in tier 1, importers-of-callers (from-import and module.attr) in tier 2"] = (
            len(rep["tiers"]) >= 2 and {"core:core_mod.py:solve", "fit:fit_mod.py:fit"} <= set(rep["tiers"][0])
            and {"chain:chain_mod.py:pipeline", "attr:attr_mod.py:run"} <= set(rep["tiers"][1]))
        ok["impact: a same-named local function or a shadowing parameter is NOT a caller"] = not any(
            "twin" in x or "shadow_mod.py:g" in x for x in flat)
        ok["impact: selftests, test_* files and SKILL.md mentions are listed; radius counts skills"] = (
            {"core:core_mod.py:_selftest", "tests:test_core.py:test_inv"} <= set(rep["tests"])
            and rep["docs"] == ["fit"] and rep["blast_radius"] == 5)
        refused = 0
        for bad in ("core:core_mod.no_such_func", "nosuchmodule.inv", "fit:core_mod.inv", "inv"):
            try:
                impact(bad, root, g)
            except ValueError:
                refused += 1
        ok["impact: unknown function/module/skill refs are refused"] = refused == 4
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _selftest() -> bool:
    ok = {}
    root = Path(tempfile.mkdtemp(prefix="exapt_"))

    def put(rel, src):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    try:
        put("stats-a/SKILL.md", "---\nname: stats-a\ndescription: x\n---\n")
        put("stats-a/roll.py", 'def rolling_mean(xs, window=5, *, strict=False) -> list:\n'
            '    """Moving average of a series over a sliding window."""\n    return [sum(xs[:window]) / window]\n'
            'def _helper(x):\n    return x\n')
        put("text-b/SKILL.md", "---\nname: text-b\ndescription: x\n---\n")
        put("text-b/scripts/dist.py", 'def edit_distance(a, b):\n    """Levenshtein distance between two strings."""\n'
            '    return {"distance": 0, "ops": []}\n')
        put("text-b/scripts/test_dist.py", "def test_edit_distance():\n    assert True\n")
        put("text-b/evals/grader.py", "def grade_moving_average(x):\n    return x\n")
        put("broken-c/bad.py", "def oops(:\n    pass\n")                          # planted bad input
        put("synced/zzz/s.py", "def rolling_window_mean(xs):\n    return xs\n")
        errs = []
        idx = index_functions(root, errors=errs)
        names = sorted(r["name"] for r in idx)
        ok["indexes public top-level functions only (private, test_*, evals/, synced/ skipped)"] = (
            names == ["edit_distance", "rolling_mean"])
        r = next(x for x in idx if x["name"] == "rolling_mean")
        ok["args keep defaults, keyword-only included"] = r["args"] == ["xs", "window=5", "strict=False"]
        ok["return hint from annotation, docstring first line, line span"] = (
            r["returns"] == ["list"] and r["doc"].startswith("Moving average") and r["lines"] == (1, 3))
        e = next(x for x in idx if x["name"] == "edit_distance")
        ok["return hint sketches a dict's keys when unannotated"] = e["returns"] == ["dict{distance,ops}"]
        ok["a file that does not parse is skipped and reported, not fatal"] = (
            len(errs) == 1 and "bad.py" in errs[0])
        f1 = find("moving average over a window", root)
        ok["a need finds the function that already does it"] = bool(f1) and f1[0]["name"] == "rolling_mean"
        f2 = find("string distance", root)
        ok["a different need finds a different function"] = bool(f2) and f2[0]["name"] == "edit_distance"
        ok["an unrelated need returns nothing rather than noise"] = find("bake sourdough bread", root) == []
        ok["private helpers can be indexed on request (for the anatomy tools)"] = (
            "_helper" in {x["name"] for x in index_functions(root, include_private=True)})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    _selftest_impact(ok)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    root, top = DEFAULT_ROOT, 10
    if "--root" in argv:
        i = argv.index("--root")
        root = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if "--top" in argv:
        i = argv.index("--top")
        top = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if argv and argv[0] == "--stats":
        errs = []
        idx = index_functions(root, errors=errs)
        print(f"{len(idx)} public functions in {len({r['skill'] for r in idx})} skills; {len(errs)} unparsable files")
        for e in errs:
            print("  !", e)
        return 0
    if argv and argv[0] == "--impact":
        try:
            rep = impact(argv[1] if len(argv) > 1 else "", root)
        except ValueError as e:
            print(e)
            return 2
        print(f"{rep['target']}: blast radius {rep['blast_radius']} skills")
        for i, tier in enumerate(rep["tiers"], 1):
            print(f"  tier {i} ({'direct' if i == 1 else 'transitive'}, {len(tier)}): {', '.join(tier)}")
        print(f"  tests ({len(rep['tests'])}): {', '.join(rep['tests']) or '-'}")
        print(f"  SKILL.md mentions ({len(rep['docs'])}): {', '.join(rep['docs']) or '-'}")
        print(f"  skills: {', '.join(rep['skills'])}")
        return 0
    res = find(" ".join(argv), root, top)
    if not res:
        print("no matching function - nothing to exapt; write it (then it will be found next time)")
        return 0
    for r in res:
        print(f"{r['score']:5.2f}  {r['skill']}:{r['module']}.{r['name']}({', '.join(r['args'])})"
              f"  -> {', '.join(r['returns']) or '?'}\n       {r['doc'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
