"""Tests for skill-forge run audit trail: session_delta + health proactive signal."""
from __future__ import annotations
import json


def _write_forge(root, **kw):
    data = {
        "stack": "python", "started_at": "2026-07-14T00:00:00", "cycles": 3,
        "skills_created": [], "skills_sharpened": [], "converged": True,
        "ceiling_hit": False, "revert_manifest": [],
    }
    data.update(kw)
    (root / "state" / "skill-forge-run.json").write_text(json.dumps(data))


class TestReadForgeRunSession:
    def test_none_when_absent(self, youk_root):
        from session import _read_forge_run
        assert _read_forge_run() is None

    def test_reads_run(self, youk_root):
        _write_forge(youk_root, skills_created=["a", "b"])
        from session import _read_forge_run
        r = _read_forge_run()
        assert r["skills_created"] == ["a", "b"]

    def test_corrupt_returns_none(self, youk_root):
        (youk_root / "state" / "skill-forge-run.json").write_text("{bad")
        from session import _read_forge_run
        assert _read_forge_run() is None


class TestSessionDeltaForge:
    def test_forge_creates_compounding_verdict(self, youk_root):
        _write_forge(youk_root, skills_created=["a"], skills_sharpened=["b", "c"])
        from session import _compute_session_delta
        d = _compute_session_delta(0, 0, None, "proj")
        assert "skill-forge created 1" in d["verdict"]
        assert d["forge_skills_created"] == 1
        assert d["forge_skills_sharpened"] == 2
        assert d["forge_converged"] is True

    def test_no_forge_falls_back_to_static(self, youk_root):
        from session import _compute_session_delta
        d = _compute_session_delta(0, 0, None, "proj")
        assert "forge_skills_created" not in d
        assert d["verdict"].startswith("STATIC")

    def test_empty_forge_run_not_counted(self, youk_root):
        # A forge run that created/sharpened nothing should not claim compounding
        _write_forge(youk_root, skills_created=[], skills_sharpened=[])
        from session import _compute_session_delta
        d = _compute_session_delta(0, 0, None, "proj")
        assert d["verdict"].startswith("STATIC")


class TestReadForgeRunHealth:
    def test_none_when_absent(self, youk_root):
        from health import _read_forge_run
        assert _read_forge_run() is None

    def test_reads_run(self, youk_root):
        _write_forge(youk_root, skills_sharpened=["x"])
        from health import _read_forge_run
        r = _read_forge_run()
        assert r["skills_sharpened"] == ["x"]
