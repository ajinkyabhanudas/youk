"""Auto-regeneration of stale generated docs — closes the detect->fix loop safely.

The load-bearing property: ONLY docs a script provably generates are regenerated. Source
files and hand-written prose are reported for a human, never auto-touched (that would be
the drifted-fix disaster). Which docs are generated is DISCOVERED from scripts/, not
hand-listed — so the feature is self-maintaining.
"""
from __future__ import annotations

from pathlib import Path

from doc_regen import (
    is_generated,
    regenerate_stale_generated_docs,
)

_YOUK = Path(__file__).parent.parent  # real repo root — scripts/ + STATS.md live here


def test_stats_md_is_discovered_generated():
    # Discovery finds export_stats.py writes STATS.md — no hand-registration.
    assert is_generated("STATS.md", youk_root=_YOUK)


def test_source_file_is_not_generated():
    assert not is_generated("servers/core/src/session.py", youk_root=_YOUK)


def test_handwritten_prose_is_not_generated():
    assert not is_generated("PHILOSOPHY.md", youk_root=_YOUK)


def test_dry_run_reports_generated_and_human_split():
    stale = [
        {"to_path": "STATS.md"},                       # discovered generated -> regenerate
        {"to_path": "PHILOSOPHY.md"},                  # prose -> needs human
        {"to_path": "servers/core/src/session.py"},    # source -> needs human
    ]
    result = regenerate_stale_generated_docs(stale, youk_root=_YOUK, dry_run=True)
    assert "STATS.md" in result["regenerated"]
    assert "PHILOSOPHY.md" in result["needs_human"]
    assert "servers/core/src/session.py" in result["needs_human"]


def test_source_files_never_regenerated_even_if_many():
    """No matter how many source files are stale, none are auto-touched."""
    stale = [{"to_path": f"servers/core/src/mod{i}.py"} for i in range(10)]
    result = regenerate_stale_generated_docs(stale, youk_root=_YOUK, dry_run=True)
    assert result["regenerated"] == []
    assert len(result["needs_human"]) == 10


def test_deduplicates_repeated_docs():
    stale = [{"to_path": "STATS.md"}, {"to_path": "STATS.md"}]
    result = regenerate_stale_generated_docs(stale, youk_root=_YOUK, dry_run=True)
    assert result["regenerated"] == ["STATS.md"]  # once, not twice


def test_empty_stale_is_safe():
    result = regenerate_stale_generated_docs([], youk_root=_YOUK, dry_run=True)
    assert result == {"regenerated": [], "needs_human": [], "errors": []}
