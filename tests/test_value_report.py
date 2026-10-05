"""The value report (scripts/value_report.py), checked against ledgers with known answers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import events
import value_report as vr

REPO = Path(__file__).parent.parent


_TICK = iter(range(1, 10_000))


def _emit(root, **kw):
    # Distinct timestamps: identical events collapse by eid on read, which is the ledger's
    # dedupe rule, so a test that wants three events has to make them three moments.
    kw.setdefault("ts", f"2026-10-05T10:{next(_TICK) // 60:02d}:{next(_TICK) % 60:02d}.000000+00:00")
    assert events.emit(root, "proj", **kw)


def _group(root, by=("arm",)):
    return vr.summarize(vr.load(root), by=by)["groups"]


class TestEmpty:
    def test_no_events_is_a_message_not_a_crash(self, tmp_path):
        text = vr.render(vr.summarize(vr.load(tmp_path)))
        assert "No events yet" in text


class TestV1Corrections:
    def test_rate_per_m_plus_task_counts_only_ok_m_plus_routes(self, tmp_path):
        for name in ("pushback", "pushback", "rule_phrase"):
            _emit(tmp_path, kind="correction", name=name, src="hook", session="s1")
        _emit(tmp_path, kind="gate", name="route.M", src="server")
        _emit(tmp_path, kind="gate", name="route.XL", src="server")
        _emit(tmp_path, kind="gate", name="route.S", src="server")
        _emit(tmp_path, kind="gate", name="route.M", src="server", status="block")
        (g,) = _group(tmp_path)
        assert g["v1"]["pushback"] == 2 and g["v1"]["rule_phrase"] == 1
        assert g["v1"]["m_plus_tasks"] == 2 and g["v1"]["per_m_plus_task"] == 1.5

    def test_no_m_plus_tasks_gives_none_not_a_division_error(self, tmp_path):
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s1")
        (g,) = _group(tmp_path)
        assert g["v1"]["per_m_plus_task"] is None

    def test_interval_appears_only_with_ten_sessions(self, tmp_path):
        for i in range(9):
            _emit(tmp_path, kind="correction", name="pushback", src="hook", session=f"s{i}")
        assert _group(tmp_path)[0]["v1"]["ci"] is None
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s9")
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s9",
              ts="2026-10-05T11:00:00.000000+00:00")
        ci = _group(tmp_path)[0]["v1"]["ci"]
        assert ci is not None and 1.0 <= ci[0] <= ci[1] <= 2.0

    def test_interval_is_deterministic(self):
        values = [0.0, 1.0, 2.0, 3.0] * 5
        assert vr.bootstrap_ci(values) == vr.bootstrap_ci(values)
        assert vr.bootstrap_ci(values[:9]) is None


class TestCountingRule:
    def test_server_tool_events_do_not_inflate_call_counts(self, tmp_path):
        _emit(tmp_path, kind="tool", name="route_task", src="hook", session="s1")
        _emit(tmp_path, kind="tool", name="route_task", src="server", ms=30)
        (g,) = _group(tmp_path)
        assert g["usage"]["tools"] == [("route_task", 1)]
        assert g["v3"]["slowest_tools"][0]["tool"] == "route_task"


class TestV2:
    def test_last_test_run_green_per_session(self, tmp_path):
        stamps = iter(f"2026-10-05T10:00:0{i}.000000+00:00" for i in range(8))
        for session, statuses in (("a", ("fail", "ok")), ("b", ("ok", "fail")), ("c", ("ok",))):
            for status in statuses:
                _emit(tmp_path, kind="test", name="pytest", src="hook", session=session,
                      status=status, ts=next(stamps))
        _emit(tmp_path, kind="commit", name="git", src="hook", session="a")
        (g,) = _group(tmp_path)
        assert g["v2"]["sessions_with_tests"] == 3 and g["v2"]["last_test_green"] == 2
        assert g["v2"]["failed_test_runs"] == 2 and g["v2"]["test_runs"] == 5
        assert g["v2"]["commits"] == 1
        assert "pending" in g["v2"]["first_pass_acceptance"]


class TestV3AndGates:
    def test_latency_percentiles_and_session_start(self, tmp_path):
        for ms in (10, 20, 30, 40, 100):
            _emit(tmp_path, kind="hook", name="post_tool_use", src="hook", ms=ms, n=10)
        for ms in (200, 300):
            _emit(tmp_path, kind="tool", name="session_start", src="server", ms=ms)
        (g,) = _group(tmp_path)
        assert g["v3"]["hook_ms_p50"] == 30 and g["v3"]["hook_ms_p95"] == 100
        assert g["v3"]["session_start_p95"] == 300

    def test_gate_checks_and_blocks_exclude_set_and_route(self, tmp_path):
        for status in ("ok", "ok", "block"):
            _emit(tmp_path, kind="gate", name="nfr", src="server", status=status)
        _emit(tmp_path, kind="gate", name="set.nfr_cleared", src="server")
        _emit(tmp_path, kind="gate", name="route.M", src="server")
        (g,) = _group(tmp_path)
        assert g["gates"] == {"nfr": {"checks": 3, "blocks": 1}}


class TestGrouping:
    def test_arms_are_separate_groups(self, tmp_path):
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s1", arm="lean")
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s2", arm="full")
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s3")
        assert [g["group"] for g in _group(tmp_path)] == ["-", "full", "lean"]

    def test_weeks_split_by_iso_week(self, tmp_path):
        _emit(tmp_path, kind="tool", name="Edit", src="hook", ts="2026-10-05T10:00:00.000000+00:00")
        _emit(tmp_path, kind="tool", name="Edit", src="hook", ts="2026-10-13T10:00:00.000000+00:00")
        groups = _group(tmp_path, by=("week",))
        assert [g["group"] for g in groups] == ["2026-W41", "2026-W42"]

    def test_percentile_edges(self):
        assert vr.percentile([], 0.5) is None
        assert vr.percentile([7], 0.95) == 7


class TestRenderAndCli:
    def test_render_is_honest_about_small_n_and_pending_fields(self, tmp_path):
        _emit(tmp_path, kind="correction", name="pushback", src="hook", session="s1")
        text = vr.render(vr.summarize(vr.load(tmp_path)))
        assert "n<10, no interval" in text and "pending" in text and "Diagnostic only" in text

    def test_json_output_round_trips(self, tmp_path):
        _emit(tmp_path, kind="commit", name="git", src="hook", session="s1")
        out = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "value_report.py"), "--root", str(tmp_path),
             "--json"], capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
        assert data["groups"][0]["v2"]["commits"] == 1

    def test_since_filters_old_events(self, tmp_path):
        _emit(tmp_path, kind="commit", name="git", src="hook", ts="2020-01-01T00:00:00.000000+00:00")
        out = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "value_report.py"), "--root", str(tmp_path),
             "--since", "2026-01-01", "--json"], capture_output=True, text=True, check=True).stdout
        assert json.loads(out)["events"] == 0
