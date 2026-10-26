"""sibling_preflight - does this layout give the project the siblings its check reads? (read-only)

A project checked from a scratch clone loses what the workspace puts beside it. Three false reds on 2026-10-13/15:
tv-blend "STACK_UNAVAILABLE: quality-kit... not importable", tv-desk "no data file at ...tv-tests\\tests\\golden",
a tv-core test reading the root check_all.bat. This turns land-a-change's prose warning into a preflight.

    python sibling_preflight.py PROJECT ROOT [--manifest siblings.json] [--log check.log]
    python sibling_preflight.py --selftest

ROOT is the folder the project sits in (the workspace root, or the scratch folder holding the clone).
Manifest: {"project": [{"path": "relative/to/ROOT", "signs": ["text a failure shows when it is missing"]}]};
the built-in default covers the three projects above. Without --log: exit 0 every sibling present, 3 LAYOUT
(something missing: a red from this layout is not a code verdict). With --log: each FAILED/ERROR line is labelled
LAYOUT (it shows a missing sibling's sign) or OTHER; exit 0 no failure lines, 3 all failures are LAYOUT,
1 at least one OTHER failure (a real red). 2 bad args.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

DEFAULT = {
    "tv-blend": [{"path": "quality-kit", "signs": ["STACK_UNAVAILABLE", "quality-kit"]}],
    "tv-desk": [{"path": "tv-tests/tests/golden/frozen", "signs": ["no data file at", "golden"]}],
    "tv-core": [{"path": "check_all.bat", "signs": ["check_all.bat"]}],
}
FAIL_LINE = re.compile(r"^(FAILED|ERROR)\b|\b(FAILED|ERROR)\s*$|^E\s")


def missing(project: str, root: Path, manifest: dict) -> list:
    return [s for s in manifest.get(project, []) if not (Path(root) / s["path"]).exists()]


def classify(log_text: str, gone: list) -> list:
    out = []
    for ln in log_text.splitlines():
        if not FAIL_LINE.search(ln.strip()):
            continue
        layout = any(sign.lower() in ln.lower() for s in gone for sign in s["signs"])
        out.append(("LAYOUT" if layout else "OTHER", ln.strip()))
    return out


def read_text(p: Path) -> str:
    raw = Path(p).read_bytes()
    return raw.decode("utf-16", errors="replace") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode(
        "utf-8", errors="replace")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    ap = argparse.ArgumentParser(prog="sibling_preflight")
    ap.add_argument("project")
    ap.add_argument("root")
    ap.add_argument("--manifest")
    ap.add_argument("--log")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8")) if a.manifest else DEFAULT
    if not (Path(a.root) / a.project).is_dir():
        print(f"no project folder {a.project} under {a.root}")
        return 2
    gone = missing(a.project, Path(a.root), manifest)
    for s in manifest.get(a.project, []):
        print(f"{'MISSING' if s in gone else 'present'}  {s['path']}")
    if not manifest.get(a.project):
        print(f"(no siblings listed for {a.project})")
    if a.log is None:
        print("VERDICT: LAYOUT - a red from this layout is not a code verdict; add the siblings or run in the workspace"
              if gone else "VERDICT: OK - layout complete")
        return 3 if gone else 0
    rows = classify(read_text(Path(a.log)), gone)
    for lab, ln in rows:
        print(f"{lab:6s} {ln[:160]}")
    other = sum(lab == "OTHER" for lab, _ in rows)
    if not rows:
        print("VERDICT: no failure lines")
        return 0
    print(f"VERDICT: {len(rows) - other} LAYOUT, {other} OTHER")
    return 1 if other else 3


def _selftest() -> bool:
    ok = {}
    root = Path(tempfile.mkdtemp(prefix="sibpre_"))
    (root / "tv-blend").mkdir()
    (root / "tv-desk").mkdir()
    ok["scratch layout without quality-kit is LAYOUT (exit 3)"] = main(["tv-blend", str(root)]) == 3
    (root / "quality-kit").mkdir()
    ok["with the sibling present it is OK (exit 0)"] = main(["tv-blend", str(root)]) == 0
    log = root / "desk.log"
    log.write_text("FAILED tests/test_desk.py::test_fan - AssertionError: no data file at x\\tv-tests\\tests\\golden\n"
                   "FAILED tests/test_desk.py::test_math - assert 2 == 3\n....\n", encoding="utf-8")
    gone = missing("tv-desk", root, DEFAULT)
    rows = classify(log.read_text(encoding="utf-8"), gone)
    ok["a failure showing the missing sibling's sign is LAYOUT, an unrelated one OTHER"] = [r[0] for r in rows] == [
        "LAYOUT", "OTHER"]
    ok["one OTHER failure means a real red (exit 1)"] = main(["tv-desk", str(root), "--log", str(log)]) == 1
    log.write_text("FAILED tests/test_desk.py::test_fan - no data file at golden\n", encoding="utf-8")
    ok["only LAYOUT failures exit 3"] = main(["tv-desk", str(root), "--log", str(log)]) == 3
    (root / "tv-tests" / "tests" / "golden" / "frozen").mkdir(parents=True)
    ok["once the sibling exists the same line is OTHER (a real red)"] = main(
        ["tv-desk", str(root), "--log", str(log)]) == 1
    ps = root / "ps.log"
    ps.write_bytes("ERROR tests/test_stack.py - STACK_UNAVAILABLE: quality-kit not importable\r\n".encode("utf-16"))
    (root / "quality-kit").rmdir()
    ok["a UTF-16 log is read"] = main(["tv-blend", str(root), "--log", str(ps)]) == 3
    m = root / "m.json"
    m.write_text(json.dumps({"tv-blend": []}), encoding="utf-8")
    ok["a custom manifest replaces the default"] = main(["tv-blend", str(root), "--manifest", str(m)]) == 0
    ok["a missing project folder exits 2"] = main(["tv-nope", str(root)]) == 2
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main())
