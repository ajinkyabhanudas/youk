"""Public benchmark instances become battery tasks and are graded by an injected harness."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "sim"))
import public_tasks as pt  # noqa: E402
import run_battery as rb  # noqa: E402

PATCH = "diff --git a/src/a.go b/src/a.go\n--- a/src/a.go\n+++ b/src/a.go\n@@ -1 +1,2 @@\n-x\n+y\n+z\n"
TEST_PATCH = "diff --git a/src/a_test.go b/src/a_test.go\n--- a/src/a_test.go\n+++ b/src/a_test.go\n@@ -1 +1 @@\n-a\n+b\n"


def row(i="gin-gonic__gin-1", repo="gin-gonic/gin", **over):
    base = {"instance_id": i, "repo": repo, "base_commit": "b" * 40, "patch": PATCH,
            "test_patch": TEST_PATCH, "problem_statement": "The router drops a trailing slash. " * 10,
            "FAIL_TO_PASS": ["TestSlash"], "PASS_TO_PASS": ["TestOther"], "image": "swebench/x:latest",
            "log_parser": "parse_log_gotest"}
    return {**base, **over}


class TestMapping:
    def test_diff_helpers_count_files_and_changed_lines(self):
        assert pt.diff_files(PATCH) == ["src/a.go"]
        assert pt.diff_lines(PATCH) == 3

    def test_task_carries_what_the_runner_and_grader_need(self):
        t = pt.to_task(row())
        assert t["id"] == "ml-gin-gonic__gin-1" and t["language"] == "go"
        assert t["repo"] == "gin-gonic__gin" and t["sha"] == t["parent_sha"] == "b" * 40
        assert t["hidden_tests"] == ["src/a_test.go"] and t["files"] == 1 and t["lines"] == 3
        assert t["public"]["image"] == "swebench/x:latest"
        assert t["public"]["fail_to_pass"] == ["TestSlash"]

    @pytest.mark.parametrize("over,word", [
        ({"problem_statement": "short"}, "too short"),
        ({"FAIL_TO_PASS": []}, "failing test"),
        ({"test_patch": ""}, "no test patch"),
        ({"repo": "nobody/unknown"}, "unknown language"),
    ])
    def test_unusable_instances_say_why(self, over, word):
        assert word in pt.reject_reason(row(**over))

    def test_oversize_diffs_are_rejected(self):
        big = "".join(PATCH.replace("a.go", f"f{i}.go") for i in range(13))
        assert "13 files" in pt.reject_reason(row(patch=big))

    def test_every_dataset_repo_has_a_language(self):
        assert set(pt.LANGUAGE_OF_REPO.values()) == {
            "javascript", "typescript", "java", "ruby", "go", "php", "c", "cpp", "rust"}


class TestSample:
    def test_spreads_across_repos_and_languages_and_skips_rejects(self):
        rows = [row(f"gin-{i}", "gin-gonic/gin") for i in range(3)]
        rows += [row("caddy-1", "caddyserver/caddy"), row("tokio-1", "tokio-rs/tokio"),
                 row("bad", "tokio-rs/axum", FAIL_TO_PASS=[])]
        got = pt.sample(rows, 2)
        ids = sorted(r["instance_id"] for r in got)
        assert "bad" not in ids
        assert sum(1 for i in ids if i.startswith(("gin", "caddy"))) == 2   # two go, one repo each
        assert "tokio-1" in ids

    def test_largest_diff_comes_first_within_a_repo(self):
        small, large = row("s"), row("l", patch=PATCH + PATCH.replace("a.go", "b.go"))
        assert pt.sample([small, large], 1)[0]["instance_id"] == "l"


@pytest.fixture
def upstream(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    for cmd in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(remote), *cmd], check=True)
    (remote / "a.txt").write_text("one\n")
    subprocess.run(["git", "-C", str(remote), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(remote), "commit", "-qm", "base"], check=True)
    sha = subprocess.run(["git", "-C", str(remote), "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", str(remote), "config", "uploadpack.allowReachableSHA1InWant", "true"],
                   check=True)
    return remote, sha


class TestCheckoutAndGrade:
    def test_checkout_is_the_base_commit_and_the_diff_includes_new_files(self, upstream, tmp_path):
        remote, sha = upstream
        task = pt.to_task(row(base_commit=sha))
        dest = tmp_path / "work"
        pt.prepare_checkout(task, dest, remote=str(remote))
        assert (dest / "a.txt").read_text() == "one\n"
        (dest / "a.txt").write_text("two\n")
        (dest / "new.txt").write_text("n\n")
        patch = pt.agent_patch(dest, sha)
        assert "a/a.txt" in patch and "new.txt" in patch

    def test_empty_diff_fails_without_calling_the_harness(self, upstream, tmp_path):
        remote, sha = upstream
        task = pt.to_task(row(base_commit=sha))
        dest = tmp_path / "work"
        pt.prepare_checkout(task, dest, remote=str(remote))
        calls = []
        assert pt.grade(task, dest, tmp_path / "g", run=lambda *a: calls.append(a)) is False
        assert calls == []

    def _graded(self, upstream, tmp_path, resolved, run=None):
        remote, sha = upstream
        task = pt.to_task(row(base_commit=sha))
        dest = tmp_path / "work"
        pt.prepare_checkout(task, dest, remote=str(remote))
        (dest / "a.txt").write_text("two\n")

        def fake(predictions, run_id, cwd, instance_id, image):
            sent = json.loads(Path(predictions).read_text())
            assert sent["instance_id"] == task["public"]["instance_id"] and "a.txt" in sent["model_patch"]
            (Path(cwd) / "report.json").write_text(json.dumps({"resolved_ids": resolved}))
        return pt.grade(task, dest, tmp_path / "g", run=run or fake)

    def test_verdict_comes_from_the_harness_report(self, upstream, tmp_path):
        assert self._graded(upstream, tmp_path, ["gin-gonic__gin-1"]) is True

    def test_an_unresolved_instance_is_a_fail_and_an_errored_one_is_no_verdict(self, upstream, tmp_path):
        remote, sha = upstream
        report = tmp_path / "r"
        report.mkdir()
        (report / "x.json").write_text(json.dumps({"resolved_ids": [], "unresolved_ids": ["a"],
                                                   "error_ids": ["b"]}))
        assert pt.resolved_in(report, "a") is False
        assert pt.resolved_in(report, "b") is None

    def test_a_harness_crash_is_no_verdict_not_a_fail(self, upstream, tmp_path):
        def boom(*a):
            raise subprocess.CalledProcessError(1, "docker")
        assert self._graded(upstream, tmp_path, [], run=boom) is None

    def test_harness_command_targets_the_dataset_with_one_worker(self):
        cmd = pt.harness_command(Path("p.jsonl"), "r1", "i-1", Path("out"))
        assert "swebench.harness.run_evaluation" in cmd and cmd[cmd.index("--max_workers") + 1] == "1"
        assert cmd[cmd.index("--dataset_name") + 1] == pt.DATASET
        assert cmd[cmd.index("--instance_ids") + 1] == "i-1"


class TestRunnerBranch:
    def test_a_public_task_is_checked_out_and_graded_through_public_tasks(self, tmp_path, monkeypatch):
        task = pt.to_task(row())
        seen = {}
        monkeypatch.setattr(rb.public_tasks, "prepare_checkout",
                            lambda t, dest: (dest.mkdir(parents=True), seen.setdefault("co", t["id"])))
        monkeypatch.setattr(rb.public_tasks, "grade", lambda t, w, scratch: True)

        def agent(spec, workdir, ctx):
            return rb.AgentOutcome(cost_usd=0.1, turns=1, tok_in=1, tok_out=1)
        out = rb.execute_run(rb.RunSpec(task, "superpowers", 0), {}, tmp_path / "w", agent,
                             tmp_path / "root")           # the youk-hooks check only applies to youk arms
        assert seen["co"] == task["id"] and out["passed"] is True and out["repo"] == "gin-gonic__gin"

    def test_no_verdict_is_set_aside_as_infrastructure(self, tmp_path, monkeypatch):
        task = pt.to_task(row())
        monkeypatch.setattr(rb.public_tasks, "prepare_checkout", lambda t, dest: dest.mkdir(parents=True))
        monkeypatch.setattr(rb.public_tasks, "grade", lambda t, w, scratch: None)
        agent = lambda spec, workdir, ctx: rb.AgentOutcome(cost_usd=0.1, turns=1, tok_in=1, tok_out=1)  # noqa: E731
        out = rb.execute_run(rb.RunSpec(task, "bare", 0), {}, tmp_path / "w", agent, tmp_path / "root")
        assert out["status"] == "infra_error" and out["passed"] is None
