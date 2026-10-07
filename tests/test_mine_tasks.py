"""The replay-task miner selects, rejects and verifies as the S08 card specifies."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "sim"))
import mine_tasks as mt

TEST_CMD = f"{sys.executable} -m pytest {{tests}} -q -p no:cacheprovider"


def git(repo: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "fixture"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, {"calc.py": "def add(a, b):\n    return a + b\n"}, "start the calculator")
    return r


def cfg(repo: Path) -> dict:
    return {"name": "fixture", "path": str(repo), "language": "python", "test_cmd": TEST_CMD}


class TestSelect:
    def _cand(self, files, message="Handle negative numbers in the parser properly"):
        return mt.Candidate("a" * 40, "b" * 40, message, files)

    def test_source_plus_test_commit_qualifies(self):
        assert mt.select(self._cand([("calc.py", 3, 1), ("tests/test_calc.py", 8, 0)])) is None

    def test_rejects_source_without_tests(self):
        assert "runnable test" in mt.select(self._cand([("calc.py", 3, 1)]))

    def test_rejects_tests_without_source(self):
        assert "no source change" in mt.select(self._cand([("tests/test_calc.py", 8, 0)]))

    def test_rejects_more_than_four_files(self):
        files = [(f"m{i}.py", 1, 0) for i in range(4)] + [("tests/test_m.py", 1, 0)]
        assert "5 files" in mt.select(self._cand(files))

    def test_tier_m_takes_the_band_above_small_and_only_that(self):
        five = [(f"m{i}.py", 1, 0) for i in range(4)] + [("tests/test_m.py", 1, 0)]
        assert mt.select(self._cand(five), "m") is None
        small = [("calc.py", 3, 1), ("tests/test_calc.py", 8, 0)]
        assert "small tier" in mt.select(self._cand(small), "m")
        big = [(f"m{i}.py", 1, 0) for i in range(12)] + [("tests/test_m.py", 1, 0)]
        assert "13 files" in mt.select(self._cand(big), "m")
        assert "lines" in mt.select(self._cand([("calc.py", 450, 60), ("tests/test_c.py", 5, 0)]), "m")

    def test_rejects_over_200_lines(self):
        assert "lines" in mt.select(self._cand([("calc.py", 150, 40), ("tests/test_c.py", 15, 0)]))

    def test_rejects_binary_files_as_oversize(self):
        assert mt.select(self._cand([("calc.py", 1, 0), ("tests/test_c.py", 1, 0),
                                     ("logo.png", 1, 0)])) is not None

    def test_rejects_lockfile_or_config_changes(self):
        files = [("calc.py", 1, 0), ("tests/test_c.py", 1, 0), ("uv.lock", 5, 5)]
        assert "non-code" in mt.select(self._cand(files))

    def test_rejects_prompt_that_is_only_file_names(self):
        files = [("calc.py", 1, 0), ("tests/test_calc.py", 1, 0)]
        assert "prompt" in mt.select(self._cand(files, message="calc.py"))


class TestPrompt:
    def test_strips_file_names_trailers_and_pr_refs(self):
        msg = ("Fix rounding in calc.py (#12)\n\nThe add helper in src/calc.py lost precision.\n\n"
               "Co-Authored-By: Someone <s@x.com>")
        out = mt.clean_prompt(msg, ["src/calc.py", "tests/test_calc.py"])
        assert "calc.py" not in out and "#12" not in out and "Co-Authored" not in out
        assert "Fix rounding" in out and "lost precision" in out


class TestPromptFairness:
    def test_only_the_subject_and_first_paragraph_survive(self):
        msg = ("Fix the retry loop\n\nIt retried forever on a 404.\n\nFix: add max_retries "
               "to the client.\n\nClaude-Session: https://x/y")
        out = mt.clean_prompt(msg, ["a.py"])
        assert "retried forever" in out and "max_retries" not in out and "Claude-Session" not in out

    def test_a_prompt_describing_only_the_problem_is_kept(self, repo):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n\ndef clamp_total(a):\n"
                                 "    return a\n",
                      "tests/test_clamp.py": "from calc import clamp_total\n\ndef test_c():\n"
                                             "    assert clamp_total(1) == 2\n"},
               "Totals in the report can exceed the allowed range and nothing stops them")
        assert len(mt.mine_repo(cfg(repo), limit=5, verify_tests=False)) == 1

    def test_names_the_tests_call_are_given_as_interface_not_rejected(self, repo):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n\ndef clamp_total(a):\n"
                                 "    return a\n",
                      "tests/test_clamp.py": "from calc import clamp_total\n\ndef test_c():\n"
                                             "    assert clamp_total(1) == 1\n"},
               "Add clamp_total so totals stay in range for the report")
        (task,) = mt.mine_repo(cfg(repo), limit=5, verify_tests=False)
        assert task.interface == ["clamp_total"]
        assert "clamp_total" in task.prompt and "tests for this change use these names" in task.prompt

    def test_a_name_in_the_prompt_that_the_tests_do_not_call_is_still_a_leak(self, repo):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n\ndef helper_split(a):\n"
                                 "    return a\n\ndef clamp_total(a):\n    return a\n",
                      "tests/test_clamp.py": "from calc import clamp_total\n\ndef test_c():\n"
                                             "    assert clamp_total(1) == 1\n"},
               "Totals escape their range because helper_split never clamps them")
        assert mt.mine_repo(cfg(repo), limit=5, verify_tests=False) == []

    def test_a_name_that_already_existed_is_not_a_leak(self, repo):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b + 0\n",
                      "tests/test_add.py": "from calc import add\n\ndef test_a():\n"
                                           "    assert add(1, 1) == 2\n"},
               "The add helper mishandles floats when summing report totals")
        assert len(mt.mine_repo(cfg(repo), limit=5, verify_tests=False)) == 1


class TestHistory:
    def test_numstat_and_parent_are_read(self, repo):
        sha = commit(repo, {"calc.py": "def add(a, b):\n    return a + b + 0\n",
                            "tests/test_calc.py": "def test_x():\n    assert True\n"}, "msg here")
        first = mt.history(repo)[0]
        assert first.sha == sha
        assert {p for p, _, _ in first.files} == {"calc.py", "tests/test_calc.py"}
        assert first.parent == git(repo, "rev-parse", "HEAD~1")

    def test_merge_commits_are_skipped(self, repo):
        git(repo, "checkout", "-q", "-b", "side")
        commit(repo, {"side.py": "x = 1\n"}, "side work")
        git(repo, "checkout", "-q", "main")
        commit(repo, {"main.py": "y = 1\n"}, "main work")
        git(repo, "merge", "-q", "--no-ff", "side", "-m", "merge side")
        assert all(len(c.parent) == 40 for c in mt.history(repo))
        assert "merge side" not in [c.message for c in mt.history(repo)]


class TestMineRepo:
    def _fix_commit(self, repo):
        return commit(repo, {
            "calc.py": "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n",
            "tests/test_calc.py": "from calc import sub\n\ndef test_sub():\n    assert sub(3, 1) == 2\n",
        }, "Add a subtraction helper so callers stop negating by hand")

    def test_keeps_a_verified_task(self, repo, monkeypatch):
        monkeypatch.chdir(repo)  # tests import calc from the checkout root
        sha = self._fix_commit(repo)
        tasks = mt.mine_repo(cfg(repo), limit=5)
        assert [t.sha for t in tasks] == [sha]
        task = tasks[0]
        assert task.parent_sha == git(repo, "rev-parse", "HEAD~1")
        assert task.hidden_tests == ["tests/test_calc.py"]
        assert task.added_tests == ["tests/test_calc.py"]
        assert task.source_files == ["calc.py"]
        assert task.language == "python"
        assert "calc.py" not in task.prompt

    def test_rejects_tests_that_pass_on_the_parent(self, repo):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b  # tidy\n",
                      "tests/test_calc.py": "from calc import add\n\ndef test_add():\n"
                                            "    assert add(1, 2) == 3\n"},
               "Tidy the addition helper and pin its behaviour")
        assert mt.mine_repo(cfg(repo), limit=5) == []

    def test_rejects_tests_that_fail_at_the_commit(self, repo):
        commit(repo, {"calc.py": "def add(a, b):\n    return a - b\n",
                      "tests/test_calc.py": "from calc import add\n\ndef test_add():\n"
                                            "    assert add(1, 2) == 3\n"},
               "Break the addition helper and add a test that notices")
        assert mt.mine_repo(cfg(repo), limit=5) == []

    def test_no_verify_lists_candidates_without_running_tests(self, repo):
        self._fix_commit(repo)
        assert len(mt.mine_repo(cfg(repo), limit=5, verify_tests=False)) == 1

    def test_limit_caps_the_count_and_worktrees_are_cleaned_up(self, repo):
        for i in range(3):
            commit(repo, {"calc.py": f"def add(a, b):\n    return a + b\n\nN = {i}\n",
                          f"tests/test_n{i}.py": "def test_n():\n    assert False\n"},
                   f"Record counter number {i} in the helper module")
        assert len(mt.mine_repo(cfg(repo), limit=2, verify_tests=False)) == 2
        assert git(repo, "worktree", "list").count("\n") == 0


class TestOutputs:
    def test_task_round_trips_through_yaml(self, repo, tmp_path):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n\nZ = 1\n",
                      "tests/test_z.py": "def test_z():\n    assert False\n"},
               "Expose the Z constant for the report module")
        task = mt.mine_repo(cfg(repo), limit=1, verify_tests=False)[0]
        path = mt.write_task(task, tmp_path / "tasks")
        loaded = yaml.safe_load(path.read_text())
        assert loaded["id"] == task.id and loaded["review"] == {"fair": None, "note": ""}
        assert mt.load_tasks(tmp_path / "tasks")[0]["sha"] == task.sha

    def test_a_remine_keeps_the_human_review_verdict(self, repo, tmp_path):
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n\nZ = 1\n",
                      "tests/test_z.py": "def test_z():\n    assert False\n"},
               "Expose the Z constant for the report module")
        task = mt.mine_repo(cfg(repo), limit=1, verify_tests=False)[0]
        path = mt.write_task(task, tmp_path / "tasks")
        data = yaml.safe_load(path.read_text())
        data["review"] = {"fair": False, "note": "gives the fix away"}
        path.write_text(yaml.safe_dump(data))
        mt.write_task(task, tmp_path / "tasks")
        assert yaml.safe_load(path.read_text())["review"]["fair"] is False

    def test_unfair_tasks_are_dropped_and_unreviewed_ones_kept(self):
        rows = [{"id": "a", "review": {"fair": False}}, {"id": "b", "review": {"fair": True}},
                {"id": "c", "review": {"fair": None}}, {"id": "d"}]
        assert [t["id"] for t in mt.usable(rows)] == ["b", "c", "d"]

    def test_summary_flags_the_kill_criterion_below_twelve(self):
        rows = [{"repo": "a", "language": "python"}] * 3
        assert "kill criterion" in mt.summary(rows)
        assert "kill criterion" not in mt.summary(rows * 5)


class TestSkipExisting:
    def test_a_skipped_task_is_not_mined_again(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n"}, "start the calculator")
        commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n\ndef sub(a, b=0):\n    return 1\n",
                      "tests/test_sub.py": "from calc import sub\n\ndef test_sub():\n    assert sub(1) == 1\n"},
               "Add the sub helper so callers can use it directly")
        first = mt.mine_repo(cfg(repo), limit=5, verify_tests=False)
        assert len(first) == 1
        again = mt.mine_repo(cfg(repo), limit=5, verify_tests=False, skip={first[0].id})
        assert again == []
