"""dream-recombination: pair salient terms from DIFFERENT past documents that never appeared together, then grade awake.

python dream_pairs.py FILE_OR_DIR ... [--top 20] [--per-doc 15] [--seed 7] [--max-mb 4] [--json]
python dream_pairs.py --selftest

Dream: each document (a transcript, a note, a prompts file; .jsonl read as text) keeps its top --per-doc terms
by TF-IDF. Pairs are drawn from two different documents with probability proportional to salience, seeded.
Awake grade, for each pair:
  co   documents containing BOTH terms (a pair with co > 0 is KNOWN and dropped - it is not a dream)
  bridges  terms that co-occur with both in some document (a path that makes the pairing plausible)
  score = salience_a * salience_b * (1 + ln(1 + bridges)); bridge terms listed rarest first (most specific)
Labels: BRIDGED (unseen pair, at least one bridge) or WILD (unseen, no bridge). Files are read up to --max-mb each.
"""
import argparse, json, math, random, re, sys, tempfile
from pathlib import Path

WORD = re.compile(r"[a-z][a-z0-9]{3,}")
STOP = set("""this that with from have will would could should there their them they then than what when where which
while about into your just like also been were does done make made more most much need only over some such sure take
very want here each other same still these those because after before being both every first last next none true false
null text type content role user assistant message tool result json http https""".split())


def docs_from(paths, max_mb=4):
    out = []
    for p in paths:
        p = Path(p)
        files = sorted(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in {".md", ".txt", ".jsonl", ".json"}) if p.is_dir() else [p]
        for f in files:
            with open(f, "rb") as fh:
                t = fh.read(int(max_mb * 1024 * 1024)).decode("utf-8", "replace")
            out.append((f"{f.parent.name}/{f.name}" if p.is_dir() else f.name, t))
    return out


def terms(text):
    return [w for w in WORD.findall(text.lower()) if w not in STOP and not w.isdigit()]


def dream(docs, per_doc=15, top=20, seed=7, draws=4000):
    sets, tfs = [], []
    for _, t in docs:
        ws = terms(t)
        tf = {}
        for w in ws:
            tf[w] = tf.get(w, 0) + 1
        tfs.append(tf)
        sets.append(set(tf))
    N = len(docs)
    df = {}
    for s in sets:
        for w in s:
            df[w] = df.get(w, 0) + 1
    sal = []
    for tf in tfs:
        tot = sum(tf.values()) or 1
        sc = {w: (c / tot) * math.log((N + 1) / df[w]) for w, c in tf.items() if df[w] < N or N == 1}
        best = sorted(sc.items(), key=lambda x: -x[1])[:per_doc]
        mx = best[0][1] if best else 1.0
        sal.append({w: v / mx for w, v in best})
    rng = random.Random(seed)
    seen, out = set(), []
    pool = [(i, w, v) for i, s in enumerate(sal) for w, v in s.items()]
    if len({i for i, _, _ in pool}) < 2:
        return []
    weights = [v for _, _, v in pool]
    for _ in range(draws):
        (i, a, va), (j, b, vb) = rng.choices(pool, weights=weights, k=2)
        if i == j or a == b:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        co = sum(1 for s in sets if a in s and b in s)
        if co:
            continue
        with_a = set().union(*[s for s in sets if a in s]) - {a, b}
        with_b = set().union(*[s for s in sets if b in s]) - {a, b}
        br = sorted(with_a & with_b, key=lambda w: (df[w], w))
        out.append({"pair": key, "from": (docs[i][0], docs[j][0]) if key[0] == a else (docs[j][0], docs[i][0]),
                    "bridges": len(br), "bridge_terms": br[:3], "score": round(va * vb * (1 + math.log1p(len(br))), 4),
                    "label": "BRIDGED" if br else "WILD"})
    out.sort(key=lambda x: (-x["score"], x["pair"]))
    return out[:top]


def _selftest():
    ok = True

    def ck(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + name)

    docs = [("s1.md", "volatility regime regime regime screener breakout breakout volume"),
            ("s2.md", "kalshi settlement settlement calibration calibration volume weather"),
            ("s3.md", "regime calibration ledger ledger forward forward"),
            ("s4.md", "mailbox mailbox issue issue cloud")]
    r = dream(docs, per_doc=6, top=50, seed=1)
    pairs = {x["pair"]: x for x in r}
    ck("dreams produced", len(r) > 3)
    ck("no KNOWN pair (co-occurring terms) survives", all(not any(set(x["pair"]) <= set(terms(t)) for _, t in docs) for x in r))
    ck("terms paired across different documents", all(x["from"][0] != x["from"][1] for x in r))
    br = pairs.get(("breakout", "settlement"))
    ck("breakout x settlement is BRIDGED via volume", br is not None and br["label"] == "BRIDGED" and "volume" in br["bridge_terms"])
    w = [x for x in r if "mailbox" in x["pair"] or "issue" in x["pair"]]
    ck("isolated document gives WILD pairs", w and all(x["label"] == "WILD" for x in w))
    ck("same seed same dream", dream(docs, 6, 50, 1) == r)
    ck("one document cannot dream", dream(docs[:1]) == [])
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "a.jsonl").write_text('{"text": "alpha beta gamma"}\n', encoding="utf-8")
        ck("directory read with byte cap", docs_from([td], max_mb=4 / 1048576)[0][1] == '{"te')
    return ok


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--per-doc", type=int, default=15)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-mb", type=float, default=4)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return 0 if _selftest() else 1
    if not a.paths:
        ap.error("give files or directories")
    r = dream(docs_from(a.paths, a.max_mb), a.per_doc, a.top, a.seed)
    if a.json:
        print(json.dumps(r, indent=1))
        return 0
    for x in r:
        print(f"{x['score']:.3f} {x['label']:<7} {x['pair'][0]} x {x['pair'][1]}   ({x['from'][0]} | {x['from'][1]})"
              + (f"  via {', '.join(x['bridge_terms'])}" if x["bridge_terms"] else ""))
    print(f"{len(r)} dream pairings (seed {a.seed}); grade each awake before acting on it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
