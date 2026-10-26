"""Claude Code transcripts -> readable digests a fresh reader can get through in full.

    python digest.py <transcript.jsonl | folder> <out folder> [--chunk 180000] [--since 2026-10-06]

For each transcript: the user's typed prompts verbatim (### MAX <time>), the assistant's visible text (CLAUDE:), and each tool
call cut to one line ([tool Name: description]). Dropped: tool results, system reminders, task notices. Key-like strings
are redacted; slash commands are collapsed to `/name args` plus what was typed after. Each digest is split into chunks of
about --chunk characters (default fits one reader's context with room to think) and an INDEX.md lists them with dates.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SECRET = re.compile(r"\b(?:PK|AK|sk-|ghp_|xox[bp]-)[A-Za-z0-9_-]{12,}|\b[A-Za-z0-9]{32,}\b")
# a value assigned to a key-like name, whatever its length: a command cut at 120 characters can leave half a secret
# (found 2026-10-13: 29 characters of an Alpaca secret in a digest, from a command the guard had blocked)
ASSIGNED = re.compile(r"(?i)\b(\w*(?:key|secret|token|passw(?:or)?d|apikey)\w*['\"]?\s*[=:]\s*['\"]?)([^'\"\s;,)]{4,})")
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def redact(text: str) -> str:
    return SECRET.sub("<redacted>", ASSIGNED.sub(lambda m: m.group(1) + "<redacted>", text))


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def collapse_command(t: str) -> str:
    name = re.search(r"<command-name>(.*?)</command-name>", t, flags=re.S)
    if not name:
        return t
    args = re.search(r"<command-args>(.*?)</command-args>", t, flags=re.S)
    tail = re.split(r"^ARGUMENTS: .*$", t, flags=re.M)
    after = tail[-1].strip() if len(tail) > 1 else ""
    return f"{name.group(1).strip()} {args.group(1).strip() if args else ''}".strip() + ("\n\n" + after if after else "")


def entries(path: Path) -> list[tuple[str, str]]:
    """(timestamp, rendered line) in transcript order."""
    out: list[tuple[str, str]] = []
    for raw in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        msg = rec.get("message") or {}
        content, ts = msg.get("content"), (rec.get("timestamp") or "")[:16]
        if msg.get("role") == "user":
            if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            t = REMINDER.sub("", text_of(content)).strip()
            if not t or "<task-notification>" in t or t.startswith("This session is being continued"):
                continue
            out.append((ts, f"\n### MAX ({ts})\n{redact(collapse_command(t))[:8000]}\n"))
        elif msg.get("role") == "assistant" and isinstance(content, list):
            for b in content:
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append((ts, f"\nCLAUDE: {redact(b['text'].strip())[:4000]}\n"))
                elif b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    what = inp.get("description") or inp.get("file_path") or str(inp.get("command", ""))[:100]
                    out.append((ts, f"  [tool {b.get('name')}: {redact(str(what))[:120]}]"))
    return out


def chunks(lines: list[tuple[str, str]], size: int) -> list[list[tuple[str, str]]]:
    out: list[list[tuple[str, str]]] = [[]]
    used = 0
    for item in lines:
        if used + len(item[1]) > size:                # an empty first chunk is dropped below
            out.append([])
            used = 0
        out[-1].append(item)
        used += len(item[1]) + 1
    return [c for c in out if c]


def _selftest() -> bool:
    """Hermetic: a small synthetic JSONL transcript in a temp dir (never a real one). One PASS/FAIL line per check."""
    import contextlib
    import io
    import shutil
    import tempfile

    key = "sk-" + "Q8" * 10                                 # planted key-like strings that must never reach a digest
    short = "zz99" * 3
    name = "DB_" + "PASS" + "WORD"

    def rec(role, content, ts):
        return json.dumps({"timestamp": ts, "message": {"role": role, "content": content}})

    lines = [
        rec("user", "an old prompt from before --since", "2026-10-05T09:00:00Z"),
        rec("user", f"<system-reminder>hidden</system-reminder>please fix it, key {key}", "2026-10-06T10:00:00Z"),
        rec("assistant", [{"type": "text", "text": f"Fixing. I set {name}={short} for the test."},
                          {"type": "tool_use", "id": "toolu_1", "name": "Bash",
                           "input": {"command": "run.bat", "description": "run the check"}},
                          {"type": "tool_use", "id": "toolu_2", "name": "Edit", "input": {"file_path": "C:/x/a.py"}}],
            "2026-10-06T10:01:00Z"),
        rec("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "TOOL OUTPUT SHOULD NOT APPEAR"}],
            "2026-10-06T10:02:00Z"),
        rec("user", "<task-notification><task-id>b1</task-id></task-notification>", "2026-10-06T10:03:00Z"),
        rec("user", "This session is being continued from a previous conversation", "2026-10-06T10:04:00Z"),
        "{ broken json line",
        rec("user", "<command-name>/demo</command-name><command-args>go</command-args>\nBODY OF SKILL\nARGUMENTS: go\nthen this",
            "2026-10-06T10:05:00Z"),
    ]
    tmp = Path(tempfile.mkdtemp(prefix="digest_selftest_"))
    checks: dict[str, bool] = {}
    try:
        src = tmp / "in"
        src.mkdir()
        (src / "abcdef1234.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        got = entries(src / "abcdef1234.jsonl")
        texts = [t for _, t in got]
        checks["entries: typed prompts and visible text kept; tool results, notices, continuations dropped"] = (
            len(got) == 6 and sum(t.startswith("\n### MAX") for t in texts) == 3
            and not any("TOOL OUTPUT" in t or "task-notification" in t or "being continued" in t for t in texts))
        checks["entries: reminders stripped, slash command collapsed to '/demo go' + typed tail"] = (
            "hidden" not in "".join(texts) and "BODY OF SKILL" not in "".join(texts)
            and any("/demo go\n\nthen this" in t for t in texts))
        checks["entries: each tool call cut to one line"] = (
            "  [tool Bash: run the check]" in texts and "  [tool Edit: C:/x/a.py]" in texts)
        checks["redact: planted long key and short value assigned to a key name are redacted"] = (
            redact(f"k {key}") == "k <redacted>" and redact(f"{name}={short}") == f"{name}=<redacted>")
        items = [("t", "x" * 40)] * 5
        parts = chunks(items, 100)
        checks["chunks: split near the size, nothing lost, no empty chunk"] = (
            [len(p) for p in parts] == [2, 2, 1] and sum(len(p) for p in parts) == 5 and chunks([], 10) == [])
        out = tmp / "out"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(src), str(out), "--since", "2026-10-06", "--chunk", "180000"])
            rc_usage = main([str(src)])
        files = sorted(p.name for p in out.iterdir())
        blob = "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
        index = (out / "INDEX.md").read_text(encoding="utf-8")
        checks["main: one digest + INDEX from a folder, --since drops the older prompt, usage exits 2"] = (
            rc == 0 and rc_usage == 2 and files == ["2026-10-06_abcdef12_part1.md", "INDEX.md"]
            and "an old prompt" not in blob and "| 2026-10-06_abcdef12_part1.md | 2026-10-06T10:00 |" in index
            and "| 2 |" in index)
        checks["main: planted secrets do NOT leak into any written file"] = (
            key not in blob and short not in blob and "<redacted>" in blob)
    except Exception as e:
        checks[f"selftest crashed: {type(e).__name__}: {e}"] = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for name_, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name_}")
    return all(checks.values())


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if len(argv) < 2:
        print(__doc__)
        return 2
    src, dst = Path(argv[0]), Path(argv[1])
    size = int(argv[argv.index("--chunk") + 1]) if "--chunk" in argv else 180_000
    since = argv[argv.index("--since") + 1] if "--since" in argv else ""
    files = sorted(src.glob("*.jsonl")) if src.is_dir() else [src]
    dst.mkdir(parents=True, exist_ok=True)
    index = ["# Transcript digests", "", "| file | from | to | prompts | chars |", "|---|---|---|---|---|"]
    for f in files:
        lines = [x for x in entries(f) if x[0] >= since]
        if not lines:
            continue
        for i, part in enumerate(chunks(lines, size), 1):
            name = f"{part[0][0][:10]}_{f.stem[:8]}_part{i}.md"
            (dst / name).write_text("\n".join(x[1] for x in part) + "\n", encoding="utf-8")
            prompts = sum(1 for x in part if x[1].startswith("\n### MAX"))
            index.append(f"| {name} | {part[0][0]} | {part[-1][0]} | {prompts} | {sum(len(x[1]) for x in part):,} |")
    (dst / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"{len(index) - 4} digest file(s) in {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
