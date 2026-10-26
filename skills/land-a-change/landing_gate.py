"""Pre-landing gate: evaluates the land-a-change ritual over facts you supply, and says LAND or HOLD.

You pass what actually happened (tests green, red-on-planted-bug for new tests, ruff clean, the test ids
pytest collected vs the ids in tests.json, precheck, full check run or explicitly stated as targeted-only,
the exact `git add` command, Co-Authored-By present, root pointer bumped, peer told, and - for a scratch
clone - which siblings it ran with). Each step comes back PASS / FAIL / STATED / N/A; any FAIL means HOLD.
Two sub-checks are mechanical on text: `git add` must name files (no -A, --all, `.` or `*`), and every
collected test id must be registered in tests.json. It runs nothing itself.

Usage:
    from landing_gate import evaluate
    steps, verdict = evaluate({"tests_green": True, "new_tests": False, "ruff_clean": True,
        "collected_ids": [...], "registered_ids": [...], "precheck_ok": True,
        "full_check": "targeted tests only", "git_add": "git add a.py tests/test_a.py",
        "co_authored": True, "root_pointer_bumped": True, "shares_project": False})
    python landing_gate.py --facts facts.json
    python landing_gate.py --selftest
"""
import json
import shlex
import sys

BAD_ADD = {"-A", "--all", ".", "*", "-u", "--update", ":/"}


def bad_add_args(cmd):
    """Return the forbidden broad pathspecs in a `git add` command (empty list = adds files by name)."""
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        return ["<unparseable>"]
    if "add" not in toks:
        return ["<not a git add command>"]
    args = toks[toks.index("add") + 1:]
    bad = [t for t in args if t in BAD_ADD or t.endswith("/.")]
    if not [t for t in args if not t.startswith("-")]:
        bad.append("<no files named>")
    return bad


def unregistered(collected, registered):
    """Collected test ids missing from tests.json, in collected order."""
    reg = set(registered)
    return [t for t in collected if t not in reg]


def evaluate(f):
    steps = []

    def add(name, status, note=""):
        steps.append((name, status, note))

    add("1 targeted tests green", "PASS" if f.get("tests_green") else "FAIL")
    if f.get("new_tests"):
        add("1b new test seen red on a planted bug", "PASS" if f.get("seen_red") else "FAIL")
    add("2 ruff clean", "PASS" if f.get("ruff_clean") else "FAIL")
    if "collected_ids" in f:
        missing = unregistered(f.get("collected_ids", []), f.get("registered_ids", []))
        add("3 every test id in tests.json", "FAIL" if missing else "PASS", ", ".join(missing))
    else:
        add("3 every test id in tests.json", "FAIL", "collected ids not supplied")
    add("4 precheck", "PASS" if f.get("precheck_ok") else "FAIL")
    fc = f.get("full_check")
    if fc is True:
        add("5 full project check", "PASS")
    elif isinstance(fc, str) and fc.strip():
        add("5 full project check", "STATED", fc.strip())
    else:
        add("5 full project check", "FAIL", "neither run nor stated - a silent skip")
    bad = bad_add_args(f.get("git_add", ""))
    add("6 git add by name", "FAIL" if bad else "PASS", " ".join(bad))
    add("6b Co-Authored-By line", "PASS" if f.get("co_authored") else "FAIL")
    add("7 root pointer bumped", "PASS" if f.get("root_pointer_bumped") else "FAIL")
    if f.get("shares_project"):
        add("8 peer told the commit id", "PASS" if f.get("peer_told") else "FAIL")
    else:
        add("8 peer told the commit id", "N/A")
    if f.get("scratch_clone"):
        sib = str(f.get("siblings_stated", "")).strip()
        add("clone check states its siblings/data", "PASS" if sib else "FAIL", sib)
    verdict = "HOLD" if any(s == "FAIL" for _, s, _ in steps) else "LAND"
    return steps, verdict


def _selftest():
    results = []

    def check(desc, ok):
        results.append(ok)
        print(("PASS " if ok else "FAIL ") + desc)

    good = {"tests_green": True, "new_tests": True, "seen_red": True, "ruff_clean": True,
            "collected_ids": ["t::a", "t::b[1]"], "registered_ids": ["t::a", "t::b[1]"], "precheck_ok": True,
            "full_check": "targeted tests only", "git_add": "git add src/a.py tests/test_a.py",
            "co_authored": True, "root_pointer_bumped": True, "shares_project": True, "peer_told": True}
    steps, v = evaluate(good)
    check("complete facts give LAND", v == "LAND")
    check("stated targeted-only check is STATED, not FAIL", ("5 full project check", "STATED",
                                                            "targeted tests only") in steps)
    check("git add -A is caught", "-A" in bad_add_args("git add -A"))
    check("git add . is caught", "." in bad_add_args("git -C proj add ."))
    check("git add of named files passes", bad_add_args("git add a.py b.py") == [])
    check("unregistered parametrized id is found", unregistered(["t::b[1]", "t::b[2]"], ["t::b[1]"]) == ["t::b[2]"])

    bad = dict(good, collected_ids=["t::a", "t::b[1]", "t::b[2]"])
    check("planted unregistered test id turns verdict to HOLD", evaluate(bad)[1] == "HOLD")
    check("silent full-check skip turns verdict to HOLD", evaluate(dict(good, full_check=None))[1] == "HOLD")
    check("new test never seen red gives HOLD", evaluate(dict(good, seen_red=False))[1] == "HOLD")
    check("scratch clone without stated siblings gives HOLD", evaluate(dict(good, scratch_clone=True))[1] == "HOLD")
    return all(results)


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "--facts" and len(argv) > 1:
        with open(argv[1], encoding="utf-8") as fh:
            steps, verdict = evaluate(json.load(fh))
        for name, status, note in steps:
            print("%-7s %s%s" % (status, name, ("  (" + note + ")") if note else ""))
        print("VERDICT:", verdict)
        return 0 if verdict == "LAND" else 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
