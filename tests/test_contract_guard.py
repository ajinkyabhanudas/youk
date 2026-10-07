"""Compiled contracts: each rule blocks its violation and lets the benign neighbour through."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import contract_guard as cg
import events

REPO = Path(__file__).parent.parent
PRE = REPO / "plugin" / "scripts" / "pre_tool_use.py"


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


@pytest.fixture(autouse=True)
def _guards_on(monkeypatch):
    monkeypatch.delenv("YOUK_GUARD_OFF", raising=False)
    monkeypatch.delenv("YOUK_ARM", raising=False)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "a.txt").write_text("a")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "start")
    return r


def rules(command: str, cwd: Path) -> list[str]:
    return [v.rule for v in cg.evaluate_bash(command, str(cwd))]


class TestBranchRules:
    def test_commit_on_the_default_branch_is_blocked(self, repo):
        assert rules('git commit -m "x"', repo) == ["commit-on-default-branch"]

    def test_commit_on_a_feature_branch_is_fine(self, repo):
        git(repo, "switch", "-q", "-c", "feat/x")
        assert rules('git commit -m "x"', repo) == []

    def test_creating_a_branch_in_the_same_command_is_fine(self, repo):
        assert rules('git switch -c feat/x && git commit -m "x"', repo) == []
        assert rules('git checkout -b feat/x && git add -A && git commit -m x', repo) == []

    def test_master_counts_as_default_too(self, tmp_path):
        r = tmp_path / "m"
        r.mkdir()
        git(r, "init", "-q", "-b", "master")
        assert rules("git commit -m x", r) == ["commit-on-default-branch"]

    def test_dash_C_checks_the_repo_it_names_not_the_cwd(self, repo, tmp_path):
        assert rules(f'git -C {repo} commit -m x', tmp_path) == ["commit-on-default-branch"]

    def test_push_to_main_by_name_or_by_default_is_blocked(self, repo):
        git(repo, "switch", "-q", "-c", "feat/x")
        assert rules("git push origin main", repo) == ["push-to-default-branch"]
        assert rules("git push origin HEAD:main", repo) == ["push-to-default-branch"]
        assert rules("git push origin feat/x", repo) == []
        assert rules("git push -u origin feat/x", repo) == []
        git(repo, "switch", "-q", "main")
        assert rules("git push", repo) == ["push-to-default-branch"]

    def test_deleting_a_remote_branch_is_not_a_push_to_main(self, repo):
        assert rules("git push origin --delete feat/x", repo) == []


class TestPushAndVerifyRules:
    def test_force_push_is_blocked_but_force_with_lease_is_not(self, repo):
        git(repo, "switch", "-q", "-c", "feat/x")
        assert "force-push" in rules("git push --force origin feat/x", repo)
        assert "force-push" in rules("git push -f origin feat/x", repo)
        assert rules("git push --force-with-lease origin feat/x", repo) == []

    def test_no_verify_is_blocked_on_commit_and_push(self, repo):
        git(repo, "switch", "-q", "-c", "feat/x")
        assert rules('git commit --no-verify -m x', repo) == ["no-verify"]
        assert rules('git commit -nm x', repo) == ["no-verify"]
        assert "no-verify" in rules('git push --no-verify origin feat/x', repo)
        assert rules('git commit -m "no verify here"', repo) == []


class TestStagedFiles:
    def _feature(self, repo):
        git(repo, "switch", "-q", "-c", "feat/x")

    def test_a_newly_staged_screenshot_blocks_the_commit(self, repo):
        self._feature(repo)
        (repo / "screenshots").mkdir()
        (repo / "screenshots" / "home.png").write_bytes(b"x")
        (repo / "ui-screenshot-1.png").write_bytes(b"x")
        git(repo, "add", "-A")
        assert rules("git commit -m x", repo) == ["staged-screenshot", "staged-screenshot"]

    def test_a_staged_env_file_or_key_blocks_but_env_example_does_not(self, repo):
        self._feature(repo)
        (repo / ".env").write_text("K=v")
        (repo / "deploy.pem").write_text("k")
        (repo / ".env.example").write_text("K=")
        git(repo, "add", "-A")
        assert rules("git commit -m x", repo) == ["staged-secret", "staged-secret"]

    def test_a_changed_tracked_file_is_never_a_false_block(self, repo):
        self._feature(repo)
        (repo / ".env.testing").write_text("A=1")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "tracked already")
        (repo / ".env.testing").write_text("A=2")
        git(repo, "add", "-A")
        assert rules("git commit -m x", repo) == []

    def test_ordinary_files_pass(self, repo):
        self._feature(repo)
        (repo / "notes.md").write_text("secret-handling notes")
        git(repo, "add", "-A")
        assert rules("git commit -m x", repo) == []


class TestReadAndInstall:
    def test_printing_a_dotenv_is_blocked_sourcing_it_is_not(self, tmp_path):
        assert rules("cat .env", tmp_path) == ["read-dotenv"]
        assert rules("head -5 config/.env.local", tmp_path) == ["read-dotenv"]
        assert rules("grep KEY .env", tmp_path) == ["read-dotenv"]
        assert rules("set -a && source .env && set +a", tmp_path) == []
        assert rules("cat .env.example", tmp_path) == []
        assert rules("cat README.md", tmp_path) == []

    def test_forced_installs_are_blocked(self, tmp_path):
        assert rules("npm install --legacy-peer-deps", tmp_path) == ["dependency-force"]
        assert rules("pnpm add react --force", tmp_path) == ["dependency-force"]
        assert rules("npm install react", tmp_path) == []
        assert rules("npm run build --force", tmp_path) == []


class TestEscapeAndRobustness:
    def test_guard_off_turns_named_rules_or_all_off(self, repo, monkeypatch):
        monkeypatch.setenv("YOUK_GUARD_OFF", "commit-on-default-branch")
        assert rules("git commit -m x", repo) == []
        monkeypatch.setenv("YOUK_GUARD_OFF", "all")
        assert rules("git push --force origin main", repo) == []

    def test_unparseable_and_empty_commands_do_not_raise(self, tmp_path):
        assert rules("echo 'unterminated", tmp_path) == []
        assert rules("", tmp_path) == []
        assert rules("   ;  && ", tmp_path) == []

    def test_a_message_names_the_rule_and_the_way_out(self, repo):
        text = cg.first_violation("git commit -m x", str(repo)).text()
        assert "commit-on-default-branch" in text and "git switch -c" in text
        assert "YOUK_GUARD_OFF" in text

    def test_every_rule_has_a_remedy(self):
        assert all(said and instead for said, instead in cg.RULES.values())


def run_hook(command: str, cwd: Path, root: Path, arm: str = "") -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("YOUK_ARM", "YOUK_GUARD_OFF")}
    env["YOUK_ROOT"] = str(root)
    if arm:
        env["YOUK_ARM"] = arm
    out = subprocess.run([sys.executable, str(PRE)], capture_output=True, text=True, env=env,
                         input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                                           "cwd": str(cwd)}), timeout=30)
    return json.loads(out.stdout)


class TestHook:
    def test_the_hook_denies_with_the_contract_message_and_records_a_gate_event(self, repo, tmp_path):
        root = tmp_path / "root"
        (root / "state").mkdir(parents=True)
        out = run_hook("git commit -m x", repo, root)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "commit-on-default-branch" in out["hookSpecificOutput"]["permissionDecisionReason"]
        logged = list(events.read_events(root, "r", kinds={"gate"}))
        assert [(e["name"], e["status"]) for e in logged] == [
            ("contract.commit-on-default-branch", "block")]

    def test_a_clean_command_passes_untouched(self, repo, tmp_path):
        root = tmp_path / "root"
        (root / "state").mkdir(parents=True)
        out = run_hook("git status", repo, root)
        assert out == {"continue": True}

    def test_the_bare_arm_runs_ungated(self, repo, tmp_path):
        root = tmp_path / "root"
        (root / "state").mkdir(parents=True)
        assert run_hook("git commit -m x", repo, root, arm="bare") == {"continue": True}
        assert run_hook("git commit -m x", repo, root, arm="lean")["hookSpecificOutput"][
            "permissionDecision"] == "deny"


class TestGuardrailsYamlAgreesWithTheCode:
    def test_every_rule_in_code_is_listed_and_every_listed_rule_exists(self):
        import yaml
        listed = {c["id"] for c in yaml.safe_load(
            (REPO / "config" / "guardrails.yaml").read_text())["compiled_contracts"]}
        assert listed == set(cg.RULES)
