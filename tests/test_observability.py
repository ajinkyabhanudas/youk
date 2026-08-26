"""Tests for observability.py — NoOp path, singleton, and compute_patch_cycle_rate."""
import importlib
import sys
import pytest


@pytest.fixture(autouse=True)
def _reset_obs_singleton():
    """Clear module-level singleton between tests."""
    import observability
    observability._instance = None
    yield
    observability._instance = None


class TestNoOpPath:
    def test_get_obs_returns_noop_when_env_absent(self, monkeypatch):
        for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
            monkeypatch.delenv(k, raising=False)
        import observability
        obs = observability.get_obs()
        assert isinstance(obs, observability.NoOpObs)

    def test_noop_start_run_returns_noop_trace(self):
        import observability
        obs = observability.NoOpObs()
        trace = obs.start_run("slug", "/tmp")
        assert trace.id == "noop"

    def test_noop_attach_score_by_id_is_silent(self):
        import observability
        obs = observability.NoOpObs()
        obs.attach_score_by_id("some-id", "metric", 0.5)

    def test_noop_end_run_by_id_is_silent(self):
        import observability
        obs = observability.NoOpObs()
        obs.end_run_by_id("some-id", outcome="SHIPPED")

    def test_noop_flush_is_silent(self):
        import observability
        observability.NoOpObs().flush()


class TestComputePatchCycleRate:
    def test_empty_candidates_returns_none(self):
        from observability import compute_patch_cycle_rate
        assert compute_patch_cycle_rate([]) is None

    def test_all_cycling(self):
        from observability import compute_patch_cycle_rate
        candidates = [{"patch_cycle": True}, {"patch_cycle": True}]
        assert compute_patch_cycle_rate(candidates) == 1.0

    def test_none_cycling(self):
        from observability import compute_patch_cycle_rate
        candidates = [{"patch_cycle": False}, {}]
        assert compute_patch_cycle_rate(candidates) == 0.0

    def test_partial_cycling(self):
        from observability import compute_patch_cycle_rate
        candidates = [{"patch_cycle": True}, {"patch_cycle": False}, {"patch_cycle": False}]
        rate = compute_patch_cycle_rate(candidates)
        assert abs(rate - 0.333) < 0.001

    def test_missing_key_treated_as_false(self):
        from observability import compute_patch_cycle_rate
        candidates = [{"other_key": True}, {"patch_cycle": True}]
        assert compute_patch_cycle_rate(candidates) == 0.5


class TestSingleton:
    def test_get_obs_is_idempotent(self, monkeypatch):
        for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
            monkeypatch.delenv(k, raising=False)
        import observability
        obs1 = observability.get_obs()
        obs2 = observability.get_obs()
        assert obs1 is obs2

    def test_singleton_reset_between_tests(self, monkeypatch):
        for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
            monkeypatch.delenv(k, raising=False)
        import observability
        assert observability._instance is None
