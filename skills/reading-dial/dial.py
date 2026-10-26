"""dial - the user picks how literally a prompt is read; the dial switches modes and remembers sticky choices
(backs the reading-dial skill).

Modes, most literal first:   1 code  -  2 spec (default)  -  3 brief  -  4 human
Markers the user can type anywhere in a prompt (case-insensitive):
    #code  #spec  #brief  #human  #dial 1..4  "read as code" / "read as human" / "as code:" ...
    add " on" or "from now on" to make it sticky:   "#code on", "from now on read as human"
    "#off" / "#default" clears a sticky mode
A marker without "on" applies to THIS prompt only. A persistent default (across sessions) lives in
~/.claude/reading-mode.json via set_default(); a sticky mode in the conversation overrides it, a per-prompt marker
overrides both.

    from dial import dispatch
    out = dispatch(prompt, state={})       # -> {mode, reading, state, marker, cleaned_prompt}
    python dial.py "#code fix the bug in fdr.py"
    python dial.py --selftest
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
_SK = Path(__file__).resolve().parents[1]
for _d in ("read-as-code", "read-as-spec", "read-as-brief", "read-as-human"):
    sys.path.insert(0, str(_SK / _d))
from read_brief import brief_read  # noqa: E402
from read_code import code_read  # noqa: E402
from read_human import human_read  # noqa: E402
from read_spec import spec_read  # noqa: E402

MODES = ["code", "spec", "brief", "human"]
READERS = {"code": code_read, "spec": spec_read, "brief": brief_read, "human": human_read}
DEFAULT_FILE = Path.home() / ".claude" / "reading-mode.json"
_MARK = re.compile(r"(?:#(code|spec|brief|human)\b|#dial\s*([1-4])\b|\b(?:read|take this|take it) as (code|spec|a brief|brief|a human|human)\b"
                   r"|\bas (code|human):)(\s+on\b)?", re.I)
_STICKY = re.compile(r"\bfrom now on\b", re.I)
_OFF = re.compile(r"#(off|default)\b", re.I)


def get_default(path: Path = DEFAULT_FILE) -> str:
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8")).get("default", "spec")
        return m if m in MODES else "spec"
    except (OSError, ValueError):
        return "spec"


def set_default(mode: str, path: Path = DEFAULT_FILE) -> None:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    Path(path).write_text(json.dumps({"default": mode}), encoding="utf-8")


def dispatch(prompt: str, state: dict | None = None, default_path: Path = DEFAULT_FILE) -> dict:
    state = dict(state or {})
    marker, mode = None, None
    if _OFF.search(prompt):
        state.pop("sticky", None)
        marker = "off"
    m = _MARK.search(prompt)
    if m:
        word = next(g for g in m.groups()[:4] if g).lower().replace("a ", "")
        mode = MODES[int(word) - 1] if word.isdigit() else word
        marker = m.group(0).strip()
        if m.group(5) or _STICKY.search(prompt):
            state["sticky"] = mode
    cleaned = _OFF.sub("", _MARK.sub("", prompt)).strip()
    cleaned = re.sub(r"^\W+", "", re.sub(r"\bfrom now on\b,?", "", cleaned, flags=re.I)).strip()
    mode = mode or state.get("sticky") or get_default(default_path)
    if not cleaned:
        return {"mode": mode, "reading": None, "state": state, "marker": marker, "cleaned_prompt": ""}
    return {"mode": mode, "reading": READERS[mode](cleaned), "state": state, "marker": marker,
            "cleaned_prompt": cleaned}


_SELF_VERBS = {"i", "you", "we", "it", "this", "that", "there", "want", "wish", "imagine", "picture", "dream"}
_WEIGHTS = {"code error": 0.35, "hyperbole": 0.25, "soft ask": 0.2, "vision": 0.35, "purpose mismatch": 0.2}


def ambiguity(prompt: str) -> dict:
    """Ambiguity meter (merged from ambiguity-meter; seed: metaphorical questions x prompts having sex x the dial).
    Read the prompt in all four modes and measure how differently they bind it:
      code errors       unresolved references / undefined quantities (read-as-code cannot run it)
      hyperbole, soft asks   what read-as-human treats as signal and read-as-code would take literally
      vision            human goals with no concrete command verb (code reads 'I want a world...' as a command)
      purpose mismatch  read-as-brief's purpose differs from read-as-code's first command
    score = 1 - prod(1 - weight) over every flagged phrase (0 = every mode binds it the same).
    marker: '#code' when the gaps are code errors (ask / name the referent), '#human' when the human signals dominate."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    text = " ".join(prompt.split())
    if not text:
        return {"score": 0.0, "phrases": [], "marker": None, "advice": "empty prompt", "readings": {}}
    rd = {m: READERS[m](text) for m in MODES}
    flags = []
    for e in rd["code"].get("errors", []):
        flags.append(("code error", e["error"]))
    for h in rd["human"].get("hyperbole", []):
        flags.append(("hyperbole", h))
    for s in rd["human"].get("soft_asks", []):
        flags.append(("soft ask", s))
    stmts = rd["code"].get("statements", [])
    first = stmts[0] if stmts else {}
    goals = rd["human"].get("goals", [])
    if goals and (not first or first.get("verb", "") in _SELF_VERBS):
        flags.append(("vision", goals[0]))
    purpose = (rd["brief"].get("purpose") or [""])[0]
    if first and purpose and purpose.strip().lower() != first.get("clause", "").strip().lower():
        flags.append(("purpose mismatch", f"purpose {purpose!r} vs first command {first.get('clause')!r}"))
    p = 1.0
    for kind, _ in flags:
        p *= 1 - _WEIGHTS[kind]
    score = round(1 - p, 3)
    code_n = sum(k == "code error" for k, _ in flags)
    human_n = sum(k in ("hyperbole", "soft ask", "vision") for k, _ in flags)
    if score < 0.2:
        marker, advice = None, "binds the same in every mode - the default #spec is fine"
    elif human_n >= code_n and human_n:
        marker, advice = "#human", "this needs #human: read the spirit, the literal words overstate or only hint"
    else:
        marker, advice = "#code", "this needs #code: name the referent / the number, or ask before acting"
    return {"score": score, "phrases": [{"kind": k, "phrase": ph} for k, ph in flags], "marker": marker,
            "advice": advice, "readings": rd}


def _selftest() -> bool:
    import shutil
    import tempfile
    ok = {}
    tmp = Path(tempfile.mkdtemp(prefix="dial_"))
    try:
        cfg = tmp / "mode.json"
        ok["no marker and no default file -> spec"] = dispatch("sync the repo", default_path=cfg)["mode"] == "spec"
        r = dispatch("#code fix that bug", default_path=cfg)
        ok["#code switches this prompt and strips the marker"] = (r["mode"] == "code" and r["cleaned_prompt"] == "fix that bug"
                                                                  and not r["reading"]["runnable"])
        s = dispatch("from now on read as human. keep going", default_path=cfg)
        nxt = dispatch("build more skills", state=s["state"], default_path=cfg)
        ok["sticky mode persists to the next prompt"] = s["state"]["sticky"] == "human" and nxt["mode"] == "human"
        one = dispatch("#code delete row D70", state=s["state"], default_path=cfg)
        ok["a per-prompt marker beats the sticky mode, without clearing it"] = (one["mode"] == "code"
                                                                               and one["state"]["sticky"] == "human")
        off = dispatch("#off sync", state=s["state"], default_path=cfg)
        ok["#off clears the sticky mode"] = off["mode"] == "spec" and "sticky" not in off["state"]
        set_default("brief", cfg)
        ok["a saved default applies when nothing else does; #dial 4 = human"] = (
            dispatch("sync", default_path=cfg)["mode"] == "brief" and dispatch("#dial 4 sync", default_path=cfg)["mode"] == "human")
        try:
            set_default("telepathy", cfg)
            ok["planted bad mode is rejected"] = False
        except ValueError:
            ok["planted bad mode is rejected"] = True
        lo, hi = ambiguity("Delete the D70 row from DECISIONS.md"), ambiguity("fix that and add some tests")
        vis = ambiguity("I want a world where the library grows itself like a forest")
        ok["ambiguity: precise prompt low, 'fix that and add some tests' high (#code), a vision recommends #human"] = (
            lo["score"] < 0.2 and lo["marker"] is None and hi["score"] >= 0.5 and hi["marker"] == "#code"
            and vis["marker"] == "#human")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if argv[0] == "--ambiguity":
        a = ambiguity(" ".join(argv[1:]))
        print(f"ambiguity {a['score']:.2f}  {a['advice']}")
        for p in a["phrases"]:
            print(f"  {p['kind']:16s} {p['phrase']}")
        return 0
    out = dispatch(" ".join(argv))
    print(f"mode: {out['mode']}" + (f" (marker {out['marker']!r})" if out["marker"] else ""))
    print(json.dumps(out["reading"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
