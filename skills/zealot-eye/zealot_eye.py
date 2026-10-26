"""zealot-eye - amplify each claim to its absolutist form and find where it breaks (backs the zealot-eye skill).

The zealot reads every softened claim at full strength: some/many/most -> all, often/usually -> always,
may/might/could -> must, small -> zero, rarely/few -> never/none. Claims already absolute are taken as written.
Each amplified claim is then tested against the REST of the same text: a sentence that shares a content word with
it and carries a counter marker (not, lost, fails, except, but, unless, worse, wrong...) is its breaking point.
Claims with no breaking point inside the text are untested extremes, not confirmed ones. Heuristic word maps.

    python zealot_eye.py memo.md
    python zealot_eye.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import load_subject, view, run_cli, report, PROBES, sentences, words, STOP  # noqa: E402

KINDS = {"text", "plan"}
AMP = {"some": "all", "many": "all", "most": "all", "several": "all", "often": "always", "usually": "always",
       "sometimes": "always", "generally": "always", "typically": "always", "may": "must", "might": "must",
       "could": "must", "can": "always", "probably": "certainly", "likely": "certainly", "maybe": "certainly",
       "small": "zero", "little": "no", "rarely": "never", "seldom": "never", "few": "no", "less": "no",
       "better": "best", "worse": "worst", "fast": "instant", "slow": "frozen"}
ABSOLUTE = {"all", "always", "never", "none", "every", "must", "certainly", "obviously", "zero", "nobody",
            "everyone", "only", "best", "worst"}
COUNTER = {"not", "no", "never", "lost", "lose", "loses", "fail", "fails", "failed", "except", "but", "unless",
           "worse", "wrong", "however", "although", "yet", "broke", "broken", "revises", "stop", "again", "drawdown"}


def amplify(s):
    out, changed = [], []
    for tok in re.split(r"(\W+)", s):
        low = tok.lower()
        if low in AMP:
            rep = AMP[low]
            out.append(rep.capitalize() if tok[:1].isupper() else rep)
            changed.append(f"{low}->{rep}")
        else:
            out.append(tok)
    return "".join(out), changed


def _content(s):
    return {w for w in words(s) if w not in STOP and w not in COUNTER and w not in AMP and len(w) > 2}


def apply(subject, kind=None, **opts) -> dict:
    kind, value = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"zealot-eye reads {sorted(KINDS)}, not {kind}")
    claims = [c for c in (value if kind == "plan" else sentences(value)) if re.search(r"[A-Za-z]{3}", c)]
    if len(claims) < 2:
        raise ValueError("zealot-eye needs at least 2 claims (the rest of the text is the test bench)")
    findings, broken, already = [], 0, 0
    for i, c in enumerate(claims):
        amp, changed = amplify(c)
        absolute = bool(set(words(c)) & ABSOLUTE)
        if not changed and not absolute:
            continue
        already += absolute and not changed
        mine = _content(c)
        breaker = None
        for j, other in enumerate(claims):
            if j == i:
                continue
            shared = mine & _content(other)
            ctr = set(words(other)) & COUNTER
            if shared and ctr:
                breaker = (j + 1, other, sorted(shared)[:3], sorted(ctr)[:2])
                break
        broken += breaker is not None
        tag = "BREAKS" if breaker else "UNTESTED"
        what = (f"{tag} #{i + 1} " + (f"amplified [{', '.join(changed)}]: {amp[:90]}" if changed
                                       else f"already absolute: {c[:90]}"))
        if breaker:
            what += f" | broken by #{breaker[0]} on '{'/'.join(breaker[2])}' ({'/'.join(breaker[3])}): {breaker[1][:70]}"
        findings.append({"what": what, "claim": i + 1, "amplified": amp, "swaps": changed,
                         "broken_by": breaker[0] if breaker else None})
    findings.sort(key=lambda f: f["broken_by"] is None)
    summary = (f"{len(findings)} claim(s) pushed to the extreme ({already} already absolute); "
               f"{broken} break against the text's own evidence, {len(findings) - broken} stand untested")
    return view("zealot-eye", kind, findings, summary, amplified=len(findings), broken=broken,
                untested=len(findings) - broken)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["text"])
    ok["probe: 'small, maybe 5 bps' amplifies to 'zero, certainly'"] = any(
        "Costs are zero, certainly 5 bps" in f["amplified"] for f in v["findings"])
    ok["probe: the 'never lost' claim is taken as already absolute"] = any(
        f["claim"] == 1 and not f["swaps"] for f in v["findings"])
    p = apply("Some trades lose money. The strategy usually wins. In March the strategy lost 9 percent.")
    win = next(f for f in p["findings"] if f["claim"] == 2)
    ok["planted: 'usually wins' -> 'always wins' is broken by the March loss"] = (
        "always wins" in win["amplified"] and win["broken_by"] == 3)
    q = apply("The cache is often stale. The weather was nice.")
    ok["planted: no counter-evidence leaves the extreme untested"] = q["stats"]["untested"] == 1
    ok["amplify keeps capitals"] = amplify("Most bars are fine")[0] == "All bars are fine"
    ok["plain sentence is not amplified"] = amplify("The job ran at noon")[1] == []
    try:
        apply("One claim only.")
        ok["planted bad input (single claim) refused"] = False
    except ValueError:
        ok["planted bad input (single claim) refused"] = True
    return report(ok)


def main(argv):
    return run_cli("zealot-eye", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
