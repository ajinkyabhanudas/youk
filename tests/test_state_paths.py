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

    def test_default_scope_is_flat_layout_unchanged(self, isolated_youk_root):
        """Zero-migration requirement: no scope configured must match pre-scope behaviour."""
        p = state_paths.slug_state_dir("youk", scope=None)
        assert p == isolated_youk_root / "state" / "sessions" / "youk"

    def test_named_scope_gets_nested_tree(self, isolated_youk_root):
        p = state_paths.slug_state_dir("youk", scope="acme")
        assert p == isolated_youk_root / "state" / "scopes" / "acme" / "sessions" / "youk"
        assert p.is_dir()

    def test_different_scopes_same_slug_are_different_directories(self, isolated_youk_root):
        p1 = state_paths.slug_state_dir("youk", scope="acme")
        p2 = state_paths.slug_state_dir("youk", scope="beta")
        assert p1 != p2


# ── resolve_scope / scope_state_root ────────────────────────────────────────────

class TestResolveScope:
    def test_none_resolves_to_default(self):
        assert state_paths.resolve_scope(None) == "_default"

    def test_empty_string_resolves_to_default(self):
        assert state_paths.resolve_scope("") == "_default"
        assert state_paths.resolve_scope("   ") == "_default"

    def test_named_scope_passes_through(self):
        assert state_paths.resolve_scope("acme") == "acme"


class TestScopeStateRoot:
    def test_default_scope_root_is_state_dir(self, isolated_youk_root):
        assert state_paths.scope_state_root(None) == isolated_youk_root / "state"
        assert state_paths.scope_state_root("_default") == isolated_youk_root / "state"

    def test_named_scope_root_is_nested(self, isolated_youk_root):
        assert (
            state_paths.scope_state_root("acme")
            == isolated_youk_root / "state" / "scopes" / "acme"
        )


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

    def test_scope_isolation_default_scope_cannot_see_named_scope_session(self, isolated_youk_root):
        """The isolation guarantee itself: a session open in one scope must be invisible
        to current_session_slug() resolving a different scope, by construction."""
        state_paths.slug_state_dir("acme-session", scope="acme")
        acme_open = isolated_youk_root / "state" / "scopes" / "acme" / "sessions" / "acme-session" / "open.json"
        acme_open.write_text(json.dumps({"slug": "acme-session", "written_at": time.time()}))

        assert state_paths.current_session_slug() == "unknown"
        assert state_paths.current_session_slug(scope="acme") == "acme-session"

    def test_scope_isolation_named_scope_cannot_see_default_scope_session(self, isolated_youk_root):
        default_dir = isolated_youk_root / "state" / "sessions" / "youk"
        default_dir.mkdir(parents=True, exist_ok=True)
        (default_dir / "open.json").write_text(json.dumps({"slug": "youk", "written_at": time.time()}))

        assert state_paths.current_session_slug() == "youk"
        assert state_paths.current_session_slug(scope="acme") == "unknown"

    def test_two_named_scopes_do_not_see_each_other(self, isolated_youk_root):
        for scope, slug in (("acme", "acme-slug"), ("beta", "beta-slug")):
            d = state_paths.slug_state_dir(slug, scope=scope)
            (d / "open.json").write_text(json.dumps({"slug": slug, "written_at": time.time()}))

        assert state_paths.current_session_slug(scope="acme") == "acme-slug"
        assert state_paths.current_session_slug(scope="beta") == "beta-slug"


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

    def test_default_scope_matches_pre_scope_layout(self, isolated_youk_root):
        p = state_paths.gate_flag_path("youk", "challenge-ran.json", scope=None)
        assert p == isolated_youk_root / "state" / "sessions" / "youk" / "challenge-ran.json"

    def test_named_scope_same_slug_different_path(self, isolated_youk_root):
        default_p = state_paths.gate_flag_path("youk", "challenge-ran.json")
        scoped_p = state_paths.gate_flag_path("youk", "challenge-ran.json", scope="acme")
        assert default_p != scoped_p


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


# ── actor extension (resolve_actor / session_actor) ────────────────────────────

class TestResolveActor:
    def test_valid_actor_passes_through(self):
        assert state_paths.resolve_actor("founder") == "founder"
        assert state_paths.resolve_actor("contractor") == "contractor"

    def test_unrecognised_value_falls_back_to_founder(self):
        assert state_paths.resolve_actor("admin") == "founder"
        assert state_paths.resolve_actor("") == "founder"

    def test_none_falls_back_to_founder(self):
        assert state_paths.resolve_actor(None) == "founder"


class TestSessionActor:
    def test_no_open_file_defaults_to_founder(self, isolated_youk_root):
        assert state_paths.session_actor("no-such-slug") == "founder"

    def test_reads_actor_from_open_json(self, isolated_youk_root):
        d = state_paths.slug_state_dir("youk")
        (d / "open.json").write_text(json.dumps({"slug": "youk", "actor": "contractor"}))
        assert state_paths.session_actor("youk") == "contractor"

    def test_old_open_json_with_no_actor_field_defaults_to_founder(self, isolated_youk_root):
        """A session written before this feature existed must not need a migration."""
        d = state_paths.slug_state_dir("youk")
        (d / "open.json").write_text(json.dumps({"slug": "youk", "written_at": time.time()}))
        assert state_paths.session_actor("youk") == "founder"

    def test_malformed_open_json_defaults_to_founder(self, isolated_youk_root):
        d = state_paths.slug_state_dir("youk")
        (d / "open.json").write_text("not valid json")
        assert state_paths.session_actor("youk") == "founder"
