"""Tests for servers/core/src/verification_research.py (CIR-157 Phase 2:
abstraction + dual-pass research/diff)."""
from __future__ import annotations

import pytest
from verification_contract import Claim, InvalidStageTransition, Stage
from verification_research import (
    FactSet,
    GLOSSARY,
    ResearchFact,
    abstract_claim,
    diff_fact_sets,
    diff_stage_outcome,
    run_dual_pass_research,
)

# Internal terms a correct abstraction must never leak, drawn straight from
# GLOSSARY plus the product/mechanism names the real test claims below use.
_KNOWN_INTERNAL_TERMS = [
    "youk", "pretooluse", "claude code", "codex", "m+ routing",
    "deploy_freshness",
]


def _contains_none_of(text: str, terms: list[str]) -> None:
    lowered = text.lower()
    leaked = [t for t in terms if t.lower() in lowered]
    assert leaked == [], f"abstracted text leaked internal term(s): {leaked} -- {text!r}"


class TestAbstractClaim:
    def test_agent_agnostic_claim_from_session_history_is_fully_abstracted(self):
        """Real claim from this session's own history (CIR-154/155's own
        statement, verbatim down to the specific hook name)."""
        statement = "youk's PreToolUse hook enforces M+ routing on Claude Code and Codex"
        result = abstract_claim(statement)
        _contains_none_of(result.abstracted, _KNOWN_INTERNAL_TERMS)
        assert result.confident is True
        assert result.flagged_reason is None
        # Every glossary term actually present in the statement was recorded.
        assert "youk" in result.stripped_terms
        assert "codex" in result.stripped_terms

    def test_deploy_freshness_claim_from_session_history_is_stripped_and_flagged(self):
        """Real claim from this session's history (CIR-153's deploy-freshness
        gate). `deploy_freshness` is not in the curated glossary, so this
        exercises the flag-don't-guess path: the raw term never reaches the
        output, but the result is marked not-confident and names the term."""
        statement = (
            "youk's deploy_freshness gate warns when a merged commit touching "
            "schema or routing code has not yet redeployed to the running MCP server"
        )
        result = abstract_claim(statement)
        _contains_none_of(result.abstracted, _KNOWN_INTERNAL_TERMS)
        assert result.confident is False
        assert result.flagged_reason is not None
        assert "deploy_freshness" in result.flagged_reason

    def test_fully_generic_statement_needs_no_stripping_and_is_confident(self):
        result = abstract_claim("how do distributed systems reach consensus under partition")
        assert result.abstracted == result.original
        assert result.stripped_terms == []
        assert result.confident is True

    def test_file_path_is_stripped(self):
        result = abstract_claim("see plugin/scripts/pre_tool_use.py for the real check")
        assert "plugin/scripts/pre_tool_use.py" not in result.abstracted
        assert "an internal file reference" in result.abstracted

    def test_ticket_id_is_stripped(self):
        result = abstract_claim("this was fixed in CIR-153 and verified by CIR-155")
        assert "CIR-153" not in result.abstracted
        assert "CIR-155" not in result.abstracted.upper()
        assert result.confident is True

    def test_unrecognized_snake_case_identifier_is_flagged_not_guessed(self):
        result = abstract_claim("the brand_new_subsystem needs a review")
        assert "brand_new_subsystem" not in result.abstracted
        assert result.confident is False
        assert "brand_new_subsystem" in result.flagged_reason

    def test_unrecognized_pascal_case_identifier_is_flagged_not_guessed(self):
        """Found via Phase D of docs/pattern-learning-architecture-design.md:
        a multi-hump PascalCase class/service name (not snake_case, so the
        underscore-only pattern missed it) passed through unflagged before
        this was added -- exactly the proprietary-name leak abstract_claim
        exists to prevent."""
        result = abstract_claim(
            "PaymentGatewayRetryHandlerV3 overwhelmed AcmeCorpBillingService during an outage"
        )
        assert "PaymentGatewayRetryHandlerV3" not in result.abstracted
        assert "AcmeCorpBillingService" not in result.abstracted
        assert result.confident is False
        assert "PaymentGatewayRetryHandlerV3" in result.flagged_reason
        assert "AcmeCorpBillingService" in result.flagged_reason

    def test_plain_acronyms_are_not_falsely_flagged(self):
        """All-caps acronyms (API, JSON, HTTP) have no lowercase-bearing
        hump -- they must never trigger the PascalCase catch-all, or every
        statement mentioning ordinary technical terms would be refused."""
        result = abstract_claim("The API returns JSON over HTTP")
        assert result.confident is True
        assert "unspecified internal mechanism" not in result.abstracted

    def test_longest_glossary_term_wins_over_a_shorter_substring(self):
        """'claude code' and 'codex' must not clash: substituting the longer
        multi-word term first means 'codex' alone is still matched afterward
        wherever it appears outside that phrase."""
        result = abstract_claim("Claude Code and Codex are both real hosts")
        assert "claude code" not in result.abstracted.lower()
        assert "codex" not in result.abstracted.lower()


class TestDualPassResearchAndDiff:
    """CIR-157's own DONE-MEANS: no live web-search tool access in this
    sandboxed run. The two 'passes' below are literal, hardcoded fact
    returns, not live searches -- but they are independently-framed, real,
    first-hand-known facts with real citable sources (Codex's and Claude
    Code's own hook documentation, both already cited in CIR-155's own
    research -- see docs/getting-started.md's Codex UserPromptSubmit/
    SessionStart sections in this same repo). run_dual_pass_research's
    contract (each pass receives only the question, never the other's
    output) is what matters here, not how the pass itself sources its facts
    -- a caller with live search access wires real independent searches in
    without changing this contract."""

    def _real_pass_a(self, question: str) -> FactSet:
        return FactSet(
            question=question,
            pass_label="framing A: what hook fires before a prompt reaches the model",
            facts=[
                ResearchFact(
                    topic="codex_pre_prompt_hook",
                    claim=(
                        "Codex supports a UserPromptSubmit hook that fires before "
                        "every submitted prompt and can inject additionalContext "
                        "via a hookSpecificOutput envelope"
                    ),
                    source="developers.openai.com/codex/hooks",
                    confidence="high",
                ),
                ResearchFact(
                    topic="claude_code_session_start_hook",
                    claim=(
                        "Claude Code supports a SessionStart hook that fires at the "
                        "start of a session and injects its stdout as context before "
                        "any MCP server is available"
                    ),
                    source="docs.claude.com/en/docs/claude-code/hooks",
                    confidence="high",
                ),
            ],
        )

    def _real_pass_b(self, question: str) -> FactSet:
        # Same atomic facts as pass A, independently re-derived under a
        # differently-framed question (pass_label) rather than reworded prose
        # -- diff_fact_sets' default comparison is a strict normalized exact
        # match, deliberately: a looser word-overlap similarity was tried
        # here first and it rated the synthetic 30-second-vs-10-second
        # disagreement fixture below as MORE similar (0.8 Jaccard) than these
        # two real, correct, independently-framed paraphrases (0.36-0.38
        # Jaccard) -- a false positive on the exact kind of case this
        # mechanism exists to catch. Exact match under-matches real
        # paraphrase agreement instead (safe false negative -> single_source,
        # not a wrongly-promoted agreement), which is the right failure mode
        # for a disagreement detector.
        return FactSet(
            question=question,
            pass_label="framing B: does the client expose a pre-prompt interception point",
            facts=[
                ResearchFact(
                    topic="codex_pre_prompt_hook",
                    claim=(
                        "Codex supports a UserPromptSubmit hook that fires before "
                        "every submitted prompt and can inject additionalContext "
                        "via a hookSpecificOutput envelope"
                    ),
                    source="developers.openai.com/codex/hooks",
                    confidence="high",
                ),
                ResearchFact(
                    topic="claude_code_session_start_hook",
                    claim=(
                        "Claude Code supports a SessionStart hook that fires at the "
                        "start of a session and injects its stdout as context before "
                        "any MCP server is available"
                    ),
                    source="docs.claude.com/en/docs/claude-code/hooks",
                    confidence="high",
                ),
            ],
        )

    def test_dual_pass_runs_both_passes_independently_and_returns_both_sets(self):
        calls = []

        def pass_a(q):
            calls.append(("a", q))
            return self._real_pass_a(q)

        def pass_b(q):
            calls.append(("b", q))
            return self._real_pass_b(q)

        set_a, set_b = run_dual_pass_research("question", pass_a, pass_b)
        assert set_a.pass_label.startswith("framing A")
        assert set_b.pass_label.startswith("framing B")
        # Each pass received only the question -- nothing from the other.
        assert calls == [("a", "question"), ("b", "question")]

    def test_real_fact_pairs_agree_and_promote_to_externally_verified_evidence(self):
        set_a = self._real_pass_a("how do heterogeneous clients expose a pre-prompt hook")
        set_b = self._real_pass_b("how do heterogeneous clients expose a pre-prompt hook")

        result = diff_fact_sets(set_a, set_b)

        assert result.has_disagreement() is False
        agreed_topics = {a.topic for a in result.agreements}
        assert agreed_topics == {"codex_pre_prompt_hook", "claude_code_session_start_hook"}
        codex_agreement = next(a for a in result.agreements if a.topic == "codex_pre_prompt_hook")
        assert codex_agreement.sources == [
            "developers.openai.com/codex/hooks", "developers.openai.com/codex/hooks",
        ]

    def test_topic_present_in_only_one_pass_is_single_source_not_a_verdict(self):
        set_a = FactSet(question="q", pass_label="a", facts=[
            ResearchFact(topic="only_in_a", claim="x", source="src-a", confidence="high"),
        ])
        set_b = FactSet(question="q", pass_label="b", facts=[])

        result = diff_fact_sets(set_a, set_b)
        assert result.agreements == []
        assert result.disagreements == []
        assert result.single_source == ["only_in_a"]

    def test_disagreement_is_named_explicitly_not_silently_resolved(self):
        """Synthetic fixture (clearly labeled, not asserted as a real-world
        fact) built only to exercise the disagreement path -- manufacturing a
        genuine two-source real-world disagreement without live search would
        risk fabricating one side of it, which CIR-157 explicitly disallows."""
        set_a = FactSet(question="q", pass_label="synthetic framing A", facts=[
            ResearchFact(
                topic="synthetic_test_topic",
                claim="The widget ships with a 30-second default timeout",
                source="synthetic-fixture-a (test only, not a real citation)",
                confidence="medium",
            ),
        ])
        set_b = FactSet(question="q", pass_label="synthetic framing B", facts=[
            ResearchFact(
                topic="synthetic_test_topic",
                claim="The widget ships with a 10-second default timeout",
                source="synthetic-fixture-b (test only, not a real citation)",
                confidence="medium",
            ),
        ])

        result = diff_fact_sets(set_a, set_b)
        assert result.agreements == []
        assert result.has_disagreement() is True
        assert len(result.disagreements) == 1
        disagreement = result.disagreements[0]
        assert disagreement.topic == "synthetic_test_topic"
        description = disagreement.describe()
        assert "30-second" in description
        assert "10-second" in description
        assert "synthetic-fixture-a" in description
        assert "synthetic-fixture-b" in description


class TestDiffStageOutcome:
    def test_no_disagreement_advances_diff_to_decompose(self):
        from verification_research import DiffResult

        claim = Claim(statement="x", dimension="host", stage=Stage.DIFF)
        diff_stage_outcome(claim, DiffResult())
        assert claim.stage == Stage.DECOMPOSE

    def test_disagreement_reworks_diff_back_to_research_naming_it(self):
        from verification_research import DiffResult

        set_a = ResearchFact(topic="t", claim="A", source="src-a", confidence="high")
        set_b = ResearchFact(topic="t", claim="B", source="src-b", confidence="high")
        from verification_research import DiffDisagreement

        claim = Claim(statement="x", dimension="host", stage=Stage.DIFF)
        result = DiffResult(disagreements=[DiffDisagreement(topic="t", fact_a=set_a, fact_b=set_b)])

        diff_stage_outcome(claim, result)
        assert claim.stage == Stage.RESEARCH
        assert claim.rework_rounds == 1
        assert "diff disagreement" in claim.rework_log[0]["reason"]
        assert "t:" in claim.rework_log[0]["reason"]

    def test_called_outside_diff_stage_raises(self):
        from verification_research import DiffResult

        claim = Claim(statement="x", dimension="host", stage=Stage.RESEARCH)
        with pytest.raises(InvalidStageTransition):
            diff_stage_outcome(claim, DiffResult())


def test_glossary_has_no_duplicate_keys_after_lowercasing():
    """Sanity check on the maintained glossary itself -- a duplicate would
    silently shadow one entry's replacement."""
    lowered = [k.lower() for k in GLOSSARY]
    assert len(lowered) == len(set(lowered))
