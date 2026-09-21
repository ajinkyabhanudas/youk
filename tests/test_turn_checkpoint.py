"""
Tests for turn_checkpoint — cheap save points between full checkpoints
(compact_context / task_checkpoint / session_end).

The property that matters most here, beyond comprehension_digest's own three
(project-scoped, render marks not deletes, oversize rejected), is concurrency:
this store is written by two agents (Claude, Codex) that can call checkpoint_now
at close to the same moment, so the read-modify-write cycle has to be locked
end to end, not just the write.
"""
from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))

import turn_checkpoint as tc  # noqa: E402


@pytest.fixture
def root(tmp_path):
    return tmp_path


SLUG = "test-project"


class TestWriteNote:
    def test_writes_a_valid_note(self, root):
        r = tc.write_note(root, SLUG, "decided to use option B", agent="claude")
        assert r["ok"] and r["written"]
        assert r["pending"] == 1

    def test_rejects_empty_note(self, root):
        r = tc.write_note(root, SLUG, "")
        assert r["ok"] is False
        assert r["error_type"] == "INPUT"

    def test_rejects_oversize_note(self, root):
        r = tc.write_note(root, SLUG, "x" * (tc.MAX_NOTE + 1))
        assert r["ok"] is False
        assert r["error_type"] == "INPUT"
        assert str(tc.MAX_NOTE) in r["error"]

    def test_accepts_note_at_exactly_the_cap(self, root):
        r = tc.write_note(root, SLUG, "x" * tc.MAX_NOTE)
        assert r["ok"] is True


class TestPendingAndRender:
    def test_pending_peek_is_non_destructive(self, root):
        tc.write_note(root, SLUG, "note one")
        first = tc.pending_notes(root, SLUG)
        second = tc.pending_notes(root, SLUG)
        assert len(first) == len(second) == 1

    def test_render_marks_consumed_not_deleted(self, root):
        tc.write_note(root, SLUG, "note one", agent="claude")
        r = tc.render_and_consume(root, SLUG)
        assert r["item_count"] == 1
        assert r["lines"] == ["- [claude] note one"]
        # consumed, not gone: a second render sees nothing pending
        r2 = tc.render_and_consume(root, SLUG)
        assert r2["item_count"] == 0
        # but the record itself is still on disk, tagged consumed
        raw = tc._read(tc.checkpoint_path(root, SLUG))
        assert len(raw) == 1 and raw[0]["consumed"] is True

    def test_render_on_empty_store_is_a_clean_no_op(self, root):
        r = tc.render_and_consume(root, SLUG)
        assert r == {"ok": True, "lines": [], "item_count": 0}

    def test_untagged_note_has_no_agent_prefix(self, root):
        tc.write_note(root, SLUG, "no agent given")
        r = tc.render_and_consume(root, SLUG)
        assert r["lines"] == ["- no agent given"]


class TestProjectScoping:
    def test_two_projects_do_not_share_notes(self, root):
        tc.write_note(root, "project-a", "a's note")
        tc.write_note(root, "project-b", "b's note")
        assert len(tc.pending_notes(root, "project-a")) == 1
        assert len(tc.pending_notes(root, "project-b")) == 1


def _concurrent_writer(tmp_str: str, slug: str, i: int) -> None:
    sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
    sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))
    import turn_checkpoint as tc_child
    tc_child.write_note(Path(tmp_str), slug, f"note {i}", agent="claude" if i % 2 == 0 else "codex")


class TestConcurrency:
    def test_simultaneous_writers_lose_no_notes(self, root):
        """The scenario this store exists for: Claude and Codex writing at once.
        A lock only around the write (not the read-modify-write cycle) would let
        this drop notes under real concurrency — sequential calls in one process
        can't exercise that, so this uses real OS processes."""
        n = 40
        procs = [
            multiprocessing.Process(target=_concurrent_writer, args=(str(root), SLUG, i))
            for i in range(n)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
            assert p.exitcode == 0

        pending = tc.pending_notes(root, SLUG)
        assert len(pending) == n, f"expected {n} notes, found {len(pending)} — a write was lost"
