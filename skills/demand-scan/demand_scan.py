"""demand_scan - which skills did the user's REAL prompts actually need? (backs the demand-scan skill).

skill-finder runs need -> skill. This runs it the other way: every real the user prompt (read with prompt-genealogy's
iter_prompts) is routed through skill-finder's search, and the hits are counted per skill. Reports
  * demand     - how many real asks each skill would have served (top-k hits; top-1 hits shown too)
  * zero demand - skills no real ask ever routed to: UNREACHED - sharpen their triggers (never deleted here)
  * unserved   - asks whose best score is weak: needs no skill covers, gaps for skill-foundry
  * reach_log  - (the inward view) for each real ask, the skills that SHOULD have served it vs the skills the
                 assistant ACTUALLY reached for before the next ask (Skill tool calls + tool paths under skills/)
Prompts with fewer than `min_tokens` routable words ("go", "MORE", "yes") are not asks and are skipped.
Read-only: it never writes to the library or the transcripts. Pure stdlib + sibling skills.

    python demand_scan.py                         # real library x real prompts
    python demand_scan.py --top 3 --weak 8 --show 15 [transcripts...]
    python demand_scan.py --reach [transcripts...]   # should-vs-used per ask, reach rate, most-missed skills
    python demand_scan.py --selftest
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "skill-finder"))
sys.path.insert(0, str(SK / "prompt-genealogy"))
from find_skill import load, search, _tokens          # noqa: E402
from genealogy import iter_prompts, default_paths, redact, transcript_files, NOT_MAX, REMINDER, _text   # noqa: E402

_SKILL_PATH = re.compile(r"skills[\\/]+([a-z0-9]+(?:-[a-z0-9]+)*)[\\/]")


def scan(skills: list, prompts, top: int = 3, weak: float = 8.0, min_tokens: int = 4, max_chars: int = 1500) -> dict:
    """skills: skill-finder load() output. prompts: iterable of {ts, text, ...}. Long prompts are cut to max_chars
    so a pasted wall of text does not match everything."""
    if not skills:
        raise ValueError("empty skill library")
    demand = {s["name"]: 0 for s in skills}
    top1 = dict(demand)
    unserved, n_asks, n_skipped = [], 0, 0
    for p in prompts:
        text = p["text"][:max_chars]
        if len(set(_tokens(text))) < min_tokens:
            n_skipped += 1
            continue
        n_asks += 1
        res = search(skills, text, top)
        for i, r in enumerate(res):
            demand[r["name"]] += 1
            top1[r["name"]] += i == 0
        best = res[0]["score"] if res else 0.0
        if best < weak:
            unserved.append({"ts": p.get("ts", ""), "best": best, "best_skill": res[0]["name"] if res else None,
                             "excerpt": redact(" ".join(text.split())[:160])})
    unserved.sort(key=lambda u: (u["best"], u["ts"]))
    ranked = sorted(demand, key=lambda k: (-demand[k], -top1[k], k))
    return {"asks": n_asks, "skipped": n_skipped, "top": top, "weak": weak,
            "demand": [{"name": k, "hits": demand[k], "top1": top1[k]} for k in ranked],
            "zero_demand": sorted(k for k in demand if demand[k] == 0), "unserved": unserved}


def iter_turns(paths, names=None):
    """Yield {ts, text, used} per real the user prompt; `used` = skills the main assistant reached for before the next
    prompt (Skill tool calls, and any tool input naming a path skills/<name>/). Sidechains are ignored; when `names`
    is given, path hits are kept only for real skill names. Streams line by line."""
    for f in transcript_files(paths):
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cur = None
        with fh:
            for raw in fh:
                is_user = '"user"' in raw and '"tool_result"' not in raw
                if not is_user and '"tool_use"' not in raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("isSidechain") or rec.get("isMeta"):
                    continue
                msg = rec.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None
                if rec.get("type") == "user" and is_user:
                    text = REMINDER.sub("", _text(content)).strip()
                    if text and not text.startswith(NOT_MAX):
                        if cur:
                            yield cur
                        cur = {"ts": str(rec.get("timestamp") or "")[:16].replace("T", " "), "text": text, "used": set()}
                elif rec.get("type") == "assistant" and cur is not None and isinstance(content, list):
                    for b in content:
                        if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                            continue
                        inp = b.get("input") or {}
                        if b.get("name") == "Skill" and isinstance(inp, dict) and inp.get("skill"):
                            cur["used"].add(str(inp["skill"]).split(":")[-1])
                        for m in _SKILL_PATH.finditer(json.dumps(inp)):
                            if names is None or m.group(1) in names:
                                cur["used"].add(m.group(1))
        if cur:
            yield cur


def reach_log(skills: list, turns, top: int = 3, min_tokens: int = 4, max_chars: int = 1500) -> dict:
    """Should-vs-used per real ask: reached = one of the top-k routed skills was actually used."""
    if not skills:
        raise ValueError("empty skill library")
    rows, missed, used_count = [], {}, {}
    for t in turns:
        text = t["text"][:max_chars]
        if len(set(_tokens(text))) < min_tokens:
            continue
        should = [r["name"] for r in search(skills, text, top)]
        reached = bool(set(should) & t["used"])
        for u in t["used"]:
            used_count[u] = used_count.get(u, 0) + 1
        if should and not reached:
            missed[should[0]] = missed.get(should[0], 0) + 1
        rows.append({"ts": t["ts"], "should": should, "used": sorted(t["used"]), "reached": reached,
                     "excerpt": redact(" ".join(text.split())[:120])})
    n = len(rows)
    return {"asks": n, "reached": sum(r["reached"] for r in rows), "used_any": sum(bool(r["used"]) for r in rows),
            "reach_rate": (sum(r["reached"] for r in rows) / n) if n else 0.0,
            "most_missed": sorted(missed.items(), key=lambda kv: (-kv[1], kv[0])),
            "most_used": sorted(used_count.items(), key=lambda kv: (-kv[1], kv[0])), "rows": rows}


def render_reach(res: dict, show: int = 10) -> str:
    out = [f"# reach-log: {res['asks']} real asks; a top-k skill was actually used on {res['reached']} "
           f"({res['reach_rate']:.1%}); any skill used on {res['used_any']}"]
    out.append("## most-missed (top-1 route never reached for)")
    out += [f"{c:5d}  {n}" for n, c in res["most_missed"][:show]]
    out.append("## most-used (reached for, routed or not)")
    out += [f"{c:5d}  {n}" for n, c in res["most_used"][:show]]
    return "\n".join(out)


def render(res: dict, show: int = 10) -> str:
    out = [f"# demand-scan: {res['asks']} real asks routed (top-{res['top']}), {res['skipped']} non-asks skipped"]
    out.append("## top demand (hits = asks with the skill in the top-k; top1 = asks where it ranked first)")
    out += [f"{d['hits']:5d} {d['top1']:5d}  {d['name']}" for d in res["demand"][:show]]
    z = res["zero_demand"]
    out.append(f"## zero demand: {len(z)} skill(s) UNREACHED by any real ask - sharpen their triggers, not deletions")
    out.append(", ".join(z[:show * 4]) + (f" ... +{len(z) - show * 4}" if len(z) > show * 4 else ""))
    out.append(f"## unserved: {len(res['unserved'])} ask(s) with best score < {res['weak']} - gaps for skill-foundry")
    out += [f"{u['best']:6.2f} {u['ts']} (best: {u['best_skill']}) \"{u['excerpt']}\"" for u in res["unserved"][:show]]
    return "\n".join(out)


def _selftest() -> bool:
    import shutil
    import tempfile
    rng = random.Random("demand-scan/selftest")
    ok = {}
    tmp = Path(tempfile.mkdtemp(prefix="demand_scan_selftest_"))
    try:
        lib = tmp / "lib"
        for name, desc in [
                ("hurst", "Classify a time series as trending, mean-reverting or a random walk via the Hurst exponent."),
                ("token-bucket", "Throttle alerts with a token bucket and cooldown to rate-limit noisy alerts."),
                ("convex-hull", "Compute the minimal convex boundary of 2-D points."),
                ("drawdown-stats", "the user drawdown, recovery time and ulcer index of an equity curve.")]:
            (lib / name).mkdir(parents=True)
            (lib / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n", encoding="utf-8")
        before = sorted(str(p) for p in lib.rglob("*"))

        def rec(text, ts):
            return json.dumps({"type": "user", "timestamp": ts, "sessionId": "s1", "message": {"content": text}})
        lines = [rec("is the BTC series trending or mean reverting, check the hurst exponent", "2026-10-01T10:00:00Z"),
                 rec("does this spread look mean reverting or a random walk to you", "2026-10-02T10:00:00Z"),
                 rec("my alerts fire too often, throttle them with a cooldown please", "2026-10-03T10:00:00Z"),
                 rec("how deep was the max drawdown of the equity curve and its recovery", "2026-10-04T10:00:00Z"),
                 rec("bake sourdough bread for the family weekend picnic", "2026-10-05T10:00:00Z"),
                 rec("go", "2026-10-06T10:00:00Z"),
                 "{ broken json line", json.dumps(["not", "a", "record"])]
        (tmp / "t.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        skills = load(lib)
        prompts = list(iter_prompts([tmp / "t.jsonl", tmp / "missing.jsonl"]))
        res = scan(skills, prompts, top=1, weak=1.0)       # a 4-skill library has small idf: scale the bar
        d = {x["name"]: x for x in res["demand"]}
        ok["real asks route to the skills that serve them (hurst 2, token-bucket 1, drawdown-stats 1)"] = (
            d["hurst"]["hits"] == 2 and d["token-bucket"]["hits"] == 1 and d["drawdown-stats"]["hits"] == 1)
        ok["a skill no ask needed is listed as zero demand (convex-hull)"] = res["zero_demand"] == ["convex-hull"]
        ok["an ask no skill covers is reported as unserved (the sourdough ask)"] = (
            [u["excerpt"][:14] for u in res["unserved"]] == ["bake sourdough"])
        ok["a non-ask ('go') is skipped, not counted as unserved; broken lines and a missing file are skipped"] = (
            res["skipped"] == 1 and res["asks"] == 5)
        shuffled = prompts[:]
        rng.shuffle(shuffled)
        r2 = scan(skills, shuffled, top=1, weak=1.0)
        ok["prompt order does not change demand, zero demand or the unserved set"] = (
            r2["demand"] == res["demand"] and r2["zero_demand"] == res["zero_demand"]
            and sorted(u["ts"] for u in r2["unserved"]) == sorted(u["ts"] for u in res["unserved"]))
        r3 = scan(skills, prompts, top=3)
        ok["top-k demand >= top-1 demand for every skill, and top1 <= hits"] = all(
            a["hits"] >= d[a["name"]]["hits"] and a["top1"] <= a["hits"] for a in r3["demand"])
        bad = False
        try:
            scan([], prompts)
        except ValueError:
            bad = True
        ok["planted bad input: an empty library is rejected"] = bad
        out = render(res)
        ok["read-only: the library is untouched, and the report names UNREACHED skills, not deletions"] = (
            sorted(str(p) for p in lib.rglob("*")) == before and "UNREACHED" in out)

        def use(skill_or_path, ts):
            inp = {"skill": skill_or_path} if "/" not in skill_or_path else {"command": f"python {skill_or_path} --x"}
            return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": [
                {"type": "tool_use", "name": "Skill" if "/" not in skill_or_path else "Bash", "input": inp}]}})
        side = json.dumps({"type": "assistant", "isSidechain": True, "message": {"content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "convex-hull"}}]}})
        (tmp / "r.jsonl").write_text("\n".join([
            lines[0], use("hurst", "2026-10-01T10:01:00Z"),
            lines[2], use("C:/Users/x/.claude/skills/token-bucket/bucket.py", "2026-10-03T10:01:00Z"),
            lines[3], side, use("plugin:convex-hull", "2026-10-04T10:01:00Z")]) + "\n", encoding="utf-8")
        rl = reach_log(skills, iter_turns([tmp / "r.jsonl"], names={s["name"] for s in skills}), top=1)
        ok["reach_log: Skill call and a skills/<name>/ path count as reached; a sidechain use does not; "
           "a wrong skill is a miss"] = (
            rl["asks"] == 3 and rl["reached"] == 2 and rl["most_missed"] == [("drawdown-stats", 1)]
            and dict(rl["most_used"]).get("convex-hull") == 1)
    except Exception as e:
        ok[f"selftest crashed: {type(e).__name__}: {e}"] = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def _opt(argv: list, name: str, default):
    if name in argv:
        i = argv.index(name)
        val = type(default)(argv[i + 1])
        del argv[i:i + 2]
        return val
    return default


def main(argv) -> int:
    argv = list(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    as_json = "--json" in argv
    reach = "--reach" in argv
    argv = [a for a in argv if a not in ("--json", "--real", "--reach")]
    top, weak, show = _opt(argv, "--top", 3), _opt(argv, "--weak", 8.0), _opt(argv, "--show", 10)
    if reach:
        skills = load(SK)
        res = reach_log(skills, iter_turns(argv or default_paths(), names={s["name"] for s in skills}), top=top)
        print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1) if as_json else render_reach(res, show))
        return 0
    res = scan(load(SK), iter_prompts(argv or default_paths()), top=top, weak=weak)
    print(json.dumps(res, indent=1) if as_json else render(res, show))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
