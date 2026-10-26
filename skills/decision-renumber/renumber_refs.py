"""Move decision-number MENTIONS (D69..D129 -> D92..D152, i.e. +offset) in the files a branch ADDED, with proof that
no code changed. The exception path of decision-renumber step 5: use it only when text must cite main's real rows
(a manifest's LAWS list, a CLAUDE.md read by every session), never to rewrite a branch's history wholesale.

    python renumber_refs.py --repo <clone> --base <main-ref> --branch <branch-ref> --lo 69 --hi 129 --offset 23
    ... --apply            (default is a dry run that prints what would change)
    python renumber_refs.py --selftest      (hermetic: synthetic sources + a temp git repo)

What changes: .md/.patch wholly; .toml/.gitignore only in # comments; .py only in comments and docstrings (by
tokenizer position), so no runtime string - and no test matching one - changes. Never touched: prompts/ (the user's),
errata.md, progress.txt, tests.json (append-only), *.chain.jsonl, *.json, and any file the branch did not ADD (a file
both sides have, like the root CLAUDE.md, cites MAIN's numbers already: the 2026-10-13 slip).
Proof printed per .py file: the AST with docstrings removed is identical before and after (AST_SAME), else the file is
refused (AST_CHANGED) and left alone. Exit 1 if anything was refused.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

SKIP = re.compile(r"(^|/)(prompts/|errata\.md$|progress\.txt$|tests\.json$)|\.chain\.jsonl$|\.json$")


def pattern(lo: int, hi: int) -> re.Pattern[str]:
    alts = "|".join(str(n) for n in range(lo, hi + 1))     # \b on both sides: alternation order does not matter
    return re.compile(rf"\bD({alts})\b")


def shift(text: str, rx: re.Pattern[str], offset: int) -> tuple[str, int]:
    return rx.subn(lambda m: f"D{int(m.group(1)) + offset}", text)


def _docstring_ids(tree: ast.AST) -> set[int]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def code_shape(src: str) -> str:
    """ast.dump with every docstring blanked: equal shapes mean only comments/docstrings differ."""
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if id(n) in _docstring_ids(tree):
            n.value = ""   # type: ignore[attr-defined]
    return ast.dump(tree)


def sweep_py(src: str, rx: re.Pattern[str], offset: int) -> tuple[str, int]:
    lines = src.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    spans = []
    for i, t in enumerate(toks):
        if t.type == tokenize.STRING:
            prev = [x for x in toks[:i] if x.type not in (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT)]
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            starts = not prev or prev[-1].type == tokenize.NEWLINE or (prev[-1].type == tokenize.OP and prev[-1].string == ":")
            if not (starts and nxt is not None and nxt.type in (tokenize.NEWLINE, tokenize.ENDMARKER)):
                continue
        elif t.type != tokenize.COMMENT:
            continue
        spans.append((offs[t.start[0] - 1] + t.start[1], offs[t.end[0] - 1] + t.end[1]))
    out, n, last = [], 0, 0
    for a, b in spans:
        new, k = shift(src[a:b], rx, offset)
        out.append(src[last:a] + new)
        n, last = n + k, b
    out.append(src[last:])
    return "".join(out), n


def sweep_comments(src: str, rx: re.Pattern[str], offset: int) -> tuple[str, int]:
    out, n = [], 0
    for ln in src.splitlines(keepends=True):
        i = ln.find("#")
        if i >= 0 and ln[:i].count('"') % 2 == 0:
            new, k = shift(ln[i:], rx, offset)
            ln, n = ln[:i] + new, n + k
        out.append(ln)
    return "".join(out), n


def sweep_file(rel: str, src: str, rx: re.Pattern[str], offset: int) -> tuple[str, int, str]:
    """-> (new text, references moved, status) with status one of OK, AST_SAME, AST_CHANGED, SKIPPED."""
    if SKIP.search(rel):
        return src, 0, "SKIPPED"
    if rel.endswith(".py"):
        new, n = sweep_py(src, rx, offset)
        if n and code_shape(new) != code_shape(src):
            return src, 0, "AST_CHANGED"
        return new, n, "AST_SAME"
    if rel.endswith((".md", ".patch")):
        return (*shift(src, rx, offset), "OK")
    if rel.endswith((".toml", ".gitignore")):
        return (*sweep_comments(src, rx, offset), "OK")
    return src, 0, "SKIPPED"


def added_files(repo: Path, base: str, branch: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", "--diff-filter=A", f"{base}...{branch}"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return out.split()


def _rmtree(path: Path) -> None:
    """shutil.rmtree that also removes git's read-only object files on Windows."""
    import os
    import shutil
    import stat

    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


def _selftest() -> bool:
    """Hermetic: synthetic sources, then one temp git repo with a branch. Prints PASS/FAIL per check."""
    import io
    import tempfile
    from contextlib import redirect_stdout

    rx = pattern(69, 71)
    ok: dict[str, bool] = {}
    ok["the pattern matches whole numbers only"] = (shift("D69 D700 D7 (D71)", rx, 23) == ("D92 D700 D7 (D94)", 2))
    py = '"""Module doc: D70."""\nX = "D70"  # see D70\n\n\ndef f():\n    """f doc D69."""\n    return "D69"\n'
    new, n, status = sweep_file("tool.py", py, rx, 23)
    ok["planted: .py runtime strings stay, comments and docstrings move"] = (
        status == "AST_SAME" and n == 3 and 'X = "D70"' in new and 'return "D69"' in new
        and "D93." in new and "# see D93" in new and "f doc D92." in new)
    _, n, status = sweep_file("bad.py", 'x = 1\n"D70"\n', rx, 23)
    ok["planted: a bare non-docstring string is REFUSED (AST_CHANGED)"] = status == "AST_CHANGED" and n == 0
    ok["append-only and the user's files are SKIPPED"] = all(
        sweep_file(p, "D70\n", rx, 23)[2] == "SKIPPED"
        for p in ("tests.json", "shared/x.chain.jsonl", "prompts/p.md", "errata.md", "progress.txt", "a.json"))
    ok[".md moves wholly, .toml only in comments"] = (
        sweep_file("a.md", "D70\n", rx, 23)[0] == "D93\n"
        and sweep_file("a.toml", 'k = "D70"  # D70\n', rx, 23)[0] == 'k = "D70"  # D93\n')
    tmp = Path(tempfile.mkdtemp(prefix="renumber_refs_selftest_"))
    try:
        def g(*args: str) -> None:
            subprocess.run(["git", "-c", "user.name=selftest", "-c", "user.email=selftest@invalid", *args],
                           cwd=tmp, check=True, capture_output=True)
        (tmp / "shared.md").write_text("cites D70\n", encoding="utf-8", newline="\n")
        g("init", "-q")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        g("branch", "-q", "basebr")
        g("checkout", "-q", "-b", "feature")
        (tmp / "shared.md").write_text("cites D70 and D71\n", encoding="utf-8", newline="\n")
        (tmp / "new.md").write_text("new note: D70\n", encoding="utf-8", newline="\n")
        g("add", "-A")
        g("commit", "-q", "-m", "feature")
        args = ["--repo", str(tmp), "--base", "basebr", "--branch", "feature", "--lo", "69", "--hi", "71", "--offset", "23"]
        with redirect_stdout(io.StringIO()):
            dry = main(args)
        ok["temp repo: a dry run writes nothing"] = (dry == 0 and
                                                     (tmp / "new.md").read_text(encoding="utf-8") == "new note: D70\n")
        with redirect_stdout(io.StringIO()):
            applied = main(args + ["--apply"])
        ok["temp repo: --apply moves only files the branch ADDED"] = (
            applied == 0 and (tmp / "new.md").read_text(encoding="utf-8") == "new note: D93\n"
            and (tmp / "shared.md").read_text(encoding="utf-8") == "cites D70 and D71\n")
    except Exception as e:  # a crash is a FAIL line, not a traceback
        ok[f"temp-repo checks ran ({type(e).__name__}: {e})"] = False
    finally:
        _rmtree(tmp)
    for name, passed in ok.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return all(ok.values())


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--lo", type=int, required=True)
    ap.add_argument("--hi", type=int, required=True)
    ap.add_argument("--offset", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    repo, rx = Path(a.repo), pattern(a.lo, a.hi)
    total, refused = 0, []
    for rel in added_files(repo, a.base, a.branch):
        p = repo / rel
        if not p.is_file():
            continue
        try:
            raw = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        crlf = "\r\n" in raw
        new, n, status = sweep_file(rel, raw.replace("\r\n", "\n"), rx, a.offset)
        if status == "AST_CHANGED":
            refused.append(rel)
            print(f"REFUSED {rel}: AST_CHANGED (a code string would change)")
            continue
        if n:
            total += n
            print(f"{n:4d} {status:<9} {rel}")
            if a.apply:
                p.write_bytes((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print(f"total {total} reference(s) {'moved' if a.apply else 'would move (dry run)'}; refused {len(refused)}")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
