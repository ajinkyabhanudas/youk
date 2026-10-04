"""Tests for jsonl_lock (2026-10-04): real concurrent-write safety.

Found live this session: every append_* function across disposition_event.py,
domain_scope_event.py, reversal_check.py, pattern_promotion.py used a bare
`open(path, "a")` -- no lock -- while this very session had two separate
processes (a Codex session and this Claude Code session) connected to the
same youk-core server at once. These tests prove the fix actually holds
under real concurrent writers, not just that the code compiles.
"""
from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from jsonl_lock import locked_append_if_id_absent, locked_jsonl_append, locked_jsonl_read_all


def _writer_proc(path_str: str, n: int, tag: str) -> None:
    path = Path(path_str)
    for i in range(n):
        locked_jsonl_append(path, json.dumps({"tag": tag, "i": i}))


def test_concurrent_processes_never_interleave_or_corrupt_lines(tmp_path):
    """The real failure mode this fix exists to prevent: two real OS
    processes appending at the same time must never produce a line that
    fails to parse as JSON, and must never lose a write."""
    path = tmp_path / "concurrent.jsonl"
    n_per_proc = 200
    procs = [
        multiprocessing.Process(target=_writer_proc, args=(str(path), n_per_proc, tag))
        for tag in ("a", "b", "c", "d")
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == n_per_proc * len(procs), "a write was lost under concurrency"

    parsed = [json.loads(line) for line in lines]  # raises if any line is corrupt/interleaved
    counts = {}
    for row in parsed:
        counts[row["tag"]] = counts.get(row["tag"], 0) + 1
    assert counts == {"a": n_per_proc, "b": n_per_proc, "c": n_per_proc, "d": n_per_proc}


def test_locked_jsonl_append_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "log.jsonl"
    locked_jsonl_append(path, json.dumps({"x": 1}))
    assert path.exists()
    assert json.loads(path.read_text().splitlines()[0]) == {"x": 1}


def test_locked_jsonl_read_all_returns_empty_list_for_missing_file(tmp_path):
    assert locked_jsonl_read_all(tmp_path / "missing.jsonl") == []


def test_locked_jsonl_read_all_round_trips_real_rows(tmp_path):
    path = tmp_path / "log.jsonl"
    locked_jsonl_append(path, json.dumps({"n": 1}))
    locked_jsonl_append(path, json.dumps({"n": 2}))
    assert locked_jsonl_read_all(path) == [{"n": 1}, {"n": 2}]


def test_locked_jsonl_read_all_skips_unparseable_lines(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text('{"n": 1}\nnot json\n{"n": 2}\n', encoding="utf-8")
    assert locked_jsonl_read_all(path) == [{"n": 1}, {"n": 2}]


# --- locked_append_if_id_absent: the TOCTOU-safe check-and-append ----------


def test_locked_append_if_id_absent_appends_when_new():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "log.jsonl"
        appended = locked_append_if_id_absent(path, "pat-1", json.dumps({"id": "pat-1"}))
        assert appended is True
        assert len(path.read_text().splitlines()) == 1


def test_locked_append_if_id_absent_is_a_noop_when_id_already_present():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "log.jsonl"
        locked_append_if_id_absent(path, "pat-1", json.dumps({"id": "pat-1"}))
        appended_again = locked_append_if_id_absent(path, "pat-1", json.dumps({"id": "pat-1"}))
        assert appended_again is False
        assert len(path.read_text().splitlines()) == 1, "re-confirming the same id must never duplicate the row"


def _idempotent_writer_proc(path_str: str, entry_id: str) -> None:
    path = Path(path_str)
    locked_append_if_id_absent(path, entry_id, json.dumps({"id": entry_id}))


def test_concurrent_processes_racing_the_same_id_never_duplicate(tmp_path):
    """The exact TOCTOU race a plain has-id-check-then-append has: N
    processes all confirming the SAME real pattern at once must still only
    ever produce one row, never N."""
    path = tmp_path / "race.jsonl"
    procs = [
        multiprocessing.Process(target=_idempotent_writer_proc, args=(str(path), "pat-shared"))
        for _ in range(8)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly 1 row from 8 concurrent racers, got {len(lines)}"
