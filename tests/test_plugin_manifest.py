"""The plugin manifest must load in Claude Code, or none of youk's hooks run.

On 2026-10-05 the battery found that Claude Code 2.1.198 rejected plugin.json (author was a
string, hooks pointed outside the plugin root), so no hook ever fired under --plugin-dir. These
checks encode the rules that validation applies, with no dependency on the claude CLI.
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).parent.parent / "plugin"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_author_is_an_object_with_a_name():
    author = _manifest()["author"]
    assert isinstance(author, dict) and author.get("name")


def test_hook_paths_stay_inside_the_plugin_root():
    hooks = _manifest().get("hooks")
    for ref in ([hooks] if isinstance(hooks, str) else (hooks or [])):
        assert isinstance(ref, str) and ".." not in ref and ref.startswith("./")
        assert (PLUGIN / ref).is_file()


def test_the_default_hooks_file_exists_and_every_script_it_runs_exists():
    hooks_file = PLUGIN / "hooks" / "hooks.json"
    data = json.loads(hooks_file.read_text())["hooks"]
    assert data
    for entries in data.values():
        for entry in entries:
            for hook in entry["hooks"]:
                script = hook["command"].split("${CLAUDE_PLUGIN_ROOT}/")[1].split('"')[0]
                assert (PLUGIN / script).is_file(), script
