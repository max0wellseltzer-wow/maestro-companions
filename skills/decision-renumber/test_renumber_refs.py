"""Run: python -m pytest -q .claude/skills/decision-renumber/test_renumber_refs.py"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import renumber_refs as R

RX = R.pattern(69, 129)

PY = '''"""Module doc: law D69 and D129."""
LAWS = ("D69", "D104")   # runtime strings stay: D69 here is a comment, moved


def f():
    """Under D81."""
    return "D81"
'''


def test_python_moves_comments_and_docstrings_only():
    new, n, status = R.sweep_file("forge/m.py", PY, RX, 23)
    assert status == "AST_SAME" and n == 4
    assert 'LAWS = ("D69", "D104")' in new and 'return "D81"' in new          # code strings untouched
    assert "law D92 and D152" in new and "D92 here is a comment" in new and "Under D104." in new


def test_markdown_whole_and_toml_comments_only():
    assert R.sweep_file("PLAN.md", "see D70, D130, D68\n", RX, 23)[0] == "see D93, D130, D68\n"   # range bounds kept
    toml = 'law = "D70"  # D70 governs\n'
    assert R.sweep_file("forge.toml", toml, RX, 23)[0] == 'law = "D70"  # D93 governs\n'


def test_append_only_and_prompts_and_json_are_skipped():
    for rel in ("tv-forge/errata.md", "progress.txt", "tv-lens/prompts/p1.md", "WORKSTATION.json",
                "shared/x.chain.jsonl", "tests.json"):
        assert R.sweep_file(rel, "D70\n", RX, 23) == ("D70\n", 0, "SKIPPED")


def test_ast_guard_refuses_a_change_to_code(monkeypatch):
    # plant: a sweep that also rewrote a code string must be refused, not written
    monkeypatch.setattr(R, "sweep_py", lambda src, rx, off: (src.replace('"D81"', '"D104"'), 1))
    assert R.sweep_file("m.py", PY, RX, 23) == (PY, 0, "AST_CHANGED")


def test_only_files_the_branch_added(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "<email>")
    g("config", "user.name", "t")
    (tmp_path / "CLAUDE.md").write_text("main says D70\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "base")
    g("checkout", "-qb", "side")
    (tmp_path / "CLAUDE.md").write_text("main says D70\nbranch line D71\n", encoding="utf-8")
    (tmp_path / "NEW.md").write_text("drafted D70\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "side")
    assert R.main(["--repo", str(tmp_path), "--base", "main", "--branch", "side", "--lo", "69", "--hi", "129",
                   "--offset", "23", "--apply"]) == 0
    assert (tmp_path / "NEW.md").read_text(encoding="utf-8") == "drafted D93\n"
    assert "D70" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")   # the 2026-10-13 slip cannot recur
