"""check_e1.py RUN_DIR: mechanical assertions for eval 1 (csv-report-3x). RUN_DIR holds repo/ (the candidate) and the subagent's
TRANSCRIPT.md / REPORT.md. Prints JSON results; exit 1 when any failed."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from check_common import (
    all_text,
    copy_repo,
    cpu_min,
    emit,
    first_commit_touching,
    fresh_fixture,
    git_commits,
    non_stdlib_imports,
    planted_bug_lines,
    result,
    run,
    same_stdout,
    sha_lf,
    sha_raw,
    tmpdir,
    transcript_text,
)

A = [
    "A committed baseline file with per-command CPU-second numbers exists in a commit that precedes, in git log order, the first commit that changes report.py",
    "The baseline file records the sha256 of report.py and it equals the sha256 of the original fixture's report.py",
    "The metric is labelled CPU seconds (or process time), min (or median) of N>=3 runs - not a single wall-clock figure",
    "With the first 'generated:' line removed, the new output is byte-identical to the original for data.csv and for a second data file (seed 2) the candidate never saw",
    "An independent re-measure shows the new report.py at least 3x faster in CPU seconds than the original",
    "No import outside the Python standard library appears in any .py file of the repo",
    "At least 3 planted bugs are listed with a KILLED/SURVIVED verdict each, at least one targeting the 20-day window mechanism",
    "The write-up has a before/after table, names the metric and the equality proof, and lists at least one thing deliberately not sped up",
]


def main(run_dir: Path) -> int:
    repo = run_dir / "repo"
    tmp = tmpdir()
    orig = fresh_fixture("e1", tmp)
    cand = copy_repo(repo, tmp / "cand")
    out = []
    commits = git_commits(cand)
    is_bench = lambda f: f.startswith("bench/") or re.search(r"baseline|bench", f, re.IGNORECASE) is not None
    i_bench = first_commit_touching(commits, is_bench)
    i_code = first_commit_touching(commits, lambda f: f == "report.py")
    out.append(result(A[0], i_bench is not None and (i_code is None or i_bench < i_code),
                      f"commits={len(commits)} first bench commit index={i_bench} first report.py commit index={i_code}; "
                      + "; ".join(c['subject'][:40] for c in commits[:6])))
    want = {sha_lf(orig / "report.py"), sha_raw(orig / "report.py")}
    text = all_text(cand, ("*.json", "*.md", "*.txt"))
    found = [h for h in want if h in text]
    out.append(result(A[1], bool(found), f"original report.py sha256 found in repo text: {bool(found)}"))
    metric = re.search(r"\b(cpu|process[_ ]?time|user\s*\+\s*sys)\b", text + transcript_text(run_dir), re.IGNORECASE)
    runs = re.search(r'"cpu_runs":\s*\[([^\]]*)\]', text)
    n_ok = runs is not None and len([x for x in runs.group(1).split(",") if x.strip()]) >= 3
    minmed = re.search(r"\b(min|median)\b", text, re.IGNORECASE) and re.search(r"\b(of|N\s*=|n=)\s*([3-9]|\d\d)\b", text, re.IGNORECASE)
    out.append(result(A[2], bool(metric) and (n_ok or bool(minmed)),
                      f"metric word: {metric.group(0) if metric else None}; cpu_runs>=3: {n_ok}; min/median of N>=3 in text: {bool(minmed)}"))
    subprocess.run([sys.executable, "gen.py", "data2.csv", "150000", "100", "2"], cwd=orig, check=True, capture_output=True)
    (cand / "data2.csv").write_bytes((orig / "data2.csv").read_bytes())
    same = []
    for f in ("data.csv", "data2.csv"):
        a, b = run(["python", "report.py", f], orig), run(["python", "report.py", f], cand)
        same.append(a["exit"] == b["exit"] == 0 and same_stdout(a, b, drop_first_line=True))
    out.append(result(A[3], all(same), f"data.csv identical: {same[0]}; data2.csv identical: {same[1]}"))
    before, after = cpu_min(["python", "report.py", "data.csv"], orig), cpu_min(["python", "report.py", "data.csv"], cand)
    ratio = before / after if after else float("inf")
    out.append(result(A[4], ratio >= 3, f"CPU min of 3: before {before:.3f}s after {after:.3f}s ratio {ratio:.2f}x"))
    bad = non_stdlib_imports(cand)
    out.append(result(A[5], not bad, f"non-stdlib imports: {bad}"))
    pb = planted_bug_lines(text + "\n" + transcript_text(run_dir))
    gate = [ln for ln in pb if re.search(r"20|window|last", ln, re.IGNORECASE)]
    out.append(result(A[6], len(pb) >= 3 and bool(gate), f"{len(pb)} verdict lines; window-related: {len(gate)}; e.g. {pb[:3]}"))
    rep = transcript_text(run_dir) + text
    table = re.search(r"\|.*\d.*\|.*\d.*\|", rep)
    not_sped = re.search(r"not (sped|speeded|made faster|optimi[sz]ed)|unchanged|left (as|alone)|out of scope", rep, re.IGNORECASE)
    proof = re.search(r"identical|byte-for-byte|fingerprint|diff", rep, re.IGNORECASE)
    out.append(result(A[7], bool(table and metric and not_sped and proof),
                      f"table: {bool(table)}; metric: {bool(metric)}; not-sped-up line: {bool(not_sped)}; proof named: {bool(proof)}"))
    return emit(out)


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
