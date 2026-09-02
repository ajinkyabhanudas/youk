"""Tests for the pre_tool_use.py PreToolUse hook entrypoint itself — stdin in,
stdout out, via a real subprocess (not just the underlying function), since the
hook's actual contract with Claude Code is the JSON on stdout.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
_HOOK = _REPO / "plugin" / "scripts" / "pre_tool_use.py"


def _run_hook(payload: dict) -> dict:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
    )
    return json.loads(result.stdout)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False,
    )


class TestNonBashToolsPassThrough:
    def test_read_tool_is_ignored(self, tmp_path):
        out = _run_hook({"tool_name": "Read", "tool_input": {"file_path": "x"}, "cwd": str(tmp_path)})
        assert out == {"continue": True}

    def test_edit_tool_is_ignored(self, tmp_path):
        out = _run_hook({"tool_name": "Edit", "tool_input": {}, "cwd": str(tmp_path)})
        assert out == {"continue": True}


class TestSafeBashCommandsPassThroughSilently:
    def test_git_status_produces_no_message(self, tmp_path):
        out = _run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": str(tmp_path)})
        assert out == {"continue": True}
        assert "systemMessage" not in out

    def test_ls_produces_no_message(self, tmp_path):
        out = _run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": str(tmp_path)})
        assert out == {"continue": True}


class TestDestructiveBashCommandsGetCheckpointed:
    def test_never_blocks_the_command(self, tmp_path):
        """The whole design point: this is a safety net, not a permission gate —
        continue must always be True regardless of what the command is."""
        r = tmp_path / "repo"
        r.mkdir()
        _git(["init", "-q"], r)
        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git reset --hard HEAD~1"},
            "cwd": str(r),
        })
        assert out["continue"] is True

    def test_checkpoint_noted_when_there_is_something_to_protect(self, tmp_path):
        r = tmp_path / "repo"
        r.mkdir()
        _git(["init", "-q"], r)
        _git(["config", "user.email", "t@t.com"], r)
        _git(["config", "user.name", "t"], r)
        (r / "f.txt").write_text("v1\n")
        _git(["add", "f.txt"], r)
        _git(["commit", "-q", "-m", "init"], r)
        (r / "f.txt").write_text("uncommitted change\n")

        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git checkout ."},
            "cwd": str(r),
        })
        assert "systemMessage" in out
        assert "checkpoint" in out["systemMessage"].lower()
        assert "revert_checkpoint.py" in out["systemMessage"]

    def test_no_checkpoint_noted_when_tree_is_clean(self, tmp_path):
        r = tmp_path / "repo"
        r.mkdir()
        _git(["init", "-q"], r)
        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git checkout ."},
            "cwd": str(r),
        })
        assert out == {"continue": True}

    def test_non_git_directory_does_not_crash_the_hook(self, tmp_path):
        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf ./build"},
            "cwd": str(tmp_path),
        })
        assert out == {"continue": True}


class TestMissingFieldsDegradeGracefully:
    def test_empty_payload(self):
        out = _run_hook({})
        assert out == {"continue": True}

    def test_missing_command(self, tmp_path):
        out = _run_hook({"tool_name": "Bash", "tool_input": {}, "cwd": str(tmp_path)})
        assert out == {"continue": True}
