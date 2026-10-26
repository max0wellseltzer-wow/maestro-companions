"""hostile_caller.py - read an API the way a caller who wants to cheat would: the workspace's own attack list.

    python hostile_caller.py scan PATH [PATH ...] [--json]
    python hostile_caller.py params            # a pytest parametrize list of hostile inputs to paste into a test
    python hostile_caller.py --selftest

Rules (each one a TRUST erratum in tv-forge, tv-core, tv-tests or tv-harvest):
  H-SUBSTR   `x in actor` / `model_id in author` - substring membership on an identity string: 'ai:gpt' is "in"
             'ai:gpt-5-max' (tv-forge E20). Compare ids exactly, or parse them.
  H-TRUTHY   `if not check(...)` where check only returns dicts: {allowed: False} is truthy (tv-forge E1).
  H-CLAIM    a caller-supplied value compared to a trust word ("human", "max", "PASSED", "verified", "approved"):
             the caller declares its own kind or verdict (tv-forge E47 author.kind 'human'; tv-core E1 "PASSED").
  H-TTY      isatty() as the test for "a person is here": the NUL device answers True on Windows (tv-forge E68).
  H-EVIDENCE an evidence/refs/proof parameter never checked against existing records (tv-forge E48: ['trust me', 42]).
  H-ECHO     a writer stores a caller parameter under a trusted key (verified, verified_by, granted_by, is_human,
             trusted) (tv-forge E61).
  H-REPLAY   grant/spend/redeem/consume/unmask/reveal with nothing that remembers it already happened (append_if,
             used, spent, seen, already, once, nonce) (tv-forge E43's holdout look spent twice).
Findings are places to look - each needs a hostile test (see `params`) before it is called real or safe.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ID_WORD = re.compile(r"(actor|author|owner|user|who|caller|model_id|model|principal|identity|account|by)$", re.I)
TRUST_WORDS = {"human", "person", "owner", "admin", "passed", "verified", "approved", "trusted"}   # not max/pass:
EVIDENCE = re.compile(r"^(new_)?(evidence|evidence_ids|citations|proof|proofs)$")                # max() and grades
CHECKING = re.compile(r"verify|exist|lookup|resolve|find|check|validat|known|entries|seqs|ids_of|records|get\b|"
                      r"problem|evidence")       # passing it to evidence_problems() / validate_x() is delegation
TRUSTED_KEYS = {"verified", "verified_by", "granted_by", "is_human", "trusted", "approved_by", "human"}
REPLAYABLE = re.compile(r"^(grant|spend|redeem|consume|unmask|reveal|claim)(_[a-z_]+)?$")   # verbs, not revealed()
REMEMBERS = re.compile(r"append_if|append_unless|\bused\b|spent|\bseen\b|already|once|nonce|redeemed|consumed|revealed|"
                       r"unmasked|granted", re.I)


def _ident(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return node.id if isinstance(node, ast.Name) else None


def _funcs(tree):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _dict_only(fn) -> bool:
    rets = [r for r in ast.walk(fn) if isinstance(r, ast.Return)]
    return bool(rets) and all(isinstance(r.value, ast.Dict) or (isinstance(r.value, ast.Call) and
                                                                 isinstance(r.value.func, ast.Name) and
                                                                 r.value.func.id == "dict") for r in rets)


def _call_key(n: ast.AST):
    if not isinstance(n, ast.Call):
        return None
    f = n.func
    if isinstance(f, ast.Name):
        return ("top", None, f.id)
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return ("method", None, f.attr) if f.value.id in ("self", "cls") else ("top", f.value.id, f.attr)
    return None


def dict_returners(trees: dict[Path, ast.AST]) -> set:
    shapes: dict[tuple, set[bool]] = {}
    for f, tree in trees.items():
        methods = {id(m) for c in ast.walk(tree) if isinstance(c, ast.ClassDef) for m in c.body}
        for fn in _funcs(tree):
            keys = [("method", None, fn.name)] if id(fn) in methods else [("top", None, fn.name), ("top", f.stem, fn.name)]
            for k in keys:
                shapes.setdefault(k, set()).add(_dict_only(fn))
    return {k for k, v in shapes.items() if v == {True}}


def scan_tree(path: Path, tree: ast.AST, dicts: set, src: str) -> list[tuple[str, str, int, str]]:
    p = str(path)
    out = []
    mappings = {t.value.id for t in ast.walk(tree) if isinstance(t, ast.Subscript) and isinstance(t.ctx, ast.Store)
                and isinstance(t.value, ast.Name)} | \
        {a.targets[0].id for a in ast.walk(tree) if isinstance(a, ast.Assign) and len(a.targets) == 1
         and isinstance(a.targets[0], ast.Name) and isinstance(a.value, (ast.Dict, ast.Set, ast.List, ast.DictComp,
                                                                         ast.SetComp, ast.ListComp))}
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], (ast.In, ast.NotIn)):
            right = n.comparators[0]
            rid, lid = _ident(right), _ident(n.left)
            if rid and ID_WORD.search(rid) and lid and rid not in mappings and \
                    not isinstance(right, (ast.List, ast.Tuple, ast.Set, ast.Dict)) and \
                    re.search(r"id|name|model|actor|author|user|prefix", lid, re.I):
                out.append(("H-SUBSTR", p, n.lineno, f"`{ast.unparse(n)[:50]}` is substring membership on an "
                                                     "identity string: compare exactly"))
        if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            t = n.test.operand if isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not) else n.test
            if _call_key(t) in dicts:
                out.append(("H-TRUTHY", p, n.lineno, f"{ast.unparse(t)[:40]} returns a dict: always truthy when "
                                                     "non-empty - read its allowed/ok field"))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "isatty" \
                and "GetConsoleMode" not in src:
            out.append(("H-TTY", p, n.lineno, "isatty() as 'a person is here': NUL answers True on Windows; also "
                                              "require GetConsoleMode on the stdin handle"))
    for fn in _funcs(tree):
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs} - {"self", "cls"}
        body_nodes = fn.body[1:] if fn.body and isinstance(fn.body[0], ast.Expr) and \
            isinstance(fn.body[0].value, ast.Constant) else fn.body
        body = "\n".join(ast.unparse(s) for s in body_nodes)
        for c in ast.walk(fn):
            if isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.ops[0], (ast.Eq, ast.NotEq, ast.In)):
                sides = [c.left, c.comparators[0]]
                lits = [s.value.lower() for s in sides if isinstance(s, ast.Constant) and isinstance(s.value, str)]
                lits += [e.value.lower() for s in sides if isinstance(s, (ast.Tuple, ast.List, ast.Set))
                         for e in s.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                roots = {_root_name(s) for s in sides} & params
                if roots and set(lits) & TRUST_WORDS:
                    out.append(("H-CLAIM", p, c.lineno, f"{fn.name}(): the caller's `{sorted(roots)[0]}` is compared "
                                                        f"to {sorted(set(lits) & TRUST_WORDS)[0]!r} - the caller "
                                                        "declares its own kind/verdict"))
                    break
        for a in params:
            if not EVIDENCE.match(a) or a not in body:
                continue
            names = {a} | {ast.unparse(g.target) for g in ast.walk(fn) if isinstance(g, (ast.For, ast.comprehension))
                           and ast.unparse(g.iter) == a}
            checked = any(isinstance(c, ast.Call) and CHECKING.search(ast.unparse(c.func)) and
                          {x.id for x in ast.walk(c) if isinstance(x, ast.Name)} & names for c in ast.walk(fn)) or \
                any(isinstance(c, ast.Compare) and isinstance(c.ops[0], (ast.In, ast.NotIn)) and
                    _root_name(c.left) in names for c in ast.walk(fn)) or \
                any(isinstance(g, ast.For) and ast.unparse(g.iter) == a and
                    any(isinstance(c, ast.Compare) and isinstance(c.ops[0], (ast.In, ast.NotIn, ast.Lt, ast.GtE))
                        for c in ast.walk(g)) for g in ast.walk(fn))       # each item looked up inside the loop
            if not checked:
                out.append(("H-EVIDENCE", p, fn.lineno, f"{fn.name}() accepts `{a}` without checking each item "
                                                        "names an existing record"))
        if re.match(r"^_?(record|append|grant|seal|register|log|write|add|publish)", fn.name):
            for d in ast.walk(fn):
                if isinstance(d, ast.Dict):
                    for k, v in zip(d.keys, d.values):
                        if isinstance(k, ast.Constant) and k.value in TRUSTED_KEYS and isinstance(v, ast.Name) \
                                and v.id in params:
                            out.append(("H-ECHO", p, d.lineno, f"{fn.name}() stores the caller's `{v.id}` as the "
                                                               f"trusted field {k.value!r}"))
        if REPLAYABLE.match(fn.name) and not REMEMBERS.search(body):
            out.append(("H-REPLAY", p, fn.lineno, f"{fn.name}() can be called twice: nothing records that it "
                                                  "already happened"))
    return out


def scan(paths: list[Path]) -> list[tuple[str, str, int, str]]:
    trees, srcs = {}, {}
    for root in paths:
        for f in (sorted(root.rglob("*.py")) if root.is_dir() else [root]):
            try:
                srcs[f] = f.read_text(encoding="utf-8", errors="replace")
                trees[f] = ast.parse(srcs[f])
            except (SyntaxError, ValueError):
                pass
    dicts = dict_returners(trees)
    out = []
    for f, t in trees.items():
        if f.name.startswith("test_") or "tests" in f.parts:
            continue
        out += scan_tree(f, t, dicts, srcs[f])
    return out


PARAMS = '''HOSTILE = [   # (label, value) - feed each where a caller controls the input; every one must be REFUSED
    ("substring id", "ai:gpt"),                       # 'ai:gpt' in 'ai:gpt-5-max' (tv-forge E20)
    ("id with suffix", "ai:claude-opus-5-5-evil"),
    ("unicode lookalike", "ai:cl\\u0430ude"),          # Cyrillic a
    ("kind spoof", {"kind": "human", "id": "max"}),     # an AI asking as a human (tv-forge E47)
    ("self-declared verdict", "PASSED"),               # tv-core E1
    ("evidence nonsense", ["trust me", 42]),           # tv-forge E48
    ("evidence future id", [10**9]),
    ("empty dict (truthy check)", {}),
    ("dict refusal (truthy)", {"allowed": False, "reason": "no"}),   # tv-forge E1
    ("caller text as field", "VERIFIED by the user"),       # tv-forge E61
    ("None", None),
    ("whitespace id", " max "),
]
# Replay: call the same grant/spend/reveal twice with identical arguments - the second must refuse (tv-forge E43).
# Person doors: run the CLI with stdin from NUL (`< NUL`) - it must refuse (tv-forge E68).
'''


# ----------------------------------------------------------------------------------------------------- selftest
PLANT = '''import sys
def check(actor, cap):
    if actor.startswith("ai:"):
        return {"allowed": False, "reason": "ai"}
    return {"allowed": True}
def propose(model_id, actor, author, evidence):
    if model_id in actor:
        pass
    if not check(actor, "propose"):
        raise PermissionError
    if author["kind"] == "human":
        spend_human_ledger()
    return list(evidence)
def grant(feature):
    if not sys.stdin.isatty():
        raise PermissionError("person only")
    write(feature)
def record_review(text, verified_by):
    return {"text": text, "verified_by": verified_by}
'''
CLEAN = '''import sys
def check(actor, cap):
    return not actor.startswith("ai:")
def propose(model_id, actor, author, evidence, store):
    if model_id == parse_actor(actor).model:
        pass
    if not check(actor, "propose"):
        raise PermissionError
    if verified_kind(author) == "human":
        spend_human_ledger()
    return [e for e in evidence if store.exists(e)]
def grant(feature, chain):
    if not person_present():
        raise PermissionError("person only")
    chain.append_if(lambda rs: feature not in rs, feature)
def record_review(text, reviewer_id):
    return {"text": text, "verified_by": lookup_reviewer(reviewer_id)}
'''


def _selftest() -> bool:
    import tempfile
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "plant").mkdir()
        (Path(td) / "clean").mkdir()
        (Path(td) / "plant" / "api.py").write_text(PLANT, encoding="utf-8")
        (Path(td) / "clean" / "api.py").write_text(CLEAN, encoding="utf-8")
        found = scan([Path(td) / "plant"])
        rules = {r for r, *_ in found}
        for rule, why in (("H-SUBSTR", "model_id in actor (tv-forge E20)"), ("H-TRUTHY", "not check() on a dict (E1)"),
                          ("H-CLAIM", "author['kind'] == 'human' (E47)"), ("H-TTY", "isatty person door (E68)"),
                          ("H-EVIDENCE", "evidence never checked (E48)"), ("H-ECHO", "verified_by from the caller (E61)"),
                          ("H-REPLAY", "grant() with no memory (E43)")):
            check(f"{rule}: {why}", rule in rules)
        fc = scan([Path(td) / "clean"])
        check("clean twins: 0 findings", fc == [])
        if fc:
            print("   ", fc)
        check("membership in a set of ids is not a substring check",
              scan_tree(Path("x.py"), ast.parse("def f(model_id, allowed_ids):\n    return model_id in allowed_ids\n"),
                        set(), "") == [])
        check("membership in a dict built in the module (owner[name] = ...) is not a substring check",
              scan_tree(Path("x.py"), ast.parse("def f(names):\n    owner = {}\n    for name in names:\n"
                                                "        if name in owner:\n            pass\n        owner[name] = 1\n"),
                        set(), "") == [])
    check("params: the hostile list compiles and holds 12 inputs", len(eval(PARAMS.split("=", 1)[1].split("]\n#")[0]
                                                                          + "]")) == 12)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "params":
        print(PARAMS)
        return 0
    if argv[0] == "scan":
        found = scan([Path(a) for a in argv[1:] if not a.startswith("--")])
        if "--json" in argv:
            print(json.dumps([dict(zip(("rule", "path", "line", "why"), f)) for f in found], indent=1))
        else:
            for r, p, ln, why in found:
                print(f"{r:10} {p}:{ln}  {why}")
            print(f"{len(found)} finding(s)")
        return 1 if found else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
