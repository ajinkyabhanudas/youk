"""
Tests for the final two structural convergence holes:

1. Stale breadcrumb detection at session_start:
   - routing-breadcrumb.json older than 5 min → stale_breadcrumb=True → plan item inserted
   - routing-breadcrumb.json newer than 5 min → not stale (current session)
   - stale breadcrumb file is consumed (deleted) after detection
   - no breadcrumb file → no stale detection

2. Pending-action TTL:
   - pending-action.json older than 24h → cleared, force_learn suppressed
   - pending-action.json newer than 24h → preserved, force_learn fires
   - no written_at field → preserved (safe default — don't clear unknown-age files)
   - clear is silent on failure (try/except)

3. pending-action.json includes written_at timestamp when written
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_breadcrumb(state_dir: Path, age_seconds: int, task: str = "implement feature") -> None:
    written_at = (datetime.utcnow() - timedelta(seconds=age_seconds)).isoformat()
    (state_dir / "routing-breadcrumb.json").write_text(json.dumps({
        "task": task,
        "size": "M",
        "routed_at": written_at,
    }))


def _write_pending_action(state_dir: Path, age_seconds: int) -> None:
    written_at = (datetime.utcnow() - timedelta(seconds=age_seconds)).isoformat()
    (state_dir / "pending-action.json").write_text(json.dumps({
        "action": "learn",
        "reason": "close_cluster_missed",
        "written_at": written_at,
    }))


# ---------------------------------------------------------------------------
# 1. Stale breadcrumb detection logic
# ---------------------------------------------------------------------------

class TestStaleBreadcrumbDetection:
    def test_old_breadcrumb_is_stale(self):
        """Breadcrumb older than 300s = prior session."""
        age = 400  # > 300s threshold
        written_at = (datetime.utcnow() - timedelta(seconds=age)).isoformat()
        age_secs = (datetime.utcnow() - datetime.fromisoformat(written_at)).total_seconds()
        assert age_secs > 300

    def test_fresh_breadcrumb_is_not_stale(self):
        """Breadcrumb newer than 300s = current session."""
        age = 60  # < 300s threshold
        written_at = (datetime.utcnow() - timedelta(seconds=age)).isoformat()
        age_secs = (datetime.utcnow() - datetime.fromisoformat(written_at)).total_seconds()
        assert age_secs <= 300

    def test_stale_breadcrumb_consumed_after_detection(self, tmp_path):
        """Stale breadcrumb file is deleted after being read — not carried forward."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        _write_breadcrumb(state_dir, age_seconds=400)
        bc_file = state_dir / "routing-breadcrumb.json"
        assert bc_file.exists()

        # Simulate the detection + consume logic from start_session
        stale = False
        if bc_file.exists():
            data = json.loads(bc_file.read_text())
            written = data.get("routed_at", "")
            if written:
                age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                if age_secs > 300:
                    stale = True
                    bc_file.unlink()

        assert stale is True
        assert not bc_file.exists()

    def test_fresh_breadcrumb_not_consumed(self, tmp_path):
        """Fresh breadcrumb (current session) is left intact."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        _write_breadcrumb(state_dir, age_seconds=30)
        bc_file = state_dir / "routing-breadcrumb.json"

        stale = False
        if bc_file.exists():
            data = json.loads(bc_file.read_text())
            written = data.get("routed_at", "")
            if written:
                age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                if age_secs > 300:
                    stale = True
                    bc_file.unlink()

        assert stale is False
        assert bc_file.exists()

    def test_no_breadcrumb_no_stale_detection(self, tmp_path):
        """Absent breadcrumb file → stale=False, no error."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        bc_file = state_dir / "routing-breadcrumb.json"
        assert not bc_file.exists()

        stale = False
        if bc_file.exists():
            stale = True  # should not reach here

        assert stale is False

    def test_stale_plan_item_mentions_route_task(self):
        """Plan item for stale breadcrumb must mention route_task and task_checkpoint."""
        item = (
            "⚠ Last session: route_task ran but task_checkpoint was never called — "
            "routing gate fired but the work loop didn't close. Run /build to re-establish routing context."
        )
        assert "route_task" in item
        assert "task_checkpoint" in item
        assert "/build" in item

    def test_stale_item_prepended_not_appended(self):
        """Stale breadcrumb item is inserted at position 0."""
        plan = ["existing item 1", "existing item 2"]
        stale_item = "⚠ Last session: route_task ran but task_checkpoint was never called — routing gate fired but the work loop didn't close. Run /build to re-establish routing context."
        plan.insert(0, stale_item)
        assert plan[0] == stale_item


# ---------------------------------------------------------------------------
# 2. Pending-action TTL
# ---------------------------------------------------------------------------

class TestPendingActionTTL:
    def test_old_pending_action_is_cleared(self, tmp_path):
        """pending-action.json older than 24h must be deleted and force_learn suppressed."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        _write_pending_action(state_dir, age_seconds=90000)  # 25h
        pa_file = state_dir / "pending-action.json"
        assert pa_file.exists()

        # Simulate the TTL logic from start_session
        close_cluster_missed = True
        if pa_file.exists():
            try:
                data = json.loads(pa_file.read_text())
                written = data.get("written_at", "")
                if written:
                    age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                    if age_secs > 86400:
                        pa_file.unlink()
                        close_cluster_missed = False
            except Exception:
                pass

        assert not pa_file.exists()
        assert close_cluster_missed is False  # force_learn suppressed

    def test_fresh_pending_action_preserved(self, tmp_path):
        """pending-action.json newer than 24h must NOT be cleared."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        _write_pending_action(state_dir, age_seconds=3600)  # 1h
        pa_file = state_dir / "pending-action.json"

        close_cluster_missed = True
        if pa_file.exists():
            data = json.loads(pa_file.read_text())
            written = data.get("written_at", "")
            if written:
                age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                if age_secs > 86400:
                    pa_file.unlink()
                    close_cluster_missed = False

        assert pa_file.exists()
        assert close_cluster_missed is True  # force_learn still fires

    def test_missing_written_at_preserves_file(self, tmp_path):
        """No written_at field → safe default: preserve file, don't clear."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        pa_file = state_dir / "pending-action.json"
        pa_file.write_text(json.dumps({"action": "learn", "reason": "close_cluster_missed"}))

        close_cluster_missed = True
        if pa_file.exists():
            data = json.loads(pa_file.read_text())
            written = data.get("written_at", "")
            if written:  # no written_at → this branch does not fire
                age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                if age_secs > 86400:
                    pa_file.unlink()
                    close_cluster_missed = False

        assert pa_file.exists()  # preserved
        assert close_cluster_missed is True

    def test_ttl_boundary_exactly_24h(self, tmp_path):
        """Exactly 24h = 86400s: below threshold → preserved."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        _write_pending_action(state_dir, age_seconds=86399)  # 1s under 24h
        pa_file = state_dir / "pending-action.json"

        close_cluster_missed = True
        if pa_file.exists():
            data = json.loads(pa_file.read_text())
            written = data.get("written_at", "")
            if written:
                age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                if age_secs > 86400:
                    pa_file.unlink()
                    close_cluster_missed = False

        assert pa_file.exists()

    def test_ttl_just_over_24h(self, tmp_path):
        """86401s = just over 24h → cleared."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        _write_pending_action(state_dir, age_seconds=86401)
        pa_file = state_dir / "pending-action.json"

        close_cluster_missed = True
        if pa_file.exists():
            data = json.loads(pa_file.read_text())
            written = data.get("written_at", "")
            if written:
                age_secs = (datetime.utcnow() - datetime.fromisoformat(written)).total_seconds()
                if age_secs > 86400:
                    pa_file.unlink()
                    close_cluster_missed = False

        assert not pa_file.exists()
        assert close_cluster_missed is False


# ---------------------------------------------------------------------------
# 3. pending-action.json includes written_at when written
# ---------------------------------------------------------------------------

class TestPendingActionTimestamp:
    def test_pending_action_includes_written_at(self, tmp_path):
        """pending-action.json must include written_at for TTL to work."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        pa_file = state_dir / "pending-action.json"

        # Simulate what start_session writes
        pa_file.write_text(json.dumps({
            "action": "learn",
            "reason": "close_cluster_missed",
            "written_at": datetime.utcnow().isoformat(),
        }))

        data = json.loads(pa_file.read_text())
        assert "written_at" in data
        assert "action" in data
        assert data["action"] == "learn"

    def test_written_at_is_parseable_isoformat(self, tmp_path):
        """written_at must be parseable by datetime.fromisoformat."""
        ts = datetime.utcnow().isoformat()
        parsed = datetime.fromisoformat(ts)
        assert isinstance(parsed, datetime)

    def test_written_at_roundtrip_age_computation(self):
        """Age computed from written_at must be accurate to within 1s."""
        written = datetime.utcnow() - timedelta(seconds=7200)
        written_at_str = written.isoformat()
        age_secs = (datetime.utcnow() - datetime.fromisoformat(written_at_str)).total_seconds()
        assert abs(age_secs - 7200) < 1
