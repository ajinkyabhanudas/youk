"""
Quality measurement framework for youk context hooks.

Tests three quality dimensions:
1. Contract survival  — after a compact cycle, do contracts survive intact?
2. Resume accuracy    — does the post-compact brief answer "where were we"?
3. Reasoning continuity — does the brief carry enough to continue a debug chain?

And two integrity checks:
4. Brief token budget — index brief stays under 250 tokens (~1000 chars)
5. No regression on full brief — mode="full" still includes everything

These are deterministic assertions against the brief *content*, not LLM
responses. We test that the brief is sufficient to answer the resume
questions — not that Claude answers them (that would require an API call).

Token approximation: len(text) // 4
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))
sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "scripts"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def project_env(tmp_path, monkeypatch):
    """
    Full project environment: youk_root, contracts, decisions, session plan,
    active_task.json. Mirrors a real mid-session state.
    """
    import compaction

    root = tmp_path / "youk"
    slug = "myproject"
    proj_dir = root / "knowledge" / "projects" / slug
    proj_dir.mkdir(parents=True)
    state_dir = root / "state"
    state_dir.mkdir()

    # Contracts
    (proj_dir / "contracts.md").write_text(
        "# contracts\n"
        "- always use logical commits\n"
        "- never skip tests before committing\n"
        "- use TypeScript strict mode in all new files\n"
        "- run ruff before every PR\n"
    )

    # Decisions
    (proj_dir / "decisions.md").write_text(
        "## Auth: use JWT not sessions\n"
        "Decided 2026-07-01. Sessions don't scale across services.\n\n"
        "## API versioning: prefix with /v1/\n"
        "Decided 2026-07-02. Allows breaking changes without client breakage.\n"
    )

    # Session plan
    (state_dir / "session-plan.json").write_text(json.dumps({
        "slug": slug,
        "plan": [
            "Fix token expiry bug in auth middleware",
            "Add tests for refresh token flow",
            "Update API docs after auth changes",
        ],
    }))

    # Session state
    (state_dir / "session.json").write_text(json.dumps({
        "session_counter": 12,
        "last_project": f"/home/user/{slug}",
    }))

    # Active task (from PostToolUse hook)
    (state_dir / "active_task.json").write_text(json.dumps({
        "task": "editing auth/middleware.py",
        "cwd": f"/home/user/{slug}",
        "slug": slug,
        "files_touched": ["auth/middleware.py", "tests/test_auth.py"],
        "last_signal": "AssertionError: token expired after 3600s expected 86400s",
        "last_tool": "Bash",
        "updated_at": "2026-07-09T12:00:00Z",
    }))

    monkeypatch.setattr(compaction, "YOUK_ROOT", root)
    return {"root": root, "slug": slug, "project_dir": f"/home/user/{slug}"}


# ── 1. Contract Survival ───────────────────────────────────────────────────────

class TestContractSurvival:
    """After compact cycle, all contracts must be recoverable from the brief."""

    def test_full_brief_contains_all_contracts(self, project_env):
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        brief = result["brief"]
        assert "always use logical commits" in brief
        assert "never skip tests before committing" in brief
        assert "use TypeScript strict mode" in brief
        assert "run ruff before every PR" in brief

    def test_full_brief_contracts_verbatim_not_paraphrased(self, project_env):
        """Contracts must appear character-for-character, not summarized."""
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        brief = result["brief"]
        # These exact strings must survive, not paraphrases like "use logical commits"
        assert "- always use logical commits" in brief
        assert "- never skip tests before committing" in brief

    def test_index_brief_matching_contracts_verbatim(self, project_env):
        """Index mode: contracts matching intent appear verbatim."""
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix auth token expiry bug",
            mode="index",
        )
        brief = result["brief"]
        # "auth" doesn't appear in any contract so none match — but the count should
        # None of our contracts mention "auth" or "token" or "expiry"
        # So we test the count-only fallback:
        assert "contracts.md" in brief or "contract" in brief.lower()

    def test_index_brief_matching_contracts_when_keyword_matches(self, project_env):
        """Index mode: a contract containing an intent keyword appears verbatim."""
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="ruff linting check",
            mode="index",
        )
        brief = result["brief"]
        assert "run ruff before every PR" in brief

    def test_index_brief_non_matching_contracts_appear_as_count(self, project_env):
        """Non-matching contracts must be count-only, not included verbatim."""
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="ruff linting check",  # only "ruff" contract matches
            mode="index",
        )
        brief = result["brief"]
        # The other 3 contracts should NOT appear verbatim
        assert "always use logical commits" not in brief
        assert "never skip tests" not in brief
        # But there should be a "others" count
        assert "+3 other" in brief or "+3 contract" in brief

    def test_pre_compact_brief_contains_all_contracts(self, project_env, tmp_path):
        """PreCompact hook brief must include all contracts for the summarizer."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "scripts"))
        import pre_compact
        import youk_hook_utils

        root = project_env["root"]
        slug = project_env["slug"]

        brief = pre_compact.build_pre_compact_brief(root, slug, project_env["project_dir"])
        assert "always use logical commits" in brief
        assert "never skip tests before committing" in brief
        assert "use TypeScript strict mode" in brief
        assert "VERBATIM" in brief  # preservation instruction present


# ── 2. Resume Accuracy ────────────────────────────────────────────────────────

class TestResumeAccuracy:
    """After compact, brief must answer 'where were we' accurately."""

    def test_full_brief_contains_resume_plan_item(self, project_env):
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        brief = result["brief"]
        assert "Fix token expiry bug in auth middleware" in brief

    def test_index_brief_contains_resume_item(self, project_env):
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix token expiry",
            mode="index",
        )
        brief = result["brief"]
        assert "Fix token expiry bug" in brief

    def test_index_brief_contains_active_task(self, project_env):
        """Active task from PostToolUse hook must appear in index brief."""
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix auth middleware",
            mode="index",
        )
        brief = result["brief"]
        assert "auth/middleware.py" in brief

    def test_index_brief_contains_last_signal(self, project_env):
        """Last error signal from PostToolUse must be in brief for debugging continuity."""
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix token bug",
            mode="index",
        )
        brief = result["brief"]
        assert "AssertionError" in brief or "token expired" in brief

    def test_pre_compact_brief_contains_active_task(self, project_env):
        import pre_compact
        root = project_env["root"]
        slug = project_env["slug"]
        brief = pre_compact.build_pre_compact_brief(root, slug, project_env["project_dir"])
        assert "auth/middleware.py" in brief
        assert "AssertionError" in brief or "token expired" in brief

    def test_pre_compact_brief_contains_session_plan(self, project_env):
        import pre_compact
        root = project_env["root"]
        slug = project_env["slug"]
        brief = pre_compact.build_pre_compact_brief(root, slug, project_env["project_dir"])
        assert "Fix token expiry bug in auth middleware" in brief


# ── 3. Reasoning Continuity ───────────────────────────────────────────────────

class TestReasoningContinuity:
    """
    Simulates: Claude identifies error → compact fires → can Claude continue?
    Tests that the brief carries enough context to pick up a debug chain.
    """

    def test_brief_carries_error_context_for_debug_chain(self, project_env):
        """
        Scenario: we identified 'token expired after 3600s' as the bug.
        After compact, brief must still reference this so Claude can continue.
        """
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix token expiry debug",
            mode="index",
        )
        brief = result["brief"]
        # The error was stored in active_task.last_signal by PostToolUse hook
        assert "3600" in brief or "token expired" in brief or "AssertionError" in brief

    def test_brief_carries_files_being_edited(self, project_env):
        """After compact, Claude must know which files were being edited."""
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="auth middleware",
            mode="index",
        )
        brief = result["brief"]
        assert "middleware.py" in brief

    def test_decision_context_survives_in_full_brief(self, project_env):
        """Key decisions (like 'use JWT') must survive for reasoning continuity."""
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        brief = result["brief"]
        assert "JWT" in brief or "Auth" in brief

    def test_warnings_not_included_in_resume_item(self, project_env):
        """⚠ warning items must not appear as the resume point."""
        import compaction
        # Add a warning to the plan
        state_dir = project_env["root"] / "state"
        (state_dir / "session-plan.json").write_text(json.dumps({
            "slug": project_env["slug"],
            "plan": [
                "⚠ Last session closed without /done",
                "Fix token expiry bug in auth middleware",
            ],
        }))
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix token",
            mode="index",
        )
        brief = result["brief"]
        # Warning item must not be the resume point
        assert "Fix token expiry bug" in brief
        # The warning may or may not appear — but must not be the *resume* line
        resume_line = next(
            (ln for ln in brief.splitlines() if ln.startswith("Resume:")), ""
        )
        assert "⚠" not in resume_line


# ── 4. Brief Token Budget ─────────────────────────────────────────────────────

class TestBriefTokenBudget:
    """Index brief must stay within token budget to avoid per-turn cost bloat."""

    INDEX_TOKEN_LIMIT = 250   # ~1000 chars
    FULL_TOKEN_LIMIT = 1500   # ~6000 chars (full brief is intentionally larger)

    def test_index_brief_under_token_limit(self, project_env):
        import compaction
        result = compaction.build_brief(
            project_env["project_dir"],
            intent="fix auth token",
            mode="index",
        )
        brief = result["brief"]
        approx_tokens = len(brief) // 4
        assert approx_tokens <= self.INDEX_TOKEN_LIMIT, (
            f"Index brief too large: ~{approx_tokens} tokens "
            f"(limit: {self.INDEX_TOKEN_LIMIT}). "
            f"Brief:\n{brief}"
        )

    def test_full_brief_under_token_limit(self, project_env):
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        brief = result["brief"]
        approx_tokens = len(brief) // 4
        assert approx_tokens <= self.FULL_TOKEN_LIMIT, (
            f"Full brief too large: ~{approx_tokens} tokens "
            f"(limit: {self.FULL_TOKEN_LIMIT}). "
        )

    def test_index_smaller_than_full(self, project_env):
        """Index mode must always be smaller than full mode."""
        import compaction
        full = compaction.build_brief(project_env["project_dir"], mode="full")["brief"]
        index = compaction.build_brief(
            project_env["project_dir"],
            intent="fix auth token",
            mode="index",
        )["brief"]
        assert len(index) < len(full), (
            f"Index ({len(index)} chars) is not smaller than full ({len(full)} chars)"
        )


# ── 5. No-Intent Regression ───────────────────────────────────────────────────

class TestNoIntentRegression:
    """build_brief with no intent must behave identically to before (full mode)."""

    def test_no_intent_defaults_to_full_mode(self, project_env):
        import compaction
        # No intent = full mode (backward compatible)
        result = compaction.build_brief(project_env["project_dir"])
        brief = result["brief"]
        assert "always use logical commits" in brief
        assert "never skip tests" in brief
        assert "YOUK CONTEXT BRIEF" in brief

    def test_full_mode_includes_session_plan(self, project_env):
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        brief = result["brief"]
        assert "Session plan" in brief
        assert "Fix token expiry" in brief

    def test_contracts_count_returned_correctly(self, project_env):
        import compaction
        result = compaction.build_brief(project_env["project_dir"], mode="full")
        assert result["contracts_count"] == 4


# ── 6. Hook Utils Quality ─────────────────────────────────────────────────────

class TestHookUtils:
    """Unit tests for youk_hook_utils functions."""

    def test_extract_intent_keywords_filters_stop_words(self):
        from youk_hook_utils import extract_intent_keywords
        kw = extract_intent_keywords("help me fix the auth token expiry bug")
        assert "auth" in kw
        assert "token" in kw
        assert "expiry" in kw
        assert "the" not in kw   # stop word
        assert "me" not in kw    # stop word
        # "fix" is 3 chars — filtered by len > 3; "bug" same
        assert "fix" not in kw
        assert "bug" not in kw

    def test_contract_matches_intent_true(self):
        from youk_hook_utils import contract_matches_intent
        assert contract_matches_intent(
            "run ruff before every PR", {"ruff", "linting"}
        )

    def test_contract_matches_intent_false(self):
        from youk_hook_utils import contract_matches_intent
        assert not contract_matches_intent(
            "always use logical commits", {"ruff", "linting"}
        )

    def test_contract_matches_empty_keywords_always_true(self):
        from youk_hook_utils import contract_matches_intent
        # Empty keywords = no intent filter = include everything
        assert contract_matches_intent("anything", set())

    def test_estimate_context_tokens_from_chars(self, tmp_path):
        from youk_hook_utils import estimate_context_tokens
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("x" * 4000)  # 4000 chars = ~1000 tokens
        result = estimate_context_tokens(str(transcript))
        assert result == 1000

    def test_estimate_context_tokens_missing_file(self):
        from youk_hook_utils import estimate_context_tokens
        assert estimate_context_tokens("/nonexistent/path") == 0

    def test_slug_from_cwd(self):
        from youk_hook_utils import slug_from_cwd
        assert slug_from_cwd("/home/user/myproject") == "myproject"
        assert slug_from_cwd("/") == "unknown"

    def test_build_intent_gated_brief_under_250_tokens(self, tmp_path):
        from youk_hook_utils import build_intent_gated_brief, extract_intent_keywords

        root = tmp_path / "youk"
        slug = "proj"
        proj_dir = root / "knowledge" / "projects" / slug
        proj_dir.mkdir(parents=True)
        (root / "state").mkdir()
        (proj_dir / "contracts.md").write_text(
            "- always use logical commits\n- run tests before commit\n"
        )
        (root / "state" / "session-plan.json").write_text(json.dumps({
            "slug": slug,
            "plan": ["Fix the login bug"],
        }))

        keywords = extract_intent_keywords("fix login authentication")
        brief = build_intent_gated_brief(root, slug, keywords)
        approx_tokens = len(brief) // 4
        assert approx_tokens <= 250, f"Hook brief too large: ~{approx_tokens} tokens"

    def test_build_intent_gated_brief_contains_youk_markers(self, tmp_path):
        from youk_hook_utils import build_intent_gated_brief

        root = tmp_path / "youk"
        (root / "knowledge" / "projects" / "proj").mkdir(parents=True)
        (root / "state").mkdir()

        brief = build_intent_gated_brief(root, "proj", {"fix", "auth"})
        assert "[YOUK BRIEF]" in brief
        assert "[/YOUK BRIEF]" in brief


# ── 7. PostToolUse Hook Quality ───────────────────────────────────────────────

class TestPostToolUseHook:
    """active_task.json written correctly for different tool types."""

    def _run_hook(self, tool_name: str, tool_input: dict, tool_result: str,
                  cwd: str, root: Path) -> dict:
        import post_tool_use
        import youk_hook_utils
        import io

        monkeypatch_data = json.dumps({
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": tool_result,
            "cwd": cwd,
            "session_id": "test-session",
            "transcript_path": "",
            "hook_event_name": "PostToolUse",
        })

        original_root = None
        try:
            original_root = youk_hook_utils.youk_root
            youk_hook_utils.youk_root = lambda: root

            original_stdin = sys.stdin
            sys.stdin = io.StringIO(monkeypatch_data)

            try:
                post_tool_use.main()
            except SystemExit:
                pass
            finally:
                sys.stdin = original_stdin
        finally:
            if original_root:
                youk_hook_utils.youk_root = original_root

        active_file = root / "state" / "active_task.json"
        if active_file.exists():
            return json.loads(active_file.read_text())
        return {}

    def _invoke_post_tool_use(self, root: Path, data: dict, monkeypatch) -> dict:
        """Run post_tool_use.main() with patched youk_root and stdin."""
        import io
        import post_tool_use
        import youk_hook_utils

        monkeypatch.setattr(youk_hook_utils, "youk_root", lambda: root)
        # Also patch the reference post_tool_use imported at module load time
        monkeypatch.setattr(post_tool_use, "youk_root", lambda: root)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))

        try:
            post_tool_use.main()
        except SystemExit:
            pass

        active_file = root / "state" / "active_task.json"
        if active_file.exists():
            return json.loads(active_file.read_text())
        return {}

    def test_bash_tool_extracts_last_line_as_signal(self, tmp_path, monkeypatch):
        root = tmp_path / "youk"
        (root / "state").mkdir(parents=True)
        state = self._invoke_post_tool_use(root, {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_result": ".....\n5 passed in 0.3s",
            "cwd": str(tmp_path / "myproject"),
            "session_id": "s1",
            "transcript_path": "",
            "hook_event_name": "PostToolUse",
        }, monkeypatch)
        assert "5 passed" in state.get("last_signal", "")

    def test_edit_tool_records_file_path(self, tmp_path, monkeypatch):
        root = tmp_path / "youk"
        (root / "state").mkdir(parents=True)
        state = self._invoke_post_tool_use(root, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/home/user/myproject/auth/middleware.py"},
            "tool_result": "OK",
            "cwd": str(tmp_path / "myproject"),
            "session_id": "s1",
            "transcript_path": "",
            "hook_event_name": "PostToolUse",
        }, monkeypatch)
        # files_touched stores full path
        assert any("middleware.py" in f for f in state.get("files_touched", []))

    def test_different_cwd_resets_state(self, tmp_path, monkeypatch):
        """If cwd changes (different project), active_task files_touched is reset."""
        root = tmp_path / "youk"
        (root / "state").mkdir(parents=True)
        # Pre-seed state for project A
        (root / "state" / "active_task.json").write_text(json.dumps({
            "task": "project A task",
            "cwd": "/home/user/projectA",
            "slug": "projectA",
            "files_touched": ["a.py"],
            "last_signal": "A signal",
            "last_tool": "Edit",
            "updated_at": "2026-07-09T10:00:00Z",
        }))
        # PostToolUse fires from project B
        state = self._invoke_post_tool_use(root, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/home/user/projectB/b.py"},
            "tool_result": "OK",
            "cwd": "/home/user/projectB",
            "session_id": "s2",
            "transcript_path": "",
            "hook_event_name": "PostToolUse",
        }, monkeypatch)
        # a.py belonged to project A — should not appear after cwd reset
        assert not any("a.py" in f for f in state.get("files_touched", []))
        assert any("b.py" in f for f in state.get("files_touched", []))
