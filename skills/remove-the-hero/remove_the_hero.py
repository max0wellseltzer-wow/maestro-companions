"""remove_the_hero - delete the main cause and test whether the story still explains the outcome (backs remove-the-hero).

Causal links are read from markers: "E because (of) C", "E due to C", "E thanks to C", "C caused/causes/drove/
drives/led to/leads to E", "C, so E", "C therefore E", "since C, E", "if C, E". Each link has a cause side and an
effect side (content-word sets). The HERO is the content word that appears in the most cause sides (ties: total
mentions). With every link whose cause names the hero deleted, each effect it explained is tested: does a remaining
link explain an effect sharing a content word? If yes the story survives through that alternative; if not, the
outcome is ORPHANED - the story rests on the hero alone.

    python remove_the_hero.py <file|text> [--opt hero=word] [--json]
    python remove_the_hero.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, sentences, view, words  # noqa: E402

KINDS = {"text"}
EC = re.compile(r"^(?P<e>.+?)\s+(?:because(?: of)?|due to|thanks to)\s+(?P<c>.+)$", re.I)
CE = re.compile(r"^(?P<c>.+?)\s+(?:caused|causes|drove|drives|led to|leads to|produced|produces)\s+(?P<e>.+)$", re.I)
SO = re.compile(r"^(?P<c>.+?),?\s+(?:so|therefore|hence|thus)\s+(?P<e>.+)$", re.I)
COND = re.compile(r"^(?:since|if)\s+(?P<c>.+?),\s*(?:then\s+)?(?P<e>.+)$", re.I)


def _kw(s):
    return {w for w in words(s) if w not in STOP and len(w) > 2}


def links(text):
    out = []
    for s in sentences(text):
        s = s.strip().rstrip(".!?")
        for rx in (COND, EC, CE, SO):
            m = rx.match(s)
            if m:
                out.append({"cause": m.group("c").strip(), "effect": m.group("e").strip(),
                            "C": _kw(m.group("c")), "E": _kw(m.group("e"))})
                break
    return out


def apply(subject, kind=None, hero=None, **opts) -> dict:
    k, text = load_subject(subject, kind)
    if k not in KINDS:
        raise ValueError(f"remove-the-hero reads text, not {k}")
    ls = links(text)
    if not ls:
        return view("remove-the-hero", k, [], "no causal statements - no hero to remove", links=0, orphaned=0)
    if not hero:
        tally = {}
        for l in ls:
            for w in l["C"]:
                tally[w] = tally.get(w, 0) + 1
        mention = {w: sum(w in l["C"] | l["E"] for l in ls) for w in tally}
        low = text.lower()
        first = {w: (m.start() if (m := re.search(r"\b" + re.escape(w) + r"\b", low)) else len(low)) for w in tally}
        hero = max(sorted(tally), key=lambda w: (tally[w], mention[w], -first[w]))   # ties: earliest in the text
    gone = [l for l in ls if hero in l["C"]]
    rest = [l for l in ls if hero not in l["C"]]
    findings, orphans = [], 0
    for l in gone:
        alt = next((r for r in rest if r["E"] & (l["E"] - {hero})), None)
        if alt:
            findings.append({"what": f"SURVIVES '{l['effect'][:60]}' - still explained by '{alt['cause'][:60]}'",
                             "effect": l["effect"], "alternative": alt["cause"]})
        else:
            orphans += 1
            findings.append({"what": f"ORPHANED '{l['effect'][:60]}' - only '{hero}' ever explained it",
                             "effect": l["effect"], "alternative": None})
    findings.sort(key=lambda f: f["alternative"] is not None)
    return view("remove-the-hero", k, findings, f"hero '{hero}' drives {len(gone)} of {len(ls)} causal links; without "
                f"it {orphans} outcome(s) are orphaned, {len(gone) - orphans} still explained", hero=hero,
                links=len(ls), orphaned=orphans)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["text"])
    ok["probe: 2 causal links (because-launch and if-nightly-stop)"] = v["stats"]["links"] == 2
    ok["probe: removing the hero orphans an outcome"] = v["stats"]["orphaned"] >= 1
    t = ("Sales rose because of the ad campaign. The ad campaign drove signups. "
         "Sales rose due to lower prices. Churn fell because of support.")
    p = apply(t)
    by = {f["effect"]: f for f in p["findings"]}
    ok["planted: the campaign is the hero (2 cause sides)"] = p["stats"]["hero"] == "campaign"
    ok["planted: sales survive via lower prices, signups are orphaned"] = (
        by["Sales rose"]["alternative"] == "lower prices" and by["signups"]["alternative"] is None)
    ok["planted: a text with no causal marker has 0 links"] = apply("Bars are cached. The job runs.")["stats"]["links"] == 0
    try:
        apply(PROBES["series"])
        ok["planted bad input (a series) is refused"] = False
    except ValueError:
        ok["planted bad input (a series) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("remove-the-hero", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
