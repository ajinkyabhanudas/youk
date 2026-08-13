"""Unit tests for state_paths — slug-scoped state path resolution.

Tests cover:
  - slug_state_dir: creates and returns correct per-slug path
  - current_session_slug: mtime-based resolution, staleness gate, unknown fallback
  - atomic_write: creates file, idempotent, handles concurrent writes
  - gate_flag_path: correct slug-scoped path construction
  - open_json_payload: contains required fields including written_at
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

import state_paths


@pytest.fixture(autouse=True)
def isolated_youk_root(tmp_path, monkeypatch):
    """Point state_paths.YOUK_ROOT at a fresh tmp dir for every test."""
    root = tmp_path / "youk"
    (root / "state" / "sessions").mkdir(parents=True)
    monkeypatch.setattr(state_paths, "YOUK_ROOT", root)
    return root


# ── slug_state_dir ────────────────────────────────────────────────────────────

class TestSlugStateDir:
    def test_returns_per_slug_path(self, isolated_youk_root):
        p = state_paths.slug_state_dir("youk")
        assert p == isolated_youk_root / "state" / "sessions" / "youk"

    def test_creates_dir_on_first_use(self, isolated_youk_root):
        p = state_paths.slug_state_dir("canopy")
        assert p.is_dir()

    def test_idempotent_on_repeated_calls(self, isolated_youk_root):
        state_paths.slug_state_dir("youk")
        state_paths.slug_state_dir("youk")  # must not raise
        assert (isolated_youk_root / "state" / "sessions" / "youk").is_dir()


# ── current_session_slug ──────────────────────────────────────────────────────

class TestCurrentSessionSlug:
    def test_returns_unknown_when_no_sessions_dir(self, tmp_path, monkeypatch):
        root = tmp_path / "empty"
        root.mkdir()
        monkeypatch.setattr(state_paths, "YOUK_ROOT", root)
        assert state_paths.current_session_slug() == "unknown"

    def test_returns_unknown_when_sessions_dir_empty(self, isolated_youk_root):
        assert state_paths.current_session_slug() == "unknown"

    def test_returns_slug_from_single_open_json(self, isolated_youk_root):
        slug_dir = isolated_youk_root / "state" / "sessions" / "youk"
        slug_dir.mkdir(parents=True, exist_ok=True)
        (slug_dir / "open.json").write_text(json.dumps({
            "slug": "youk",
            "written_at": time.time(),
        }))
        assert state_paths.current_session_slug() == "youk"

    def test_prefers_most_recent_mtime(self, isolated_youk_root):
        sessions = isolated_youk_root / "state" / "sessions"
        for name in ("older", "newer"):
            d = sessions / name
            d.mkdir()
            (d / "open.json").write_text(json.dumps({
                "slug": name,
                "written_at": time.time(),
            }))

        older = sessions / "older" / "open.json"
        newer = sessions / "newer" / "open.json"
        # Force older to have an older mtime
        old_ts = time.time() - 60
        os.utime(older, (old_ts, old_ts))
        # Ensure newer has the latest mtime
        os.utime(newer, (time.time(), time.time()))

        assert state_paths.current_session_slug() == "newer"

    def test_skips_stale_entries(self, isolated_youk_root):
        slug_dir = isolated_youk_root / "state" / "sessions" / "stale"
        slug_dir.mkdir()
        open_f = slug_dir / "open.json"
        open_f.write_text(json.dumps({
            "slug": "stale",
            "written_at": time.time(),
        }))
        # Backdate mtime beyond the 4h threshold
        stale_ts = time.time() - (5 * 60 * 60)
        os.utime(open_f, (stale_ts, stale_ts))

        assert state_paths.current_session_slug() == "unknown"

    def test_ignores_malformed_open_json(self, isolated_youk_root):
        slug_dir = isolated_youk_root / "state" / "sessions" / "broken"
        slug_dir.mkdir()
        (slug_dir / "open.json").write_text("not json{{{")
        assert state_paths.current_session_slug() == "unknown"


# ── atomic_write ──────────────────────────────────────────────────────────────

class TestAtomicWrite:
    def test_creates_file(self, isolated_youk_root):
        target = isolated_youk_root / "state" / "sessions" / "youk" / "test.json"
        state_paths.atomic_write(target, '{"a": 1}')
        assert target.exists()
        assert json.loads(target.read_text()) == {"a": 1}

    def test_idempotent_second_write(self, isolated_youk_root):
        target = isolated_youk_root / "state" / "sessions" / "youk" / "test.json"
        state_paths.atomic_write(target, '{"v": 1}')
        state_paths.atomic_write(target, '{"v": 2}')
        assert json.loads(target.read_text()) == {"v": 2}

    def test_creates_parent_dirs(self, isolated_youk_root):
        target = isolated_youk_root / "state" / "sessions" / "new" / "sub" / "f.json"
        state_paths.atomic_write(target, "{}")
        assert target.exists()

    def test_concurrent_writes_no_corruption(self, isolated_youk_root):
        """Two threads writing different content must not corrupt the file."""
        target = isolated_youk_root / "state" / "sessions" / "youk" / "concurrent.json"
        errors: list[str] = []

        def write_entry(val: int) -> None:
            try:
                state_paths.atomic_write(target, json.dumps({"v": val}))
            except Exception as exc:
                errors.append(str(exc))

        t1 = threading.Thread(target=write_entry, args=(1,))
        t2 = threading.Thread(target=write_entry, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"write errors: {errors}"
        # File must be valid JSON after both writes
        data = json.loads(target.read_text())
        assert "v" in data
        assert data["v"] in (1, 2)


# ── gate_flag_path ────────────────────────────────────────────────────────────

class TestGateFlagPath:
    def test_returns_slug_scoped_path(self, isolated_youk_root):
        p = state_paths.gate_flag_path("youk", "challenge-ran.json")
        assert p == isolated_youk_root / "state" / "sessions" / "youk" / "challenge-ran.json"

    def test_different_slugs_different_paths(self, isolated_youk_root):
        p1 = state_paths.gate_flag_path("youk", "nfr-check-ran.json")
        p2 = state_paths.gate_flag_path("canopy", "nfr-check-ran.json")
        assert p1 != p2
        assert "youk" in str(p1)
        assert "canopy" in str(p2)


# ── open_json_payload ─────────────────────────────────────────────────────────

class TestOpenJsonPayload:
    def test_contains_slug(self):
        payload = json.loads(state_paths.open_json_payload("myproject"))
        assert payload["slug"] == "myproject"

    def test_contains_written_at(self):
        before = time.time()
        payload = json.loads(state_paths.open_json_payload("myproject"))
        after = time.time()
        assert "written_at" in payload
        assert before <= payload["written_at"] <= after
