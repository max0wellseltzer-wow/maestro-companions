"""schema-contract: declare and enforce a data contract for a feed/table.

Pure stdlib. Rows are CSV rows, a list of dicts, or JSON lines. A contract is a
plain dict (JSON-serialisable):

    {
      "columns": {
        "ts":     {"type": "datetime"},
        "sym":    {"type": "str", "enum": ["AAA", "BBB"], "regex": "[A-Z]{3}"},
        "close":  {"type": "float", "min": 0},
        "volume": {"type": "int", "min": 0, "nullable": False, "required": True}
      },
      "unique": ["sym", "ts"],                       # single column or composite key
      "time": {"column": "ts", "by": ["sym"],         # per-key time discipline
               "monotonic": True, "strict": False,    # strict=True also flags equal ts
               "max_gap_seconds": 3600},
      "rules": {"high_ge_oc": "high >= max(open, close)"},   # row-level cross-field
      "extra_columns": "drift"                        # or "allow"
    }

Row numbers in reports are 1-based DATA rows (row 1 = first row after a CSV header).

    python contract.py --selftest
    python contract.py infer data.csv            > contract.json
    python contract.py validate data.csv contract.json [--examples 5] [--json]
"""
import ast
import csv
import datetime as _dt
import io
import json
import math
import random
import re
import sys

TYPES = ("int", "float", "str", "bool", "date", "datetime")
COLUMN_KEYS = {"type", "required", "nullable", "min", "max", "enum", "regex"}
TOP_KEYS = {"columns", "unique", "time", "rules", "extra_columns"}
TIME_KEYS = {"column", "by", "monotonic", "strict", "max_gap_seconds"}
RULE_FUNCS = {"max": max, "min": min, "abs": abs}
NULL_TOKENS = {"", "nan", "null", "none", "na", "n/a"}
_INT_RE = re.compile(r"[+-]?\d+")
_FLOAT_RE = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_BOOL = {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False,
         "t": True, "f": False}


class ContractError(ValueError):
    """The contract itself is malformed."""


class _Bad(Exception):
    pass


# ---------------------------------------------------------------- value parsing
def is_null(v, typ="float"):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str):
        s = v.strip().lower()
        return s == "" if typ == "str" else s in NULL_TOKENS
    return False


def _parse_dt(v):
    if isinstance(v, _dt.datetime):
        d = v
    elif isinstance(v, _dt.date):
        d = _dt.datetime(v.year, v.month, v.day)
    elif isinstance(v, str):
        s = v.strip()
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"
        d = _dt.datetime.fromisoformat(s)
    else:
        raise _Bad("not a datetime")
    if d.tzinfo is not None:  # normalise aware values to naive UTC so they compare
        d = d.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return d


def parse_value(v, typ):
    """Parse one non-null value as `typ`; raise _Bad on failure."""
    try:
        if typ == "str":
            if not isinstance(v, str):
                raise _Bad("not a string")
            return v
        if typ == "int":
            if isinstance(v, bool):
                raise _Bad("bool is not int")
            if isinstance(v, int):
                return v
            if isinstance(v, float) and math.isfinite(v) and v.is_integer():
                return int(v)
            if isinstance(v, str) and _INT_RE.fullmatch(v.strip()):
                return int(v.strip())
            raise _Bad("not an int")
        if typ == "float":
            if isinstance(v, bool):
                raise _Bad("bool is not float")
            if isinstance(v, (int, float)):
                f = float(v)
            elif isinstance(v, str) and _FLOAT_RE.fullmatch(v.strip()):
                f = float(v.strip())
            else:
                raise _Bad("not a float")
            if not math.isfinite(f):
                raise _Bad("non-finite")
            return f
        if typ == "bool":
            if isinstance(v, bool):
                return v
            if isinstance(v, str) and v.strip().lower() in _BOOL:
                return _BOOL[v.strip().lower()]
            raise _Bad("not a bool")
        if typ == "date":
            if isinstance(v, _dt.datetime):
                raise _Bad("datetime is not date")
            if isinstance(v, _dt.date):
                return v
            if isinstance(v, str):
                return _dt.date.fromisoformat(v.strip())
            raise _Bad("not a date")
        if typ == "datetime":
            return _parse_dt(v)
    except _Bad:
        raise
    except (ValueError, TypeError, OverflowError) as e:
        raise _Bad(str(e))
    raise _Bad("unknown type")


# ------------------------------------------------------------- safe rule exprs
_ALLOWED_NODES = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub,
                  ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Compare, ast.Eq,
                  ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Call, ast.Name, ast.Load,
                  ast.Constant)


def compile_rule(expr, columns):
    """Validate a rule expression; return (ast tree, referenced column names)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ContractError(f"rule {expr!r}: syntax error {e.msg}")
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ContractError(f"rule {expr!r}: {type(node).__name__} not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in RULE_FUNCS or node.keywords:
                raise ContractError(f"rule {expr!r}: only max/min/abs calls allowed")
        elif isinstance(node, ast.Name):
            if node.id in RULE_FUNCS:
                continue
            if node.id not in columns:
                raise ContractError(f"rule {expr!r}: unknown column {node.id!r}")
            names.add(node.id)
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str, bool)):
            raise ContractError(f"rule {expr!r}: constant {node.value!r} not allowed")
    return tree, names


def _ev(node, env):
    if isinstance(node, ast.Expression):
        return _ev(node.body, env)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_ev(v, env) for v in node.values)
        return any(_ev(v, env) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        x = _ev(node.operand, env)
        return (not x) if isinstance(node.op, ast.Not) else (-x if isinstance(node.op, ast.USub) else +x)
    if isinstance(node, ast.BinOp):
        a, b = _ev(node.left, env), _ev(node.right, env)
        op = node.op
        return a + b if isinstance(op, ast.Add) else a - b if isinstance(op, ast.Sub) else \
            a * b if isinstance(op, ast.Mult) else a / b
    if isinstance(node, ast.Call):
        return RULE_FUNCS[node.func.id](*[_ev(a, env) for a in node.args])
    if isinstance(node, ast.Compare):
        left = _ev(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _ev(comp, env)
            ok = {ast.Eq: left == right, ast.NotEq: left != right, ast.Lt: left < right,
                  ast.LtE: left <= right, ast.Gt: left > right, ast.GtE: left >= right}[type(op)]
            if not ok:
                return False
            left = right
        return True
    raise ContractError(f"cannot evaluate {type(node).__name__}")


# ------------------------------------------------------------ contract checking
def check_contract(contract):
    """Validate the contract's own shape. Returns a normalised copy; raises ContractError."""
    if not isinstance(contract, dict):
        raise ContractError("contract must be a dict")
    bad = set(contract) - TOP_KEYS
    if bad:
        raise ContractError(f"unknown contract keys: {sorted(bad)}")
    cols = contract.get("columns")
    if not isinstance(cols, dict) or not cols:
        raise ContractError("contract needs a non-empty 'columns' dict")
    out = {"columns": {}, "unique": [], "time": None, "rules": {},
           "extra_columns": contract.get("extra_columns", "drift")}
    if out["extra_columns"] not in ("drift", "allow"):
        raise ContractError("extra_columns must be 'drift' or 'allow'")
    for name, spec in cols.items():
        if not isinstance(spec, dict):
            raise ContractError(f"column {name!r}: spec must be a dict")
        bad = set(spec) - COLUMN_KEYS
        if bad:
            raise ContractError(f"column {name!r}: unknown rule keys {sorted(bad)}")
        typ = spec.get("type")
        if typ not in TYPES:
            raise ContractError(f"column {name!r}: unknown type {typ!r} (use one of {TYPES})")
        s = {"type": typ, "required": bool(spec.get("required", True)),
             "nullable": bool(spec.get("nullable", False))}
        for k in ("min", "max"):
            if k in spec:
                if typ in ("str", "bool"):
                    raise ContractError(f"column {name!r}: {k} not valid for {typ}")
                try:
                    s[k] = parse_value(spec[k], typ)
                except _Bad:
                    raise ContractError(f"column {name!r}: {k}={spec[k]!r} is not a {typ}")
        if "min" in s and "max" in s and s["min"] > s["max"]:
            raise ContractError(f"column {name!r}: min > max")
        if "enum" in spec:
            if not isinstance(spec["enum"], (list, tuple)) or not spec["enum"]:
                raise ContractError(f"column {name!r}: enum must be a non-empty list")
            try:
                s["enum"] = {parse_value(e, typ) for e in spec["enum"]}
            except _Bad:
                raise ContractError(f"column {name!r}: enum value not a {typ}")
        if "regex" in spec:
            try:
                s["regex"] = re.compile(spec["regex"])
            except (re.error, TypeError) as e:
                raise ContractError(f"column {name!r}: bad regex ({e})")
        out["columns"][name] = s
    uq = contract.get("unique", [])
    if isinstance(uq, str):
        uq = [uq]
    for c in uq:
        if c not in cols:
            raise ContractError(f"unique: unknown column {c!r}")
    out["unique"] = list(uq)
    tm = contract.get("time")
    if tm is not None:
        if not isinstance(tm, dict):
            raise ContractError("time must be a dict")
        bad = set(tm) - TIME_KEYS
        if bad:
            raise ContractError(f"time: unknown keys {sorted(bad)}")
        tc = tm.get("column")
        if tc not in cols or cols[tc]["type"] not in ("date", "datetime", "int", "float"):
            raise ContractError("time.column must name a date/datetime/int/float column")
        by = tm.get("by", [])
        by = [by] if isinstance(by, str) else list(by)
        for c in by:
            if c not in cols:
                raise ContractError(f"time.by: unknown column {c!r}")
        gap = tm.get("max_gap_seconds")
        if gap is not None and (not isinstance(gap, (int, float)) or isinstance(gap, bool) or gap <= 0):
            raise ContractError("time.max_gap_seconds must be a positive number")
        out["time"] = {"column": tc, "by": by, "monotonic": bool(tm.get("monotonic", True)),
                       "strict": bool(tm.get("strict", False)), "max_gap_seconds": gap}
    rules = contract.get("rules", {})
    if not isinstance(rules, dict):
        raise ContractError("rules must be a dict {name: expression}")
    for rname, expr in rules.items():
        if not isinstance(expr, str):
            raise ContractError(f"rule {rname!r}: expression must be a string")
        out["rules"][rname] = compile_rule(expr, cols)
    return out


# ---------------------------------------------------------------- data loading
def load_rows(path_or_text, fmt=None):
    """Load rows from a .csv / .jsonl / .json path, or from text when fmt is given."""
    if fmt is None:
        low = str(path_or_text).lower()
        fmt = "csv" if low.endswith(".csv") else "jsonl" if low.endswith((".jsonl", ".ndjson")) \
            else "json" if low.endswith(".json") else None
        if fmt is None:
            raise ValueError("cannot tell format; use .csv/.jsonl/.json or pass fmt")
        with open(path_or_text, encoding="utf-8", newline="") as fh:
            text = fh.read()
    else:
        text = path_or_text
    if fmt == "csv":
        return [dict(r) for r in csv.DictReader(io.StringIO(text))]
    if fmt == "jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if fmt == "json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("json must be a list of objects")
        return data
    raise ValueError(f"unknown fmt {fmt!r}")


# ------------------------------------------------------------------ validation
class _Report:
    def __init__(self, examples):
        self.n = examples
        self.groups = {}

    def add(self, key, row, msg):
        g = self.groups.setdefault(key, {"count": 0, "rows": [], "examples": []})
        g["count"] += 1
        if len(g["rows"]) < self.n:
            g["rows"].append(row)
            g["examples"].append(msg)


def _observed_type(values):
    """Narrowest type that every non-null value parses as."""
    for typ in ("bool", "int", "float", "date", "datetime"):
        if typ == "bool" and not all(isinstance(v, bool) or
                                     (isinstance(v, str) and v.strip().lower() in ("true", "false"))
                                     for v in values):
            continue
        try:
            for v in values:
                parse_value(v, typ)
            return typ
        except _Bad:
            continue
    return "str"


def validate(rows, contract, examples=5):
    """Validate rows against a contract. Returns a report dict:
    {ok, rows, violations: {rule_key: {count, rows, examples}}, drift: {...}, summary}.
    rule_key is '<family>:<target>', families: null, type, range, enum, regex, unique,
    monotonic, max_gap, rule; drift families: new_column, missing_column, type_change."""
    c = check_contract(contract)
    cols = c["columns"]
    viol, drift = _Report(examples), _Report(examples)
    rows = list(rows)
    seen_cols, first_seen = [], {}
    for i, r in enumerate(rows, 1):
        for k in r:
            if k not in first_seen:
                first_seen[k] = i
                seen_cols.append(k)
    present = set(first_seen)
    # --- schema drift
    if c["extra_columns"] == "drift":
        for k in seen_cols:
            if k not in cols:
                drift.add(f"new_column:{k}", first_seen[k], f"column {k!r} not in contract")
    missing = set()
    for name, s in cols.items():
        if name not in present and rows:
            missing.add(name)
            if s["required"]:
                drift.add(f"missing_column:{name}", 1, f"required column {name!r} absent")
    # --- per-cell checks
    parsed = [dict() for _ in rows]   # i -> {col: parsed value}; absent if null/bad
    raw_by_col = {name: [] for name in cols}
    for i, r in enumerate(rows, 1):
        p = parsed[i - 1]
        for name, s in cols.items():
            if name in missing:
                continue
            v = r.get(name)
            if is_null(v, s["type"]):
                if not s["nullable"]:
                    viol.add(f"null:{name}", i, f"{name}={v!r} is null")
                continue
            raw_by_col[name].append(v)
            try:
                pv = parse_value(v, s["type"])
            except _Bad as e:
                viol.add(f"type:{name}", i, f"{name}={v!r} is not {s['type']} ({e})")
                continue
            p[name] = pv
            if ("min" in s and pv < s["min"]) or ("max" in s and pv > s["max"]):
                viol.add(f"range:{name}", i, f"{name}={v!r} outside [{s.get('min')}, {s.get('max')}]")
            if "enum" in s and pv not in s["enum"]:
                viol.add(f"enum:{name}", i, f"{name}={v!r} not in enum")
            if "regex" in s and not s["regex"].fullmatch(str(v)):
                viol.add(f"regex:{name}", i, f"{name}={v!r} fails regex {s['regex'].pattern!r}")
    # --- type drift: more than half of non-null values fail the declared type
    for name, vals in raw_by_col.items():
        if len(vals) >= 2:
            bad = sum(1 for v in vals if not _parses(v, cols[name]["type"]))
            if bad * 2 > len(vals):
                obs = _observed_type(vals)
                drift.add(f"type_change:{name}", 1, f"declared {cols[name]['type']}, data looks {obs} "
                                                    f"({bad}/{len(vals)} fail)")
    # --- uniqueness
    if c["unique"]:
        key_name = "+".join(c["unique"])
        seen = {}
        for i, p in enumerate(parsed, 1):
            if all(k in p for k in c["unique"]):
                key = tuple(p[k] for k in c["unique"])
                if key in seen:
                    viol.add(f"unique:{key_name}", i, f"key {key_name}={_fmt(key)} repeats row {seen[key]}")
                else:
                    seen[key] = i
    # --- time discipline per group
    tm = c["time"]
    if tm:
        tc = tm["column"]
        groups = {}
        for i, p in enumerate(parsed, 1):
            if tc in p and all(k in p for k in tm["by"]):
                groups.setdefault(tuple(p[k] for k in tm["by"]), []).append((i, p[tc]))
        for g, seq in groups.items():
            if tm["monotonic"]:
                hwm = None
                for i, t in seq:
                    if hwm is not None and (t < hwm or (tm["strict"] and t == hwm)):
                        viol.add(f"monotonic:{tc}", i, f"{tc}={_fmt(t)} not after {_fmt(hwm)} (group {_fmt(g)})")
                    hwm = t if hwm is None or t > hwm else hwm
            if tm["max_gap_seconds"]:
                first_row = {}
                for i, t in seq:
                    first_row.setdefault(t, i)
                ts = sorted(first_row)
                for a, b in zip(ts, ts[1:]):
                    gap = _seconds(b, a)
                    if gap > tm["max_gap_seconds"]:
                        viol.add(f"max_gap:{tc}", first_row[b],
                                 f"gap {gap:g}s > {tm['max_gap_seconds']}s before {_fmt(b)} (group {_fmt(g)})")
    # --- cross-field rules (rows with a null/bad referenced cell are skipped: already reported)
    for rname, (tree, names) in c["rules"].items():
        for i, p in enumerate(parsed, 1):
            if all(n in p for n in names):
                try:
                    ok = _ev(tree, p)
                except (TypeError, ZeroDivisionError) as e:
                    viol.add(f"rule:{rname}", i, f"rule {rname} error: {e}")
                    continue
                if not ok:
                    viol.add(f"rule:{rname}", i, f"rule {rname} false: " +
                             ", ".join(f"{n}={_fmt(p[n])}" for n in sorted(names)))
    nv = sum(g["count"] for g in viol.groups.values())
    nd = sum(g["count"] for g in drift.groups.values())
    return {"ok": nv == 0 and nd == 0, "rows": len(rows), "violations": viol.groups,
            "drift": drift.groups,
            "summary": f"{len(rows)} rows: {nv} violations in {len(viol.groups)} rules, "
                       f"{nd} drift findings"}


def rule_keys(report):
    """All violated rule keys, drift ones prefixed 'drift:'."""
    return set(report["violations"]) | {"drift:" + k for k in report["drift"]}


def _parses(v, typ):
    try:
        parse_value(v, typ)
        return True
    except _Bad:
        return False


def _seconds(b, a):
    d = b - a
    if isinstance(d, _dt.timedelta):
        return d.total_seconds()
    return float(d)


def _fmt(x):
    if isinstance(x, tuple):
        return "(" + ", ".join(_fmt(v) for v in x) + ")"
    if isinstance(x, (_dt.date, _dt.datetime)):
        return x.isoformat()
    return repr(x)


# ------------------------------------------------------------------- inference
def infer(rows, enum_max=20):
    """Propose a starting contract from CLEAN rows. Review it before trusting it:
    min=0 is proposed only for numeric columns that never go negative; enums only for
    low-cardinality strings; cross-field rules are 'a >= b' between float columns that
    held on every row; max_gap is the largest gap seen per group."""
    rows = list(rows)
    order, present_in = [], {}
    for r in rows:
        for k in r:
            if k not in present_in:
                order.append(k)
                present_in[k] = 0
            present_in[k] += 1
    cols, typed = {}, {}
    for name in order:
        vals = [r.get(name) for r in rows]
        nonnull = [v for v in vals if not is_null(v)]
        typ = _observed_type(nonnull) if nonnull else "str"
        spec = {"type": typ, "required": present_in[name] == len(rows),
                "nullable": len(nonnull) < len(vals)}
        parsed = [parse_value(v, typ) for v in nonnull]
        typed[name] = [None if is_null(r.get(name)) else parse_value(r.get(name), typ) for r in rows]
        if typ in ("int", "float") and parsed and min(parsed) >= 0:
            spec["min"] = 0
        if typ == "str":
            distinct = sorted(set(parsed))
            if len(distinct) <= enum_max and len(rows) >= 2 * len(distinct):
                spec["enum"] = distinct
        cols[name] = spec
    contract = {"columns": cols, "extra_columns": "drift"}

    def unique_on(keys):
        seen = set()
        for i in range(len(rows)):
            k = tuple(typed[c][i] for c in keys)
            if None in k or k in seen:
                return False
            seen.add(k)
        return True

    tcols = [n for n in order if cols[n]["type"] in ("datetime", "date")]
    cats = [n for n in order if cols[n]["type"] in ("str", "int", "bool")]
    key = None
    if tcols:
        t = tcols[0]
        if unique_on([t]):
            key = [t]
        else:
            for cat in cats:
                if unique_on([cat, t]):
                    key = [cat, t]
                    break
    if key is None:
        for n in order:
            if cols[n]["type"] in ("str", "int") and unique_on([n]):
                key = [n]
                break
    if key:
        contract["unique"] = key
    if tcols:
        t = tcols[0]
        by = [k for k in (key or []) if k != t]
        groups = {}
        for i in range(len(rows)):
            if typed[t][i] is not None:
                groups.setdefault(tuple(typed[b][i] for b in by), []).append(typed[t][i])
        mono = all(all(a <= b for a, b in zip(s, s[1:])) for s in groups.values())
        gaps = [_seconds(b, a) for s in groups.values()
                for a, b in zip(sorted(set(s)), sorted(set(s))[1:])]
        tm = {"column": t, "by": by, "monotonic": mono, "strict": False}
        if gaps:
            tm["max_gap_seconds"] = max(gaps)
        contract["time"] = tm
    floats = [n for n in order if cols[n]["type"] == "float"]
    rules = {}
    for a in floats:
        for b in floats:
            if a == b:
                continue
            pairs = [(x, y) for x, y in zip(typed[a], typed[b]) if x is not None and y is not None]
            if len(pairs) >= 10 and all(x >= y for x, y in pairs) and any(x > y for x, y in pairs):
                rules[f"{a}_ge_{b}"] = f"{a} >= {b}"
    if rules:
        contract["rules"] = rules
    return contract


def format_report(rep):
    lines = [("OK  " if rep["ok"] else "FAIL ") + rep["summary"]]
    for title, groups in (("violations", rep["violations"]), ("drift", rep["drift"])):
        for k in sorted(groups):
            g = groups[k]
            lines.append(f"  [{title}] {k}: {g['count']}  rows {g['rows']}")
            lines.append(f"      e.g. {g['examples'][0]}")
    return "\n".join(lines)


# -------------------------------------------------------------------- selftest
def _clean_ohlcv(rng, hours=200, syms=("AAA", "BBB")):
    t0 = _dt.datetime(2026, 1, 1)
    last = {s: 100.0 for s in syms}
    rows = []
    for h in range(hours):
        ts = (t0 + _dt.timedelta(hours=h)).isoformat()
        for s in syms:
            o = last[s]
            c = max(1.0, o * (1 + rng.gauss(0, 0.01)))
            hi = max(o, c) + abs(rng.gauss(0, 0.3))
            lo = max(0.5, min(o, c) - abs(rng.gauss(0, 0.3)))
            last[s] = c
            rows.append({"ts": ts, "sym": s, "open": f"{o:.4f}", "high": f"{hi:.4f}",
                         "low": f"{lo:.4f}", "close": f"{c:.4f}", "volume": str(rng.randint(100, 10000))})
    return rows


HAND_CONTRACT = {
    "columns": {
        "ts": {"type": "datetime"},
        "sym": {"type": "str", "enum": ["AAA", "BBB"], "regex": "[A-Z]{3}"},
        "open": {"type": "float", "min": 0}, "high": {"type": "float", "min": 0},
        "low": {"type": "float", "min": 0}, "close": {"type": "float", "min": 0},
        "volume": {"type": "int", "min": 0},
    },
    "unique": ["sym", "ts"],
    "time": {"column": "ts", "by": ["sym"], "monotonic": True, "max_gap_seconds": 3600},
    "rules": {"high_ge_oc": "high >= max(open, close)", "low_le_oc": "low <= min(open, close)"},
}


def _defects(clean):
    """Yield (name, rows, expected_key_family_map, expected_row). Expected row is found
    by identity after mutation, not by index arithmetic."""
    import copy
    a_rows = [i for i, r in enumerate(clean) if r["sym"] == "AAA"]
    r = a_rows[60]

    def fresh():
        return copy.deepcopy(clean)

    d = fresh(); d[r]["close"] = "NaN"
    yield "nan_in_required", d, ("null", "null:close"), r + 1
    d = fresh(); d[r]["open"] = ""
    yield "blank_in_required", d, ("null", "null:open"), r + 1
    d = fresh(); d[r]["close"] = "abc"
    yield "string_in_float", d, ("type", "type:close"), r + 1
    d = fresh(); d[r]["high"] = f"{float(d[r]['low']) - 0.5:.4f}"
    yield "high_below_low", d, ("rule", "rule:high_ge_oc"), r + 1
    d = fresh(); d.insert(r + 1, dict(d[r]))
    yield "duplicate_key", d, ("unique", "unique:sym+ts"), r + 2
    d = fresh(); j = a_rows[61]; d[r], d[j] = d[j], d[r]   # swap two consecutive AAA bars
    yield "out_of_order_ts", d, ("monotonic", "monotonic:ts"), j + 1
    d = fresh(); nxt = d[a_rows[61]]; del d[r]
    yield "gap_too_large", d, ("max_gap", "max_gap:ts"), d.index(nxt) + 1
    d = fresh(); d[r]["volume"] = "-5"
    yield "out_of_range", d, ("range", "range:volume"), r + 1
    d = fresh(); d[r]["note"] = "manual fix"
    yield "new_column", d, ("drift", "drift:new_column:note"), r + 1


def _all_rows(rep):
    out = set()
    for groups in (rep["violations"], rep["drift"]):
        for g in groups.values():
            out.update(g["rows"])
    return out


def _families(rep):
    return {k.split(":")[0] for k in rep["violations"]} | ({"drift"} if rep["drift"] else set())


def _selftest():
    rng = random.Random("contract/0")
    clean = _clean_ohlcv(rng)
    results = []

    def check(name, ok, detail):
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
        results.append(ok)

    rep = validate(clean, HAND_CONTRACT)
    check("clean_ohlcv_passes", rep["ok"], f"{rep['rows']} rows, {rep['summary']}")

    for name, rows, (fam, key), row in _defects(clean):
        rep = validate(rows, HAND_CONTRACT)
        keys = rule_keys(rep)
        got_rows = _all_rows(rep)
        ok = keys == {key} and got_rows == {row}
        check(f"defect_{name}", ok, f"expect {key}@row{row}; got {sorted(keys)} rows {sorted(got_rows)}")

    inferred = json.loads(json.dumps(infer(clean)))  # must survive JSON round-trip
    rep = validate(clean, inferred)
    check("infer_clean_roundtrip", rep["ok"],
          f"inferred {len(inferred['columns'])} cols, unique={inferred.get('unique')}, "
          f"gap={inferred['time'].get('max_gap_seconds')}s, {len(inferred.get('rules', {}))} rules; {rep['summary']}")

    caught, total, misses = 0, 0, []
    for name, rows, (fam, key), row in _defects(clean):
        total += 1
        rep = validate(rows, inferred)
        if _families(rep) == {fam} and _all_rows(rep) == {row}:
            caught += 1
        else:
            misses.append(f"{name}:{sorted(rule_keys(rep))}@{sorted(_all_rows(rep))}")
    check("infer_catches_defects", caught == total, f"{caught}/{total} caught by the right family+row"
          + (f" misses {misses}" if misses else ""))

    bad_contracts = {
        "unknown_type": {"columns": {"x": {"type": "decimal"}}},
        "unknown_col_rule": {"columns": {"x": {"type": "int", "minimum": 0}}},
        "unknown_top_key": {"columns": {"x": {"type": "int"}}, "checks": []},
        "unsafe_expr": {"columns": {"x": {"type": "int"}}, "rules": {"r": "__import__('os').system('x')"}},
        "rule_unknown_col": {"columns": {"x": {"type": "int"}}, "rules": {"r": "x >= y"}},
        "bad_regex": {"columns": {"x": {"type": "str", "regex": "[a-"}}},
        "min_gt_max": {"columns": {"x": {"type": "int", "min": 5, "max": 1}}},
        "unique_unknown": {"columns": {"x": {"type": "int"}}, "unique": ["y"]},
    }
    rejected = []
    for nm, bc in bad_contracts.items():
        try:
            check_contract(bc)
        except ContractError:
            rejected.append(nm)
    check("malformed_contract_rejected", len(rejected) == len(bad_contracts),
          f"{len(rejected)}/{len(bad_contracts)} rejected"
          + ("" if len(rejected) == len(bad_contracts) else f" accepted {set(bad_contracts) - set(rejected)}"))

    # formats: CSV text and JSON lines give identical reports to the dict list
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(clean[0]), lineterminator="\n")
    w.writeheader(); w.writerows(clean)
    jl = "\n".join(json.dumps(r) for r in clean)
    native = [{"ts": _dt.datetime.fromisoformat(r["ts"]), "sym": r["sym"],
               **{k: float(r[k]) for k in ("open", "high", "low", "close")},
               "volume": int(r["volume"])} for r in clean]
    reps = [validate(load_rows(buf.getvalue(), "csv"), HAND_CONTRACT),
            validate(load_rows(jl, "jsonl"), HAND_CONTRACT), validate(native, HAND_CONTRACT)]
    check("csv_jsonl_native_agree", all(r["ok"] and r["rows"] == len(clean) for r in reps),
          f"csv/jsonl/native rows={[r['rows'] for r in reps]} ok={[r['ok'] for r in reps]}")

    # type drift + example capping: volume became decimal strings everywhere
    d = [dict(r, volume=r["volume"] + ".5") for r in clean]
    rep = validate(d, HAND_CONTRACT, examples=3)
    tv = rep["violations"].get("type:volume", {})
    ok = ("type_change:volume" in rep["drift"] and tv.get("count") == len(clean)
          and tv.get("rows") == [1, 2, 3])
    check("type_drift_and_example_cap", ok,
          f"drift={sorted(rep['drift'])}, type:volume count={tv.get('count')} first rows={tv.get('rows')}")

    # missing column + single-column key + strict monotonic
    d = [{k: v for k, v in r.items() if k != "volume"} for r in clean if r["sym"] == "AAA"]
    c2 = json.loads(json.dumps(HAND_CONTRACT)); c2["unique"] = "ts"
    c2["time"] = {"column": "ts", "strict": True, "max_gap_seconds": 3600}
    d.insert(5, dict(d[4]))
    rep = validate(d, c2)
    ok = (set(rule_keys(rep)) == {"drift:missing_column:volume", "unique:ts", "monotonic:ts"}
          and rep["violations"]["unique:ts"]["rows"] == [6] and rep["violations"]["monotonic:ts"]["rows"] == [6])
    check("missing_col_single_key_strict", ok, f"got {sorted(rule_keys(rep))}")

    n_ok = sum(results)
    print(f"{'PASS' if n_ok == len(results) else 'FAIL'} summary: {n_ok}/{len(results)} checks")
    return n_ok == len(results)


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "infer" and len(argv) >= 2:
        print(json.dumps(infer(load_rows(argv[1])), indent=2, default=str))
        return 0
    if argv[0] == "validate" and len(argv) >= 3:
        n = 5
        if "--examples" in argv:
            n = int(argv[argv.index("--examples") + 1])
        with open(argv[2], encoding="utf-8") as fh:
            contract = json.load(fh)
        rep = validate(load_rows(argv[1]), contract, examples=n)
        print(json.dumps(rep, indent=2, default=str) if "--json" in argv else format_report(rep))
        return 0 if rep["ok"] else 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
