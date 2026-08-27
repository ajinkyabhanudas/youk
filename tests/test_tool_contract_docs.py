"""Documentation-completeness tests for docs/tool-contract-template.md.

Renamed from test_tool_contract_sentinel. The old name implied this verified tool
behaviour; it does not, and never did. It imports no server module and calls no tool.
It reads a markdown template and checks that the expected headings and fields are
present, which is worth doing but is a documentation check.

The name mattered. Three things named for contracts and verification — this file,
verify_mcp_contracts, and _audit_skill_quality — were all green while route_task
returned schema-invalid output and 14 routed skills could not load. Nobody looked for
execution coverage because the names suggested it already existed.

Execution coverage lives in tests/test_mcp_tool_contracts.py, which runs real tools and
asserts on what FastMCP serializes.
"""
from __future__ import annotations

from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "docs" / "tool-contract-template.md"

CRITICAL_TOOLS = [
    "session_start",
    "session_end",
    "task_checkpoint",
    "route_task",
    "mark_challenge_ran",
    "check_loop_dry",
    "check_nfr_gate",
    "check_challenge_gate",
]

CONTRACT_REQUIRED_FIELDS = [
    "Name:",
    "Description:",
    "Input schema:",
    "Output schema:",
    "Failure modes:",
    "Side effects:",
]


def _extract_contract_block(content: str, tool_name: str) -> str:
    """Extract the contract block for a tool from the markdown content."""
    start = content.find(f"### {tool_name}")
    if start == -1:
        return ""
    end = content.find("\n### ", start + 1)
    return content[start:end] if end != -1 else content[start:]


class TestToolContractSentinel:
    def test_template_file_exists(self):
        assert TEMPLATE_PATH.exists(), (
            f"docs/tool-contract-template.md missing — contract coverage unknown. "
            f"Expected at: {TEMPLATE_PATH}"
        )

    def test_all_critical_tools_have_contract_section(self):
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        missing = [t for t in CRITICAL_TOOLS if f"### {t}" not in content]
        assert not missing, (
            f"Missing contract sections for: {missing}. "
            "Add a '### <tool_name>' block to docs/tool-contract-template.md."
        )

    def test_each_contract_has_all_required_fields(self):
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        gaps: list[str] = []
        for tool in CRITICAL_TOOLS:
            block = _extract_contract_block(content, tool)
            if not block:
                gaps.append(f"{tool}: section missing entirely")
                continue
            for field in CONTRACT_REQUIRED_FIELDS:
                if field not in block:
                    gaps.append(f"{tool}: missing '{field}'")
        assert not gaps, "Contract field gaps:\n" + "\n".join(f"  - {g}" for g in gaps)

    def test_pending_build_task_field_documented_in_session_start(self):
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        session_start_block = _extract_contract_block(content, "session_start")
        assert "pending_build_task" in session_start_block, (
            "session_start contract is missing documentation for 'pending_build_task' field. "
            "Add it to the Output schema in docs/tool-contract-template.md."
        )

    def test_failure_modes_block_is_non_empty_for_each_tool(self):
        content = TEMPLATE_PATH.read_text(encoding="utf-8")
        empty_failures: list[str] = []
        for tool in CRITICAL_TOOLS:
            block = _extract_contract_block(content, tool)
            if not block:
                continue
            fail_start = block.find("Failure modes:")
            if fail_start == -1:
                empty_failures.append(tool)
                continue
            side_start = block.find("Side effects:", fail_start)
            fail_content = block[fail_start:side_start] if side_start != -1 else block[fail_start:]
            lines = [ln.strip() for ln in fail_content.splitlines() if ln.strip().startswith("-")]
            if not lines:
                empty_failures.append(tool)
        assert not empty_failures, (
            f"Failure modes section is empty for: {empty_failures}. "
            "Each tool must enumerate at least one failure condition."
        )
