"""view_from_zero - read a plan or text as if starting from nothing (empty machine, no account, no history) and list
everything it presupposes already exists: things named with 'the' before anything made them, prior state implied by
re-verbs (rebuild, again, restart), owned things (our, the user's), outside tools and accounts named in capitals, and the
access that verbs like land, push, download or tell silently require (backs the view-from-zero skill).

    python view_from_zero.py <plan|text> [--kind plan|text] [--json]
    python view_from_zero.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]; sys.dont_write_bytecode = True; sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, sentences, view, words  # noqa: E402

KINDS = {"plan", "text"}
MAKE = set("download build create make write generate compute fetch produce draft collect gather export train".split())
REVERB = re.compile(r"\b(re[a-z]{3,}|again|resume|restore|fix|update|still|back|another|continue)\b", re.I)
NOT_RE = {"read", "ready", "real", "really", "recent", "result", "results", "return", "report", "record", "reason",
          "region", "regime", "remain", "rely", "request", "require", "research", "reply", "respond", "red", "rest",
          "revises", "revise", "reversion", "review", "receipt"}
ACCESS = {"land": "a repo with write access to the target branch", "push": "a repo remote and push rights",
          "merge": "a repo with write access", "deploy": "a deploy target and credentials",
          "download": "network access and a data source that serves it", "fetch": "network access and a source",
          "tell": "a channel that reaches the person", "send": "a channel that reaches the recipient",
          "email": "an email account", "post": "an account on the place being posted to",
          "run": "an installed, working runtime for the thing run", "schedule": "a scheduler that is registered",
          "buy": "a funded brokerage account", "sell": "a position to sell and a broker", "launch": "something built to launch"}
VERBISH = {"came", "went", "says", "say", "fails", "failed", "runs", "wants", "revises", "makes", "gets", "got", "needs",
           "shows", "said", "goes", "works", "broke", "breaks", "keeps", "never", "always"}
VAGUE = {"result", "results", "output", "it", "change", "this", "that", "answer", "outcome"}


def apply(subject, kind=None, **opts) -> dict:
    kind, value = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"view-from-zero reads a plan or text, not {kind}")
    units = value if kind == "plan" else sentences(value)
    if not units:
        raise ValueError("empty subject")
    made, seen, findings = set(), set(), []

    def add(cat, thing, i, why):
        if (cat, thing) not in seen:
            seen.add((cat, thing))
            findings.append({"what": f"[{cat}] {thing} - {why} (line {i})", "category": cat, "thing": thing, "line": i})

    for i, u in enumerate(units, 1):
        ws = words(u)
        if ws and ws[0] in MAKE:                                 # making verbs create their object
            made |= {w for w in ws[1:] if w not in STOP}
        for m in re.finditer(r"\b(?:a|an)\s+(?:new\s+)?([a-z][\w\-]*)", u, re.I):
            made.add(m.group(1).lower())
        for m in re.finditer(r"\bthe\s+((?:[A-Za-z][\w\-]*\s+)?[A-Za-z][\w\-]*)", u, re.I):
            parts = m.group(1).lower().split()
            if len(parts) == 2 and (parts[1] in STOP or parts[1] in VERBISH or parts[1].endswith("ed")):
                parts = parts[:1]                                 # 'the crowd is' -> 'crowd'
            phrase, head = " ".join(parts), parts[-1]
            if head in VAGUE or head in STOP or head in made or phrase.split()[0] in MAKE:
                continue
            add("thing", phrase, i, "named with 'the' before anything made it")
            made.add(head)
        for m in REVERB.finditer(u):
            w = m.group(1).lower()
            if w not in NOT_RE:
                add("prior-state", w, i, "only makes sense if it existed or happened before")
        for m in re.finditer(r"\b(our|my|your|their|[A-Z][a-z]+'s)\s+([a-z][\w\-]*)", u):
            add("ownership", f"{m.group(1)} {m.group(2)}", i, "assumes it is already owned")
        caps = words(u, lower=False)
        for w in caps[1:]:
            if w[:1].isupper() and w.lower() not in STOP and len(w) > 2:
                add("external", w, i, "a named outside tool, place or person that must already be there")
        for w in ws:
            if w in ACCESS:
                add("access", w, i, ACCESS[w])
        if re.search(r"\b(main|master|repo|branch)\b", u, re.I):
            add("access", "repository", i, "a repository with that branch already set up")
    cats = {}
    for f in findings:
        cats[f["category"]] = cats.get(f["category"], 0) + 1
    summary = (f"from zero, {len(units)} line(s) presuppose {len(findings)} things already exist: "
               + ", ".join(f"{n} {c}" for c, n in sorted(cats.items(), key=lambda kv: -kv[1])))
    return view("view-from-zero", kind, findings, summary, presupposed=len(findings), by_category=cats)


def _selftest() -> bool:
    ok = {}
    p = apply(PROBES["plan"])
    things = {f["thing"] for f in p["findings"]}
    ok["probe plan: the cache and screener are presupposed; the downloaded bars are not"] = (
        "cache" in things and "screener" in things and not any("bars" in t for t in things))
    ok["probe plan: 'rebuild' implies prior state, 'land ... main' implies a repository"] = (
        "rebuild" in things and "repository" in things)
    t = apply(PROBES["text"])
    tt = {f["thing"] for f in t["findings"]}
    ok["probe text: TradingView is external, 'again' is prior state, 'the nightly job' is presupposed"] = (
        "TradingView" in tt and "again" in tt and "nightly job" in tt)
    intro = apply("Build a cache. Then load the cache.")
    ok["planted introduction: 'a cache' then 'the cache' presupposes nothing"] = not any(
        f["thing"] == "cache" for f in intro["findings"])
    own = apply("Restart our scheduler on the user's laptop.")
    ot = {f["thing"] for f in own["findings"]}
    ok["planted possessives and re-verb: our scheduler, the user's laptop, restart"] = {
        "our scheduler", "the user's laptop", "restart"} <= ot
    ok["probe plan: 'tell the user' needs a channel"] = any(f["thing"] == "tell" for f in p["findings"])
    try:
        apply(PROBES["series"])
        ok["planted bad input (a series) is refused"] = False
    except ValueError:
        ok["planted bad input (a series) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("view-from-zero", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
