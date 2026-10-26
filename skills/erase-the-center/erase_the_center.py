"""erase_the_center - remove the most central topic and list what is left to say (backs erase-the-center).

Units are sentences (or plan steps). Each unit's keywords are its content words (stopwords and words under 3
letters dropped, discourse words such as obviously/clearly/basically/really/just dropped, a plural -s folded). Two
keywords are linked when they share a unit; the CENTER is the keyword with the widest sentence span (in the most
units), ties broken by the most distinct partner words (co-occurrence degree), then first seen. A discourse word is
never a keyword, so it is never the center. The lens erases every unit that carries the
center and reports the share of the text erased, the units left (what there is still to say), the new center of
what is left, and the words that vanish with the center because they never appear without it.

    python erase_the_center.py <file|text|plan> [--opt center=word] [--json]
    python erase_the_center.py --selftest
"""
from __future__ import annotations

import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SK / "pov-core"))
from pov_core import PROBES, STOP, load_subject, report, run_cli, sentences, view, words  # noqa: E402

KINDS = {"text", "plan"}
# Stopword-like discourse words: they colour a sentence but are never its topic, so they are never keywords
# (and so never the center, even when the tie-break would favour them).
DISCOURSE = set("""obviously clearly basically really just actually simply literally honestly certainly definitely
surely totally truly quite rather pretty somehow anyway anyhow etc maybe perhaps probably""".split())


def _kw(s):
    """Unique keywords in text order (a list, so ties break by first appearance, never by set hashing)."""
    return list(dict.fromkeys((w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
                              for w in words(s) if w not in STOP and w not in DISCOURSE and len(w) > 2))


def center_of(units):
    order, partners, count = [], {}, {}
    for u in units:
        for w in u:
            if w not in partners:
                order.append(w)
            partners.setdefault(w, set()).update(set(u) - {w})
            count[w] = count.get(w, 0) + 1
    if not order:
        return None, 0
    c = max(order, key=lambda w: (count[w], len(partners[w]), -order.index(w)))
    return c, len(partners[c])


def apply(subject, kind=None, center=None, **opts) -> dict:
    k, val = load_subject(subject, kind)
    if k not in KINDS:
        raise ValueError(f"erase-the-center reads text or a plan, not {k}")
    units_txt = list(val) if k == "plan" else sentences(val)
    units = [_kw(u) for u in units_txt]
    if sum(bool(u) for u in units) < 2:
        raise ValueError("need 2+ units with content words")
    c, deg = (center, None) if center else center_of(units)
    gone = [i for i, u in enumerate(units) if c in u]
    left = [i for i in range(len(units)) if i not in gone]
    survivors = set().union(*(units[i] for i in left)) if left else set()
    vanished = sorted(set().union(*(units[i] for i in gone)) - survivors - {c})
    nc, _ = center_of([units[i] for i in left])
    findings = [{"what": f"CENTER '{c}'" + (f" ({deg} partner words)" if deg is not None else " (given)") +
                         f" - erasing it removes {len(gone)} of {len(units)} units", "center": c, "erased": len(gone)},
                {"what": f"vanish with it: {', '.join(vanished) or 'nothing'}", "vanished": vanished},
                {"what": f"new center of what is left: {nc or 'none'}", "new_center": nc}]
    findings += [{"what": f"left to say: {units_txt[i][:120]}", "left": units_txt[i]} for i in left]
    return view("erase-the-center", k, findings, f"without '{c}' {len(left)} of {len(units)} units remain, "
                f"{len(vanished)} words vanish, new center '{nc}'", center=c, remaining=len(left), new_center=nc)


def _selftest() -> bool:
    ok = {}
    v = apply(PROBES["text"])
    ok["probe text: a center is found and some units remain"] = v["stats"]["center"] and 0 < v["stats"]["remaining"] < 7
    p = apply(PROBES["plan"])
    ok["probe plan: 6 steps, erasing the center leaves 5"] = p["stats"]["remaining"] == 5
    t = ("The cache feeds the screener. The cache is rebuilt nightly by the scheduler. "
         "A stale cache breaks the forward record. Lunch was good.")
    c = apply(t)
    ok["planted: the cache is the center and only lunch is left"] = c["stats"]["center"] == "cache" and c["stats"]["remaining"] == 1
    ok["planted: scheduler and screener vanish with the cache"] = {"scheduler", "screener"} <= set(c["findings"][1]["vanished"])
    d = apply("Obviously the cache matters. Obviously the screener reads it. The cache is stale.")
    ok["planted: a discourse word (obviously) that wins on span and degree is never the center"] = (
        d["stats"]["center"] == "cache" and v["stats"]["center"] not in DISCOURSE)
    ok["center= forces the erased word"] = apply(t, center="lunch")["stats"]["remaining"] == 3
    try:
        apply(PROBES["series"])
        ok["planted bad input (a series) is refused"] = False
    except ValueError:
        ok["planted bad input (a series) is refused"] = True
    return report(ok)


def main(argv):
    return run_cli("erase-the-center", apply, argv, _selftest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
