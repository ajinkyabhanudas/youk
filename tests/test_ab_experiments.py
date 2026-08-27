"""Tests for A/B experiment infrastructure: variant assignment and exposure logging.

Built from ~/Desktop/AB-Tests/ab-test-plan.md, deferred there because the deploy path
was unknown from that project's context. Picked up here once it was.

The behaviours that matter: assignment must be deterministic (same session always gets
the same variant) and independent per experiment (drawing treatment on one experiment
must not correlate with the draw on another). Logging must never carry raw session
identity or any session content, per ADR-011, and must never be able to raise into the
caller — an exposure log is telemetry, not a gate.
"""
from __future__ import annotations


from ab_experiments import assign_variant, log_exposure, read_exposures


class TestAssignVariantIsDeterministic:
    def test_same_session_same_experiment_always_matches(self):
        v1 = assign_variant("session-abc", "exp-1")
        v2 = assign_variant("session-abc", "exp-1")
        assert v1 == v2

    def test_returns_only_declared_variants(self):
        for i in range(50):
            v = assign_variant(f"session-{i}", "exp-1")
            assert v in ("control", "treatment")

    def test_distribution_is_roughly_balanced(self):
        """Not a statistical test — just a sanity bound against a broken hash."""
        counts = {"control": 0, "treatment": 0}
        for i in range(500):
            counts[assign_variant(f"session-{i}", "exp-1")] += 1
        ratio = counts["control"] / 500
        assert 0.35 < ratio < 0.65, f"distribution skewed: {counts}"


class TestAssignVariantIsIndependentPerExperiment:
    def test_different_experiments_can_diverge_for_the_same_session(self):
        """A session drawing treatment on one experiment must not be locked into
        treatment on every other experiment — otherwise experiments are correlated
        rather than independent."""
        results = {
            exp: assign_variant("fixed-session", exp)
            for exp in [f"exp-{i}" for i in range(20)]
        }
        assert len(set(results.values())) == 2, "all experiments drew the same variant"


class TestLogExposure:
    def test_write_creates_the_file(self, tmp_path):
        log_exposure(tmp_path, "session-1", "exp-1", "nfr-check", "control")
        assert (tmp_path / "state" / "ab-exposures.json").exists()

    def test_entry_has_expected_shape(self, tmp_path):
        log_exposure(tmp_path, "session-1", "exp-1", "nfr-check", "treatment")
        records = read_exposures(tmp_path)
        assert len(records) == 1
        r = records[0]
        assert r["experiment"] == "exp-1"
        assert r["skill"] == "nfr-check"
        assert r["variant"] == "treatment"
        assert "ts" in r

    def test_raw_session_slug_never_written(self, tmp_path):
        """ADR-011: only a hash may touch disk."""
        log_exposure(tmp_path, "my-secret-project-slug", "exp-1", "nfr-check", "control")
        raw = (tmp_path / "state" / "ab-exposures.json").read_text()
        assert "my-secret-project-slug" not in raw

    def test_session_hash_is_present_and_stable(self, tmp_path):
        log_exposure(tmp_path, "session-1", "exp-1", "a", "control")
        log_exposure(tmp_path, "session-1", "exp-2", "b", "treatment")
        records = read_exposures(tmp_path)
        hashes = {r["session_hash"] for r in records}
        assert len(hashes) == 1, "same session produced different hashes"

    def test_duplicate_exposure_is_deduplicated(self, tmp_path):
        """Repeated route_to_skill calls in one session for the same skill must not
        multiply-count in the exposure rate."""
        for _ in range(5):
            log_exposure(tmp_path, "session-1", "exp-1", "nfr-check", "control")
        assert len(read_exposures(tmp_path)) == 1

    def test_same_session_different_skill_is_not_deduplicated(self, tmp_path):
        log_exposure(tmp_path, "session-1", "exp-1", "skill-a", "control")
        log_exposure(tmp_path, "session-1", "exp-1", "skill-b", "control")
        assert len(read_exposures(tmp_path)) == 2

    def test_appends_across_separate_calls(self, tmp_path):
        log_exposure(tmp_path, "session-1", "exp-1", "a", "control")
        log_exposure(tmp_path, "session-2", "exp-1", "a", "treatment")
        assert len(read_exposures(tmp_path)) == 2

    def test_never_raises_on_unwritable_directory(self, tmp_path):
        """An exposure log must never be able to fail the routing call it comes from."""
        blocked = tmp_path / "state"
        blocked.write_text("not a directory")
        log_exposure(tmp_path, "session-1", "exp-1", "a", "control")  # must not raise

    def test_never_raises_on_corrupt_existing_file(self, tmp_path):
        """A corrupt log must not block a new write; it resets rather than crashes."""
        state = tmp_path / "state"
        state.mkdir()
        (state / "ab-exposures.json").write_text("{not valid json")
        log_exposure(tmp_path, "session-1", "exp-1", "a", "control")
        records = read_exposures(tmp_path)
        assert len(records) == 1
        assert records[0]["skill"] == "a"


class TestReadExposures:
    def test_missing_file_returns_empty_list(self, tmp_path):
        assert read_exposures(tmp_path) == []

    def test_filters_by_experiment(self, tmp_path):
        log_exposure(tmp_path, "s1", "exp-a", "x", "control")
        log_exposure(tmp_path, "s1", "exp-b", "x", "control")
        assert len(read_exposures(tmp_path, experiment="exp-a")) == 1

    def test_no_filter_returns_all(self, tmp_path):
        log_exposure(tmp_path, "s1", "exp-a", "x", "control")
        log_exposure(tmp_path, "s1", "exp-b", "x", "control")
        assert len(read_exposures(tmp_path)) == 2
