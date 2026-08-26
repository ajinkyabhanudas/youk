"""Voice gate accuracy benchmark.

Validates that check_text correctly distinguishes AI-generated prose from
human writing, using representative specimens of each. This is the swap test
from the voice-fingerprint protocol — the gate is only worth wiring once it
passes this test.

Properties verified:
- Known AI-tell specimens: each hard tell produces BLOCKED; each soft-tell cluster
  produces at minimum REVIEW
- Known-human specimens: clean prose without AI markers produces CLEAR
- Gate verdicts are stable (deterministic across repeated calls)
- No false positives on common technical prose patterns (code identifiers, lists,
  short factual sentences in context)

These are NOT profile-comparison tests (profile requires a mature corpus).
They test the tell-detection layer only, which is what matters before corpus matures.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
from voice_fingerprint import check_text

# ── Known AI specimens (must trigger) ─────────────────────────────────────────

_EM_DASH = "The model was accurate — but the benchmark was flawed."

_NOT_JUST = "It's not just a performance problem, but a trust problem."

_CHATBOT_ARTIFACT = "I hope this helps! Feel free to reach out if you have more questions."

_CUTOFF = "As of my last training update, the framework did not support async."

_SIGNPOST = "Let's dive in to what this means for the project."

_AUTHORITY = "The real question is whether we optimised for the right metric."

_GRADED_CLUSTER = (
    "The holistic approach fosters a nuanced understanding of the landscape. "
    "Leveraging these insights, we can seamlessly align our roadmap with strategic priorities. "
    "This transformative shift will enhance outcomes across the ecosystem in meaningful ways. "
    "The multifaceted nature of the challenge underscores the pivotal role of robust tooling. "
    "Additionally, delving deeper into the data reveals a testament to the team's resilience."
)

_PARTICIPLE_PADDING = (
    "The system processed the request, highlighting the need for better error handling, "
    "underscoring the importance of validation, emphasizing the gaps in test coverage, "
    "reflecting a deeper architectural problem, showcasing the limits of the current design."
)

# ── Known-human specimens (must not trigger) ───────────────────────────────────

# Short factual paragraph, no AI markers — sentences vary enough to stay within budget
_HUMAN_SHORT = (
    "We ran the query against five representative tables and measured response time under load. "
    "Three returned results under 100ms with no index changes. "
    "The fourth timed out at 30 seconds on the join because the predicate forced a full scan. "
    "We added an index on report_date, re-ran the same query, and all five completed under 80ms."
)

# Technical commit message style
_HUMAN_COMMIT = (
    "Cache lookup was using case-sensitive comparison. "
    "Normalised to lowercase before hashing so 'What is X?' and 'what is X?' "
    "share a cache entry. Tested against the existing fixture set."
)

# Longer analytical paragraph, no AI cues
_HUMAN_ANALYSIS = (
    "The schema change introduced a NOT NULL column without a backfill migration. "
    "Any row written before the migration ran would fail the constraint check on read. "
    "We caught this in staging because the fixture dataset predated the migration by three weeks. "
    "Production data goes back four years. "
    "The fix is a two-step migration: add the column as nullable, backfill, then add the constraint. "
    "We ran step one in the maintenance window and step two will follow after verification."
)

# Technical prose with colons and lists — should not over-flag
_HUMAN_TECHNICAL = (
    "Three things changed in this release: the auth token format, the session expiry window, "
    "and the rate limit headers. The token format change is breaking for clients on v1.3 or earlier. "
    "Session expiry moved from 24h to 8h. Rate limit headers now use the standard X-RateLimit-* "
    "format instead of the legacy custom ones. Clients on v2.0 or later get all three automatically."
)


# ── Hard tell tests (BLOCKED) ─────────────────────────────────────────────────

class TestHardTells:
    def test_em_dash_blocked(self):
        r = check_text(_EM_DASH)
        assert r["gate"] == "BLOCKED"
        assert any("em_dash" in t for t in r["tells_hard"])

    def test_not_just_pivot_blocked(self):
        r = check_text(_NOT_JUST)
        assert r["gate"] == "BLOCKED"
        assert any("not_just_pivot" in t for t in r["tells_hard"])

    def test_chatbot_artifact_blocked(self):
        r = check_text(_CHATBOT_ARTIFACT)
        assert r["gate"] == "BLOCKED"
        assert any("chatbot_artifact" in t for t in r["tells_hard"])

    def test_cutoff_disclaimer_blocked(self):
        r = check_text(_CUTOFF)
        assert r["gate"] == "BLOCKED"
        assert any("cutoff_disclaimer" in t for t in r["tells_hard"])

    def test_signposting_blocked(self):
        r = check_text(_SIGNPOST)
        assert r["gate"] == "BLOCKED"
        assert any("signposting" in t for t in r["tells_hard"])

    def test_authority_trope_blocked(self):
        r = check_text(_AUTHORITY)
        assert r["gate"] == "BLOCKED"
        assert any("authority_trope" in t for t in r["tells_hard"])


# ── Graded tell tests (at least REVIEW) ───────────────────────────────────────

class TestGradedTells:
    def test_graded_cluster_flagged(self):
        r = check_text(_GRADED_CLUSTER)
        assert r["gate"] in ("REVIEW", "BLOCKED")
        assert len(r["tells_soft"]) >= 3, f"Expected 3+ soft tells, got: {r['tells_soft']}"

    def test_participle_padding_flagged(self):
        r = check_text(_PARTICIPLE_PADDING)
        assert r["gate"] in ("REVIEW", "BLOCKED")
        assert any("participle_padding" in t for t in r["tells_soft"])

    def test_graded_cluster_flags_specific_words(self):
        r = check_text(_GRADED_CLUSTER)
        soft_str = " ".join(r["tells_soft"])
        # At least two of these should appear
        found = sum(1 for w in ("holistic", "nuanced", "leverage", "seamless", "transformative", "delve") if w in soft_str)
        assert found >= 2, f"Expected 2+ graded vocab flags, got: {r['tells_soft']}"


# ── Clean prose tests (CLEAR) ─────────────────────────────────────────────────

class TestCleanProse:
    def test_human_short_clear(self):
        r = check_text(_HUMAN_SHORT)
        assert r["gate"] == "CLEAR", f"False positive: {r['tells_hard']} / {r['tells_soft']}"

    def test_human_commit_clear(self):
        r = check_text(_HUMAN_COMMIT)
        assert r["gate"] == "CLEAR", f"False positive: {r['tells_hard']} / {r['tells_soft']}"

    def test_human_analysis_clear(self):
        r = check_text(_HUMAN_ANALYSIS)
        assert r["gate"] == "CLEAR", f"False positive: {r['tells_hard']} / {r['tells_soft']}"

    def test_human_technical_clear(self):
        r = check_text(_HUMAN_TECHNICAL)
        assert r["gate"] == "CLEAR", f"False positive: {r['tells_hard']} / {r['tells_soft']}"


# ── Stability (determinism) ───────────────────────────────────────────────────

class TestDeterminism:
    def test_blocked_is_stable(self):
        r1 = check_text(_EM_DASH)
        r2 = check_text(_EM_DASH)
        assert r1 == r2

    def test_clear_is_stable(self):
        r1 = check_text(_HUMAN_ANALYSIS)
        r2 = check_text(_HUMAN_ANALYSIS)
        assert r1 == r2


# ── No false positive on common technical patterns ─────────────────────────────

class TestNoFalsePositives:
    def test_code_identifiers_not_flagged(self):
        # Function names containing graded words should not over-trigger
        text = (
            "The enhance_results() function takes a query string and returns a ranked list. "
            "It calls align_scores() internally to normalise the output. "
            "Both functions are tested in test_search.py against a fixture corpus of 500 queries."
        )
        r = check_text(text)
        # May be REVIEW but must not be BLOCKED on a hard tell
        assert r["gate"] != "BLOCKED", f"False BLOCKED: {r['tells_hard']}"

    def test_short_sentences_in_context_not_over_flagged(self):
        # A few short sentences embedded in longer prose should not trigger short_decl_pair
        # when the overall rate is within budget
        long_para = (
            "We audited the query planner output for the five slowest endpoints over the past week. "
            "Each one had a sequential scan on a table with more than two million rows. "
            "The scans were caused by type mismatches in the WHERE clause predicates, "
            "which forced Postgres to cast every row before comparing. "
            "Adding explicit casts to the query parameters eliminated the sequential scans. "
            "Query time dropped from 4.2 seconds to 180ms. "
            "We verified the fix holds under the load test profile we run before each release."
        )
        r = check_text(long_para)
        assert r["gate"] == "CLEAR", f"False positive: {r['tells_soft']}"

    def test_commit_body_colon_scaffolding_filtered_in_audit(self):
        # voice_audit strips colon_scaffolding from soft tells before reporting.
        # Commit bodies are structurally colon-dense (change lists, section headers)
        # and check_text is calibrated for prose. The filter lives in voice_audit, not here.
        # This test verifies that colon_scaffolding is a known soft tell (not a hard block).
        commit_body = (
            "session.py crossed 3900 lines. This PR splits three cohesive function groups "
            "into dedicated modules. No behaviour changes; all callers unchanged.\n\n"
            "- project_detection.py: _detect_project_type/purpose/stack_context, PURPOSE maps\n"
            "- git_context.py: all subprocess git-log helpers, deploy freshness, commit counting\n"
            "- knowledge_loader.py: _load_l2_context, _scan_project_context_files\n"
            "- state_paths.py: adds CLAUDE_ROOT, HOST_HOME constants and resolve_project_path()\n"
            "- session.py: imports from new modules; adds _sync_sp() to keep constants in sync\n"
            "- test_pending_build_task.py: import and monkeypatch targets updated for git_context"
        )
        r = check_text(commit_body)
        # Must not be BLOCKED — colon_scaffolding is a soft tell, not a hard block.
        assert r["gate"] != "BLOCKED", (
            f"Commit body with file-annotation colons must not be BLOCKED: {r['tells_hard']}"
        )


# ── Voice audit colon filter ───────────────────────────────────────────────────

class TestVoiceAuditColonFilter:
    """voice_audit strips colon_scaffolding from soft tells before surfacing results.

    Commit bodies are structurally colon-dense — change lists, section headers,
    file annotations. check_text is calibrated for prose. The filter is in
    voice_audit._audit_recent_commits, not in check_text.
    """

    def test_colon_scaffolding_filtered_from_audit_tells(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
        from voice_audit import audit_recent_commits

        # Patch git log to return a commit body with many colons but no hard tells.
        import subprocess as _sp
        import unittest.mock as _mock

        colon_heavy_body = (
            "- project_detection.py: purpose detection, stack context\n"
            "- git_context.py: git-log helpers, deploy freshness\n"
            "- knowledge_loader.py: L2 context, project file scan\n"
            "- state_paths.py: CLAUDE_ROOT, HOST_HOME constants\n"
            "- session.py: imports from new modules, _sync_sp() added\n"
        )
        fake_log = f"abc1234\x1frefactor: extract modules\x1f{colon_heavy_body}\x1f---END---"

        with _mock.patch("voice_audit.subprocess.run") as mock_run:
            mock_run.return_value = _sp.CompletedProcess(
                args=[], returncode=0, stdout=fake_log, stderr=""
            )
            import tempfile, pathlib
            with tempfile.TemporaryDirectory() as tmp:
                result = audit_recent_commits(pathlib.Path(tmp), n=1)

        # colon_scaffolding must not appear in any reported finding
        for finding in result.get("findings", []):
            soft = " ".join(finding.get("tells_soft", []))
            assert "colon_scaffolding" not in soft, (
                f"colon_scaffolding leaked into audit finding: {finding}"
            )

    def test_em_dash_still_reported_by_audit(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
        from voice_audit import audit_recent_commits
        import subprocess as _sp
        import unittest.mock as _mock

        em_dash_body = "session.py crossed 3900 lines — this PR splits three groups."
        fake_log = f"abc1234\x1frefactor: extract modules\x1f{em_dash_body}\x1f---END---"

        with _mock.patch("voice_audit.subprocess.run") as mock_run:
            mock_run.return_value = _sp.CompletedProcess(
                args=[], returncode=0, stdout=fake_log, stderr=""
            )
            import tempfile, pathlib
            with tempfile.TemporaryDirectory() as tmp:
                result = audit_recent_commits(pathlib.Path(tmp), n=1)

        findings = result.get("findings", [])
        assert len(findings) == 1, "em_dash commit must still be reported"
        hard = " ".join(findings[0].get("tells_hard", []))
        assert "em_dash" in hard, f"em_dash not in hard tells: {findings[0]}"
