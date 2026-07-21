"""L4 — Static + Dynamic Integrity.

L4a (class TestStaticIntegrity): YAML parsing + path resolution. No Docker.
L4b (class TestDynamicIntegrity): check_doc_graph + stale state file audit. Requires L1.
"""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from .mcp_client import call_tool, YOUK_DIR

YOUK_DIR_STR = str(YOUK_DIR)
CONFIG_DIR = YOUK_DIR / "config"
KNOWLEDGE_DIR = YOUK_DIR / "knowledge"
DOCS_DIR = YOUK_DIR / "docs"
STATE_DIR = YOUK_DIR / "state"
CLAUDE_DIR = Path.home() / ".claude"


def _resolve_path(raw: str) -> Path:
    """Resolve a doc-map path that may use ~/.claude/ prefix."""
    if raw.startswith("~/.claude/"):
        return CLAUDE_DIR / raw[len("~/.claude/"):]
    return YOUK_DIR / raw


# ===========================================================================
# L4a — Static Integrity (no Docker)
# ===========================================================================

class TestStaticIntegrity:

    def test_routes_yaml_valid(self):
        p = CONFIG_DIR / "routes.yaml"
        assert p.exists(), f"config/routes.yaml missing"
        data = yaml.safe_load(p.read_text())
        assert data is not None

    def test_routes_yaml_has_all_sizes(self):
        data = yaml.safe_load((CONFIG_DIR / "routes.yaml").read_text())
        task_sizes = data.get("task_sizes", {})
        for size in ("XS", "S", "M", "L", "XL"):
            assert size in task_sizes, f"config/routes.yaml missing size: {size}"

    def test_guardrails_yaml_valid(self):
        p = CONFIG_DIR / "guardrails.yaml"
        assert p.exists(), "config/guardrails.yaml missing"
        data = yaml.safe_load(p.read_text())
        assert data is not None

    def test_guardrails_has_hard_rules(self):
        data = yaml.safe_load((CONFIG_DIR / "guardrails.yaml").read_text())
        hard_rules = data.get("hard_rules", [])
        assert len(hard_rules) >= 5, (
            f"Expected ≥5 hard rules in guardrails.yaml, found {len(hard_rules)}"
        )

    def test_skill_graph_yaml_valid(self):
        p = KNOWLEDGE_DIR / "skill-graph.yaml"
        assert p.exists(), "knowledge/skill-graph.yaml missing"
        data = yaml.safe_load(p.read_text())
        assert data is not None

    def test_skill_graph_reentry_edges_valid(self):
        data = yaml.safe_load((KNOWLEDGE_DIR / "skill-graph.yaml").read_text())
        reentry = data.get("reentry_edges", {})
        skills_dir = YOUK_DIR / "skills"
        broken = []
        for from_skill, edges in reentry.items():
            if not (skills_dir / from_skill).is_dir():
                broken.append(f"reentry_edges source '{from_skill}' has no skills/ directory")
            for edge in (edges or []):
                to_skill = edge.get("to", "")
                if to_skill and not (skills_dir / to_skill).is_dir():
                    broken.append(f"reentry_edges target '{to_skill}' has no skills/ directory")
        assert not broken, "\n".join(broken)

    def test_doc_map_yaml_valid(self):
        p = DOCS_DIR / "doc-map.yaml"
        assert p.exists(), "docs/doc-map.yaml missing"
        data = yaml.safe_load(p.read_text())
        assert data is not None

    def test_doc_map_authority_files_exist(self):
        data = yaml.safe_load((DOCS_DIR / "doc-map.yaml").read_text())
        missing = []
        for concept in data.get("concepts", []):
            authority = concept.get("authority", "")
            if authority:
                p = _resolve_path(authority)
                if not p.exists():
                    missing.append(f"concept '{concept['concept']}' authority missing: {authority}")
        assert not missing, (
            f"{len(missing)} authority file(s) missing:\n" + "\n".join(f"  {m}" for m in missing)
        )

    def test_doc_map_derived_files_exist(self):
        data = yaml.safe_load((DOCS_DIR / "doc-map.yaml").read_text())
        missing = []
        for concept in data.get("concepts", []):
            for derived in concept.get("derived_in", []):
                p = _resolve_path(derived)
                if not p.exists():
                    missing.append(f"concept '{concept['concept']}' derived missing: {derived}")
        if missing:
            pytest.xfail(
                f"{len(missing)} derived file(s) missing (WARN):\n"
                + "\n".join(f"  {m}" for m in missing)
            )

    def test_youk_root_required_dirs(self):
        for subdir in ("state", "config", "knowledge", "skills", "docs"):
            assert (YOUK_DIR / subdir).is_dir(), f"YOUK_ROOT/{subdir} missing"


# ===========================================================================
# L4b — Dynamic Integrity (requires Docker)
# ===========================================================================

class TestDynamicIntegrity:

    def test_no_stale_session_open(self):
        """Warn if session-open.json exists — a live session may be running."""
        f = STATE_DIR / "session-open.json"
        if f.exists():
            pytest.xfail(
                "state/session-open.json exists — live session may be running or prior session leaked"
            )

    def test_no_stale_routing_breadcrumb(self):
        f = STATE_DIR / "routing-breadcrumb.json"
        if f.exists():
            pytest.xfail(
                "state/routing-breadcrumb.json exists — prior M+ session may not have called task_checkpoint"
            )

    def test_no_stale_pending_action(self):
        """pending-action.json older than 24h is a blocker that should have been cleared."""
        import datetime, json as _json
        f = STATE_DIR / "pending-action.json"
        if not f.exists():
            return
        try:
            data = _json.loads(f.read_text())
            written_at = datetime.datetime.fromisoformat(data.get("written_at", ""))
            age = datetime.datetime.utcnow() - written_at
            if age.total_seconds() > 86400:
                pytest.xfail(
                    f"state/pending-action.json is {age.days}d old — last session closed without /done "
                    f"and pending action was never consumed. Action: {data.get('action')}"
                )
        except (ValueError, KeyError):
            pytest.xfail("state/pending-action.json exists but is malformed")

    def test_check_doc_graph_returns_result(self, sandbox_state):
        r = call_tool("youk-core:latest", "check_doc_graph", {}, state_dir=sandbox_state)
        assert "concepts_checked" in r or "stale_concepts" in r or "verdict" in r, (
            f"check_doc_graph returned unexpected structure: {r}"
        )

    def test_check_doc_graph_no_stale_concepts(self, sandbox_state):
        r = call_tool("youk-core:latest", "check_doc_graph", {}, state_dir=sandbox_state)
        stale = r.get("stale_concepts", [])
        if stale:
            names = [c.get("concept", str(c)) for c in stale]
            pytest.xfail(
                f"{len(stale)} stale concept(s) detected (WARN — run /done to sync):\n"
                + "\n".join(f"  {n}" for n in names)
            )

    def test_all_mcp_tools_in_doc_map(self):
        """Every @mcp.tool() in server.py should appear in docs/doc-map.yaml."""
        doc_map = yaml.safe_load((DOCS_DIR / "doc-map.yaml").read_text())
        documented = set()
        for server_tools in doc_map.get("mcp_tools", {}).values():
            for entry in server_tools:
                documented.add(entry.get("tool", ""))

        undocumented = []
        for server_file in [
            YOUK_DIR / "servers" / "core" / "src" / "server.py",
            YOUK_DIR / "servers" / "code" / "src" / "server.py",
        ]:
            if not server_file.exists():
                continue
            src = server_file.read_text()
            for m in re.finditer(r'@mcp\.tool\(\)\s*\nasync def (\w+)', src):
                name = m.group(1)
                if name not in documented:
                    undocumented.append(f"{server_file.name}:{name}")

        if undocumented:
            pytest.xfail(
                f"{len(undocumented)} MCP tool(s) not in doc-map.yaml (WARN):\n"
                + "\n".join(f"  {t}" for t in undocumented)
            )
