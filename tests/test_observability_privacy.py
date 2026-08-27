"""Drift sentinel for the trace content invariant (ADR-011).

    Traces carry derived scalars and enums. Never free text from the session.

This is what keeps a shared team Langfuse instance a config change rather than a
redesign. If trace metadata starts carrying raw paths, project names or task text,
pointing LANGFUSE_HOST at a shared host silently leaks session content, and no
later fix removes data already sitting on that server.

These tests fail if a future change adds an identifying field, so the decision to
widen the trace surface has to be made deliberately rather than by convenience.
"""
from __future__ import annotations

import observability as obs


class TestNoRawIdentifiersInMetadata:
    def test_project_dir_never_appears(self, tmp_path):
        """The original leak: project_dir is an absolute path containing the username."""
        project_dir = "/Users/somebody/Desktop/secret-client-work"
        meta = obs.build_trace_metadata("youk", youk_root=tmp_path)
        flat = repr(meta)
        assert project_dir not in flat
        assert "somebody" not in flat
        assert "secret-client-work" not in flat

    def test_raw_slug_never_appears(self, tmp_path):
        """A project slug is a project name, so it is hashed rather than sent."""
        meta = obs.build_trace_metadata("acme-billing-migration", youk_root=tmp_path)
        assert "acme-billing-migration" not in repr(meta)
        assert meta["session_slug_hash"] == obs.hash_identifier("acme-billing-migration")

    def test_only_allowlisted_keys_present(self, tmp_path):
        meta = obs.build_trace_metadata("youk", youk_root=tmp_path)
        assert set(meta).issubset(obs._ALLOWED_METADATA_KEYS)

    def test_all_values_are_scalars(self, tmp_path):
        """Nested structures are how free text sneaks back in."""
        meta = obs.build_trace_metadata("youk", youk_root=tmp_path)
        for k, v in meta.items():
            assert isinstance(v, (str, int, float, bool)), f"{k} is {type(v).__name__}"


class TestRealStartRunCallSite:
    """Covers start_run itself, not just build_trace_metadata.

    The original leak was in start_run's metadata dict. A test that only exercises the
    helper would pass while the real call site still leaked, which is the adjacent-stage
    failure that verify bar 8 exists to prevent.
    """

    @staticmethod
    def _capture_start_run(slug: str, project_dir: str) -> dict:
        captured: dict = {}

        class _FakeLangfuse:
            def trace(self, **kw):
                captured.update(kw)

                class _T:
                    id = "t1"

                return _T()

        o = obs.LangfuseObs.__new__(obs.LangfuseObs)  # bypass __init__, no env needed
        o._lf = _FakeLangfuse()
        o.start_run(slug, project_dir)
        return captured

    def test_start_run_sends_no_identifying_values(self):
        captured = self._capture_start_run(
            "acme-billing", "/Users/somebody/Desktop/secret-client-work"
        )
        flat = repr(captured)
        for banned in ("somebody", "secret-client-work", "acme-billing", "/Users", "Desktop"):
            assert banned not in flat, f"leaked {banned!r}"

    def test_start_run_metadata_is_not_empty(self):
        """Guards against the assertion above passing vacuously on an empty dict."""
        captured = self._capture_start_run("youk", "/tmp/x")
        assert captured["metadata"], "empty metadata makes the leak assertions vacuous"

    def test_start_run_metadata_obeys_allowlist(self):
        captured = self._capture_start_run("youk", "/tmp/x")
        assert set(captured["metadata"]).issubset(obs._ALLOWED_METADATA_KEYS)


class TestGenerationCarriesNoPromptText:
    """Langfuse generations normally carry prompt and completion.

    Here the prompt is the user's raw task description, so recording it would break
    ADR-011 at the single most tempting point. Only model name, token counts and
    latency go on the wire.
    """

    @staticmethod
    def _capture(**kwargs) -> dict:
        captured: dict = {}

        class _FakeLangfuse:
            def generation(self, **kw):
                captured.update(kw)

        o = obs.LangfuseObs.__new__(obs.LangfuseObs)
        o._lf = _FakeLangfuse()
        o.record_generation(
            "trace-1", "optimize_intent", "claude-haiku-4-5-20251001",
            input_tokens=1200, output_tokens=340, duration_s=1.234, **kwargs
        )
        return captured

    def test_records_model_tokens_and_latency(self):
        c = self._capture()
        assert c["model"] == "claude-haiku-4-5-20251001"
        assert c["usage"]["input"] == 1200
        assert c["usage"]["output"] == 340
        assert c["metadata"]["duration_s"] == 1.234

    def test_no_prompt_or_completion_field_is_sent(self):
        c = self._capture()
        for banned in ("input", "output", "prompt", "completion", "messages"):
            assert banned not in c, f"generation carried {banned!r}, which can hold session text"

    def test_payload_contains_no_free_text_beyond_literals(self):
        """model and name are code literals; nothing else may be a string."""
        c = self._capture()
        assert set(c) == {"trace_id", "name", "model", "usage", "metadata"}

    def test_cost_is_not_hardcoded(self):
        """Langfuse derives cost from model + usage; a local price table would drift."""
        c = self._capture()
        assert "cost" not in c
        assert not any("price" in str(k).lower() for k in c)


class TestAllowlistIsDeliberate:
    def test_allowlist_contents_are_pinned(self):
        """Fails when the allowlist changes, forcing a re-read of ADR-011.

        Pinned deliberately. Widening the trace surface should require editing this
        test, not just the source, so it cannot happen as a silent side effect.
        """
        assert obs._ALLOWED_METADATA_KEYS == frozenset({
            "session_slug_hash",
            "install_id",
            "youk_version",
        })

    def test_no_obviously_identifying_key_names(self):
        banned = {
            "project_dir", "path", "cwd", "task", "prompt", "user",
            "email", "hostname", "username", "home", "file", "finding",
        }
        assert not (obs._ALLOWED_METADATA_KEYS & banned)


class TestHashIdentifier:
    def test_is_stable(self):
        assert obs.hash_identifier("youk") == obs.hash_identifier("youk")

    def test_differs_across_inputs(self):
        assert obs.hash_identifier("youk") != obs.hash_identifier("canopy")

    def test_does_not_contain_input(self):
        assert "youk" not in obs.hash_identifier("youk")

    def test_is_not_reversible_by_length(self):
        """Same width regardless of input, so the hash leaks nothing about the name."""
        short = obs.hash_identifier("a")
        long = obs.hash_identifier("a-very-long-internal-client-project-name")
        assert len(short) == len(long) == 16


class TestInstallId:
    def test_generated_once_and_reused(self, tmp_path):
        first = obs.get_install_id(tmp_path)
        second = obs.get_install_id(tmp_path)
        assert first == second
        assert first != "unknown"

    def test_differs_across_installs(self, tmp_path):
        a = tmp_path / "install-a"
        b = tmp_path / "install-b"
        assert obs.get_install_id(a) != obs.get_install_id(b)

    def test_not_derived_from_identity(self, tmp_path, monkeypatch):
        """Must not be reconstructible from the environment it was generated in."""
        monkeypatch.setenv("USER", "ajinkya")
        monkeypatch.setenv("HOME", "/Users/ajinkya")
        install_id = obs.get_install_id(tmp_path)
        assert "ajinkya" not in install_id
        assert install_id != obs.hash_identifier("ajinkya")

    def test_unwritable_state_returns_unknown(self, tmp_path):
        """Observability must never be able to fail a session."""
        blocker = tmp_path / "state"
        blocker.write_text("not a directory")
        assert obs.get_install_id(tmp_path) == "unknown"

    def test_persisted_value_is_used(self, tmp_path):
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "install-id").write_text("pinned-value-123")
        assert obs.get_install_id(tmp_path) == "pinned-value-123"
