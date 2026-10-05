"""The event ledger (servers/shared/events.py).

The properties that matter: events never carry free text (ADR-011), emit never raises or
blocks, concurrent writers never lose lines, and readers stream and dedupe.
"""
from __future__ import annotations

import json
import multiprocessing
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import events
import observability


def _lines(path):
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


class TestContentRule:
    def test_allowed_keys_match_the_dataclass(self):
        """Drift sentinel: widening the event surface has to be a deliberate edit to both."""
        assert events.ALLOWED_KEYS == {f.name for f in fields(events.Event)}

    def test_written_keys_are_a_subset_of_allowed(self, tmp_path):
        events.emit(tmp_path, "youk", kind="tool", name="route_task", ms=12, n=1,
                    session="youk-5", task="T-1", arm="lean", src="hook")
        (path,) = (tmp_path / "state" / "events" / "youk").glob("*.jsonl")
        (record,) = _lines(path)
        assert set(record) <= events.ALLOWED_KEYS

    def test_session_and_task_are_hashed_not_stored(self, tmp_path):
        events.emit(tmp_path, "acme-billing", kind="gate", name="challenge",
                    session="acme-billing-7", task="migrate customer table")
        (path,) = (tmp_path / "state" / "events" / "acme-billing").glob("*.jsonl")
        raw = path.read_text()
        assert "acme-billing-7" not in raw
        assert "migrate customer table" not in raw
        (record,) = _lines(path)
        assert record["session"] == events.hash_identifier("acme-billing-7")

    def test_hash_matches_the_trace_layer(self):
        """Grouping keys must agree between the ledger and Langfuse traces."""
        assert events.hash_identifier("youk") == observability.hash_identifier("youk")

    def test_free_text_name_is_rejected(self, tmp_path):
        assert not events.emit(tmp_path, "youk", kind="tool", name="please fix the login bug")
        assert not (tmp_path / "state" / "events").exists()

    def test_unknown_field_is_rejected(self, tmp_path):
        assert not events.emit(tmp_path, "youk", kind="tool", name="x", prompt="secret text")

    def test_unknown_kind_and_status_are_rejected(self, tmp_path):
        assert not events.emit(tmp_path, "youk", kind="chat", name="x")
        assert not events.emit(tmp_path, "youk", kind="tool", name="x", status="maybe")

    def test_numbers_must_be_non_negative_integers(self, tmp_path):
        assert not events.emit(tmp_path, "youk", kind="tool", name="x", ms=-1)
        assert not events.emit(tmp_path, "youk", kind="tool", name="x", ms=1.5)
        assert not events.emit(tmp_path, "youk", kind="tool", name="x", n=True)


class TestNeverRaises:
    def test_garbage_input(self, tmp_path):
        assert events.emit(tmp_path, "youk") is False  # no kind or name
        assert events.emit(tmp_path, None, kind="tool", name="x") in (True, False)

    def test_unwritable_root(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("not a directory")
        assert events.emit(blocker, "youk", kind="tool", name="x") is False

    def test_hostile_slug_cannot_leave_the_events_dir(self, tmp_path):
        assert events.emit(tmp_path, "../../etc", kind="tool", name="x")
        written = list((tmp_path / "state" / "events").rglob("*.jsonl"))
        assert len(written) == 1
        assert tmp_path / "state" / "events" in written[0].parents
        assert ".." not in written[0].relative_to(tmp_path).parts


class TestSharding:
    def test_events_land_in_a_per_project_month_file(self, tmp_path):
        events.emit(tmp_path, "youk", kind="skill", name="code-review")
        events.emit(tmp_path, "stencil", kind="skill", name="code-review")
        month = datetime.now(UTC).strftime("%Y-%m")
        assert (tmp_path / "state" / "events" / "youk" / f"{month}.jsonl").exists()
        assert (tmp_path / "state" / "events" / "stencil" / f"{month}.jsonl").exists()


def _writer(root, slug, count, tag):
    for i in range(count):
        events.emit(root, slug, kind="tool", name="t", n=i, session=f"s{tag}")


class TestConcurrency:
    def test_parallel_processes_lose_nothing(self, tmp_path):
        procs = [
            multiprocessing.Process(target=_writer, args=(tmp_path, "youk", 50, tag))
            for tag in range(4)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
        assert all(p.exitcode == 0 for p in procs)
        got = list(events.read_events(tmp_path, "youk"))
        assert len(got) == 200


class TestReading:
    def test_dedupes_by_eid(self, tmp_path):
        for _ in range(2):
            events.emit(tmp_path, "youk", kind="tool", name="x", eid="same-id")
        assert len(list(events.read_events(tmp_path, "youk"))) == 1

    def test_filters_by_kind_and_time(self, tmp_path):
        old = (datetime.now(UTC) - timedelta(days=2)).isoformat(timespec="microseconds")
        events.emit(tmp_path, "youk", kind="tool", name="old", ts=old)
        events.emit(tmp_path, "youk", kind="skill", name="new")
        events.emit(tmp_path, "youk", kind="tool", name="new2")
        since = datetime.now(UTC) - timedelta(days=1)
        names = [e["name"] for e in events.read_events(tmp_path, "youk", since=since, kinds={"tool"})]
        assert names == ["new2"]

    def test_skips_a_partial_line(self, tmp_path):
        events.emit(tmp_path, "youk", kind="tool", name="ok")
        (path,) = (tmp_path / "state" / "events" / "youk").glob("*.jsonl")
        with path.open("a") as handle:
            handle.write('{"kind": "tool", "na')  # a write in flight
        assert [e["name"] for e in events.read_events(tmp_path, "youk")] == ["ok"]

    def test_missing_project_is_empty_not_an_error(self, tmp_path):
        assert list(events.read_events(tmp_path, "nobody")) == []
