"""pov_core - the shared engine of the point-of-view family (backs the pov-core skill).

Every point-of-view skill is a LENS: a function apply(subject, **opts) -> view dict that changes how one subject is
seen (focus, vantage, persona, time, scale, distortion, obliteration, mutation, the subconscious, the senses, the
plural, the epistemic, values). This module holds what the lenses share, so each lens file is only its own operation:

    subject loading   load_subject(arg) -> (kind, value); kinds text / series / table / code / plan / items
    text helpers      sentences, words, keywords, numbers_with_units, STOP
    series helpers    mean, sd, median, mad, quantile, diff, moving_average, ranks, zscores, corr
    the view record   view(name, kind, findings, summary, **stats) and render(view)
    the probe corpus  PROBES - one small subject per kind, shared by every lens selftest and by distinctness()
    distinctness      fingerprint(view) and distinctness(lens_modules) - proves two lenses see differently
    cli               run_cli(name, apply, argv, selftest) - the shared `python <lens>.py <file|text> [--json]` entry

    python pov_core.py --selftest
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import sys
from pathlib import Path

STOP = set("""a an the and or but if then else of to in on at by for with from as is are was were be been being it its
this that these those there here we you he she they i me my our your their them his her not no so do does did done
have has had will would can could should may might must shall than too very just also into over under about
what which who whom whose when where why how all any each few more most other some such only own same both
again further once up down out off above below between through during before after while because until""".split())

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|\n{2,}|\n(?=\s*(?:[-*]|\d+[.)])\s)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_NUM_UNIT = re.compile(r"(?<![\w.])([-+]?\d[\d,]*\.?\d*)\s*(%|bps|bp|x|ms|s|sec|min|h|hrs?|days?|d|weeks?|months?|years?|y|"
                       r"[kKmMbB]|USD|\$|GB|MB|KB|rows?|bars?|trades?|skills?)?(?![A-Za-z])", re.I)


# ---------------------------------------------------------------- subjects
def looks_like_code(text: str) -> bool:
    """Literal python source: a top-level def/class/import line AND it parses."""
    if not re.search(r"^(?:def |class |import |from \S+ import )", text, re.M):
        return False
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        return False


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False


def load_subject(arg, kind: str | None = None):
    """Return (kind, value). arg is a path or literal text. kind forces the reading.

    series: list[float]; table: list[dict]; code: str; plan: list[str]; items: list[dict]; text: str."""
    text = arg
    if isinstance(arg, (list, tuple)):
        if kind == "text":
            return "text", "\n".join(json.dumps(x, default=str) if isinstance(x, dict) else str(x) for x in arg)
        if arg and all(isinstance(x, (int, float)) for x in arg):
            return "series", [float(x) for x in arg]
        if arg and all(isinstance(x, dict) for x in arg):
            return (kind or "items"), list(arg)
        return "plan", [str(x) for x in arg]
    p = Path(str(arg)) if isinstance(arg, (str, Path)) and len(str(arg)) < 400 and "\n" not in str(arg) else None
    suffix = ""
    if p is not None and p.is_file():
        text = p.read_text(encoding="utf-8", errors="replace")
        suffix = p.suffix.lower()
    text = str(text)
    if kind == "text":
        return "text", text
    if kind == "code" or (kind is None and suffix == ".py") or (kind is None and looks_like_code(text)):
        return "code", text
    if suffix == ".json" or kind in ("items", "table"):
        try:
            data = json.loads(text)
            if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
                return (kind or "items"), data
            if isinstance(data, list) and data and all(isinstance(x, (int, float)) for x in data):
                return "series", [float(x) for x in data]
        except ValueError:
            pass
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    # A series is one value per line, or `label,value` (a date or index first). A CSV whose rows carry three or more
    # cells is a table even when its last column is numeric (the 2026-10-24 survey trap: `name,wins,trials` was read
    # as a series and twelve lenses crashed or refused); `--kind series` still forces the old reading.
    cells = [ln.split(",") for ln in lines]
    wide = (kind is None and len(cells) >= 2 and len(cells[0]) >= 3 and len({len(c) for c in cells}) == 1
            and any(_is_number(x) for row in cells[1:] for x in row))
    if kind == "series" or (kind is None and lines and not wide
                            and all(_is_number(ln.split(",")[-1]) for ln in lines[1:] or lines)):
        vals = [float(ln.split(",")[-1].replace(",", "")) for ln in lines if _is_number(ln.split(",")[-1])]
        if vals:
            return "series", vals
    if suffix == ".csv" or kind == "table" or wide:
        head = [h.strip() for h in lines[0].split(",")]
        rows = []
        for ln in lines[1:]:
            cells = [c.strip() for c in ln.split(",")]
            rows.append({h: (float(c) if _is_number(c) else c) for h, c in zip(head, cells)})
        return "table", rows
    if kind == "plan" or (kind is None and lines and sum(bool(re.match(r"^(?:[-*]|\d+[.)])\s", ln)) for ln in lines) >= max(2, len(lines) * 0.6)):
        return "plan", [re.sub(r"^(?:[-*]|\d+[.)])\s+", "", ln) for ln in lines]
    return "text", text


# ---------------------------------------------------------------- text helpers
def sentences(text: str) -> list:
    return [s.strip() for s in _SENT.split(text.strip()) if s and s.strip()]


def words(text: str, lower: bool = True) -> list:
    return [w.lower() if lower else w for w in _WORD.findall(text)]


def keywords(text: str, k: int = 10) -> list:
    """Top-k content words by frequency (ties by first appearance) as (word, count)."""
    seen, counts = {}, {}
    for i, w in enumerate(words(text)):
        if w in STOP or len(w) < 3:
            continue
        counts[w] = counts.get(w, 0) + 1
        seen.setdefault(w, i)
    return sorted(counts.items(), key=lambda kv: (-kv[1], seen[kv[0]]))[:k]


def numbers_with_units(text: str) -> list:
    """[(value, unit_or_empty, position)] for every number in text."""
    out = []
    for m in _NUM_UNIT.finditer(text):
        raw = m.group(1).replace(",", "")
        if raw in ("", "-", "+", ".") or not _is_number(raw):
            continue
        out.append((float(raw), (m.group(2) or "").lower(), m.start()))
    return out


# ---------------------------------------------------------------- series helpers
def mean(x):
    x = list(x)
    if not x:
        raise ValueError("empty series")
    return sum(x) / len(x)


def sd(x):
    x = list(x)
    if len(x) < 2:
        return 0.0
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def quantile(x, q):
    s = sorted(x)
    if not s:
        raise ValueError("empty series")
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def median(x):
    return quantile(x, 0.5)


def mad(x):
    m = median(x)
    return median([abs(v - m) for v in x])


def diff(x):
    return [b - a for a, b in zip(x, x[1:])]


def moving_average(x, w):
    w = max(1, int(w))
    out, s = [], 0.0
    for i, v in enumerate(x):
        s += v
        if i >= w:
            s -= x[i - w]
        out.append(s / min(i + 1, w))
    return out


def ranks(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def zscores(x):
    m, s = mean(x), sd(x)
    return [0.0 if s == 0 else (v - m) / s for v in x]


def corr(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return 0.0 if den == 0 else num / den


def slope(y, x=None):
    """Least-squares slope of y on x (x defaults to 0..n-1)."""
    x = list(range(len(y))) if x is None else list(x)
    if len(y) < 2:
        raise ValueError("need >= 2 points for a slope")
    mx, my = mean(x), mean(y)
    den = sum((a - mx) ** 2 for a in x)
    return 0.0 if den == 0 else sum((a - mx) * (b - my) for a, b in zip(x, y)) / den


def numeric_columns(items: list) -> list:
    """Keys whose value is numeric in every item dict."""
    if not items:
        return []
    return [k for k in items[0] if all(isinstance(it.get(k), (int, float)) and not isinstance(it.get(k), bool)
                                       for it in items)]


def label_of(item: dict, i: int = 0) -> str:
    """A display label for an item dict: name/label/id/title/first string value, else '#i'."""
    for k in ("name", "label", "id", "title"):
        if k in item:
            return str(item[k])
    return next((str(v) for v in item.values() if isinstance(v, str)), f"#{i}")


def code_functions(src: str) -> list:
    """[{name, lineno, lines, args, calls}] for each def in python source (ast; raises SyntaxError on bad code)."""
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = sorted({n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)})
            out.append({"name": node.name, "lineno": node.lineno,
                        "lines": (getattr(node, "end_lineno", node.lineno) - node.lineno + 1),
                        "args": [a.arg for a in node.args.args], "calls": calls})
    return out


# ---------------------------------------------------------------- the view record
def view(name: str, kind: str, findings: list, summary: str, **stats) -> dict:
    """The one shape every lens returns. findings: list of dicts (each should carry a 'what' key)."""
    return {"lens": name, "kind": kind, "summary": summary, "findings": list(findings), "stats": stats}


def render(v: dict, limit: int = 25) -> str:
    lines = [f"[{v['lens']}] ({v['kind']}) {v['summary']}"]
    for f in v["findings"][:limit]:
        lines.append("  - " + (f.get("what") if isinstance(f, dict) and "what" in f else json.dumps(f, default=str))[:200])
    if len(v["findings"]) > limit:
        lines.append(f"  ... {len(v['findings']) - limit} more")
    if v["stats"]:
        lines.append("  stats: " + json.dumps(v["stats"], default=str)[:300])
    return "\n".join(lines)


# ---------------------------------------------------------------- probe corpus (shared by selftests + distinctness)
PROBES = {
    "text": ("We will obviously launch the new screener next week because the backtest Sharpe was 3.4 and it never lost. "
             "the user wants it fast. The data came from TradingView, which revises recent bars. "
             "Costs are small, maybe 5 bps. If the nightly job fails again, we stop. "
             "Somehow the old version was better, etc. They say the crowd is always wrong!"),
    "series": [100.0, 101.2, 100.8, 102.5, 103.1, 102.9, 104.6, 105.0, 98.2, 97.5, 99.1, 100.4,
               101.9, 103.3, 102.7, 104.8, 106.1, 105.5, 107.2, 108.0, 107.1, 109.4, 110.2, 109.8],
    "plan": ["download the stock bars", "rebuild the cache", "run the screener", "score the forward record",
             "land the change on main", "tell the user the result"],
    "items": [{"name": "trend", "sharpe": 1.1, "turnover": 0.2, "drawdown": 0.18},
              {"name": "reversion", "sharpe": 0.4, "turnover": 3.1, "drawdown": 0.25},
              {"name": "carry", "sharpe": 0.8, "turnover": 0.5, "drawdown": 0.30},
              {"name": "momentum", "sharpe": 0.9, "turnover": 1.2, "drawdown": 0.35},
              {"name": "pm-calibration", "sharpe": 0.1, "turnover": 0.8, "drawdown": 0.05}],
    "code": ("def load(path):\n    return open(path).read()\n\n"
             "def score(rows, k=42):\n    total = 0\n    for r in rows:\n        total += r * 3.7\n    return total / k\n\n"
             "def main():\n    data = load('x.csv')\n    print(score([1, 2, 3]))\n"),
}


def fingerprint(v: dict) -> set:
    """Token shingles of a view's findings+summary - what the lens SAID, not how it is named."""
    text = v.get("summary", "") + " " + " ".join(json.dumps(f, sort_keys=True, default=str) for f in v.get("findings", []))
    toks = [t for t in re.findall(r"[a-z0-9.]+", text.lower()) if t not in STOP]
    return {" ".join(toks[i:i + 3]) for i in range(max(0, len(toks) - 2))} or set(toks)


def jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / max(1, len(a | b))


def distinctness(views: dict, threshold: float = 0.8) -> list:
    """views: {lens_name: view on the SAME probe}. Returns pairs whose outputs overlap >= threshold (renamed twins)."""
    names = sorted(views)
    fps = {n: fingerprint(views[n]) for n in names}
    return [(a, b, round(jaccard(fps[a], fps[b]), 3)) for i, a in enumerate(names) for b in names[i + 1:]
            if jaccard(fps[a], fps[b]) >= threshold]


# ---------------------------------------------------------------- cli
def run_cli(name: str, apply, argv, selftest) -> int:
    """`python <lens>.py` / `--selftest` runs the selftest; `<file|text> [--kind K] [--json] [--opt key=value ...]`."""
    if not argv or argv[0] == "--selftest":
        return 0 if selftest() else 1
    kind, as_json, opts, subject = None, False, {}, []
    it = iter(argv)
    for a in it:
        if a == "--kind":
            kind = next(it)
        elif a == "--json":
            as_json = True
        elif a == "--opt":
            k, _, val = next(it).partition("=")
            opts[k] = float(val) if _is_number(val) else val
        else:
            subject.append(a)
    try:
        v = apply(" ".join(subject), kind=kind, **opts)
    except ValueError as e:                          # 2026-10-24: an unfit input is a one-line refusal, not a traceback
        print(f"[{name}] cannot use this input: {e}  (try --kind series|table|items|text|plan|code)")
        return 2
    print(json.dumps(v, indent=1, default=str) if as_json else render(v))
    return 0


def report(ok: dict) -> bool:
    for k, val in ok.items():
        print(("PASS " if val else "FAIL ") + k)
    return all(ok.values())


def _selftest() -> bool:
    ok = {}
    ok["load_subject reads series, plan, items, code and text"] = (
        load_subject("1\n2\n3")[0] == "series" and load_subject("- a\n- b\n- c")[0] == "plan"
        and load_subject(PROBES["items"])[0] == "items" and load_subject(PROBES["code"], kind="code")[0] == "code" and load_subject(PROBES["code"])[0] == "code"
        and load_subject(PROBES["text"])[0] == "text")
    ok["a 3-column CSV with a numeric last column is a table, not a series (survey 2026-10-24); date,value stays a series"] = (
        load_subject("name,wins,trials\nAAPL,12,20\nMSFT,9,20")[0] == "table"
        and load_subject("date,close\n2026-10-01,100\n2026-10-02,101")[0] == "series"
        and load_subject("name,wins,trials\nAAPL,12,20\nMSFT,9,20", kind="series")[0] == "series")
    ok["sentences and keywords on the probe text"] = (len(sentences(PROBES["text"])) >= 6
                                                     and keywords(PROBES["text"], 3)[0][1] >= 1)
    nums = numbers_with_units(PROBES["text"])
    ok["numbers_with_units finds 3.4 and 5 bps, and '24 skills' is skills not seconds"] = (
        any(v == 3.4 for v, _, _ in nums) and any(u == "bps" for _, u, _ in nums)
        and numbers_with_units("24 skills")[0][1] == "skills" and numbers_with_units("3 sessions")[0][1] == ""
        and abs(slope([1, 3, 5]) - 2) < 1e-12 and numeric_columns(PROBES["items"]) == ["sharpe", "turnover", "drawdown"])
    s = PROBES["series"]
    ok["series helpers agree with hand values"] = (abs(median([1, 3, 2]) - 2) < 1e-12 and ranks([3, 1, 3]) == [2.5, 1.0, 2.5]
                                                   and abs(corr(s, s) - 1) < 1e-12 and diff([1, 4]) == [3])
    ok["code_functions lists defs with line counts and calls"] = (
        [f["name"] for f in code_functions(PROBES["code"])] == ["load", "score", "main"]
        and "score" in code_functions(PROBES["code"])[2]["calls"])
    a = view("a", "text", [{"what": "x one two three"}], "same words here")
    b = view("b", "text", [{"what": "x one two three"}], "same words here")
    c = view("c", "text", [{"what": "completely different finding about drawdown"}], "other")
    ok["distinctness flags a renamed twin and passes a different lens"] = (
        distinctness({"a": a, "b": b, "c": c}) == [("a", "b", 1.0)])
    try:
        mean([])
        ok["planted bad input (empty series) is rejected"] = False
    except ValueError:
        ok["planted bad input (empty series) is rejected"] = True
    return report(ok)


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
