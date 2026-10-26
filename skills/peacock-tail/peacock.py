"""peacock - honest-advertising audit of the skill library: does each SKILL.md claim only what its tool does?
(backs the peacock-tail skill)

Sexual selection grows showy traits that do nothing for survival - the peacock's tail - and biology's answer is
the handicap principle: a signal is only worth trusting when it is costly to fake. A SKILL.md description is a
signal (it decides whether the skill gets picked); the tool is the body. For every skill with a tool this
extracts the claims and checks each against the code:

  named functions   `foo(`, `module.foo(`, `from module import a, b` in SKILL.md -> defined or imported by the tool?
  selftest counts   "selftest 7/7" -> how many PASS/FAIL lines the selftest really prints (it is run, from a
                    neutral cwd, with a timeout; --no-run skips this)
  capabilities      the description's clauses before "Use this/when" -> does at least one content word of each
                    clause appear in the tool's function/argument names, docstrings or selftest check names?

and ranks skills by over-claim score (2 per missing function, 3 per wrong selftest count, 1 per unbacked
clause). A flag is a prompt to look - the claim may be true in prose the matcher cannot see.

    python peacock.py --run                 # whole library (~/.claude/skills), runs every selftest (no args = selftest)
    python peacock.py --only a,b --no-run   # quick static pass
    python peacock.py --selftest
"""
from __future__ import annotations

import ast
import builtins
import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "exaptation-finder"))
sys.path.insert(0, str(SK / "skill-finder"))
from exaptation import DEFAULT_ROOT, parse, skill_dirs, tool_files  # noqa: E402
from find_skill import _tokens  # noqa: E402

NOT_CLAIMS = set(dir(builtins)) | set(keyword.kwlist) | {
    "python", "py", "e", "g", "i", "x", "f", "self", "main", "exp", "log", "sqrt", "argv", "path", "open"}
GENERIC = set(_tokens("skill tool python file run return value result output input data list number check "
                      "pure stdlib every each some print report give show plus also only like into over under "
                      "selftest test pass fail optional default new old real one two three"))
COUNT = re.compile(r"selftests?\b[^\d\n]{0,12}(\d+)\s*/\s*(\d+)", re.I)
CALL = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\(")
MODCALL = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\(")
FROM = re.compile(r"from\s+(\w+)\s+import\s+([\w ,]+)")


def _frontmatter(text: str):
    desc, body = "", text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            body = parts[2]
            for line in parts[1].splitlines():
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip("'\"")
    return desc, body


def clauses(desc: str) -> list:
    """Capability clauses: the description before its 'Use this/when' trigger, split on punctuation and dashes."""
    head = re.split(r"\bUse (?:this|it|when|whenever|before)\b", desc, maxsplit=1)[0]
    out = []
    for c in re.split(r"[;,()]|\s-\s|\s+then\s+|\s+and\s+", head):
        toks = [t for t in _tokens(c) if t not in GENERIC and len(t) >= 4]
        if len(toks) >= 2:
            out.append({"text": c.strip(), "toks": toks})
    return out


def tool_facts(paths: list) -> dict:
    """What the tool really has: defined names, imported names, module stems, a token corpus of names, argument
    names, docstrings and selftest strings; unparsable files are listed."""
    defined, imported, stems, words, bad, idents = set(), set(), set(), [], [], set()
    for p in paths:
        stems.add(p.stem)
        tree = parse(p)
        if tree is None:
            bad.append(p.name)
            continue
        for node in ast.walk(tree):
            for attr in ("id", "attr", "arg"):                         # every identifier the code mentions
                v = getattr(node, attr, None)
                if isinstance(v, str):
                    idents.add(v)
            if isinstance(node, ast.keyword) and node.arg:
                idents.add(node.arg)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
                words.append(node.name.replace("_", " "))
                words.append(ast.get_docstring(node) or "")
                if not isinstance(node, ast.ClassDef):
                    words.extend(a.arg.replace("_", " ") for a in ast.walk(node.args) if isinstance(a, ast.arg))
                if node.name in ("_selftest", "selftest") or node.name.startswith("test"):
                    words.extend(n.value for n in ast.walk(node)
                                 if isinstance(n, ast.Constant) and isinstance(n.value, str))
            elif isinstance(node, ast.ImportFrom):
                imported.update(a.asname or a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update((a.asname or a.name).split(".")[0] for a in node.names)
            elif isinstance(node, ast.Assign) and node in tree.body:
                defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
            words.append(str(tree.body[0].value.value))                    # module docstring
    return {"defined": defined, "imported": imported, "stems": stems, "corpus": set(_tokens(" ".join(words))),
            "idents": idents | defined | imported, "unparsable": bad}


def code_spans(text: str) -> str:
    """Only the code in a SKILL.md: fenced blocks, indented example lines and `inline` spans - prose that
    happens to contain 'word(' is not a function claim."""
    fenced = re.findall(r"```.*?```", text, flags=re.S)
    rest = re.sub(r"```.*?```", " ", text, flags=re.S)
    indented = [ln for ln in rest.splitlines() if ln.startswith("    ") and ln.strip()]
    return "\n".join(fenced + indented + re.findall(r"`([^`\n]+)`", rest))


def run_counts(paths: list, timeout: int = 60) -> dict:
    """{tool name: number of PASS/FAIL lines its --selftest prints} for tools that offer one (None = timeout)."""
    out = {}
    cwd = tempfile.mkdtemp(prefix="peacock_")
    try:
        for p in paths:
            src = p.read_text(encoding="utf-8", errors="replace")
            if "--selftest" not in src or "_selftest" not in src:
                continue
            try:
                r = subprocess.run([sys.executable, "-B", str(p), "--selftest"], cwd=cwd, capture_output=True,
                                   text=True, timeout=timeout, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                out[p.name] = sum(1 for ln in r.stdout.splitlines() if re.match(r"\s*(PASS|FAIL)\b", ln))
            except subprocess.TimeoutExpired:
                out[p.name] = None
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    return out


def audit_skill(skill_dir: Path, paths: list, run: bool = True) -> dict:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace") if (
        skill_dir / "SKILL.md").exists() else ""
    desc, body = _frontmatter(text)
    facts = tool_facts(paths)
    have = facts["idents"]
    code = code_spans(text)
    named = set()
    for m in CALL.finditer(code):
        named.add(m.group(1))
    for m in MODCALL.finditer(code):
        if m.group(1) in facts["stems"]:
            named.add(m.group(2))
    for m in FROM.finditer(code):
        if m.group(1) in facts["stems"]:
            named.update(n.strip() for n in m.group(2).split(",") if n.strip())
    named = {n for n in named if n not in NOT_CLAIMS and n not in facts["stems"] and len(n) > 1}
    missing = sorted(n for n in named if n not in have)
    unbacked = [c["text"] for c in clauses(desc) if not set(c["toks"]) & facts["corpus"]]
    counts, wrong = (run_counts(paths) if run else {}), []
    if run:
        real = [v for v in counts.values() if v is not None]
        for m in COUNT.finditer(text):
            claimed = int(m.group(2))
            if real and claimed not in real and claimed != sum(real):
                wrong.append(f"claims {m.group(1)}/{m.group(2)}, prints {'+'.join(map(str, real))}")
    score = 2 * len(missing) + 3 * len(wrong) + len(unbacked)
    return {"skill": skill_dir.name, "score": score, "missing_functions": missing, "wrong_counts": wrong,
            "unbacked_claims": unbacked, "claims": len(named) + len(clauses(desc)) + len(COUNT.findall(text)),
            "unparsable": facts["unparsable"]}


def audit(root=DEFAULT_ROOT, only=None, run: bool = True) -> list:
    """Every tool-backed skill, most over-claiming first (doc-only skills have no body to check and are left out)."""
    root = Path(root)
    by_skill = {}
    for s, p in tool_files(root):
        by_skill.setdefault(s, []).append(p)
    rows = [audit_skill(d, by_skill[d.name], run) for d in skill_dirs(root)
            if d.name in by_skill and (not only or d.name in only)]
    rows.sort(key=lambda r: (-r["score"], r["skill"]))
    return rows


def _selftest() -> bool:
    ok = {}
    root = Path(tempfile.mkdtemp(prefix="peacock_st_"))
    tool = ("import sys\n{defs}\ndef _selftest():\n    ok = {{{checks}}}\n"
            "    for k, v in ok.items():\n        print(('PASS ' if v else 'FAIL ') + k)\n    return all(ok.values())\n"
            "def main(a):\n    return 0 if _selftest() else 1\n"
            "if __name__ == '__main__':\n    sys.exit(main(sys.argv[1:]))  # --selftest\n")

    def mk(name, desc, body, src):
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n", encoding="utf-8")
        if src is not None:
            (d / f"{name.replace('-', '_')}.py").write_text(src, encoding="utf-8")
    try:
        mk("honest", "Compute a rolling mean of a price series over a sliding window. Use this whenever the user ...",
           "`honest.py` - selftest 2/2.\n\n    from honest import rolling_mean\n    rolling_mean(xs, window=5)\n",
           tool.format(defs="def rolling_mean(series, window=5):\n    '''Rolling mean of a price series.'''\n"
                       "    return series", checks="'mean of a sliding window': True, 'empty series': True"))
        mk("peacock", "Compute a rolling mean of prices, detect quantum turbulence regimes, forecast lunar "
           "harvests. Use this whenever the user ...",
           "`peacock.py` - selftest 9/9. Call `fly_away(sky)` or `peacock.rolling_mean(xs)`.\n",
           tool.format(defs="def rolling_mean(prices):\n    '''Rolling mean of prices.'''\n    return prices",
                       checks="'rolling mean': True"))
        mk("plain-doc", "A doc-only skill about lunar harvests and quantum turbulence.", "Prose only.", None)
        mk("no-front", "x", "y", "def broken(:\n")                                      # planted bad input
        (root / "no-front" / "SKILL.md").write_text("no frontmatter, calls `ghost_fn()` here; prose like word(s) is not a claim\n", encoding="utf-8")
        rows = {r["skill"]: r for r in audit(root)}
        ok["an honest skill raises no flag"] = rows["honest"]["score"] == 0
        ok["a named function the tool does not define is flagged; one it defines is not"] = (
            rows["peacock"]["missing_functions"] == ["fly_away"])
        ok["a selftest count that the tool does not print is flagged"] = (
            rows["peacock"]["wrong_counts"] == ["claims 9/9, prints 1"])
        ok["capability clauses with no trace in names/docstrings/check names are flagged; the real one is not"] = (
            len(rows["peacock"]["unbacked_claims"]) == 2 and not any(
                "rolling" in c for c in rows["peacock"]["unbacked_claims"]))
        ok["the most over-claiming skill ranks first"] = audit(root)[0]["skill"] == "peacock"
        ok["doc-only skills are left out (no body to check)"] = "plain-doc" not in rows
        ok["planted bad input: no frontmatter + unparsable tool is audited, not fatal"] = (
            rows["no-front"]["unparsable"] == ["no_front.py"] and rows["no-front"]["missing_functions"] == ["ghost_fn"])
        ok["--no-run mode skips counts but keeps the static flags"] = (
            {r["skill"]: r for r in audit(root, run=False)}["peacock"]["wrong_counts"] == [])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    only, run, root = None, "--no-run" not in argv, DEFAULT_ROOT
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    if "--root" in argv:
        root = Path(argv[argv.index("--root") + 1])
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 15
    rows = audit(root, only, run)
    flagged = [r for r in rows if r["score"]]
    print(f"{len(rows)} tool-backed skills audited ({'selftests run' if run else 'static only'}); "
          f"{len(flagged)} with at least one unbacked claim")
    for r in flagged[:top]:
        print(f"  {r['score']:3d}  {r['skill']}")
        for x in r["wrong_counts"]:
            print(f"         count: {x}")
        if r["missing_functions"]:
            print(f"         not defined: {', '.join(r['missing_functions'])}")
        for c in r["unbacked_claims"][:3]:
            print(f"         unbacked: {c[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
