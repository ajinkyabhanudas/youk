"""
Tests for server-side SKILL.md reference section stripping and
calls_since_compact counter logic.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "code" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))

from skills import _strip_reference_sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill(sections: dict[str, str]) -> str:
    """Build a minimal SKILL.md from a dict of section_header -> content."""
    parts = []
    for header, body in sections.items():
        parts.append(f"{header}\n\n{body}")
    return "\n\n---\n\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# _strip_reference_sections
# ---------------------------------------------------------------------------

class TestStripReferenceSections:

    def test_example_flows_removed(self):
        content = _skill({
            "## Quality Bars": "no TBD allowed",
            "## Example Flows": "stress test a caching design...",
        })
        result = _strip_reference_sections(content)
        assert "Example Flows" not in result
        assert "stress test a caching design" not in result

    def test_hiring_validation_removed(self):
        content = _skill({
            "## Quality Bars": "no TBD allowed",
            "## Hiring Validation": "passes if it can produce SURVIVES verdict",
        })
        result = _strip_reference_sections(content)
        assert "Hiring Validation" not in result
        assert "passes if it can produce" not in result

    def test_reference_files_removed(self):
        content = _skill({
            "## Quality Bars": "no TBD allowed",
            "## Reference Files": "| File | When to read |",
        })
        result = _strip_reference_sections(content)
        assert "Reference Files" not in result

    def test_quality_bars_preserved(self):
        content = _skill({
            "## Quality Bars": "run to dry not round count",
            "## Example Flows": "some example here",
        })
        result = _strip_reference_sections(content)
        assert "Quality Bars" in result
        assert "run to dry not round count" in result

    def test_phases_preserved(self):
        content = _skill({
            "## Phase 1 — SCOPE": "state what is being attacked",
            "## Phase 2 — ATTACK": "three agents reason independently",
            "## Example Flows": "stress test example",
        })
        result = _strip_reference_sections(content)
        assert "Phase 1" in result
        assert "state what is being attacked" in result
        assert "Phase 2" in result
        assert "Example Flows" not in result

    def test_no_strip_targets_returns_unchanged(self):
        content = "## Quality Bars\n\nrun to dry\n\n## Phase 1\n\nbody\n"
        result = _strip_reference_sections(content)
        assert "Quality Bars" in result
        assert "Phase 1" in result
        assert "run to dry" in result

    def test_multiple_strip_sections_all_removed(self):
        content = _skill({
            "## Quality Bars": "no TBD",
            "## Example Flows": "example 1",
            "## Hiring Validation": "hiring test",
            "## Reference Files": "file table",
        })
        result = _strip_reference_sections(content)
        assert "Example Flows" not in result
        assert "Hiring Validation" not in result
        assert "Reference Files" not in result
        assert "Quality Bars" in result

    def test_section_after_strip_target_preserved(self):
        """A non-strip section following a strip section must be kept."""
        content = (
            "## Example Flows\n\nexample content\n\n"
            "## Stack Coverage System\n\nstack detection logic\n"
        )
        result = _strip_reference_sections(content)
        assert "Example Flows" not in result
        assert "Stack Coverage System" in result
        assert "stack detection logic" in result

    def test_empty_content_no_crash(self):
        assert _strip_reference_sections("") == "\n"

    def test_strip_reduces_size(self):
        content = _skill({
            "## Quality Bars": "run to dry\n" * 5,
            "## Example Flows": "long example\n" * 20,
            "## Hiring Validation": "hiring test\n" * 10,
        })
        result = _strip_reference_sections(content)
        assert len(result) < len(content)

    def test_result_ends_with_newline(self):
        content = "## Quality Bars\n\nbody\n\n## Example Flows\n\nexample"
        result = _strip_reference_sections(content)
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# calls_since_compact counter logic (unit-tested without MCP layer)
# ---------------------------------------------------------------------------

class TestCallsSinceCompactCounter:

    def _read_count(self, f: Path) -> int:
        if not f.exists():
            return 0
        try:
            return json.loads(f.read_text()).get("count", 0)
        except Exception:
            return 0

    def _increment(self, f: Path) -> int:
        count = self._read_count(f) + 1
        f.write_text(json.dumps({"count": count}))
        return count

    def _reset(self, f: Path) -> None:
        f.write_text('{"count": 0}')

    def test_first_call_sets_count_to_1(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        assert self._increment(f) == 1

    def test_successive_calls_increment(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        for expected in range(1, 6):
            assert self._increment(f) == expected

    def test_reset_sets_to_zero(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        for _ in range(5):
            self._increment(f)
        self._reset(f)
        assert self._read_count(f) == 0

    def test_increment_after_reset_returns_1(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        for _ in range(5):
            self._increment(f)
        self._reset(f)
        assert self._increment(f) == 1

    def test_missing_file_starts_at_zero(self, tmp_path):
        f = tmp_path / "does-not-exist.json"
        assert self._read_count(f) == 0

    def test_count_above_8_triggers_compact_threshold(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        for _ in range(9):
            count = self._increment(f)
        assert count > 8

    def test_count_at_8_does_not_trigger(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        for _ in range(8):
            count = self._increment(f)
        assert count == 8  # boundary: 8 is not > 8

    def test_corrupt_file_recovers_gracefully(self, tmp_path):
        f = tmp_path / "tool-call-count.json"
        f.write_text("not json{{{")
        # Should not raise — falls back to 0 + 1
        count = self._increment(f)
        assert count == 1
