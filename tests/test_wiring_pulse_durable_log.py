"""wiring_pulse/pipeline_pulse warnings are capped at 5 in session-start
text, and check_wiring's orphan order is deterministic (file order), so
the same first 5 orphans would be the only ones ever shown -- anything
past slot 5 never individually named, in any session.

_check_doc_freshness (which, despite its name, also runs the wiring and
pipeline pulse checks) appends the FULL, uncapped result to a durable
JSONL log every time it runs, so the data exists even if nobody reads the
capped session-start text that run.
"""
from __future__ import annotations

import json

import session


def test_wiring_pulse_writes_full_uncapped_result_to_durable_log(tmp_path, monkeypatch):
    youk_root = tmp_path / "youk"
    claude_root = tmp_path / "claude"
    (youk_root / "state").mkdir(parents=True)
    (claude_root).mkdir(parents=True)
    monkeypatch.setattr(session, "YOUK_ROOT", youk_root)
    monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

    # No real server.py on disk in this sandbox -- check_wiring's own guard
    # (`if not server_py.exists(): return []`) means total=0, orphaned=[].
    # This proves the WRITE mechanism fires and records a real entry, not
    # that check_wiring finds non-trivial orphans (that needs a real server.py
    # fixture, covered by wiring_pulse's own tests).
    session._check_doc_freshness()

    log_path = youk_root / "state" / "wiring-pulse-log.jsonl"
    assert log_path.exists(), "wiring-pulse-log.jsonl must be written every run, not only when orphans exist"
    lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    assert "orphaned" in lines[0]
    assert "total" in lines[0]
    assert "timestamp" in lines[0]


def test_wiring_pulse_log_is_append_only_across_multiple_runs(tmp_path, monkeypatch):
    youk_root = tmp_path / "youk"
    claude_root = tmp_path / "claude"
    (youk_root / "state").mkdir(parents=True)
    claude_root.mkdir(parents=True)
    monkeypatch.setattr(session, "YOUK_ROOT", youk_root)
    monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

    session._check_doc_freshness()
    session._check_doc_freshness()
    session._check_doc_freshness()

    log_path = youk_root / "state" / "wiring-pulse-log.jsonl"
    lines = [line for line in log_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 3, "every real session_start run must add a new entry, never overwrite history"


def test_doc_freshness_check_never_crashes_when_server_py_absent(tmp_path, monkeypatch):
    """The surrounding try/except must still degrade silently -- this check
    must never block a real session_start."""
    youk_root = tmp_path / "youk"
    claude_root = tmp_path / "claude"
    youk_root.mkdir(parents=True)
    claude_root.mkdir(parents=True)
    monkeypatch.setattr(session, "YOUK_ROOT", youk_root)
    monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

    result = session._check_doc_freshness()
    assert isinstance(result, list)
