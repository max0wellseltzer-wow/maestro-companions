"""digest.py on a small fake transcript: what is kept, what is dropped, redaction, chunking, --since, the index.
Run: python -m pytest test_digest.py -q -p no:cacheprovider"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import digest as D  # noqa: E402

KEY = "PK" + "Z9" * 9


def rec(role, content, ts):
    return json.dumps({"timestamp": ts, "message": {"role": role, "content": content}})


def transcript(tmp_path):
    lines = [
        rec("user", f"build it with {KEY}", "2026-10-11T10:00:00Z"),
        rec("assistant", [{"type": "text", "text": "Building."},
                          {"type": "tool_use", "name": "Bash", "input": {"command": "ls", "description": "List files"}}],
            "2026-10-11T10:01:00Z"),
        rec("user", [{"type": "tool_result", "tool_use_id": "x", "content": "huge output"},
                     {"type": "text", "text": "a reminder riding on the tool result"}], "2026-10-11T10:01:30Z"),
        rec("user", "<system-reminder>noise</system-reminder>", "2026-10-11T10:02:00Z"),
        rec("user", "<task-notification><task-id>b1</task-id></task-notification>", "2026-10-11T10:03:00Z"),
        rec("user", "<command-name>/skill-creator</command-name><command-args>make x</command-args>\nbody\nARGUMENTS: make x\nplus this",
            "2026-10-12T09:00:00Z"),
        rec("assistant", [{"type": "text", "text": "Done."}], "2026-10-12T09:05:00Z"),
        "not json",
    ]
    p = tmp_path / "abcdef12-0000.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_prompts_text_and_one_line_tools_are_kept_and_noise_and_keys_are_not(tmp_path):
    got = [line for _, line in D.entries(transcript(tmp_path))]
    text = "\n".join(got)
    assert "### MAX (2026-10-11T10:00)" in text and "<redacted>" in text and KEY not in text
    assert "CLAUDE: Building." in text and "[tool Bash: List files]" in text
    assert "huge output" not in text and "noise" not in text and "task-id" not in text and "riding" not in text
    assert "/skill-creator make x\n\nplus this" in text and "body" not in text
    assert len(got) == 5


def test_a_short_or_cut_value_assigned_to_a_key_name_is_redacted_too():
    half = "".join(["ab", "cd"] * 7)                          # 28 harmless characters, too short for the long-string rule
    secret_name, pw_name = "ALPACA_" + "SEC" + "RET", "pass" + "word"
    assert D.redact(f"$env:{secret_name} = '{half}'") == f"$env:{secret_name} = '<redacted>'"
    assert D.redact(f"api_{'k' + 'ey'}={half} next") == f"api_{'k' + 'ey'}=<redacted> next"
    assert D.redact('{"' + pw_name + '": "' + half + '"}') == '{"' + pw_name + '": "<redacted>"}'
    assert D.redact("the keyboard is fine; monkey = 3") == "the keyboard is fine; monkey = 3"


def test_chunks_split_at_the_size_and_keep_every_line(tmp_path):
    lines = D.entries(transcript(tmp_path))
    parts = D.chunks(lines, 60)
    assert sum(len(p) for p in parts) == len(lines) and len(parts) > 1
    assert D.chunks(lines, 10**9) == [lines]


def test_the_command_writes_parts_and_an_index_and_since_drops_older_days(tmp_path):
    src = transcript(tmp_path)
    out = tmp_path / "out"
    assert D.main([str(src), str(out), "--since", "2026-10-12"]) == 0
    files = sorted(p.name for p in out.glob("*.md"))
    assert files == ["2026-10-12_abcdef12_part1.md", "INDEX.md"]
    index = (out / "INDEX.md").read_text(encoding="utf-8")
    assert "| 2026-10-12_abcdef12_part1.md | 2026-10-12T09:00 | 2026-10-12T09:05 | 1 |" in index
    assert D.main([str(tmp_path), str(tmp_path / "all")]) == 0 and (tmp_path / "all" / "INDEX.md").exists()
    assert D.main([str(src)]) == 2
