"""genealogy - when did the user first ask for X, and how did the idea grow? (backs the prompt-genealogy skill).

Scans Claude Code session transcripts (JSONL) for the user's own typed prompts that match a theme regex and prints a
dated timeline, earliest first, with a short quoted excerpt around each match, then the first appearance of every
keyword (the top-level `|` alternatives of the pattern). Excerpts are redacted with transcript-miner's `redact`.

    python genealogy.py "sex|reproduc|mutation"                      # all transcripts under ~/.claude/projects
    python genealogy.py "living prompt" a.jsonl folder/ --max 40 --context 100
    python genealogy.py --selftest

A "the user prompt" is a user record (type user, not a tool result, not a sidechain) whose text, after stripping
system reminders, does not start with "<", "Another Claude session", "This session is being continued" or
"Base directory". Resumed sessions copy old records, so prompts are de-duplicated on (minute, text).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "transcript-miner" / "scripts"))
from digest import redact  # noqa: E402  (sibling skill: one redaction rule for every transcript tool)

NOT_MAX = ("<", "Another Claude session", "This session is being continued", "Base directory")
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def default_paths() -> list:
    return [Path.home() / ".claude" / "projects"]


def transcript_files(paths) -> list:
    out = []
    for p in map(Path, paths):
        out.extend(sorted(p.rglob("*.jsonl")) if p.is_dir() else [p] if p.exists() else [])
    return out


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def iter_prompts(paths):
    """Yield {ts, session, file, text} for every real the user prompt, in file order, de-duplicated across files."""
    seen = set()
    for f in transcript_files(paths):
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for raw in fh:
                if '"user"' not in raw or '"tool_result"' in raw:     # cheap skip before parsing huge lines
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "user" or rec.get("isSidechain") or rec.get("isMeta"):
                    continue
                msg = rec.get("message") or {}
                text = REMINDER.sub("", _text(msg.get("content") if isinstance(msg, dict) else None)).strip()
                if not text or text.startswith(NOT_MAX):
                    continue
                ts = str(rec.get("timestamp") or "")[:16].replace("T", " ")
                key = (ts, text[:300])
                if key in seen:
                    continue
                seen.add(key)
                yield {"ts": ts, "session": str(rec.get("sessionId") or f.stem)[:8], "file": f.name, "text": text}


def keywords(pattern: str) -> list:
    """Top-level `|` alternatives of a regex (a `|` inside (...) or [...] does not split)."""
    out, cur, depth, i = [], "", 0, 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            cur += pattern[i:i + 2]
            i += 2
            continue
        depth += c in "([" and 1 or (-1 if c in ")]" else 0)
        if c == "|" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return [k for k in out if k]


def excerpt(text: str, m: re.Match, width: int) -> str:
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    s = " ".join(text[a:b].split())
    return ("..." if a else "") + redact(s) + ("..." if b < len(text) else "")


def genealogy(pattern: str, paths, context: int = 120) -> dict:
    rx = re.compile(pattern, re.I)
    kws = {k: re.compile(k, re.I) for k in keywords(pattern)}
    hits, first = [], {k: None for k in kws}
    for p in iter_prompts(paths):
        m = rx.search(p["text"])
        if not m:
            continue
        found = [k for k, r in kws.items() if r.search(p["text"])]
        hit = {**p, "keywords": found, "excerpt": excerpt(p["text"], m, context)}
        hit.pop("text")
        hits.append(hit)
    hits.sort(key=lambda h: h["ts"])
    for h in hits:
        for k in h["keywords"]:
            if first[k] is None:
                first[k] = h
    return {"pattern": pattern, "hits": hits, "first": first,
            "sessions": len({h["session"] for h in hits})}


def render(res: dict, limit: int = 60) -> str:
    hits = res["hits"]
    lines = [f"# genealogy of /{res['pattern']}/: {len(hits)} prompt(s) in {res['sessions']} session(s)"
             + (f", {hits[0]['ts'][:10]} -> {hits[-1]['ts'][:10]}" if hits else "")]
    for h in hits[:limit] if limit else hits:
        lines.append(f"{h['ts']} [{h['session']}] ({', '.join(h['keywords']) or '-'}) \"{h['excerpt']}\"")
    if limit and len(hits) > limit:
        lines.append(f"... +{len(hits) - limit} later prompt(s) (raise --max)")
    lines.append("## first appearance per keyword")
    for k, h in res["first"].items():
        lines.append(f"{k:14s} " + (f"{h['ts']} [{h['session']}] \"{h['excerpt'][:160]}\"" if h else "never"))
    return "\n".join(lines)


MEME_STOP = set("the a an and or of to in on for with is are be it this that my our your i we you do does how what which "
                "when where why can should would could from by as at into about than then them they there was were "
                "will just so if not no but all any some its it's i'm i'll let me us he she his her have has had "
                "been being am also too very here now up out over more most other such only own same few".split())


def iter_assistant(paths):
    """Yield {ts, session, file, text} for every main-thread assistant text record (no tool calls, no sidechains)."""
    seen = set()
    for f in transcript_files(paths):
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for raw in fh:
                if '"assistant"' not in raw or '"text"' not in raw:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "assistant" or rec.get("isSidechain"):
                    continue
                msg = rec.get("message") or {}
                text = _text(msg.get("content") if isinstance(msg, dict) else None).strip()
                if not text:
                    continue
                ts = str(rec.get("timestamp") or "")[:16].replace("T", " ")
                key = (ts, text[:300])
                if key in seen:
                    continue
                seen.add(key)
                yield {"ts": ts, "session": str(rec.get("sessionId") or f.stem)[:8], "file": f.name, "text": text}


def ngrams(text: str, nmin: int = 2, nmax: int = 4) -> set:
    """Word n-grams minus stopword junk: never ending on a stopword, never starting on one except 'the'."""
    toks = re.findall(r"[a-z][a-z0-9'-]*", text.lower())
    out = set()
    for n in range(nmin, nmax + 1):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if g[-1] in MEME_STOP or (g[0] in MEME_STOP and g[0] != "the"):
                continue
            out.add(" ".join(g))
    return out


def memes(paths, min_adoptions: int = 1, top: int = 50, max_chars: int = 4000) -> list:
    """Memes (merged from meme-tracker): phrases that move between the user and Claude. Candidates are n-grams the user used at
    least once (keeps memory bounded on huge assistant text); every turn of both speakers is replayed in time order.
    Per phrase: who used it first, when the OTHER speaker first adopted it, and how many of the adopter's turns used
    it from then on. A shorter phrase with exactly the same history as a longer one containing it is dropped."""
    events = [(p["ts"], "max", p["session"], ngrams(p["text"][:max_chars])) for p in iter_prompts(paths)]
    vocab = set().union(*(e[3] for e in events)) if events else set()
    events += [(a["ts"], "claude", a["session"], ngrams(a["text"][:max_chars]) & vocab) for a in iter_assistant(paths)]
    events.sort(key=lambda e: (e[0], e[1]))
    st = {}
    for ts, who, sess, grams in events:
        for g in grams:
            s = st.get(g)
            if s is None:
                st[g] = {"phrase": g, "coined_by": who, "coined_ts": ts, "coined_session": sess,
                         "adopted_ts": None, "adopted_session": None, "adoptions": 0}
            elif who != s["coined_by"]:
                if s["adopted_ts"] is None:
                    s["adopted_ts"], s["adopted_session"] = ts, sess
                s["adoptions"] += 1
    rows = [s for s in st.values() if s["adopted_ts"] and s["adoptions"] >= min_adoptions]
    sig = {}
    for s in rows:
        sig.setdefault((s["coined_by"], s["coined_ts"], s["adopted_ts"], s["adoptions"]), []).append(s["phrase"])
    keep = []
    for s in rows:
        same = sig[(s["coined_by"], s["coined_ts"], s["adopted_ts"], s["adoptions"])]
        if not any(o != s["phrase"] and f" {s['phrase']} " in f" {o} " for o in same):
            keep.append(s)
    keep.sort(key=lambda s: (-s["adoptions"], s["coined_ts"], s["phrase"]))
    return keep[:top] if top else keep


def render_memes(rows: list) -> str:
    lines = [f"# {len(rows)} shared phrase(s): coined by -> adopted by the other speaker"]
    for s in rows:
        other = "max" if s["coined_by"] == "claude" else "claude"
        lines.append(f"{s['adoptions']:4d}x  \"{redact(s['phrase'])}\"  {s['coined_by']} {s['coined_ts']} "
                     f"-> {other} {s['adopted_ts']}")
    return "\n".join(lines)


def _selftest() -> bool:
    """Synthetic temp transcripts only - never reads real ones."""
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="genealogy_selftest_"))
    key = "sk-" + "Zq" * 10
    checks = {}

    def rec(text, ts, **kw):
        r = {"type": "user", "timestamp": ts, "sessionId": kw.pop("sid", "s1aaaaaaaa"),
             "message": {"role": "user", "content": text}}
        r.update(kw)
        return json.dumps(r)
    try:
        a = [rec("let the prompts have sex and breed", "2026-10-09T10:00:00Z"),
             rec([{"type": "text", "text": "<system-reminder>sex hidden</system-reminder>try a mutation pass"}],
                 "2026-10-08T09:00:00Z"),
             rec("<command-name>/x</command-name> sex", "2026-10-07T09:00:00Z"),
             rec("Another Claude session says: sex", "2026-10-07T09:01:00Z"),
             rec("Base directory for this skill: sex", "2026-10-07T09:02:00Z"),
             rec("This session is being continued ... sex", "2026-10-07T09:03:00Z"),
             rec("sidechain sex", "2026-10-07T09:04:00Z", isSidechain=True),
             json.dumps({"type": "user", "timestamp": "2026-10-07T09:05:00Z",
                         "message": {"content": [{"type": "tool_result", "content": "sex"}]}}),
             "{ not json at all sex",
             json.dumps(["a", "list", "sex"])]
        b = [rec(f"reproduction with key {key} please", "2026-10-10T11:00:00Z", sid="s2bbbbbbbb"),
             rec("let the prompts have sex and breed", "2026-10-09T10:00:30Z")]       # resumed copy -> dup
        (tmp / "a.jsonl").write_text("\n".join(a) + "\n", encoding="utf-8")
        (tmp / "sub").mkdir()
        (tmp / "sub" / "b.jsonl").write_text("\n".join(b) + "\n", encoding="utf-8")
        ps = list(iter_prompts([tmp]))
        checks["only real the user prompts survive (reminder/command/peer/skill/continued/sidechain/tool_result dropped)"] = (
            sorted(p["text"][:9] for p in ps) == ["let the p", "reproduct", "try a mut"])
        checks["planted bad input (broken JSON, non-dict record, missing path) is skipped, not fatal"] = (
            len(list(iter_prompts([tmp / "nope.jsonl"]))) == 0 and len(ps) == 3)
        res = genealogy("sex|reproduc|mutation|flora", [tmp], context=40)
        checks["timeline is earliest first across files"] = [h["ts"][:10] for h in res["hits"]] == [
            "2026-10-08", "2026-10-09", "2026-10-10"]
        checks["first appearance per keyword, 'never' for an absent one"] = (
            res["first"]["mutation"]["ts"].startswith("2026-10-08") and res["first"]["sex"]["ts"].startswith(
                "2026-10-09") and res["first"]["flora"] is None and "flora          never" in render(res))
        out = render(res)
        checks["planted secret is redacted in excerpts"] = key not in out and "<redacted>" in out
        checks["keywords split only at top-level |"] = keywords(r"a(b|c)|[x|y]|d\|e") == ["a(b|c)", "[x|y]", r"d\|e"]
        checks["--max caps the timeline and says how many were cut"] = "+2 later prompt(s)" in render(res, limit=1)
        mt = tmp / "memes"
        mt.mkdir()

        def asst(text, ts):
            return json.dumps({"type": "assistant", "timestamp": ts, "sessionId": "s3cccccccc",
                               "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})
        (mt / "m.jsonl").write_text("\n".join([
            asst("I will claim the pen before landing", "2026-10-08T10:00:00Z"),
            rec("ok who has the pen right now", "2026-10-09T10:00:00Z"),
            asst("still holding the pen", "2026-10-09T10:01:00Z"),
            rec("release the pen when done", "2026-10-10T10:00:00Z"),
            json.dumps({"type": "assistant", "timestamp": "2026-10-07T10:00:00Z", "isSidechain": True,
                        "message": {"content": [{"type": "text", "text": "the pen early in a sidechain"}]}})]) + "\n",
            encoding="utf-8")
        mm = {m["phrase"]: m for m in memes([mt])}
        pen = mm.get("the pen", {})
        checks["memes: Claude coins 'the pen', the user adopts it (first adoption + count), sidechain ignored"] = (
            pen.get("coined_by") == "claude" and pen.get("coined_ts", "").startswith("2026-10-08")
            and pen.get("adopted_ts", "").startswith("2026-10-09") and pen.get("adoptions") == 2)
    except Exception as e:
        checks[f"selftest crashed: {type(e).__name__}: {e}"] = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(checks.values())


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
        sys.stdout.reconfigure(errors="replace")       # Windows cp1252 console vs arrows/emoji in prompts
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if argv[0] == "--memes":
        top = _opt(argv, "--max", 50)
        rows = memes(argv[1:] or default_paths(), top=top)
        print(json.dumps(rows, indent=1) if as_json else render_memes(rows))
        return 0
    limit = _opt(argv, "--max", 60)
    context = _opt(argv, "--context", 120)
    pattern, paths = argv[0], argv[1:] or default_paths()
    res = genealogy(pattern, paths, context)
    print(json.dumps(res, indent=1) if as_json else render(res, limit))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
