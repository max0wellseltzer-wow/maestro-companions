"""Is a plan self-contained? Four checks over one markdown plan file:
  1. SECTION_REF  - a `§N` / `§N.M` pointer with no heading of that number in the file;
  2. CARD_ID      - an item id (default GT<n>) used but never given a card (`### GT<n>` heading or a `| GT<n> |` row);
  3. CODE         - a code-shaped token (1-3 capitals + digits, e.g. F51, PG10, RC1) absent from the glossary section;
  4. CITATION     - a backticked `path[:line,...]` that resolves to no file in any repo, or whose line is past the end.
Repos: --root DIR (its git `origin/main` plus every sub-folder tv-* at `origin/master`); --prefix harness/=tv-tests ...
maps a path prefix to one repo. A citation on a line containing "new" or "creates" is counted CREATED, not BAD.
Each repo's tree is listed once (`git ls-tree`); a blob is read only for a path whose lines are cited, so the git
cost is bounded by repos + cited-line paths, not citations x repos. Progress goes to stderr (--quiet silences it).

    python plan_closure.py PLAN.md --root <workspace> --glossary "^## \\d+\\. Every code" [--prefix harness/=tv-tests]
    python plan_closure.py --selftest
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

CODE = re.compile(r"\b[A-Z]{1,3}\d{1,3}\b")
CITE = re.compile(r"`([\w./-]+\.(?:py|md|jsonl|json|toml|sh|bat|txt|csv))(?::([\d,\- ]+))?(?=[`\s])")
# a marker beside a path says it does not exist yet (or on purpose): it may sit before a list of paths, or after one
_ITEMS = r"(?:`[^`]*`\s*(?:,|and|or)?\s*)*"
BEFORE = re.compile(rf"(?:\bnew|\bcreates|\bwrites|\bgenerated|\bno|\babsent:?|e\.g\.,?)\s*{_ITEMS}$", re.I)
AFTER = re.compile(r"^`?\s*(?:\((?:new|created|generated|on (?:this )?branch|not in git|scratch|absent|not yet)\b|"
                   r"(?:does not exist|is absent))", re.I)


class Repos:
    def __init__(self, root: Path, prefix: dict[str, str], extra_dirs: tuple[Path, ...] = ()) -> None:
        self.repos = {"root": (root, "origin/main")}
        for d in sorted(root.iterdir()) if root.is_dir() else []:
            if d.is_dir() and d.name.startswith("tv-"):
                self.repos[d.name] = (d, "origin/master")
        self.prefix = prefix
        self.extra = extra_dirs                      # plain folders, e.g. this branch's checkout
        self._lines: dict[tuple[str, str], int | None] = {}   # (repo, path) -> line count, filled by prefetch()

    @lru_cache(maxsize=None)
    def tree(self, repo: str) -> frozenset:
        """Every path in `repo` at its ref, from ONE `git ls-tree`. Existence is answered from this set, so a plan with
        hundreds of citations costs one subprocess per repo instead of one `git show` per path per repo (the
        2026-10-24 survey: 666 distinct paths x 15 repos on the 588 KB PLAN.md, 590 s and no output)."""
        d, ref = self.repos[repo]
        r = subprocess.run(["git", "-C", str(d), "ls-tree", "-r", "--name-only", "-z", ref], capture_output=True)
        return frozenset(r.stdout.decode("utf-8", "replace").split("\0")) - {""} if r.returncode == 0 else frozenset()

    @lru_cache(maxsize=None)
    def blob(self, repo: str, path: str) -> str | None:
        if path not in self.tree(repo):
            return None
        d, ref = self.repos[repo]
        r = subprocess.run(["git", "-C", str(d), "show", f"{ref}:{path}"], capture_output=True)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None

    def copies(self, path: str) -> list[tuple[str, str]]:
        """(repo, path-in-repo) for every copy of `path` that exists: a prefixed path in its repo only, any other in
        every repo, then the skills folder for a skill's own `<skill>/<script>.py`; 'disk' marks the extra folders."""
        disk = [("disk", str(d / path)) for d in self.extra if (d / path).is_file()]
        for pre, repo in self.prefix.items():
            if path.startswith(pre) and repo in self.repos:
                return ([(repo, path)] if path in self.tree(repo) else []) + disk
        found = [(r, path) for r in self.repos if path in self.tree(r)] + disk
        if not found and "/" in path and f".claude/skills/{path}" in self.tree("root"):
            found = [("root", f".claude/skills/{path}")]
        return found

    def text(self, repo: str, path: str) -> str | None:
        if repo == "disk":
            return Path(path).read_text(encoding="utf-8", errors="replace")
        return self.blob(repo, path)

    def prefetch(self, wanted: dict[str, list[str]]) -> None:
        """Line counts of many paths per repo from ONE `git cat-file --batch` per repo. A git spawn costs 0.5-2 s on
        this PC, so the 117 cited-line paths of the 588 KB PLAN.md took 3 minutes as single `git show` calls; batched
        they cost one spawn per repo that holds any of them."""
        for repo, paths in wanted.items():
            d, ref = self.repos[repo]
            want = [p for p in dict.fromkeys(paths) if p in self.tree(repo) and (repo, p) not in self._lines]
            if not want:
                continue
            r = subprocess.run(["git", "-C", str(d), "cat-file", "--batch"],
                               input="".join(f"{ref}:{p}\n" for p in want).encode("utf-8"), capture_output=True)
            data, pos = r.stdout, 0
            for p in want:                             # `<sha> blob <size>\n<bytes>\n`, or `<object> missing\n`
                nl = data.find(b"\n", pos)
                if nl < 0:
                    break
                head = data[pos:nl].split()
                pos = nl + 1
                if len(head) == 3 and head[1] == b"blob":
                    size = int(head[2])
                    self._lines[(repo, p)] = data[pos:pos + size].count(b"\n") + 1
                    pos += size + 1

    def line_count(self, repo: str, path: str) -> int | None:
        if repo == "disk":
            return Path(path).read_text(encoding="utf-8", errors="replace").count("\n") + 1
        if (repo, path) not in self._lines:            # not prefetched: one `git show`, cached
            t = self.blob(repo, path)
            self._lines[(repo, path)] = None if t is None else t.count("\n") + 1
        return self._lines[(repo, path)]

    def satisfies(self, path: str, nums: list[int]) -> bool:
        """Some copy of `path` exists and holds every cited line. Existence comes from the tree and line counts from
        the prefetched batch, so the git cost is bounded by the number of repos, whatever the plan's size."""
        for repo, p in self.copies(path):
            if not nums:
                return True
            n = self.line_count(repo, p)
            if n is not None and all(k <= n for k in nums):
                return True
        return False

    def resolve(self, path: str) -> list[str]:
        """Text of every existing copy of `path` (the old API, kept for callers; satisfies() is the cheap check)."""
        return [t for r, p in self.copies(path) if (t := self.text(r, p)) is not None]


def audit(text: str, repos: Repos | None, glossary_re: str, card_prefix: str = "GT",
          progress=None) -> dict[str, list[str]]:
    """progress: optional callable(str) given one line per finished class and, in the citation pass, a line every two
    seconds - partial results instead of the silence the 2026-10-24 survey watched for 590 s."""
    say = progress or (lambda msg: None)
    out: dict[str, list[str]] = {"SECTION_REF": [], "CARD_ID": [], "CODE": [], "CITATION": [], "CREATED": []}
    heads = set(re.findall(r"^#{2,4} §?(\d+(?:\.\d+)*)[. ]", text, re.M))
    for ref in sorted(set(re.findall(r"§(\d+(?:\.\d+)*)", text))):
        if ref not in heads and not any(h.startswith(ref + ".") for h in heads):
            out["SECTION_REF"].append(ref)
    say(f"SECTION_REF: {len(out['SECTION_REF'])}")
    cards = set(re.findall(rf"^### ({card_prefix}\d+)\b", text, re.M)) | set(
        re.findall(rf"^\| ({card_prefix}\d+) \|", text, re.M))
    out["CARD_ID"] = sorted(set(re.findall(rf"\b{card_prefix}\d+\b", text)) - cards)
    say(f"CARD_ID: {len(out['CARD_ID'])}")
    m = re.search(glossary_re, text, re.M)
    gloss = text[m.start():] if m else ""
    families = set(re.findall(r"\b([A-Z]{1,3})<n>", gloss))              # "D<n>: row n of DECISIONS.md"
    ranges = [(p, int(a), int(b)) for p, a, q, b in re.findall(r"\b([A-Z]{1,3})(\d+)-([A-Z]{1,3})?(\d+)\b", gloss)
              if not q or q == p]                                          # "M1-M100", "F1-F4", "OS01-OS53"

    def defined(tok: str) -> bool:
        pm = re.match(r"([A-Z]{1,3})(\d+)$", tok)
        if tok in gloss or (pm and pm.group(1) in families):
            return True
        return bool(pm) and any(p == pm.group(1) and a <= int(pm.group(2)) <= b for p, a, b in ranges)

    out["CODE"] = sorted(t for t in set(CODE.findall(text))
                         if not t.startswith(card_prefix) and not defined(t)) if m else ["NO_GLOSSARY_SECTION"]
    say(f"CODE: {len(out['CODE'])}")
    if repos is not None:
        rows = text.splitlines()
        cites = []                                   # (line no, line, path, cited lines, nums, start, end)
        for n, line in enumerate(rows, 1):
            for mt in CITE.finditer(line):
                path, cited = mt.group(1), mt.group(2)
                if "<" in path or (path.startswith(".") and "/" not in path):    # `.blend.toml` is a file type
                    continue
                nums = [int(x) for x in re.split(r"[,\- ]+", cited) if x] if cited else []
                cites.append((n, line, path, cited, nums, mt.start(), mt.end()))
        say(f"CITATION: {len(cites)} citations on {len(rows)} lines; listing {len(repos.repos)} repo tree(s)")
        for name in repos.repos:
            say(f"CITATION: {name}: {len(repos.tree(name))} paths at {repos.repos[name][1]}")
        wanted: dict[str, list[str]] = {}
        for _, _, path, _, nums, _, _ in cites:
            if nums:
                for repo, p in repos.copies(path):
                    if repo != "disk":
                        wanted.setdefault(repo, []).append(p)
        say(f"CITATION: reading {sum(len(set(v)) for v in wanted.values())} blob(s) from {len(wanted)} repo(s), "
            "one batch each")
        repos.prefetch(wanted)
        misses: list[tuple[int, str, str | None, bool]] = []
        tick = time.monotonic()
        for i, (n, line, path, cited, nums, start, end) in enumerate(cites, 1):
            if not repos.satisfies(path, nums):
                marked = bool(BEFORE.search(line[:start]) or AFTER.match(line[end:]))
                misses.append((n, path, cited, marked))
            if time.monotonic() - tick >= 2.0:
                tick = time.monotonic()
                say(f"CITATION: {i}/{len(cites)} checked (line {n}/{len(rows)}), {len(misses)} unresolved so far")
        announced = {p for _, p, _, mk in misses if mk}      # a path marked new once is new at every mention
        for n, path, cited, marked in misses:
            key = "CREATED" if marked or path in announced else "CITATION"
            out[key].append(f"L{n} {path}{':' + cited if cited else ''}")
        say(f"CITATION: {len(out['CITATION'])}  CREATED: {len(out['CREATED'])}  ({len(cites)} citations checked)")
    return out


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        g = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, check=True)  # noqa: E731
        g("init", "-q", "-b", "main")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        (root / "a.py").write_text("1\n2\n3\n")
        g("add", "a.py")
        g("commit", "-qm", "1")
        g("update-ref", "refs/remotes/origin/main", "HEAD")
        side = root / "side"
        side.mkdir()
        (side / "s.md").write_text("x\n")
        plan = ("## 1. Goal\nsee §1 and §7; card GT1 and GT2; code F51 and RC1, D44, M7, M300\n### GT1: x\n"
                "uses `a.py:2` and `a.py:9` and `b.py`; creates `c.py` (new)\n## 17. Every code\nRC1 is defined; "
                "D<n> is a decision row; M1-M100 are milestones\n"
                "absent: no `d.py`, `e.py` and `f.py`; later `c.py` again; `metrics.sharpe` and a `.blend.toml`\n"
                "branch file `s.md`\n")
        r = audit(plan, Repos(root, {}, (side,)), r"^## \d+\. Every code")
        # bounded git cost: 200 distinct missing `path:line` citations must cost one `ls-tree`, never one `show` each
        # (the 2026-10-24 survey: 666 paths x 15 repos = ~10,000 subprocesses, timed out at 590 s)
        many = "## 1. Goal\n" + "\n".join(f"uses `miss{i}.py:3`" for i in range(200)) + "\n## 17. Every code\n"
        calls: list[str] = []
        real_run = subprocess.run

        def counting_run(cmd, *args, **kwargs):
            calls.append(cmd[3] if len(cmd) > 3 else "?")
            return real_run(cmd, *args, **kwargs)
        subprocess.run = counting_run
        try:
            r2 = audit(many, Repos(root, {}, ()), r"^## \d+\. Every code")
        finally:
            subprocess.run = real_run
    checks = [r["SECTION_REF"] == ["7"], r["CARD_ID"] == ["GT2"], r["CODE"] == ["F51", "M300"],
              r["CITATION"] == ["L4 a.py:9", "L4 b.py"],
              r["CREATED"] == ["L4 c.py", "L7 d.py", "L7 e.py", "L7 f.py", "L7 c.py"],
              len(r2["CITATION"]) == 200 and calls == ["ls-tree"]]
    print(f"SELFTEST {'PASS' if all(checks) else 'FAIL'} {sum(checks)}/{len(checks)}"
          + ("" if all(checks) else f" {r} git calls={calls[:5]}x{len(calls)}"))
    return 0 if all(checks) else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(_selftest())
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--root", default=None)
    ap.add_argument("--glossary", default=r"^## \d+\. Every code")
    ap.add_argument("--cards", default="GT")
    ap.add_argument("--prefix", action="append", default=[], help="path-prefix=repo, e.g. harness/=tv-tests")
    ap.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    a = ap.parse_args()
    reps = Repos(Path(a.root), dict(p.split("=", 1) for p in a.prefix)) if a.root else None
    say = None if a.quiet else (lambda msg: print(msg, file=sys.stderr, flush=True))
    res = audit(Path(a.plan).read_text(encoding="utf-8"), reps, a.glossary, a.cards, progress=say)
    for k, v in res.items():
        print(f"{k}: {len(v)}" + (f"  {v[:12]}" if v and k != "CREATED" else ""))
    bad = sum(len(res[k]) for k in ("SECTION_REF", "CARD_ID", "CODE", "CITATION"))
    print("CLOSED" if bad == 0 else f"OPEN_REFERENCES {bad}")
    sys.exit(0 if bad == 0 else 1)
