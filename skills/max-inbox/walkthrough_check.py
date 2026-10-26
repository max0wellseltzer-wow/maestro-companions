"""walkthrough_check - check click-level steps written for the user before he gets them.

A walkthrough is a numbered list (`1.` / `1)`), one action per step. Each step must end in a way to SEE that it
worked: a backticked command to paste (`! python tools/doctor.py --quick`), or an expected sight ("you should see",
"it shows", "the window says").

    python walkthrough_check.py <steps.md>
    python walkthrough_check.py --selftest

PROBLEM lines (exit 1) or WALKTHROUGH_OK:
  NO_VERIFY       a step with no command and no expected sight
  TOO_LONG        a step over 60 words (split it: one action per step)
  NO_KEY_WARNING  steps that handle a key/secret/token, but nowhere says "never paste a key into chat"
  KEY_INTO_CHAT   a step that asks him to paste/send a key here
  NO_RESTART      steps that set an environment variable (setx, $env:, "environment variable"), but none says to
                  restart Claude Code / open a new terminal so it loads
  PYTHON3         `python3` in a command (on this Windows PC it opens the Store stub; use `python`)
  SECRET_SHAPED   a real-looking credential in the text
Stdlib only.
"""
from __future__ import annotations

import re
import sys

STEP = re.compile(r"^\s{0,3}(\d+)[.)]\s+(.*)$")
VERIFY = re.compile(r"`[^`]{3,}`|you should see|it (shows|says|prints)|the (window|page|screen|box) (says|shows)|"
                    r"should (print|show|say|read)|look for|expect", re.I)
KEYISH = re.compile(r"api[ _-]?key|key[ _-]?id|_KEY\b|_SECRET|\bsecret|\btoken|\bpassword|\bcredential", re.I)
# ("the Windows key" is a keyboard key, so bare "key" does not count)
KEY_WARN = re.compile(r"never (paste|send|type|share)[^.\n]{0,40}(key|secret|token)[^.\n]{0,30}(chat|here|claude)",
                      re.I)
INTO_CHAT = re.compile(r"(paste|send|give|type)[^.\n]{0,30}(key|secret|token)[^.\n]{0,25}(to me|here|in(to)? (the )?chat|"
                       r"to claude)", re.I)
ENVSET = re.compile(r"\bsetx\b|\$env:|environment variable|SetEnvironmentVariable", re.I)
RESTART = re.compile(r"(restart|reopen|close and (re)?open|open a new)[^.\n]{0,40}(claude|terminal|powershell|window)",
                     re.I)
SECRET = re.compile(r"\b[PA]K[A-Z0-9]{18,24}\b|\bsk-[A-Za-z0-9_\-]{16,}|\bghp_[A-Za-z0-9]{20,}")


def steps(text: str) -> list:
    out, cur = [], None
    for line in text.splitlines():
        m = STEP.match(line)
        if m:
            cur = [int(m[1]), m[2]]
            out.append(cur)
        elif cur is not None and line.strip() and (line.startswith((" ", "\t", "`")) or not line.startswith("#")):
            cur[1] += "\n" + line.strip()
        elif not line.strip():
            continue
    return [(n, s) for n, s in out]


def check(text: str) -> list:
    probs, st = [], steps(text)
    if not st:
        return ["NO_STEPS: number the steps 1., 2., ..."]
    for n, s in st:
        if not VERIFY.search(s):
            probs.append(f"NO_VERIFY step {n}: end with a command to paste or what he should see")
        words = len(re.sub(r"`[^`]*`", "x", s).split())
        if words > 60:
            probs.append(f"TOO_LONG step {n}: {words} words; one action per step")
        if INTO_CHAT.search(s) and not KEY_WARN.search(s):
            probs.append(f"KEY_INTO_CHAT step {n}: a key goes into a file or a prompt box he controls, never the chat")
    if KEYISH.search(text) and not KEY_WARN.search(text):
        probs.append("NO_KEY_WARNING: add 'never paste a key into chat' where a key is handled")
    if ENVSET.search(text) and not RESTART.search(text):
        probs.append("NO_RESTART: a new environment variable loads only after restarting Claude Code / a new terminal")
    if re.search(r"\bpython3\b", text):
        probs.append("PYTHON3: use `python` (python3 opens the Microsoft Store stub on this PC)")
    if SECRET.search(text):
        probs.append("SECRET_SHAPED: a real-looking credential is in the steps")
    return probs


def main(argv: list) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if argv[:1] == ["--selftest"]:
        return 0 if _selftest() else 1
    if not argv:
        print(__doc__)
        return 2
    from pathlib import Path
    probs = check(Path(argv[0]).read_text(encoding="utf-8"))
    for p in probs:
        print("PROBLEM " + p)
    print("WALKTHROUGH_OK" if not probs else f"{len(probs)} problem(s)")
    return 1 if probs else 0


GOOD = """Never paste a key into chat: it goes only into the box Windows shows you.

1. Press the Windows key, type `powershell`, press Enter. You should see a blue window.
2. Paste `setx ALPACA_KEY_ID "<your key id>"` and press Enter. It says SUCCESS: Specified value was saved.
3. Close Claude Code and open a new terminal, then start Claude Code again so the new variable loads.
   You should see the prompt come back.
4. In Claude Code type `! python tools/doctor.py --quick`. It prints ALPACA: OK.
"""


def _selftest() -> bool:
    ok = {}
    ok["good click-level steps pass"] = check(GOOD) == []
    no_verify = GOOD.replace("It prints ALPACA: OK.", "").replace("`! python tools/doctor.py --quick`",
                                                                  "the doctor command")
    ok["a step with no command and no expected sight is NO_VERIFY"] = check(no_verify) == [
        "NO_VERIFY step 4: end with a command to paste or what he should see"]
    ok["key handling without the warning is NO_KEY_WARNING"] = any(
        p.startswith("NO_KEY_WARNING") for p in check(GOOD.replace("Never paste a key into chat: ", "")))
    ok["asking for the key in chat is KEY_INTO_CHAT"] = any(
        p.startswith("KEY_INTO_CHAT") for p in check(GOOD + "5. Paste your secret key here to me. You should see ok.\n"))
    no_restart = GOOD.replace("3. Close Claude Code and open a new terminal, then start Claude Code again so the new "
                              "variable loads.", "3. Wait a moment.")
    ok["setting an env var without a restart step is NO_RESTART"] = any(
        p.startswith("NO_RESTART") for p in check(no_restart))
    ok["python3 is refused"] = any(p.startswith("PYTHON3") for p in check(GOOD.replace("! python ", "! python3 ")))
    ok["a 70-word step is TOO_LONG"] = any(
        p.startswith("TOO_LONG") for p in check(GOOD + "5. " + "click " * 70 + "You should see it.\n"))
    ok["a real-looking key is refused"] = any(
        p.startswith("SECRET_SHAPED") for p in check(GOOD.replace("<your key id>", "PKABCDEFGHIJKLMNOPQRST")))
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
