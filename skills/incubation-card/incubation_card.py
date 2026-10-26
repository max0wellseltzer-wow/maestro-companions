"""incubation-card - park a problem as a deferred card with a fresh-eyes question set (backs incubation-card).

The card holds: an id (sha256 of the problem text, first 12 hex), the parked date and the revisit date (+days,
default 2), the GIST (the sentence carrying the most of the text's key-term weight) and a question set built only
from the problem itself -
  OPEN       every question it already asks;
  CONDITION  every "if X, ..." -> "did X happen?";
  NUMBER     every number with a unit -> "is it still true on <revisit date>?";
  ABSOLUTE   every never / always / must claim -> "what would break it?";
  UNLINKED   pairs of top key terms that never share a sentence -> "how does A relate to B?" (the incubation itch).
--opt out=card.json writes the card; --opt card=card.json REVISITS: same hash = unchanged since parked, else the
questions added and dropped since.

    python incubation_card.py problem.md --opt days=3 --opt out=card.json
    python incubation_card.py problem.md --opt card=card.json
    python incubation_card.py --selftest
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import load_subject, view, run_cli, report, PROBES, sentences, words, keywords, numbers_with_units  # noqa: E402

KINDS = {"text", "plan"}
ABS = re.compile(r"\b(?:never|always|must|cannot|impossible|guaranteed|every)\b", re.I)


def questions(text, revisit):
    sents = sentences(text)
    kw = dict(keywords(text, 30))
    qs = [("OPEN", s.strip()) for s in sents if s.strip().endswith("?")]
    for s in sents:
        m = re.search(r"\bif\s+(.+?)(?:,|\bthen\b|$)", s, re.I)
        if m:
            qs.append(("CONDITION", f"did '{m.group(1).strip()[:60]}' happen?"))
    for v, u, p in numbers_with_units(text):
        if u and not (1900 <= v <= 2100 and not u):
            ctx = " ".join(words(text[max(0, p - 40):p])[-3:])
            qs.append(("NUMBER", f"is {v:g} {u} ({ctx} ...) still true on {revisit}?"))
    qs += [("ABSOLUTE", f"what would break: '{s.strip()[:70]}'?") for s in sents if ABS.search(s) and not s.strip().endswith("?")]
    top = [w for w, _ in keywords(text, 6)]
    sets = [set(words(s)) for s in sents]
    pairs = [(a, b) for i, a in enumerate(top) for b in top[i + 1:] if not any(a in s and b in s for s in sets)]
    qs += [("UNLINKED", f"how does {a} relate to {b}?") for a, b in pairs[:3]]
    gist = max(sents, key=lambda s: sum(kw.get(w, 0) for w in set(words(s)))) if sents else ""
    return gist, qs


def apply(subject, kind=None, **opts) -> dict:
    kind, value = load_subject(subject, kind)
    if kind not in KINDS:
        raise ValueError(f"incubation-card reads {sorted(KINDS)}, not {kind}")
    text = "\n".join(value) if kind == "plan" else value
    if len(words(text)) < 3:
        raise ValueError("too little text to park")
    today = dt.date.fromisoformat(str(opts.get("today", dt.date.today().isoformat())))
    revisit = (today + dt.timedelta(days=int(opts.get("days", 2)))).isoformat()
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    gist, qs = questions(text, revisit)
    card = {"id": h, "parked": today.isoformat(), "revisit": revisit, "gist": gist,
            "questions": [f"{k}: {q}" for k, q in qs]}
    f = [{"what": f"CARD {h} parked {card['parked']}, revisit {revisit}; gist: {gist[:90]}", "card": h}]
    f += [{"what": f"{k:9s} {q}", "type": k} for k, q in qs]
    status = "new card"
    if opts.get("card"):
        old = json.loads(Path(str(opts["card"])).read_text(encoding="utf-8"))
        if old.get("id") == h:
            status = f"UNCHANGED since parked {old.get('parked')} - fresh eyes only"
        else:
            added = [q for q in card["questions"] if q not in old.get("questions", [])]
            dropped = [q for q in old.get("questions", []) if q not in card["questions"]]
            status = f"CHANGED since {old.get('parked')}: +{len(added)} / -{len(dropped)} question(s)"
            f += [{"what": f"ADDED    {q}", "type": "added"} for q in added] + [{"what": f"DROPPED  {q}", "type": "dropped"} for q in dropped]
    if opts.get("out"):
        Path(str(opts["out"])).write_text(json.dumps(card, indent=1), encoding="utf-8")
        status += f"; written to {opts['out']}"
    counts = {}
    for k, _ in qs:
        counts[k] = counts.get(k, 0) + 1
    summary = (f"card {h}: {len(qs)} fresh-eyes question(s) (" + ", ".join(f"{k.lower()} {v}" for k, v in counts.items())
               + f"); revisit {revisit}; {status}")
    return view("incubation-card", kind, f, summary, id=h, revisit=revisit, questions=len(qs), status=status, **{k.lower(): v for k, v in counts.items()})


def _selftest() -> bool:
    import tempfile
    ok = {}
    v = apply(PROBES["text"], today="2026-10-16")
    types = {x.get("type") for x in v["findings"]}
    ok["probe: condition ('If the nightly job fails'), number (5 bps) and absolute questions built"] = {"CONDITION", "NUMBER", "ABSOLUTE"} <= types
    ok["probe: revisit date = parked + 2 days"] = v["stats"]["revisit"] == "2026-10-18"
    p = apply("Why does the cache rebuild take 15 h? The screener reads bars. Volume spikes at the open.", today="2026-10-16", days=1)
    ok["planted: its own question is kept as OPEN"] = any(x["what"].startswith("OPEN") and "15 h" in x["what"] for x in p["findings"])
    ok["planted: key terms that never meet (cache / screener) become UNLINKED questions"] = any(
        x.get("type") == "UNLINKED" and "cache" in x["what"] for x in p["findings"])
    with tempfile.TemporaryDirectory() as d:
        cp = str(Path(d) / "card.json")
        apply(p_text := "If the feed revises bars, scores drift by 3%. Is the lag 2 bars?", today="2026-10-16", out=cp)
        same = apply(p_text, today="2026-10-18", card=cp)["stats"]["status"].startswith("UNCHANGED")
        ch = apply(p_text + " Costs must stay under 5 bps.", today="2026-10-18", card=cp)
        ok["revisit: same text is UNCHANGED, edited text lists ADDED questions"] = same and any(
            x.get("type") == "added" for x in ch["findings"])
    ok["same text gives the same card id"] = apply(PROBES["text"], today="2026-10-16")["stats"]["id"] == v["stats"]["id"]
    bad = 0
    for b in (PROBES["series"], "too short"):
        try:
            apply(b)
        except ValueError:
            bad += 1
    ok["planted bad input (series; two words) refused"] = bad == 2
    return report(ok)


def main(argv):
    return run_cli("incubation-card", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
