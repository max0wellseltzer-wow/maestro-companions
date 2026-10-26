"""sqlite_fp - fingerprint every table of one or more SQLite files, and diff two of them table by table.

A speed-up that writes databases (a cache, an index, a "latest" table) is proven only when every table it wrote is
the same as before. Three traps found on 2026-10-22 (screener refresh-cache, 1 vs 2 workers, L8390-8753):
  * column names like `rsi@prev` break an unquoted SELECT - every name is quoted here;
  * column ORDER is a creation accident - rows are keyed by column NAME, so a reordered schema is still equal;
  * file metadata stored in a table (a CSV's size+mtime in seen.stat, a pickled object in states.ind) differs
    between identical runs - name such columns with --exclude TABLE.COL (or *.COL) and say so in the report.

    python sqlite_fp.py fp   DB_OR_DIR [--exclude seen.stat --exclude states.ind] [--json]
    python sqlite_fp.py diff A B       [--exclude ...] [--key COL] [--show 3]
    python sqlite_fp.py --selftest

fp prints `file|table|rows|sha16` per table (a DIR means every *.db in it). diff pairs files by name (two DIRs) or the
two files given, then per table: SAME, or which columns differ in how many rows with examples (rows matched by the
primary key, else --key, else the first column), rows only on one side, tables and columns only on one side.
Opened read-only (mode=ro). Exit: fp 0; diff 0 identical, 1 differences, 2 bad args.
Limits: each table is sorted in memory (fine for a few hundred MB of rows; not for a 10 GB table). Values compare
exactly (1.0 vs 1.0000000001 differ) - that is the point.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)


def _excluded(table: str, col: str, excl: set) -> bool:
    return f"{table}.{col}" in excl or f"*.{col}" in excl


def tables(con) -> list:
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE "
                                      "'sqlite_%' ORDER BY name")]


def columns(con, t: str) -> list:
    return [(r[1], r[5]) for r in con.execute(f"PRAGMA table_info({q(t)})")]       # (name, pk position)


def rows_by_name(con, t: str, excl: set) -> tuple:
    keep = [c for c, _ in columns(con, t) if not _excluded(t, c, excl)]
    if not keep:
        return keep, []
    cur = con.execute(f"SELECT {', '.join(q(c) for c in keep)} FROM {q(t)}")
    return keep, [dict(zip(keep, r)) for r in cur]


def table_fp(con, t: str, excl: set) -> tuple:
    keep, rows = rows_by_name(con, t, excl)
    lines = sorted(repr(tuple(sorted(r.items()))) for r in rows)        # keyed by name, order-free
    h = hashlib.sha256(("\n".join(lines)).encode("utf-8")).hexdigest()[:16]
    return len(rows), h


def db_files(p: Path) -> list:
    return sorted(p.glob("*.db")) if p.is_dir() else [p]


def fp(path: Path, excl: set) -> list:
    out = []
    for db in db_files(path):
        con = _connect(db)
        try:
            for t in tables(con):
                n, h = table_fp(con, t, excl)
                out.append({"file": db.name, "table": t, "rows": n, "sha16": h})
        finally:
            con.close()
    return out


def _key_cols(con, t: str, keep: list, key: str | None) -> list:
    if key and key in keep:
        return [key]
    pk = [c for c, p in sorted(columns(con, t), key=lambda x: x[1]) if p > 0 and c in keep]
    return pk or keep[:1]


def diff_db(a: Path, b: Path, excl: set, key: str | None = None, show: int = 3) -> list:
    """Findings as text lines; empty list = identical (after exclusions)."""
    ca, cb = _connect(a), _connect(b)
    out = []
    try:
        ta, tb = set(tables(ca)), set(tables(cb))
        for t in sorted(ta - tb):
            out.append(f"{a.name}|{t}: table only in A")
        for t in sorted(tb - ta):
            out.append(f"{b.name}|{t}: table only in B")
        for t in sorted(ta & tb):
            if table_fp(ca, t, excl) == table_fp(cb, t, excl):
                continue
            ka, ra = rows_by_name(ca, t, excl)
            kb, rb = rows_by_name(cb, t, excl)
            for c in sorted(set(ka) ^ set(kb)):
                out.append(f"{a.name}|{t}: column {c!r} only in {'A' if c in ka else 'B'}")
            common = [c for c in ka if c in kb]
            kc = _key_cols(ca, t, common, key)
            ia = {tuple(r[c] for c in kc): r for r in ra}
            ib = {tuple(r[c] for c in kc): r for r in rb}
            if len(ia) < len(ra) or len(ib) < len(rb):
                out.append(f"{a.name}|{t}: key {kc} is not unique - compare by fp only (rows {len(ra)} vs {len(rb)})")
                continue
            only_a, only_b = sorted(set(ia) - set(ib), key=repr), sorted(set(ib) - set(ia), key=repr)
            if only_a:
                out.append(f"{a.name}|{t}: {len(only_a)} row(s) only in A, e.g. {kc}={only_a[:show]}")
            if only_b:
                out.append(f"{a.name}|{t}: {len(only_b)} row(s) only in B, e.g. {kc}={only_b[:show]}")
            per_col: dict = {}
            for k in sorted(set(ia) & set(ib), key=repr):
                for c in common:
                    if ia[k][c] != ib[k][c]:
                        per_col.setdefault(c, []).append((k, ia[k][c], ib[k][c]))
            for c, v in sorted(per_col.items(), key=lambda kv: -len(kv[1])):
                ex = "; ".join(f"{k}: {x!r} -> {y!r}" for k, x, y in v[:show])
                out.append(f"{a.name}|{t}: column {c!r} differs in {len(v)} row(s), e.g. {ex}"[:400])
            if not (only_a or only_b or per_col or set(ka) ^ set(kb)):
                out.append(f"{a.name}|{t}: fingerprints differ but no keyed difference (duplicate rows?)")
    finally:
        ca.close()
        cb.close()
    return out


def diff(a: Path, b: Path, excl: set, key: str | None = None, show: int = 3) -> list:
    if a.is_dir() and b.is_dir():
        na, nb = {p.name: p for p in db_files(a)}, {p.name: p for p in db_files(b)}
        out = [f"{n}: file only in {'A' if n in na else 'B'}" for n in sorted(set(na) ^ set(nb))]
        for n in sorted(set(na) & set(nb)):
            out += diff_db(na[n], nb[n], excl, key, show)
        return out
    return diff_db(a, b, excl, key, show)


def main(argv: list) -> int:
    if argv[:1] == ["--selftest"]:
        return _selftest()
    a = list(argv)
    excl, js = set(), False
    key, show = None, 3
    try:
        while "--exclude" in a:
            i = a.index("--exclude")
            excl.add(a[i + 1])
            del a[i:i + 2]
        if "--key" in a:
            i = a.index("--key")
            key = a[i + 1]
            del a[i:i + 2]
        if "--show" in a:
            i = a.index("--show")
            show = int(a[i + 1])
            del a[i:i + 2]
        if "--json" in a:
            a.remove("--json")
            js = True
        if a[:1] == ["fp"] and len(a) == 2 and Path(a[1]).exists():
            res = fp(Path(a[1]), excl)
            if js:
                print(json.dumps(res, indent=1))
            else:
                for r in res:
                    print(f"{r['file']}|{r['table']}|{r['rows']}|{r['sha16']}")
                print(f"{len(res)} table(s); excluded: {', '.join(sorted(excl)) or 'none'}")
            return 0
        if a[:1] == ["diff"] and len(a) == 3 and Path(a[1]).exists() and Path(a[2]).exists():
            res = diff(Path(a[1]), Path(a[2]), excl, key, show)
            for line in res:
                print(line)
            print("IDENTICAL" if not res else f"{len(res)} difference line(s)",
                  f"(excluded: {', '.join(sorted(excl)) or 'none'})")
            return 1 if res else 0
    except (IndexError, ValueError, sqlite3.Error) as e:
        print(f"bad args: {e}", file=sys.stderr)
        return 2
    print(__doc__)
    return 2


def _selftest() -> int:
    import shutil
    ok = {}
    tmp = Path(tempfile.mkdtemp(prefix="sqlite_fp_st_"))
    try:
        da, db_ = tmp / "a", tmp / "b"
        da.mkdir()
        db_.mkdir()
        ca = sqlite3.connect(da / "latest.db")
        ca.execute('CREATE TABLE latest (sym TEXT PRIMARY KEY, "rsi@prev" REAL, close REAL)')
        ca.execute("CREATE TABLE seen (sym TEXT PRIMARY KEY, stat TEXT, bars INTEGER)")
        ca.execute("CREATE TABLE extra (x)")
        ca.executemany("INSERT INTO latest VALUES (?,?,?)", [("AAA", 41.5, 10.0), ("BBB", 60.25, 20.0)])
        ca.executemany("INSERT INTO seen VALUES (?,?,?)", [("AAA", "123:1700000000", 5), ("BBB", "9:1700000001", 7)])
        ca.commit()
        ca.close()
        cb = sqlite3.connect(db_ / "latest.db")
        cb.execute('CREATE TABLE latest (close REAL, sym TEXT PRIMARY KEY, "rsi@prev" REAL)')   # other column order
        cb.execute("CREATE TABLE seen (sym TEXT PRIMARY KEY, bars INTEGER, stat TEXT)")
        cb.execute("CREATE TABLE extra (x)")
        cb.executemany("INSERT INTO latest VALUES (?,?,?)", [(20.0, "BBB", 60.25), (10.0, "AAA", 41.5)])
        cb.executemany("INSERT INTO seen VALUES (?,?,?)", [("AAA", 5, "123:1800000000"), ("BBB", 7, "9:1800000001")])
        cb.commit()
        cb.close()
        A, B = da / "latest.db", db_ / "latest.db"
        fa = {r["table"]: r["sha16"] for r in fp(A, {"seen.stat"})}
        fb = {r["table"]: r["sha16"] for r in fp(B, {"seen.stat"})}
        ok["quoted rsi@prev + other column order + other insert order -> same fingerprint"] = fa == fb
        ok["planted: without --exclude the metadata column (seen.stat) shows as a difference"] = any(
            "'stat' differs in 2 row(s)" in x for x in diff(A, B, set()))
        ok["with --exclude seen.stat the two DBs are IDENTICAL"] = diff(da, db_, {"seen.stat"}) == []
        cb = sqlite3.connect(B)
        cb.execute("UPDATE latest SET \"rsi@prev\" = 60.250001 WHERE sym='BBB'")
        cb.execute("INSERT INTO latest VALUES (30.0, 'CCC', 50.0)")
        cb.execute("DROP TABLE extra")
        cb.commit()
        cb.close()
        d = diff(da, db_, {"seen.stat"})
        ok["one changed cell is named by table, column and key"] = any(
            "latest: column 'rsi@prev' differs in 1 row(s)" in x and "('BBB',)" in x for x in d)
        ok["a row only in B and a table only in A are reported"] = any("1 row(s) only in B" in x for x in d) and \
            any("extra: table only in A" in x for x in d)
        ok["*.stat wildcard exclusion works"] = fp(A, {"*.stat"}) == fp(A, {"seen.stat"})
        ok["read-only: the DB file is unchanged by fp and diff"] = (lambda h0: (fp(A, set()), diff(A, B, set()),
            hashlib.sha256(A.read_bytes()).hexdigest() == h0)[2])(hashlib.sha256(A.read_bytes()).hexdigest())
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            ok["main: diff exit 1 on differences, 0 identical, 2 bad args"] = main(["diff", str(A), str(B)]) == 1 \
                and main(["diff", str(A), str(A)]) == 0 and main(["diff", str(A)]) == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    print("SELFTEST " + ("OK" if all(ok.values()) else "FAILED"))
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
