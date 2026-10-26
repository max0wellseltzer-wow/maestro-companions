---
name: schema-contract
description: Declare a data contract for a feed or table (CSV rows, list of dicts, JSON lines) and enforce it - per-column type (int/float/str/bool/date/ISO datetime), required/nullable, range, enum, regex, unique single or composite key, monotonic timestamps per key, max gap between timestamps, and row-level cross-field rules like high >= max(open, close) - returning violations grouped by rule with counts and first-N row numbers plus schema drift (new columns, missing columns, type changes); infer() proposes a starting contract from clean data. Use this whenever the user adds or trusts a new feed, CSV export, poller output or cached bar table, asks "is this data clean?", "did the schema change?", "why did the backtest break after the refresh?", wants a gate before data enters the cache, or sees NaNs, duplicate bars, out-of-order or missing timestamps, or high < low. Pairs with data-hygiene, feed-poller-add, conserve-check, interval-merge, write-ahead-log and long-job.
---

# schema-contract

A feed is only as trustworthy as the promise it keeps. This skill writes that promise down as a plain dict (or JSON file): which columns, what type each one has, what values are allowed, which columns form the key, how the timestamps must behave, and which cross-field facts must hold on every row. `validate` checks the data against it and reports every broken promise by rule, with counts and the first few row numbers. It also reports schema drift. `infer` drafts a contract from data you already know is clean, and you then tighten it by hand.

## The tool (ships with this skill)

`contract.py` - pure stdlib, selftest 16/16:

```
from contract import validate, infer, check_contract, load_rows, format_report, rule_keys
contract = {
  "columns": {"ts": {"type": "datetime"}, "sym": {"type": "str", "enum": ["AAA", "BBB"]},
              "open": {"type": "float", "min": 0}, "high": {"type": "float", "min": 0},
              "low": {"type": "float", "min": 0}, "close": {"type": "float", "min": 0},
              "volume": {"type": "int", "min": 0}},
  "unique": ["sym", "ts"],
  "time": {"column": "ts", "by": ["sym"], "monotonic": True, "max_gap_seconds": 3600},
  "rules": {"high_ge_oc": "high >= max(open, close)", "low_le_oc": "low <= min(open, close)"},
}
rep = validate(load_rows("bars.csv"), contract, examples=5)
rep["violations"]   # {"null:close": {"count": 3, "rows": [121, 300, 301], "examples": [...]}, ...}
rep["drift"]        # {"new_column:note": ..., "missing_column:volume": ..., "type_change:volume": ...}
draft = infer(clean_rows)          # starting contract: review it, then commit it as JSON
python contract.py infer bars.csv > bars.contract.json
python contract.py validate bars.csv bars.contract.json [--examples 5] [--json]   # exit 0 ok, 2 violations
python contract.py --selftest
```

- Column keys: `type` (int/float/str/bool/date/datetime), `required` (default True: the column must exist), `nullable` (default False: blank, None, NaN, "nan", "null", "NA" count as null; in str columns only blank/None do), `min`/`max` (inclusive), `enum`, `regex` (full match). Any other key, an unknown type, a bad regex, min > max, or an unknown column in `unique`/`time`/`rules` raises `ContractError`. A broken contract never validates silently.
- Rule keys in the report are `family:target`, with these families: `null`, `type`, `range`, `enum`, `regex`, `unique`, `monotonic`, `max_gap`, `rule`, plus the drift families `new_column`, `missing_column` and `type_change`. Row numbers are 1-based data rows (row 1 is the first row after a CSV header).
- `time.monotonic` flags a timestamp that goes backwards within its `by` group. Equal timestamps are left to `unique` unless `strict: True`. `max_gap_seconds` is checked on the group's sorted distinct timestamps, so it measures missing coverage and not order. A swapped pair therefore trips `monotonic` only, and a deleted bar trips `max_gap` only.
- `rules` are safe expressions over column names: comparisons, `and`/`or`/`not`, `+ - * /`, and `max`/`min`/`abs`. Anything else is rejected, including attribute access and imports. A rule is skipped on a row where one of its cells is null or the wrong type, because that row was already reported under `null`/`type` and is not counted twice. A high below low always shows up as `high >= max(open, close)` failing.
- `type_change` drift fires when more than half of a column's non-null values fail the declared type. A single bad cell is a row-level `type` violation and not drift.
- Aware datetimes (including a trailing `Z`) are converted to naive UTC before comparison.

## Uses and limits

Use it as the gate between a poller or download and the cache: write the contract once, validate each new batch, and refuse to land a batch that is not `ok`. You can also run it on an old table to learn why a backtest changed. `infer` is a draft and not a verdict. It proposes `min: 0` only for columns that were never negative, enums only for low-cardinality strings, `a >= b` rules only between float columns where the relation held on every row (so on a short sample it can propose a coincidental rule), and a max gap equal to the largest gap it saw. Review the draft before you commit it. Limits: everything is in memory, rules are row-local (cross-row logic is limited to the unique and time checks), there is no business calendar (an overnight or weekend gap is a gap, so set `max_gap_seconds` to fit the session or validate per session), and timezones other than UTC normalisation are your job.
