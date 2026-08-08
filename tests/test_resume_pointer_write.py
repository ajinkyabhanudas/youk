"""The resume-pointer write bug — _update_resume_point silently no-op'd when run host-side
because it targeted the container path /youk (which doesn't exist outside Docker). This made
the resume pointer never update, recurring three times in one session. These tests prove the
write now lands via host-root resolution.
"""
from __future__ import annotations

import session as _sess
from session import _resolve_youk_root, _update_resume_point


def _write_pathmap(root, host_dir):
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "path-map.env").write_text(f"YOUK_HOST_DIR={host_dir}\n")


def test_resolve_falls_back_to_pathmap_when_container_path_absent(tmp_path, monkeypatch):
    """When YOUK_ROOT (/youk) doesn't exist, resolve the real host dir from path-map.env."""
    real = tmp_path / "real-youk"
    real.mkdir()
    _write_pathmap(real, str(real))
    # point the module's YOUK_ROOT at a nonexistent container path, with path-map reachable
    monkeypatch.setattr(_sess, "YOUK_ROOT", tmp_path / "does-not-exist-youk")
    monkeypatch.chdir(real)  # so the cwd-relative path-map lookup finds it
    assert _resolve_youk_root() == real


def test_resolve_returns_youk_root_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(_sess, "YOUK_ROOT", tmp_path)  # exists
    assert _resolve_youk_root() == tmp_path


def test_write_lands_when_root_resolves(tmp_path, monkeypatch):
    """The core guarantee: the pointer actually gets written (not a silent no-op)."""
    root = tmp_path / "youk"
    ctx = root / "knowledge" / "projects" / "youk"
    ctx.mkdir(parents=True)
    (ctx / "context.md").write_text("# ctx\n\nresume-from: old\n")
    monkeypatch.setattr(_sess, "YOUK_ROOT", root)  # exists -> resolves to itself

    _update_resume_point("youk", "NEXT = agentic-ux rework")
    written = (ctx / "context.md").read_text()
    assert "resume-from: NEXT = agentic-ux rework" in written
    assert "resume-from: old" not in written


def test_write_via_host_fallback(tmp_path, monkeypatch):
    """The bug's exact scenario: /youk absent, real dir found via path-map — write must land."""
    real = tmp_path / "real-youk"
    ctx = real / "knowledge" / "projects" / "youk"
    ctx.mkdir(parents=True)
    (ctx / "context.md").write_text("resume-from: stale\n")
    _write_pathmap(real, str(real))
    monkeypatch.setattr(_sess, "YOUK_ROOT", tmp_path / "nope-youk")  # container path absent
    monkeypatch.chdir(real)

    _update_resume_point("youk", "landed via host fallback")
    assert "landed via host fallback" in (ctx / "context.md").read_text()


def test_no_context_file_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(_sess, "YOUK_ROOT", tmp_path)  # exists, but no context.md
    _update_resume_point("youk", "x")  # must not raise
