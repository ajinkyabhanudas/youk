"""
Tests for CAP-10: Tiered Knowledge Index.

Coverage:
- IndexBuild: build from scratch, idempotent rebuild preserving usage
- IncrementalRow: new entry appears on rebuild
- UsageFold: fold updates last-used/use-count
- SessionStartDiet: load_index_summaries loads summaries not bodies; R10 line format
- LifecycleHotCold: HOT→COLD demotion rule
- LifecycleColdArchive: COLD→ARCHIVE emits proposal, does not move file
- ArchiveInvariant: approved archival moves file, never unlinks (file count conserved)
- Resurrection: resurrect restores COLD entry to HOT
- OrgScoreInvariant: score-neutrality — presence of index does not change org_score
"""
from __future__ import annotations
import json
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knowledge_file(root: Path, rel: str, content: str = "") -> Path:
    """Create a file in knowledge/ at the given relative path."""
    p = root / "knowledge" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content or f"Summary line for {p.stem}.\n\nBody text that should NOT appear in summaries.")
    return p


def _sentinel_body(stem: str) -> str:
    """Return body text that must NOT appear in loaded summaries."""
    return f"BODY_SENTINEL_DO_NOT_LOAD_{stem.upper()}"


def _make_knowledge_file_with_sentinel(root: Path, rel: str, summary: str) -> Path:
    """Create a knowledge file with a clear summary line and a body sentinel."""
    stem = Path(rel).stem
    p = root / "knowledge" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{summary}\n\n{_sentinel_body(stem)}\n")
    return p


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ki_root(tmp_path, monkeypatch):
    """Isolated root with knowledge/ and state/ dirs, knowledge_index module patched."""
    root = tmp_path / "youk"
    (root / "knowledge" / "domain").mkdir(parents=True)
    (root / "knowledge" / "archive").mkdir(parents=True)
    (root / "state").mkdir(parents=True)

    import knowledge_index
    monkeypatch.setattr(knowledge_index, "YOUK_ROOT", root)
    monkeypatch.setattr(knowledge_index, "_INDEX_FILE", root / "knowledge" / "INDEX.md")
    monkeypatch.setattr(knowledge_index, "_USAGE_LOG", root / "state" / "knowledge-usage.jsonl")
    monkeypatch.setattr(knowledge_index, "_ARCHIVE_DIR", root / "knowledge" / "archive")
    return root


# ---------------------------------------------------------------------------
# TestIndexBuild
# ---------------------------------------------------------------------------

class TestIndexBuild:
    def test_build_creates_index_file(self, ki_root):
        from knowledge_index import rebuild_knowledge_index
        _make_knowledge_file(ki_root, "domain/postgres.md")
        result = rebuild_knowledge_index(ki_root)
        assert (ki_root / "knowledge" / "INDEX.md").exists()
        assert result["entries_total"] == 1
        assert result["hot"] == 1

    def test_build_idempotent_preserves_usage(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, fold_usage_into_index, append_knowledge_usage
        _make_knowledge_file(ki_root, "domain/redis.md")
        rebuild_knowledge_index(ki_root)
        # Simulate usage then fold
        append_knowledge_usage("domain--redis-md", ki_root)
        fold_usage_into_index(ki_root)
        # Rebuild — must preserve use_count
        result = rebuild_knowledge_index(ki_root)
        index_text = (ki_root / "knowledge" / "INDEX.md").read_text()
        # use_count should still be 1 after rebuild (not reset to 0)
        assert "| 1 |" in index_text or "| 1|" in index_text or " 1 |" in index_text
        assert result["entries_total"] == 1

    def test_skips_archive_dir(self, ki_root):
        from knowledge_index import rebuild_knowledge_index
        _make_knowledge_file(ki_root, "domain/active.md")
        _make_knowledge_file(ki_root, "archive/old.md")  # should be skipped
        result = rebuild_knowledge_index(ki_root)
        assert result["entries_total"] == 1

    def test_skips_special_names(self, ki_root):
        from knowledge_index import rebuild_knowledge_index
        for name in ("gaps.md", "INDEX.md", "PENDING.md", "_README.md"):
            _make_knowledge_file(ki_root, f"domain/{name}")
        _make_knowledge_file(ki_root, "domain/real.md")
        result = rebuild_knowledge_index(ki_root)
        assert result["entries_total"] == 1


# ---------------------------------------------------------------------------
# TestIncrementalRow
# ---------------------------------------------------------------------------

class TestIncrementalRow:
    def test_new_entry_appears_on_rebuild(self, ki_root):
        from knowledge_index import rebuild_knowledge_index
        _make_knowledge_file(ki_root, "domain/a.md")
        rebuild_knowledge_index(ki_root)
        _make_knowledge_file(ki_root, "domain/b.md")
        result = rebuild_knowledge_index(ki_root)
        assert result["entries_total"] == 2


# ---------------------------------------------------------------------------
# TestUsageFold
# ---------------------------------------------------------------------------

class TestUsageFold:
    def test_fold_updates_use_count_and_last_used(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, fold_usage_into_index, _path_to_id
        _make_knowledge_file(ki_root, "domain/topic.md")
        rebuild_knowledge_index(ki_root)

        # Append usage event manually
        rel = "domain/topic.md"
        entry_id = _path_to_id(rel)
        usage_log = ki_root / "state" / "knowledge-usage.jsonl"
        usage_log.write_text(json.dumps({"id": entry_id, "date": "2026-07-15"}) + "\n")

        result = fold_usage_into_index(ki_root)
        assert result["entries_updated"] == 1
        assert result["events_processed"] == 1

        # Read back INDEX.md and confirm use_count increased
        index_text = (ki_root / "knowledge" / "INDEX.md").read_text()
        assert "2026-07-15" in index_text
        # use_count went from 0 → 1
        assert " | 1 |" in index_text

    def test_fold_is_additive_not_reset(self, ki_root):
        """Folding twice accumulates, not resets."""
        from knowledge_index import rebuild_knowledge_index, fold_usage_into_index, _path_to_id
        _make_knowledge_file(ki_root, "domain/acc.md")
        rebuild_knowledge_index(ki_root)
        entry_id = _path_to_id("domain/acc.md")
        usage_log = ki_root / "state" / "knowledge-usage.jsonl"
        # Write two events
        usage_log.write_text(
            json.dumps({"id": entry_id, "date": "2026-07-14"}) + "\n"
            + json.dumps({"id": entry_id, "date": "2026-07-15"}) + "\n"
        )
        fold_usage_into_index(ki_root)
        index_text = (ki_root / "knowledge" / "INDEX.md").read_text()
        # use_count should be 2
        assert " | 2 |" in index_text


# ---------------------------------------------------------------------------
# TestSessionStartDiet
# ---------------------------------------------------------------------------

class TestSessionStartDiet:
    def test_load_summaries_not_bodies(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, load_index_summaries
        stem = "neural"
        _make_knowledge_file_with_sentinel(ki_root, "domain/neural.md", f"One-line about {stem}")
        rebuild_knowledge_index(ki_root)

        result = load_index_summaries(ki_root)
        combined = " ".join(result["summaries"])
        # Summary line must appear
        assert "One-line about neural" in combined
        # Body sentinel must NOT appear
        assert _sentinel_body(stem) not in combined

    def test_r10_line_format(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, load_index_summaries
        _make_knowledge_file(ki_root, "domain/a.md")
        _make_knowledge_file(ki_root, "domain/b.md")
        rebuild_knowledge_index(ki_root)
        result = load_index_summaries(ki_root)
        r10 = result["r10_line"]
        # Must contain R10 tokens
        assert "knowledge:" in r10
        assert "hot" in r10
        assert "cold" in r10
        assert "archived" in r10
        assert "summaries" in r10
        # Byte label (ends with B)
        assert "B)" in r10

    def test_no_index_returns_zero_line(self, ki_root):
        from knowledge_index import load_index_summaries
        result = load_index_summaries(ki_root)
        assert result["summaries"] == []
        assert "0 hot" in result["r10_line"]
        assert result["index_exists"] is False

    def test_only_hot_summaries_loaded(self, ki_root):
        """COLD entries must not appear in summaries."""
        from knowledge_index import rebuild_knowledge_index, load_index_summaries, _path_to_id
        _make_knowledge_file(ki_root, "domain/hot-entry.md", "HOT summary line\n\nBody")
        _make_knowledge_file(ki_root, "domain/cold-entry.md", "COLD summary line\n\nBody")
        rebuild_knowledge_index(ki_root)

        # Manually demote one entry to COLD
        cold_id = _path_to_id("domain/cold-entry.md")
        index_file = ki_root / "knowledge" / "INDEX.md"
        text = index_file.read_text()
        text = text.replace(f"| {cold_id} | HOT |", f"| {cold_id} | COLD |")
        index_file.write_text(text)

        result = load_index_summaries(ki_root)
        combined = " ".join(result["summaries"])
        assert "HOT summary line" in combined
        assert "COLD summary line" not in combined


# ---------------------------------------------------------------------------
# TestLifecycleHotCold
# ---------------------------------------------------------------------------

class TestLifecycleHotCold:
    def test_hot_to_cold_on_sessions_threshold(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, apply_lifecycle_rules
        _make_knowledge_file(ki_root, "domain/stale.md")
        rebuild_knowledge_index(ki_root)

        # 15 dummy session records (no date → sessions_unused counts them all)
        sessions = [{"raw": ""} for _ in range(15)]
        result = apply_lifecycle_rules(ki_root, sessions)
        assert result["demoted_to_cold"] == 1
        index_text = (ki_root / "knowledge" / "INDEX.md").read_text()
        assert "COLD" in index_text

    def test_hot_not_demoted_below_threshold(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, apply_lifecycle_rules
        _make_knowledge_file(ki_root, "domain/fresh.md")
        rebuild_knowledge_index(ki_root)
        sessions = [{"raw": ""} for _ in range(5)]
        result = apply_lifecycle_rules(ki_root, sessions)
        assert result["demoted_to_cold"] == 0


# ---------------------------------------------------------------------------
# TestLifecycleColdArchive
# ---------------------------------------------------------------------------

class TestLifecycleColdArchive:
    def test_cold_to_archive_emits_proposal_not_move(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, apply_lifecycle_rules
        _make_knowledge_file(ki_root, "domain/ancient.md")
        rebuild_knowledge_index(ki_root)

        # Force entry to COLD with old last_used
        index_file = ki_root / "knowledge" / "INDEX.md"
        text = index_file.read_text()
        entry_id = "domain--ancient-md"
        text = text.replace(f"| {entry_id} | HOT |", f"| {entry_id} | COLD |")
        # Set old last_used date
        text = text.replace(f"| {entry_id} | COLD | ", f"| {entry_id} | COLD | ")
        # Patch last_used in the row to trigger >90d threshold
        import re
        text = re.sub(
            r"(\| " + re.escape(entry_id) + r" \| COLD \|[^\|]*\|[^\|]*\|)\s*\|",
            r"\1 2025-01-01 |",
            text,
        )
        index_file.write_text(text)

        # Force the last_used to old date properly
        rows_text = index_file.read_text()
        # Rebuild index with correct last_used
        from knowledge_index import _parse_index, _render_index
        rows, archive_ids = _parse_index(rows_text)
        for row in rows:
            if row["id"] == entry_id:
                row["last_used"] = "2025-01-01"
        index_file.write_text(_render_index(rows, archive_ids, "2026-07-18"))

        result = apply_lifecycle_rules(ki_root, [])
        assert len(result["archive_proposals"]) == 1
        assert result["archive_proposals"][0]["id"] == entry_id
        # File must still exist (not moved)
        assert (ki_root / "knowledge" / "domain" / "ancient.md").exists()


# ---------------------------------------------------------------------------
# TestArchiveInvariant (never-delete: file count conserved)
# ---------------------------------------------------------------------------

class TestArchiveInvariant:
    def test_approved_archive_moves_file_not_deletes(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, archive_entry, _path_to_id
        _make_knowledge_file(ki_root, "domain/to_archive.md")
        rebuild_knowledge_index(ki_root)

        entry_id = _path_to_id("domain/to_archive.md")

        # Force COLD so archive_entry can find it
        index_file = ki_root / "knowledge" / "INDEX.md"
        text = index_file.read_text().replace(
            f"| {entry_id} | HOT |", f"| {entry_id} | COLD |"
        )
        index_file.write_text(text)

        result = archive_entry(entry_id, ki_root)
        assert result["archived"] is True
        # Never-delete invariant: file count conserved
        assert result["conserved"] is True
        assert result["file_count_before"] == result["file_count_after"]
        # Original path gone, archive path exists
        assert not (ki_root / "knowledge" / "domain" / "to_archive.md").exists()
        assert Path(result["to_path"]).exists()

    def test_archive_appears_in_index_archive_section(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, archive_entry, _path_to_id
        _make_knowledge_file(ki_root, "domain/entry_x.md")
        rebuild_knowledge_index(ki_root)
        entry_id = _path_to_id("domain/entry_x.md")
        # Force COLD
        index_file = ki_root / "knowledge" / "INDEX.md"
        text = index_file.read_text().replace(
            f"| {entry_id} | HOT |", f"| {entry_id} | COLD |"
        )
        index_file.write_text(text)
        archive_entry(entry_id, ki_root)
        index_text = (ki_root / "knowledge" / "INDEX.md").read_text()
        assert "## Archive" in index_text
        assert entry_id in index_text


# ---------------------------------------------------------------------------
# TestResurrection
# ---------------------------------------------------------------------------

class TestResurrection:
    def test_resurrect_cold_entry_to_hot(self, ki_root):
        from knowledge_index import rebuild_knowledge_index, resurrect_entry, _path_to_id
        _make_knowledge_file(ki_root, "domain/dormant.md")
        rebuild_knowledge_index(ki_root)
        entry_id = _path_to_id("domain/dormant.md")
        # Demote to COLD
        index_file = ki_root / "knowledge" / "INDEX.md"
        text = index_file.read_text().replace(
            f"| {entry_id} | HOT |", f"| {entry_id} | COLD |"
        )
        index_file.write_text(text)
        result = resurrect_entry(entry_id, ki_root)
        assert result["resurrected"] is True
        assert result["from_tier"] == "COLD"
        index_text = (ki_root / "knowledge" / "INDEX.md").read_text()
        # Entry should be HOT now
        assert f"| {entry_id} | HOT |" in index_text


# ---------------------------------------------------------------------------
# TestOrgScoreInvariant (CAP-10 score-neutrality)
# ---------------------------------------------------------------------------

class TestOrgScoreInvariant:
    def test_org_score_unchanged_by_index_presence(self, tmp_path, monkeypatch):
        """Org score must be identical whether INDEX.md exists or not."""
        import health
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        monkeypatch.setattr(health, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(health, "CLAUDE_ROOT", tmp_path)
        monkeypatch.setattr(health, "AUDIT_DIR", audit_dir)
        monkeypatch.setattr(health, "PROPOSALS_FILE", tmp_path / "PENDING.md")

        score_without = health._score_org([])

        # Add a knowledge INDEX.md
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "INDEX.md").write_text(
            "# knowledge/INDEX.md\n\n| id | tier | summary | path | last-used | use-count |\n"
            "|----|------|---------|------|-----------|-----------|)\n"
            "| domain--test-md | HOT | test entry | knowledge/domain/test.md | 2026-07-10 | 3 |\n"
        )

        score_with = health._score_org([])
        assert score_without == score_with
