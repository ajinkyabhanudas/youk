"""
Tests for comprehension_digest — the persistence half of the comprehension channel.

The three properties worth guarding are the ones the design turns on: render marks
rather than deletes (so an interrupted session hands off), the store is project-scoped
(so the next session can find it at all), and oversize input is rejected rather than
truncated (so the store cannot quietly become a transcript log).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))

import comprehension_digest as cd  # noqa: E402


@pytest.fixture
def root(tmp_path):
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestAdmit:
    def test_admits_a_valid_item(self, root):
        r = cd.admit(root, "tradeoff", "chose append-only over delete-on-read")
        assert r["ok"] and r["admitted"]
        assert r["pending"] == 1

    def test_rejects_unknown_kind(self, root):
        r = cd.admit(root, "insight", "something")
        assert r["ok"] is False
        assert r["error_type"] == "INPUT"
        assert "tradeoff" in r["error"]

    def test_rejects_empty_takeaway(self, root):
        assert cd.admit(root, "pattern", "   ")["ok"] is False

    def test_rejects_oversize_takeaway_rather_than_truncating(self, root):
        """Truncating would store a transcript-shaped payload under a cap that claims
        the store holds takeaways. Rejection keeps the claim true."""
        r = cd.admit(root, "pattern", "x" * (cd.MAX_TAKEAWAY + 1))
        assert r["ok"] is False
        assert r["error_type"] == "INPUT"
        assert cd.pending(root) == []

    def test_accepts_takeaway_exactly_at_cap(self, root):
        assert cd.admit(root, "pattern", "x" * cd.MAX_TAKEAWAY)["ok"] is True

    def test_rejects_oversize_context(self, root):
        r = cd.admit(root, "pattern", "fine", context="y" * (cd.MAX_CONTEXT + 1))
        assert r["ok"] is False

    def test_duplicate_pending_item_is_not_double_entered(self, root):
        cd.admit(root, "tradeoff", "same lesson")
        second = cd.admit(root, "tradeoff", "same lesson")
        assert second["ok"] is True
        assert second["admitted"] is False
        assert len(cd.pending(root)) == 1

    def test_same_takeaway_readmitted_after_surfacing(self, root):
        """A lesson recurring later is signal, not a duplicate."""
        cd.admit(root, "tradeoff", "same lesson")
        cd.render(root)
        assert cd.admit(root, "tradeoff", "same lesson")["admitted"] is True
        assert len(cd.pending(root)) == 1

    def test_records_the_session_that_admitted(self, root):
        cd.admit(root, "pattern", "p", session_slug="youk-94")
        assert cd.pending(root)[0]["session_slug"] == "youk-94"


class TestRender:
    def test_empty_digest_renders_empty(self, root):
        r = cd.render(root)
        assert r["ok"] and r["view"] == "" and r["item_count"] == 0

    def test_renders_grouped_with_foreclosures_first(self, root):
        cd.admit(root, "pattern", "a pattern")
        cd.admit(root, "foreclosure", "a door closed")
        view = cd.render(root)["view"]
        assert view.index("Foreclosed") < view.index("Patterns")

    def test_render_marks_but_does_not_delete(self, root):
        """The file is the handoff payload — deleting it destroys the resume case."""
        cd.admit(root, "tradeoff", "kept")
        cd.render(root)
        records = json.loads(
            "[" + ",".join(cd.digest_path(root).read_text().splitlines()) + "]"
        )
        assert len(records) == 1
        assert records[0]["surfaced"] is True

    def test_second_render_is_empty(self, root):
        cd.admit(root, "tradeoff", "shown once")
        assert cd.render(root)["item_count"] == 1
        assert cd.render(root)["item_count"] == 0

    def test_preview_does_not_consume(self, root):
        cd.admit(root, "tradeoff", "peek")
        assert cd.render(root, mark_surfaced=False)["item_count"] == 1
        assert len(cd.pending(root)) == 1

    def test_origin_sessions_surface_on_handoff(self, root):
        cd.admit(root, "pattern", "from an earlier session", session_slug="youk-93")
        assert cd.render(root)["origin_sessions"] == ["youk-93"]

    def test_no_origin_key_when_nothing_pending(self, root):
        assert "origin_sessions" not in cd.render(root)


class TestCrossSessionHandoff:
    def test_items_from_an_interrupted_session_survive_for_the_next_one(self, root):
        """The whole point: session A admits and never renders, session B picks it up."""
        cd.admit(root, "foreclosure", "A never got to show this", session_slug="youk-1")
        # session A ends without calling render at all
        result = cd.render(root)
        assert result["item_count"] == 1
        assert "A never got to show this" in result["view"]
        assert result["origin_sessions"] == ["youk-1"]

    def test_path_is_project_scoped_not_slug_scoped(self, root):
        """A slug-scoped path would be invisible to the next session, which is the
        writer/reader mismatch that orphaned every gate write until PR #109."""
        cd.admit(root, "pattern", "p", session_slug="youk-1")
        assert cd.digest_path(root) == root / "state" / "comprehension-digest.jsonl"
        assert not (root / "state" / "sessions").exists()

    def test_path_resolution_creates_nothing(self, root):
        cd.digest_path(root)
        assert not (root / "state" / "comprehension-digest.jsonl").exists()


class TestDurability:
    def test_corrupt_line_does_not_hide_the_rest(self, root):
        cd.admit(root, "pattern", "good one")
        path = cd.digest_path(root)
        path.write_text("{not json\n" + path.read_text())
        assert len(cd.pending(root)) == 1

    def test_unsurfaced_records_are_never_pruned(self, root, monkeypatch):
        """Pruning a pending item would silently discard something nobody has read."""
        monkeypatch.setattr(cd, "MAX_RECORDS", 5)
        for i in range(20):
            cd.admit(root, "pattern", f"pending {i}")
        assert len(cd.pending(root)) == 20

    def test_surfaced_records_are_pruned_oldest_first(self, root, monkeypatch):
        monkeypatch.setattr(cd, "MAX_RECORDS", 5)
        for i in range(10):
            cd.admit(root, "pattern", f"old {i}")
        cd.render(root)
        cd.admit(root, "pattern", "new one")
        remaining = [json.loads(ln) for ln in cd.digest_path(root).read_text().splitlines()]
        assert len(remaining) <= 5
        assert any(r["takeaway"] == "new one" for r in remaining)
        assert not any(r["takeaway"] == "old 0" for r in remaining)

    def test_write_failure_surfaces_as_system_error(self, root, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(cd, "_write", _boom)
        r = cd.admit(root, "pattern", "never lands")
        assert r["ok"] is False
        assert r["error_type"] == "SYSTEM"

    def test_missing_file_reads_as_empty(self, root):
        assert cd.pending(root) == []
