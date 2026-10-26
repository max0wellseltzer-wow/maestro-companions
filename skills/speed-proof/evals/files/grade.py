"""grade.py RUN_DIR [--eval e1|e2|e3]: run the eval's checker on RUN_DIR (which holds outputs/ with repo, REPORT.md,
TRANSCRIPT.md, and optionally timing.json) and write RUN_DIR/grading.json in the skill-creator schema:
{"expectations": [{"text", "passed", "evidence"}], "summary": {...}, "timing": {...}}. The grader subagent may then revise
individual verdicts it can judge better from the transcript (it must keep the field names)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--eval", required=True, choices=["e1", "e2", "e3"])
    a = ap.parse_args()
    outputs = a.run_dir / "outputs"
    r = subprocess.run([sys.executable, str(HERE / f"check_{a.eval}.py"), str(outputs)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", check=False)
    try:
        exp = json.loads(r.stdout)
    except ValueError:
        exp = [{"text": "checker ran", "passed": False, "evidence": ("checker failed: " + r.stderr)[-600:]}]
    passed = sum(1 for e in exp if e["passed"])
    out = {"expectations": exp,
           "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp),
                       "pass_rate": round(passed / len(exp), 3) if exp else 0.0}}
    # timing and tokens stay in the sibling timing.json: the aggregator reads BOTH from there only when grading.json has no
    # "timing" key (with one it takes the seconds and never looks for the tokens)
    (a.run_dir / "grading.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{a.run_dir.name}: {passed}/{len(exp)} passed -> {a.run_dir / 'grading.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
