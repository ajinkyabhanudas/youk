"""Docker bloat pulse — detects accumulating youk containers/images, NEVER deletes.

The load-bearing property (from the challenge that rejected autorun-delete): this pulse only
reads and surfaces. It must never call a mutating docker command. Thresholds mirror doctor.sh.
"""
from __future__ import annotations

import docker_bloat_pulse as dbp
from docker_bloat_pulse import check_docker_bloat, format_bloat_warnings


def _fake_docker(running=0, stopped=0, images=2, dangling=0):
    """Return a fake _docker that answers based on the args it's given."""
    def _impl(args):
        if args[0] == "ps" and "-a" not in args:
            return "\n".join(["youk-core:latest"] * running) or ""
        if args[0] == "ps" and "-a" in args:
            return "\n".join(["youk-code:latest"] * stopped) or ""
        if args[0] == "images" and "reference=youk-*" in args:
            return "\n".join([f"id{i}" for i in range(images)]) or ""
        if args[0] == "images" and "dangling=true" in args:
            return "\n".join([f"d{i}" for i in range(dangling)]) or ""
        return ""
    return _impl


def test_clean_state_is_ok_and_silent(monkeypatch):
    monkeypatch.setattr(dbp, "_docker", _fake_docker(running=0, stopped=0, images=2, dangling=0))
    r = check_docker_bloat()
    assert r["severity"] == "ok"
    assert format_bloat_warnings(r) == []


def test_normal_session_pair_is_ok(monkeypatch):
    # 2 running = one active session pair — normal, no warning (matches doctor.sh).
    monkeypatch.setattr(dbp, "_docker", _fake_docker(running=2))
    assert check_docker_bloat()["severity"] == "ok"


def test_stopped_containers_warn(monkeypatch):
    monkeypatch.setattr(dbp, "_docker", _fake_docker(running=0, stopped=3))
    r = check_docker_bloat()
    assert r["severity"] == "warn"
    w = format_bloat_warnings(r)
    assert any("3 stopped" in line for line in w)
    assert any("make prune" in line for line in w)


def test_many_running_is_high(monkeypatch):
    monkeypatch.setattr(dbp, "_docker", _fake_docker(running=6))
    assert check_docker_bloat()["severity"] == "high"


def test_dangling_images_warn(monkeypatch):
    monkeypatch.setattr(dbp, "_docker", _fake_docker(dangling=2))
    r = check_docker_bloat()
    assert r["severity"] == "warn"
    assert any("dangling" in line for line in format_bloat_warnings(r))


def test_docker_unavailable_is_silent(monkeypatch):
    monkeypatch.setattr(dbp, "_docker", lambda args: None)  # docker not reachable
    r = check_docker_bloat()
    assert r["available"] is False
    assert r["severity"] == "none"
    assert format_bloat_warnings(r) == []


def test_pulse_never_calls_a_mutating_docker_command(monkeypatch):
    """The safety guarantee: detection only. No rmi / prune / rm / stop ever issued."""
    called: list[list[str]] = []

    def _spy(args):
        called.append(args)
        return ""  # empty result

    monkeypatch.setattr(dbp, "_docker", _spy)
    check_docker_bloat()
    mutating = {"rmi", "rm", "prune", "stop", "kill", "system"}
    for args in called:
        assert not (set(args) & mutating), f"pulse issued a mutating docker command: {args}"


def test_warning_says_it_is_not_autorun(monkeypatch):
    """The message must state deletion is human-triggered — the challenge outcome."""
    monkeypatch.setattr(dbp, "_docker", _fake_docker(stopped=1))
    w = format_bloat_warnings(check_docker_bloat())
    assert any("Not auto-run" in line or "not auto" in line.lower() for line in w)
