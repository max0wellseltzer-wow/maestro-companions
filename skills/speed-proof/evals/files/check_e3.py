"""check_e3.py RUN_DIR: mechanical assertions for eval 3 (slow-cli-diagnose)."""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

from check_common import (
    all_text,
    copy_repo,
    cpu_min,
    emit,
    fresh_fixture,
    planted_bug_lines,
    result,
    run,
    tmpdir,
    transcript_text,
)

C = [
    "The transcript shows a profiling or timing command (cProfile, -X importtime, or repeated timed runs) before the first edit to any .py file",
    "python -X importtime lookup.py Alice shows no heavy module import, or its cumulative import time is under 50 ms",
    "stdout, stderr and exit code are identical to the original for 8 grader-chosen names: exact, wrong case, trailing space, a unicode name, an absent name, a duplicated name, an empty argument, two arguments",
    "lookup.py --full output is identical to the original for 3 names",
    "build.py still runs and writes an identical table.sum.txt",
    "The write-up gives before/after CPU seconds for lookup, lookup --full and build, and states that build was not sped up",
    "At least 3 planted bugs are listed with verdicts, including an 'always take the fast path' bug killed by the absent-name case",
]


def same(a: dict, b: dict) -> bool:
    norm = lambda s: s.replace("\r\n", "\n")
    return a["exit"] == b["exit"] and norm(a["stdout"]) == norm(b["stdout"]) and norm(a["stderr"]) == norm(b["stderr"])


def main(run_dir: Path) -> int:
    repo = run_dir / "repo"
    tmp = tmpdir()
    orig = fresh_fixture("e3", tmp)
    cand = copy_repo(repo, tmp / "cand")
    (cand / "people.csv").write_bytes((orig / "people.csv").read_bytes())
    out = []
    tr = transcript_text(run_dir)
    lines = tr.splitlines()
    prof = next((i for i, ln in enumerate(lines) if re.search(r"cProfile|importtime|perf_counter|process_time|\btime\b.*python|timeit|bench", ln)), None)
    edit = next((i for i, ln in enumerate(lines) if re.search(r"(Edit|Write|edited|wrote|modif|patch).*\.py", ln) or re.search(r"^\s*(def |import )", ln)), None)
    out.append(result(C[0], prof is not None and (edit is None or prof < edit),
                      f"first profiling line {prof}, first edit line {edit} in TRANSCRIPT.md ({len(lines)} lines)"))
    r = run(["python", "-X", "importtime", "lookup.py", "Alice"], cand) if False else _importtime(cand)
    heavy = [ln for ln in r.splitlines() if re.search(r"\|\s*heavy\s*$", ln)]
    cum = int(heavy[-1].split("|")[1]) if heavy else 0
    out.append(result(C[1], not heavy or cum < 50000, f"importtime heavy lines: {heavy[:1]}; cumulative us: {cum}"))
    with open(orig / "people.csv", newline="", encoding="utf-8") as f:
        names = Counter(r["name"] for r in csv.DictReader(f))
    dup = next(n for n, k in names.items() if k > 1 and n not in ("Alice Brown", "Zoë Quinn"))
    cases = [["Alice Brown"], ["alice brown"], ["Alice Brown "], ["Zoë Quinn"], ["Nobody Here"], [dup], [""], ["Alice Brown", "Zoë Quinn"]]
    res = [same(run(["python", "lookup.py", *c], orig), run(["python", "lookup.py", *c], cand)) for c in cases]
    out.append(result(C[2], all(res), f"identical per case: {list(zip([c[0][:12] if c else '' for c in cases], res))}"))
    full = [same(run(["python", "lookup.py", n, "--full"], orig), run(["python", "lookup.py", n, "--full"], cand))
            for n in ("Alice Brown", "Zoë Quinn", dup)]
    out.append(result(C[3], all(full), f"--full identical: {full}"))
    ba, bb = run(["python", "build.py"], orig), run(["python", "build.py"], cand)
    art = (orig / "table.sum.txt").read_text(encoding="utf-8") == (cand / "table.sum.txt").read_text(encoding="utf-8") \
        if (cand / "table.sum.txt").exists() else False
    out.append(result(C[4], ba["exit"] == bb["exit"] == 0 and art, f"build exit {bb['exit']}; table.sum.txt identical: {art}"))
    text = tr + all_text(cand, ("*.md", "*.txt", "*.json"))
    has = all(re.search(k, text, re.IGNORECASE) for k in (r"\bcpu|process[_ ]?time", r"lookup", r"--full|lookup_full|full", r"build"))
    unchanged = re.search(r"build[^\n]{0,80}(not (sped|made faster|optimi[sz]ed|changed)|unchanged|left|same)", text, re.IGNORECASE)
    out.append(result(C[5], bool(has and unchanged), f"metric+three commands mentioned: {bool(has)}; build not-sped-up stated: {bool(unchanged)}"))
    pb = planted_bug_lines(text)
    fast = [ln for ln in pb if re.search(r"always|fast path|too strict|absent|missing|not found|unknown|scan", ln, re.IGNORECASE)
            and re.search(r"killed|red|fail|caught", ln, re.IGNORECASE) and not re.search(r"\bSURVIVED\b", ln)]
    out.append(result(C[6], len(pb) >= 3 and bool(fast), f"{len(pb)} verdict lines; always-fast-path killed: {bool(fast)}; e.g. {pb[:3]}"))
    cpu_l = cpu_min(["python", "lookup.py", "Alice Brown"], cand)
    out.append(result("(info) lookup.py CPU seconds on the candidate, min of 3 (target was < 0.25 s wall)", cpu_l < 0.25,
                      f"{cpu_l:.3f} s"))
    return emit(out)


def _importtime(cand: Path) -> str:
    import subprocess
    r = subprocess.run([sys.executable, "-X", "importtime", "lookup.py", "Alice"], cwd=cand, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", check=False)
    return r.stderr


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
