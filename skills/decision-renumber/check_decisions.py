"""Check DECISIONS.md after a merge: append-only, one row per number, the gaps named, the next free number.

    python .claude/skills/decision-renumber/check_decisions.py                  # the file in the current repo
    python .claude/skills/decision-renumber/check_decisions.py --base origin/main
    python .claude/skills/decision-renumber/check_decisions.py --file path/to/DECISIONS.md --base <ref>
    python .claude/skills/decision-renumber/check_decisions.py --selftest     (hermetic: temp dir + temp git repo)

With --base, every line of the base's DECISIONS.md must still be in the new file (a row on main is never edited,
CLAUDE.md "Records and numbers"); a missing line is ROW_EDITED_OR_REMOVED. Exit 1 on a duplicate number or an
edited/removed base line, 0 otherwise. Out-of-order rows and gaps are reported but do not fail: D89/D90 were left
unused on 2026-10-13 and that is a fact to state, not a defect.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path

ROW = re.compile(r"^\| D(\d+) \|")


def rows(text: str) -> list[int]:
    return [int(m.group(1)) for ln in text.splitlines() if (m := ROW.match(ln))]


def report(text: str, base_text: str | None) -> tuple[list[str], bool]:
    nums = rows(text)
    out: list[str] = []
    bad = False
    if not nums:
        return ["NO_ROWS: no '| Dnn |' line found"], True
    dups = sorted(n for n, c in Counter(nums).items() if c > 1)
    if dups:
        bad = True
        out.append("DUPLICATE: " + ", ".join(f"D{n}" for n in dups))
    disorder = [f"D{b} after D{a}" for a, b in pairwise(nums) if b < a]
    if disorder:
        out.append("OUT_OF_ORDER (not a failure; say why): " + "; ".join(disorder[:10]))
    present = set(nums)
    gaps = [n for n in range(min(nums), max(nums) + 1) if n not in present]
    out.append("GAPS (unused numbers): " + (", ".join(f"D{n}" for n in gaps) if gaps else "none"))
    if base_text is not None:
        have = Counter(text.splitlines())
        missing = [ln for ln, c in Counter(base_text.splitlines()).items() if have[ln] < c]
        if missing:
            bad = True
            out.append(f"ROW_EDITED_OR_REMOVED: {len(missing)} base line(s) are gone, first: {missing[0][:120]!r}")
        else:
            out.append(f"APPEND_ONLY: all {len(base_text.splitlines())} base lines kept")
        new = sorted(set(nums) - set(rows(base_text)))
        out.append("NEW_ROWS: " + (", ".join(f"D{n}" for n in new) if new else "none"))
    out.append(f"ROWS: {len(nums)}  HIGHEST: D{max(nums)}  NEXT_FREE: D{max(nums) + 1}")
    return out, bad


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
    """Hermetic: synthetic DECISIONS.md text, then one temp git repo for --base. Prints PASS/FAIL per check."""
    import io
    import tempfile
    from contextlib import redirect_stdout

    base = "# D\n| D1 | a |\n| D2 | b |\n"
    ok: dict[str, bool] = {}
    out, bad = report(base + "| D4 | d |\n", base)
    ok["an appended row is OK and named NEW, gap and next free stated"] = (
        not bad and "NEW_ROWS: D4" in out and "GAPS (unused numbers): D3" in out
        and out[-1] == "ROWS: 3  HIGHEST: D4  NEXT_FREE: D5")
    out, bad = report(base + "| D2 | again |\n", None)
    ok["planted: a duplicate number FAILS"] = bad and "DUPLICATE: D2" in out
    out, bad = report("# D\n| D1 | a EDITED |\n| D2 | b |\n| D3 | c |\n", base)
    ok["planted: an edited base row FAILS"] = bad and any(x.startswith("ROW_EDITED_OR_REMOVED") for x in out)
    out, bad = report("# D\n| D2 | b |\n| D1 | a |\n", None)
    ok["out of order is reported but does not fail"] = not bad and any(x.startswith("OUT_OF_ORDER") for x in out)
    ok["planted: a file with no rows FAILS"] = report("nothing\n", None)[1]
    tmp = Path(tempfile.mkdtemp(prefix="check_decisions_selftest_"))
    try:
        def g(*args: str) -> None:
            subprocess.run(["git", "-c", "user.name=selftest", "-c", "user.email=selftest@invalid", *args],
                           cwd=tmp, check=True, capture_output=True)
        f = tmp / "DECISIONS.md"
        f.write_text(base, encoding="utf-8", newline="\n")
        g("init", "-q")
        g("add", "DECISIONS.md")
        g("commit", "-q", "-m", "base")
        f.write_text(base + "| D3 | c |\n", encoding="utf-8", newline="\n")
        with redirect_stdout(io.StringIO()):
            c_ok = main(["--file", str(f), "--base", "HEAD"])
            f.write_text("# D\n| D2 | b |\n| D3 | c |\n", encoding="utf-8", newline="\n")
            c_bad = main(["--file", str(f), "--base", "HEAD"])
            c_ref = main(["--file", str(f), "--base", "no-such-ref"])
        ok["temp repo: append exit 0, removed base row exit 1, bad ref exit 2"] = (c_ok, c_bad, c_ref) == (0, 1, 2)
    except Exception as e:  # a crash is a FAIL line, not a traceback
        ok[f"temp-repo checks ran ({type(e).__name__}: {e})"] = False
    finally:
        _rmtree(tmp)
    for name, passed in ok.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return all(ok.values())


def main(argv: list[str] | None = None) -> int:
    first = (sys.argv[1:] if argv is None else argv)[:1]
    if first == ["--selftest"]:
        return 0 if _selftest() else 1
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default="DECISIONS.md")
    ap.add_argument("--base", help="git ref whose DECISIONS.md must survive unchanged (e.g. origin/main)")
    a = ap.parse_args(argv)
    path = Path(a.file)
    text = path.read_text(encoding="utf-8")
    base_text = None
    if a.base:
        p = subprocess.run(["git", "show", f"{a.base}:DECISIONS.md"], cwd=path.resolve().parent,
                           capture_output=True, text=True, encoding="utf-8", check=False)
        if p.returncode != 0:
            print(f"BASE_UNREADABLE: {p.stderr.strip()}")
            return 2
        base_text = p.stdout
    lines, bad = report(text, base_text)
    print("\n".join(lines))
    print("VERDICT: " + ("FAIL" if bad else "OK"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
