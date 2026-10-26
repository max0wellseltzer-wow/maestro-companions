"""land-a-change land.py on real temporary git repos: fast-forward, a peer commit in between (cherry-pick + tests.json union + a
forced re-check), a real conflict (nothing lands), a failing check (nothing pushed), the pen held by someone else.
Run: python -m pytest test_land.py -q -p no:cacheprovider"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import land as L  # noqa: E402

def sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def registry(*tests):
    return json.dumps({"checks": [{"id": t, "test": f"tests/t.py::{t}", "status": "passing"} for t in tests]},
                      indent=2) + "\n"


def commit(repo, name, text, msg):
    (repo / name).write_text(text, encoding="utf-8", newline="\n")
    sh(repo, "add", name)
    sh(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin.git"
    sh(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    seed = tmp_path / "seed"
    sh(tmp_path, "clone", "-q", str(origin), str(seed))
    commit(seed, "tests.json", registry("a"), "seed")
    commit(seed, "code.py", "x = 1\n", "code")
    sh(seed, "push", "-q", "origin", "master")
    live, clone = tmp_path / "live", tmp_path / "clone"
    sh(tmp_path, "clone", "-q", str(origin), str(live))
    sh(tmp_path, "clone", "-q", str(live), str(clone))
    for r in (live, clone):
        sh(r, "config", "user.name", "t")
        sh(r, "config", "user.email", "t@t")
    (tmp_path / "ok.bat").write_text("@echo CHECK PASSED\n", encoding="utf-8")
    (tmp_path / "bad.bat").write_text("@echo 3 failed\n@exit /b 1\n", encoding="utf-8")
    return origin, live, clone


class FakePen(L.Pen):
    def __init__(self, held=None):
        super().__init__(Path("."))
        self.held, self.log = held, []

    def holder(self):
        return self.held

    def claim(self, label):
        self.log.append("claim")
        return True

    def release(self):
        self.log.append("release")


def test_union_keeps_ours_adds_theirs_and_renames_a_colliding_id():
    ours = registry("a", "b")
    theirs = json.dumps({"checks": [{"id": "b", "test": "tests/t.py::b", "status": "passing"},
                                    {"id": "b", "test": "tests/t.py::other", "status": "passing"},
                                    {"id": "c", "test": "tests/t.py::c", "status": "passing"}]})
    got = json.loads(L.union_tests_json(ours, theirs))["checks"]
    assert [(e["id"], e["test"]) for e in got] == [("a", "tests/t.py::a"), ("b", "tests/t.py::b"),
                                                   ("b_2", "tests/t.py::other"), ("c", "tests/t.py::c")]
    assert L.union_tests_json(ours, theirs).startswith('{\n  "checks"')


def test_a_clean_fast_forward_with_the_checked_sha_skips_the_check_and_pushes(repos):
    origin, live, clone = repos
    commit(clone, "code.py", "x = 2\n", "mine")
    sha = out(clone, "rev-parse", "HEAD")
    pen = FakePen()
    res = L.land(live, clone, check="never-run.bat", checked=sha, pen=pen)
    assert res.code == 0 and out(origin, "rev-parse", "master") == sha and pen.log == ["claim", "release"]
    assert any("check skipped" in ln for ln in res.lines)


def test_a_peer_commit_in_between_is_kept_tests_json_is_unioned_and_the_check_reruns(repos):
    origin, live, clone = repos
    commit(live, "tests.json", registry("a", "peer"), "peer registers a test")
    commit(live, "peer.py", "p = 1\n", "peer code")
    commit(clone, "tests.json", registry("a", "mine"), "I register a test")
    commit(clone, "code.py", "x = 3\n", "my code")
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), checked=out(clone, "rev-parse", "HEAD"), pen=FakePen())
    assert res.code == 0, res.lines
    tests = [e["id"] for e in json.loads((live / "tests.json").read_text(encoding="utf-8"))["checks"]]
    assert tests == ["a", "peer", "mine"] and (live / "peer.py").exists() and "x = 3" in (live / "code.py").read_text()
    assert any(ln.startswith("check passed") for ln in res.lines)
    assert out(origin, "rev-parse", "master") == out(live, "rev-parse", "HEAD")


def test_a_real_conflict_lands_nothing_and_restores_the_live_tree(repos):
    origin, live, clone = repos
    commit(live, "code.py", "x = 'peer'\n", "peer edits code")
    before = out(live, "rev-parse", "HEAD")
    commit(clone, "code.py", "x = 'mine'\n", "I edit code")
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), pen=FakePen())
    assert res.code == 4 and out(live, "rev-parse", "HEAD") == before and not out(live, "status", "--porcelain")
    assert out(origin, "rev-parse", "master") != out(clone, "rev-parse", "HEAD")


def test_a_commit_the_peer_already_has_is_skipped_not_picked_twice(repos):
    origin, live, clone = repos
    commit(clone, "a.py", "a = 1\n", "shared change")
    shared = out(clone, "rev-parse", "HEAD")
    commit(clone, "b.py", "b = 1\n", "mine only")
    sh(live, "fetch", "-q", str(clone), "master")
    sh(live, "-c", "user.name=t", "-c", "user.email=t@t", "cherry-pick", shared)        # the peer took it already
    commit(live, "peer.py", "p = 1\n", "peer code")
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), pen=FakePen())
    assert res.code == 0 and "cherry-picking 1 commit(s)" in res.lines[0]
    assert out(live, "log", "--format=%s").splitlines()[:4] == ["mine only", "peer code", "shared change", "code"]


def test_a_conflict_in_tests_json_and_another_file_is_a_stop_not_a_union(repos):
    origin, live, clone = repos
    (live / "code.py").write_text("x = 'peer'\n", encoding="utf-8")
    sh(live, "add", "code.py")
    commit(live, "tests.json", registry("a", "peer"), "peer edits both")
    (clone / "code.py").write_text("x = 'mine'\n", encoding="utf-8")
    sh(clone, "add", "code.py")
    commit(clone, "tests.json", registry("a", "mine"), "I edit both")
    before = out(live, "rev-parse", "HEAD")
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), pen=FakePen())
    assert res.code == 4 and out(live, "rev-parse", "HEAD") == before and not out(live, "status", "--porcelain")


def test_a_conflict_on_the_second_commit_undoes_the_first_one_too(repos):
    origin, live, clone = repos
    commit(live, "code.py", "x = 'peer'\n", "peer edits code")
    before = out(live, "rev-parse", "HEAD")
    commit(clone, "new.py", "n = 1\n", "clean one")
    commit(clone, "code.py", "x = 'mine'\n", "conflicting one")
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), pen=FakePen())
    assert res.code == 4 and out(live, "rev-parse", "HEAD") == before and not (live / "new.py").exists()


def test_a_check_that_exits_zero_without_saying_check_passed_is_a_failure(repos):
    origin, live, clone = repos
    (live.parent / "quiet.bat").write_text("@echo all good probably\n", encoding="utf-8")
    commit(clone, "code.py", "x = 6\n", "mine")
    res = L.land(live, clone, check=str(live.parent / "quiet.bat"), pen=FakePen())
    assert res.code == 5


def test_a_failing_check_pushes_nothing_and_still_releases_the_pen(repos):
    origin, live, clone = repos
    commit(clone, "code.py", "x = 4\n", "mine")
    pen = FakePen()
    res = L.land(live, clone, check=str(live.parent / "bad.bat"), pen=pen)
    assert res.code == 5 and out(origin, "rev-parse", "master") != out(clone, "rev-parse", "HEAD")
    assert pen.log == ["claim", "release"]


def test_the_pen_held_by_someone_else_stops_before_anything_happens(repos):
    origin, live, clone = repos
    commit(clone, "code.py", "x = 5\n", "mine")
    pen = FakePen(held="peer session")
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), pen=pen)
    assert res.code == 3 and pen.log == [] and out(live, "rev-parse", "HEAD") != out(clone, "rev-parse", "HEAD")


def test_nothing_new_in_the_clone_is_a_quiet_success(repos):
    origin, live, clone = repos
    res = L.land(live, clone, check=str(live.parent / "ok.bat"), pen=FakePen())
    assert res.code == 0 and res.lines == ["nothing to land: the live tree already has every commit of the clone"]
