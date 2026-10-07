"""Registering youk's hooks in settings.json: idempotent, reversible, and it leaves the rest alone."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import install_hooks as ih  # noqa: E402

PLUGIN = REPO / "plugin"
OTHER = {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /elsewhere/other.py"}]}


def _settings(tmp_path: Path, data: dict | None) -> Path:
    path = tmp_path / "settings.json"
    if data is not None:
        path.write_text(json.dumps(data))
    return path


def _run(*args: str) -> int:
    return ih.main(list(args))


class TestMerge:
    def test_every_hook_script_path_is_absolute_and_exists(self):
        hooks = ih.load_hooks(PLUGIN)
        commands = [h["command"] for gs in hooks.values() for g in gs for h in g["hooks"]]
        assert commands and all("${CLAUDE_PLUGIN_ROOT}" not in c for c in commands)
        for command in commands:
            script = command.split('"')[1]
            assert Path(script).is_absolute() and Path(script).is_file(), script

    def test_adds_all_events_and_keeps_other_hooks_and_settings(self):
        before = {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [OTHER]}}
        after = ih.merge(before, ih.load_hooks(PLUGIN), PLUGIN)
        assert after["permissions"] == before["permissions"]
        assert OTHER in after["hooks"]["PreToolUse"]
        assert {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"} <= set(after["hooks"])
        assert len(after["hooks"]["PreToolUse"]) == 2

    def test_registering_twice_changes_nothing(self):
        once = ih.merge({}, ih.load_hooks(PLUGIN), PLUGIN)
        assert ih.merge(once, ih.load_hooks(PLUGIN), PLUGIN) == once

    def test_remove_takes_out_only_youk_entries(self):
        added = ih.merge({"hooks": {"PreToolUse": [OTHER]}}, ih.load_hooks(PLUGIN), PLUGIN)
        removed = ih.merge(added, ih.load_hooks(PLUGIN), PLUGIN, remove=True)
        assert removed == {"hooks": {"PreToolUse": [OTHER]}}

    def test_remove_from_clean_settings_leaves_no_empty_hooks_key(self):
        added = ih.merge({"model": "x"}, ih.load_hooks(PLUGIN), PLUGIN)
        assert ih.merge(added, ih.load_hooks(PLUGIN), PLUGIN, remove=True) == {"model": "x"}

    def test_a_moved_plugin_dir_replaces_the_old_entries(self, tmp_path):
        old = tmp_path / "old" / "plugin"
        (old / "hooks").mkdir(parents=True)
        (old / "scripts").mkdir()
        (old / "hooks" / "hooks.json").write_text(
            (PLUGIN / "hooks" / "hooks.json").read_text())
        stale = ih.merge({}, ih.load_hooks(old), old)
        # same plugin dir again: replaced, not duplicated
        again = ih.merge(stale, ih.load_hooks(old), old)
        assert again == stale


class TestCommandLine:
    def test_writes_a_backup_once_and_registers(self, tmp_path):
        path = _settings(tmp_path, {"permissions": {"allow": ["x"]}})
        assert _run("--settings", str(path), "--plugin-dir", str(PLUGIN)) == 0
        backup = tmp_path / "settings.json.bak-youk-hooks"
        assert json.loads(backup.read_text()) == {"permissions": {"allow": ["x"]}}
        assert "SessionStart" in json.loads(path.read_text())["hooks"]
        # a second run does not overwrite the backup with the already-changed file
        assert _run("--settings", str(path), "--plugin-dir", str(PLUGIN)) == 0
        assert json.loads(backup.read_text()) == {"permissions": {"allow": ["x"]}}

    def test_dry_run_changes_nothing(self, tmp_path, capsys):
        path = _settings(tmp_path, {"a": 1})
        assert _run("--settings", str(path), "--plugin-dir", str(PLUGIN), "--dry-run") == 0
        assert json.loads(path.read_text()) == {"a": 1}
        assert "0 -> 8" in capsys.readouterr().out

    def test_missing_settings_file_is_created(self, tmp_path):
        path = tmp_path / "new" / "settings.json"
        assert _run("--settings", str(path), "--plugin-dir", str(PLUGIN)) == 0
        assert "hooks" in json.loads(path.read_text())

    def test_invalid_json_is_never_overwritten(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{ not json")
        assert _run("--settings", str(path), "--plugin-dir", str(PLUGIN)) == 1
        assert path.read_text() == "{ not json"

    def test_a_bad_plugin_dir_is_an_error(self, tmp_path):
        assert _run("--settings", str(tmp_path / "s.json"), "--plugin-dir", str(tmp_path)) == 1


class TestRegisteredHooksActuallyRun:
    @pytest.mark.parametrize("script,payload", [
        ("pre_tool_use.py", {"tool_name": "Read", "tool_input": {}, "cwd": "/tmp"}),
        ("user_prompt_submit.py", {"prompt": "hi", "cwd": "/tmp", "session_id": "s"}),
    ])
    def test_a_registered_script_runs_in_place_and_emits_json(self, script, payload, tmp_path):
        env = {"YOUK_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"}
        out = subprocess.run([sys.executable, str(PLUGIN / "scripts" / script)],
                             input=json.dumps(payload), capture_output=True, text=True, env=env,
                             timeout=30)
        assert out.returncode == 0 and json.loads(out.stdout)["continue"] is True
