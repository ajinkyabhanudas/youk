"""Anything new has to be traceable, or CI fails.

Five surfaces, each with its own rule:
  stages   every entry in docs/system-map.yaml says how it is observed: a real_log, the ledger
           kinds it emits, or why it is untraced
  tools    every MCP tool is wrapped by the server spans (tests/test_tool_spans.py)
  gates    every check_*_gate tool is named in tool_spans.GATE_CHECKS, so its blocks are events
  skills   the usage tap matches the Skill tool, so any skill that fires is recorded
  hooks    every script in hooks.json has a registry entry
and the orphan check (a tool built and tested but never called) runs here instead of at every
session start.
"""
from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import yaml

import events
import footprint
import tool_spans
import wiring_pulse

REPO = Path(__file__).parent.parent
STAGES = yaml.safe_load((REPO / "docs" / "system-map.yaml").read_text(encoding="utf-8"))


def traceability_problems(stages: list[dict]) -> list[str]:
    """What is wrong with the registry's traceability declarations, empty when nothing is."""
    problems = []
    for stage in stages:
        name = stage.get("name", "<unnamed>")
        emits, reason = stage.get("emits"), stage.get("untraced_reason")
        if stage.get("real_log") is None and not emits and not (isinstance(reason, str) and reason.strip()):
            problems.append(f"{name}: no real_log, no emits, no untraced_reason")
        if emits and reason:
            problems.append(f"{name}: declares both emits and untraced_reason")
        if emits:
            unknown = set(emits) - events.KINDS
            if unknown:
                problems.append(f"{name}: emits unknown kinds {sorted(unknown)}")
    return problems


class TestStages:
    def test_the_shipped_registry_is_fully_declared(self):
        assert traceability_problems(STAGES) == []

    def test_the_check_is_not_vacuous(self):
        bad = [
            {"name": "silent", "real_log": None},
            {"name": "both", "real_log": None, "emits": ["tool"], "untraced_reason": "x"},
            {"name": "typo", "real_log": None, "emits": ["toool"]},
        ]
        found = traceability_problems(bad)
        assert len(found) == 3
        assert traceability_problems([{"name": "ok", "real_log": "state/x.jsonl"}]) == []


class TestHooks:
    def test_every_hook_script_has_a_registry_entry(self):
        hooks = json.loads((REPO / "plugin" / "hooks" / "hooks.json").read_text())["hooks"]
        scripts = {
            hook["command"].split("scripts/")[1].rstrip('"')
            for groups in hooks.values() for group in groups for hook in group["hooks"]
        }
        described = " ".join(str(s.get("triggers_on", "")) for s in STAGES)
        missing = sorted(s for s in scripts if f"plugin/scripts/{s}" not in described)
        assert missing == [], f"hook scripts with no entry in docs/system-map.yaml: {missing}"


class TestGates:
    def _gate_tools(self) -> set[str]:
        tree = ast.parse((REPO / "servers" / "core" / "src" / "server.py").read_text())
        return {
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("check_") and n.name.endswith("_gate")
            and any("mcp.tool" in ast.unparse(d) for d in n.decorator_list)
        }

    def test_every_gate_check_tool_emits_gate_events(self):
        missing = self._gate_tools() - set(tool_spans.GATE_CHECKS)
        assert missing == set(), f"add to tool_spans.GATE_CHECKS: {sorted(missing)}"

    def test_no_stale_gate_entries(self):
        assert set(tool_spans.GATE_CHECKS) - self._gate_tools() == set()


class TestSkills:
    def test_the_tap_matches_the_skill_tool(self):
        hooks = json.loads((REPO / "plugin" / "hooks" / "hooks.json").read_text())["hooks"]
        tap = [g for g in hooks["PostToolUse"]
               if any("usage_tap.py" in h["command"] for h in g["hooks"])]
        assert tap and all("Skill" in g["matcher"] for g in tap)

    def test_every_skill_has_a_name_and_description(self):
        bad = []
        for path in sorted((REPO / "skills").glob("*/SKILL.md")):
            front = footprint._frontmatter(path.read_text(encoding="utf-8"))
            if not front.get("name") or not str(front.get("description", "")).strip():
                bad.append(path.parent.name)
        assert bad == [], f"skills missing frontmatter name or description: {bad}"


class TestOrphans:
    # Tools the old always-on text told the model to call. The lean template does not mention
    # them, so only the full arm's frozen text reaches them. S12 decides each: compile it into a
    # hook or tool, or remove it. Growing this set means a new tool nothing calls.
    FULL_ARM_ONLY = {"log_ab_exposure", "mark_medium_risk_surfaced"}

    def _orphans(self, tmp_path, claude_md: Path) -> list[str]:
        shutil.copy(claude_md, tmp_path / "CLAUDE.md")
        result = wiring_pulse.check_wiring(REPO, tmp_path)
        assert result["total"] > 50
        return result["orphaned"]

    def test_no_tool_is_built_and_never_called(self, tmp_path):
        """The wiring pulse's check, moved from every session start to CI. The routing text it
        reads is the full arm's frozen CLAUDE.md, the complete instruction set."""
        orphans = self._orphans(tmp_path, REPO / "bench" / "arms" / "full" / "CLAUDE.md")
        assert orphans == [], (
            f"tools never invoked: {orphans}. Wire them into the routing loop, call "
            "them from code or a skill, or add them to wiring_pulse._TERMINAL_TOOLS with a reason."
        )

    def test_the_lean_template_leaves_only_the_known_full_arm_tools_uncalled(self, tmp_path):
        orphans = set(self._orphans(tmp_path, REPO / "docs" / "claude-md-template.md"))
        assert orphans <= self.FULL_ARM_ONLY, (
            f"new tools reachable only through prose that the lean template dropped: "
            f"{sorted(orphans - self.FULL_ARM_ONLY)}")
