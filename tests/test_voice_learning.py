"""The learned voice reaches the writing, and PR text is held to the commit voice gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import contract_guard as cg
import voice_profile
from voice_fingerprint import check_text

REPO = Path(__file__).parent.parent
PRE = REPO / "plugin" / "scripts" / "pre_tool_use.py"
sys.path.insert(0, str(REPO / "scripts"))
import voice_report  # noqa: E402


def tells(text: str) -> list[str]:
    r = check_text(text)
    return r["tells_hard"] + r["tells_soft"] if r["gate"] == "BLOCKED" else []


CLEAN = "the hook blocks eight things now. force-with-lease is fine and the bare arm skips it."


def pr(text: str) -> str:
    """A PR body in the required layout around some text."""
    return ("## What changed\n" + text + "\n\n## Why\nthe model had to remember these rules.\n\n"
            "## Impact\nthey cost no always-on tokens and cannot be skipped.\n\n"
            "## How it was checked\nthe full suite passed.")
DASHED = "this adds a hook — it blocks eight things the model used to remember."


class TestLearnedProfileIsFound:
    def test_the_builder_writes_where_the_skill_says_to_read(self, tmp_path):
        root = tmp_path
        corpus = root / "knowledge" / "voice-corpus.jsonl"
        corpus.parent.mkdir(parents=True)
        text = "i think we should keep it short and plain, so what do we do next? " * 160
        corpus.write_text(json.dumps({"register": "chat", "text": text}) + "\n")
        result = voice_profile.rebuild_voice_profiles(root, "myproj")
        assert result["registers_written"] == ["chat"]
        assert voice_profile.profile_path(root, "myproj", "chat").is_file()

    def test_the_humanize_skill_names_the_file_pattern_the_builder_writes(self):
        skill = (REPO / "skills" / "humanize" / "SKILL.md").read_text()
        assert "knowledge/global/voice-{slug}-{register}.md" in skill
        assert str(voice_profile.profile_path(Path("R"), "{slug}", "{register}")).endswith(
            "knowledge/global/voice-{slug}-{register}.md")
        assert "never\n   as a pass or fail test" in skill or "never as a pass or fail test" in " ".join(
            skill.split())


class TestVoiceReport:
    def test_it_says_so_when_there_is_no_corpus(self, tmp_path, capsys):
        assert voice_report.main(["--root", str(tmp_path)]) == 1
        assert "no chat samples" in capsys.readouterr().out

    def test_it_prints_the_learned_numbers_beside_the_baseline(self, tmp_path, capsys):
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        corpus.parent.mkdir(parents=True)
        corpus.write_text(json.dumps({"register": "chat", "text": "so what is the result of the test"}) + "\n")
        assert voice_report.main(["--root", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "mean_sentence" in out and "under 1500 words" in out
        assert "baseline" not in out          # none shipped, none stored locally here

    def test_a_local_baseline_is_shown_beside_the_learned_numbers(self, tmp_path, capsys):
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        corpus.parent.mkdir(parents=True)
        corpus.write_text(json.dumps({"register": "chat", "text": "so what is the result of the test"}) + "\n")
        base = tmp_path / "knowledge" / "global" / "voice-baseline.json"
        base.parent.mkdir(parents=True)
        base.write_text(json.dumps({"mean_sentence": 12.5}))
        voice_report.main(["--root", str(tmp_path)])
        assert "baseline" in capsys.readouterr().out


class TestPrText:
    def _rules(self, command: str, cwd=REPO) -> list[str]:
        return [v.rule for v in cg.evaluate_bash(command, str(cwd), tells)]

    def test_an_inline_body_with_a_tell_is_blocked(self):
        assert self._rules(f'gh pr create --title "ok" --body "{pr(DASHED)}"') == ["voice-pr-text"]

    def test_a_heredoc_body_with_a_tell_is_blocked(self):
        cmd = f"gh pr create --title \"ok\" --body \"$(cat <<'EOF'\n{pr(DASHED)}\nEOF\n)\""
        assert self._rules(cmd) == ["voice-pr-text"]

    def test_a_tell_in_the_title_is_blocked(self):
        assert self._rules('gh pr edit 5 --title "adds a hook — and more"') == ["voice-pr-text"]

    def test_a_body_file_is_read_and_checked(self, tmp_path):
        (tmp_path / "body.md").write_text(pr(DASHED))
        assert self._rules("gh pr create --title ok --body-file body.md", tmp_path) == ["voice-pr-text"]

    def test_clean_text_passes(self):
        assert self._rules(f'gh pr create --title "adds a hook" --body "{pr(CLEAN)}"') == []
        cmd = f"gh pr create --title ok --body \"$(cat <<'EOF'\n{pr(CLEAN)}\nEOF\n)\""
        assert self._rules(cmd) == []

    def test_other_gh_commands_are_not_checked(self):
        assert self._rules(f'gh issue create --body "{DASHED}"') == []

    def test_without_a_voice_check_nothing_is_flagged(self):
        assert [v.rule for v in cg.evaluate_bash(f'gh pr create --body "{pr(DASHED)}"', str(REPO))
                if v.rule == "voice-pr-text"] == []

    def test_prose_that_mentions_a_git_command_is_not_run_as_one(self, tmp_path):
        git_repo = tmp_path / "r"
        git_repo.mkdir()
        subprocess.run(["git", "-C", str(git_repo), "init", "-q", "-b", "main"], check=True)
        body = pr("the guard blocks commits and pushes to main, and this body even mentions the command "
                  "below as plain text while it explains what the change does for people who read it.\n"
                  "git push origin main\n")
        cmd = f"gh pr create --title ok --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""
        assert self._rules(cmd, git_repo) == []


class TestHookEndToEnd:
    def _run(self, command: str, tmp_path: Path, arm: str = "") -> dict:
        root = tmp_path / "root"
        (root / "state").mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in ("YOUK_ARM", "YOUK_GUARD_OFF")}
        env["YOUK_ROOT"] = str(root)
        if arm:
            env["YOUK_ARM"] = arm
        out = subprocess.run([sys.executable, str(PRE)], capture_output=True, text=True, env=env,
                             input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                                               "cwd": str(tmp_path)}), timeout=30)
        return json.loads(out.stdout)

    def test_the_hook_blocks_a_pr_body_with_a_tell_and_names_the_rule(self, tmp_path):
        out = self._run(f'gh pr create --title ok --body "{pr(DASHED)}"', tmp_path)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "voice-pr-text" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_the_hook_lets_a_clean_body_through_and_the_bare_arm_is_ungated(self, tmp_path):
        assert self._run(f'gh pr create --title ok --body "{pr(CLEAN)}"', tmp_path) == {"continue": True}
        assert self._run(f'gh pr create --body "{pr(DASHED)}"', tmp_path, arm="bare") == {"continue": True}


class TestNoPersonalDataInShippedVoiceFiles:
    """The system can adapt to a developer's voice but must not ship it. The git user's own name
    (and first name) may not appear in the voice, benchmark or plan files. Skipped when the
    environment has no git user name to look for."""

    PATHS = ("docs/voice-style.md", "scripts/voice_report.py", "scripts/sim", "bench/arms",
             "skills/humanize/SKILL.md", "servers/core/src/voice_profile.py",
             "servers/core/src/voice_fingerprint.py", "docs/value-plan")

    def _names(self) -> list[str]:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True,
                             cwd=REPO).stdout.strip()
        parts = [p for p in out.replace(".", " ").split() if len(p) >= 4]
        return ([out] if out else []) + parts

    def test_the_developers_name_is_not_in_voice_benchmark_or_plan_files(self):
        import pytest
        names = self._names()
        if not names:
            pytest.skip("no git user name to look for")
        offenders = []
        for rel in self.PATHS:
            path = REPO / rel
            files = [path] if path.is_file() else [f for f in path.rglob("*") if f.is_file()]
            for f in files:
                if f.suffix in (".png", ".jsonl", ".lock", ".pyc") or "__pycache__" in f.parts \
                        or "results" in f.parts:
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore").lower()
                offenders += [f"{f.relative_to(REPO)}: {n}" for n in names if n.lower() in text]
        assert not offenders, offenders
