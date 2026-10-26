"""Before retrying anything a guard blocked, check the retry is an honest equivalent and not a disguised copy.

The guard-respect rule: never route around a guard - no splitting a string so the pattern no longer matches, no
encoding, no "same command in PowerShell", and no retrying with small changes to see what gets through. This
module classifies a command into the action classes the guard cares about (recursive delete, discarding work,
encoded payload, secret in the command line) after undoing the usual disguises (quote splicing, string
concatenation, caret/backtick escapes, case), then `check_retry(blocked, proposed)` returns the reasons a
proposed retry is NOT honest: same action class as the blocked call (shell swap or spliced string), an encoded
payload, or a near-duplicate of the blocked text. `honest_alternative` returns the skill's table entry for the
class. It is an aid to your own judgment, never a tool for finding what the guard misses; if it says DISGUISED,
stop and ask the user.

Usage:
    from retry_check import check_retry, honest_alternative
    reasons = check_retry(blocked_cmd, proposed_cmd)   # [] = not a disguised copy (still use judgment)
    python retry_check.py "<blocked command>" "<proposed command>"
    python retry_check.py --selftest
"""
import difflib
import re
import sys

CLASSES = {
    "recursive-delete": [r"\brm\s+(-\w*\s+)*-\w*r", r"\brm\s+(-\w*\s+)*--recursive", r"remove-item\b.*-r(ecurse)?\b",
                         r"\b(rmdir|rd)\b.*\s/s\b", r"\bdel\b.*\s/s\b", r"shutil\.rmtree", r"\bri\b.*-r(ecurse)?\b"],
    "discard-work": [r"\bgit\s+checkout\s+(--\s|--theirs|--ours|\.\s*$)", r"\bgit\s+checkout\s+\S+\s+--\s", r"\bgit\s+restore\b", r"\bgit\s+reset\s+--hard",
                     r"\bgit\s+clean\s+-\w*f", r"\bgit\s+stash\s+drop", r"\bgit\s+push\s+.*(--force|-f\b)"],
    "encoded": [r"base64\s+(-d|--decode)", r"-enc(odedcommand)?\s+[a-z0-9+/=]{8,}", r"frombase64string", r"\bb64decode\b",
                r"\bcertutil\b.*-decode", r"\bxxd\s+-r"],
    "secret-in-command": [r"(api[_-]?key|secret|token|password)\s*[=:]\s*\S{8,}", r"authorization:\s*bearer\s+\S{12,}"],
}

HONEST = {
    "recursive-delete": "ask the user to delete it himself with the exact one-line command; for your own scratch files, a "
                        "small script that unlinks only the named files it created, listed in the script",
    "discard-work": "git show HEAD:<file> > <file> (explicit about which version you keep); for a file from another "
                    "ref, git cat-file blob <ref>:<path> > <path>; never discard others' work",
    "encoded": "none - an encoded payload is a disguise by definition; run the plain command or ask the user",
    "secret-in-command": "keys-in-process: load the key from the environment inside one process; it never enters text",
}


def normalize(cmd):
    """Undo common disguises so the action underneath can be read."""
    s = cmd.lower()
    s = re.sub(r"[\"']\s*\+\s*[\"']", "", s)      # "r" + "m"  -> rm
    s = re.sub(r"(\w)(''|\"\")(\w)", r"\1\3", s)   # r''m -> rm
    s = s.replace("^", "").replace("`", "")          # cmd caret / PowerShell backtick escapes
    s = s.replace("${ifs}", " ").replace("$ifs", " ")
    s = re.sub(r"[\"']", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify(cmd):
    s = normalize(cmd)
    return sorted(c for c, pats in CLASSES.items() if any(re.search(p, s) for p in pats))


def check_retry(blocked, proposed, near=0.85):
    reasons = []
    b, p = classify(blocked), classify(proposed)
    shared = sorted(set(b) & set(p))
    for c in shared:
        reasons.append("same action as the blocked call (%s) - a shell swap or spliced string is still that action" % c)
    if "encoded" in p and "encoded" not in shared:
        reasons.append("encoded payload - a disguise by definition")
    if "secret-in-command" in p and "secret-in-command" not in shared:
        reasons.append("a secret in the command line")
    ratio = difflib.SequenceMatcher(None, normalize(blocked), normalize(proposed)).ratio()
    if ratio >= near and normalize(blocked) != normalize(proposed) and not shared:
        reasons.append("near-duplicate of the blocked call (similarity %.2f) - small changes probe the guard" % ratio)
    if normalize(blocked) == normalize(proposed):
        reasons.append("identical to the blocked call after removing quoting/escapes")
    return reasons


def honest_alternative(blocked):
    return {c: HONEST[c] for c in classify(blocked)}


def _selftest():
    ok = True

    def check(cond, desc):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + desc)
        ok = ok and bool(cond)

    blocked = "rm -rf build/tmp"
    check(classify(blocked) == ["recursive-delete"] and classify("ls -la build") == [], "classifier names the recursive delete and leaves ls alone")
    check(any("same action" in r for r in check_retry(blocked, "Remove-Item -Recurse -Force build/tmp")),
          "PowerShell shell-swap of the blocked delete is CAUGHT")
    check(any("same action" in r for r in check_retry(blocked, "r''m -r''f build/tmp")) and
          any("same action" in r for r in check_retry(blocked, 'sh -c "r" + "m -rf build/tmp"')),
          "quote-spliced and concatenated copies are CAUGHT")
    check(any("encoded" in r for r in check_retry(blocked, "echo cm0gLXJmIGJ1aWxk | base64 -d | sh")), "base64-piped payload is caught")

    gb = "git checkout -- src/app.py"
    check(check_retry(gb, "git show HEAD:src/app.py > src/app.py") == [] and "discard-work" in honest_alternative(gb),
          "the skill's honest equivalent (git show HEAD:file > file) passes and is offered")
    check(any("same action" in r for r in check_retry(gb, "git restore src/app.py")), "git restore as a swap for checkout -- is caught")
    check(check_retry(blocked, "python cleanup_named.py") == [], "a scoped named-file script is not flagged")
    # 2026-10-20 L531: checkout of one file from another ref was blocked as discarding changes
    gr = "git checkout origin/wip/x -- plans/a.md"
    check(classify(gr) == ["discard-work"], "git checkout <ref> -- file is classed as discard-work")
    check(check_retry(gr, "git cat-file blob origin/wip/x:plans/a.md > plans/a.md") == [],
          "the cat-file blob route for a file from another ref passes")
    check(any("same action" in r for r in check_retry(gr, "git restore --source origin/wip/x plans/a.md")),
          "git restore --source as a swap for checkout <ref> -- is caught")
    # 2026-10-21 L2551/L7377: refresh a scratch copy by rm -rf; honest route is a fresh folder name
    rb = 'rm -rf "$S/maestro_copy" && cp -r src "$S/maestro_copy"'
    check(any("same action" in r for r in check_retry(rb, "find $S/maestro_copy -delete -depth; rm -r $S/maestro_copy")),
          "a find/rm -r rewrite of the scratch refresh is caught")
    check(check_retry(rb, 'cp -r src "$S/maestro_copy_0524"') == [], "copying into a fresh timestamped folder passes")
    check(classify("python -c \"import shutil; shutil.rmtree('x')\"") == ["recursive-delete"],
          "shutil.rmtree in python -c is still a recursive delete")
    check(any("near-duplicate" in r for r in check_retry("cat secrets/prod.env", "cat secrets/prod.env.")),
          "a small-change retry of an unclassified blocked call is caught as probing")
    return ok


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if len(argv) != 2:
        print(__doc__)
        return 2
    reasons = check_retry(argv[0], argv[1])
    for r in reasons:
        print("DISGUISED: " + r)
    for c, alt in honest_alternative(argv[0]).items():
        print("honest equivalent for %s: %s" % (c, alt))
    if not reasons:
        print("not a disguised copy by these checks - still ask: is this the honest equivalent?")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
