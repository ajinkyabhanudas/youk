"""Auto-regeneration of stale generated docs — closes the detect->fix loop safely.

The load-bearing property: ONLY registered generated docs are ever regenerated. Source
files and hand-written prose are reported for a human, never auto-touched (that would be
the drifted-fix disaster).
"""
from __future__ import annotations

from doc_regen import (
    GENERATED_DOCS,
    is_generated,
    regenerate_stale_generated_docs,
)


def test_stats_md_is_registered_generated():
    assert is_generated("STATS.md")


def test_source_file_is_not_generated():
    # A .py source file must never be classified as auto-regenerable.
    assert not is_generated("servers/core/src/session.py")


def test_handwritten_prose_is_not_generated():
    assert not is_generated("PHILOSOPHY.md")


def test_dry_run_reports_generated_and_human_split():
    stale = [
        {"to_path": "STATS.md"},                       # generated -> would regenerate
        {"to_path": "PHILOSOPHY.md"},                  # prose -> needs human
        {"to_path": "servers/core/src/session.py"},    # source -> needs human
    ]
    result = regenerate_stale_generated_docs(stale, dry_run=True)
    assert "STATS.md" in result["regenerated"]
    assert "PHILOSOPHY.md" in result["needs_human"]
    assert "servers/core/src/session.py" in result["needs_human"]


def test_source_files_never_regenerated_even_if_many():
    """No matter how many source files are stale, none are auto-touched."""
    stale = [{"to_path": f"servers/core/src/mod{i}.py"} for i in range(10)]
    result = regenerate_stale_generated_docs(stale, dry_run=True)
    assert result["regenerated"] == []
    assert len(result["needs_human"]) == 10


def test_deduplicates_repeated_docs():
    stale = [{"to_path": "STATS.md"}, {"to_path": "STATS.md"}]
    result = regenerate_stale_generated_docs(stale, dry_run=True)
    assert result["regenerated"] == ["STATS.md"]  # once, not twice


def test_empty_stale_is_safe():
    result = regenerate_stale_generated_docs([], dry_run=True)
    assert result == {"regenerated": [], "needs_human": [], "errors": []}


def test_registry_commands_are_lists_not_shell_strings():
    """Commands must be arg-lists (no shell injection surface), not shell strings."""
    for doc, cmd in GENERATED_DOCS.items():
        assert isinstance(cmd, list), f"{doc} command must be a list"
        assert all(isinstance(part, str) for part in cmd)
