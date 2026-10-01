"""Abstraction + dual-pass research/diff (CIR-157, Phase 2 of the
verification pipeline). Wires real logic behind two stages CIR-156 only
reserved: ABSTRACT and RESEARCH/DIFF.

ABSTRACTION (abstract_claim): strip proprietary specifics from a claim's
statement before anything goes external. This is a maintained rule set, not
NLP — a curated glossary of known internal terms, a file-path/ticket-ID
pattern, and a snake_case identifier pattern for anything the glossary
doesn't recognize. The identifier-pattern catch-all never guesses a specific
meaning for an unrecognized internal term: it replaces it with a generic
placeholder and flags the result as not-confident, naming the raw term it
couldn't map, so a human can extend the glossary rather than the function
silently asserting an abstraction it isn't sure of.

DUAL-PASS RESEARCH + DIFF (run_dual_pass_research, diff_fact_sets): two
independent research passes over the same abstracted question, each
producing a FactSet keyed by topic. Agreement on a topic across both passes
promotes that fact to externally_verified evidence (see
verification_contract.mark_externally_verified). Disagreement is never
silently resolved — it is named explicitly and routed to Stage.DIFF via
diff_stage_outcome, which reworks the claim back to Stage.RESEARCH.

SCOPE NOTE (live web search): this module has no live search tool access in
the sandboxed run that wrote it. `run_dual_pass_research` takes the two
research passes as injected callables precisely so a caller with real search
access can wire live, independent searches in without changing this module's
contract. The tests exercise the real mechanism end-to-end against real,
first-hand-known, citable fact pairs (Codex's and Claude Code's own hook
docs — see test_verification_research.py) for the agreement path, and a
clearly-labeled synthetic fact pair for the disagreement path, because
manufacturing a genuine two-source real-world disagreement without live
search risks fabricating one side of it. Live dual-search integration is an
explicit, scoped-out follow-up requiring real tool access this run doesn't
have.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from verification_contract import Claim, InvalidStageTransition, Stage, advance, rework

# Known internal terms this codebase actually uses, mapped to a generic,
# structurally-equivalent replacement. Lowercase keys, matched
# case-insensitively. Longest keys are substituted first (abstract_claim
# sorts by length) so multi-word terms aren't partially shadowed by a
# shorter term that happens to be a substring of them.
GLOSSARY: dict[str, str] = {
    "claude code": "a client with one set of interception points",
    "m+ routing": "a complexity-tiered routing precondition",
    "pretooluse": "a pre-action interception point",
    "sessionstart": "a session-initialization interception point",
    "userpromptsubmit": "a pre-prompt interception point",
    "pre_tool_guard": "a precondition-enforcement mechanism",
    "compaction_context": "a context-compaction mechanism",
    "prompt_context": "a prompt-context-injection mechanism",
    "session_context": "a session-context-injection mechanism",
    "hooks.json": "a host-level hook configuration file",
    "paperclip": "the orchestration platform",
    "codex": "a client with a different set of interception points",
    "youk": "the system",
    "mcp": "an inter-process tool protocol",
}

_TICKET_PATTERN = re.compile(r"\bCIR-\d+\b", re.IGNORECASE)
_PATH_PATTERN = re.compile(
    r"\b[\w\-]+(?:/[\w\-.]+)+\.\w+\b"          # a/b/c.ext
    r"|\b[\w\-]+\.(?:py|json|md|toml|ya?ml|ts|tsx|js|sh)\b"  # bare file.ext
)
# Any underscore-joined lowercase token not already stripped above is treated
# as a code identifier -- ordinary prose doesn't use underscores. Caught here
# so an unrecognized internal mechanism name never leaks into the abstracted
# output even when it isn't in GLOSSARY yet.
_IDENTIFIER_PATTERN = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


@dataclass
class AbstractionResult:
    original: str
    abstracted: str
    stripped_terms: list[str] = field(default_factory=list)
    confident: bool = True
    flagged_reason: str | None = None


def abstract_claim(statement: str) -> AbstractionResult:
    """Produce a generic, structurally-equivalent version of `statement`
    with no product names, file paths, or internal architecture terms.
    Confident=False (with flagged_reason naming the raw term(s)) when an
    identifier-shaped token survives the known glossary and the
    path/ticket-ID patterns -- flagged, never guessed."""
    text = statement
    stripped: list[str] = []

    for term in sorted(GLOSSARY, key=len, reverse=True):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        if pattern.search(text):
            stripped.append(term)
            text = pattern.sub(GLOSSARY[term], text)

    if _TICKET_PATTERN.search(text):
        stripped.extend(m.upper() for m in _TICKET_PATTERN.findall(text))
        text = _TICKET_PATTERN.sub("an internal tracking reference", text)

    if _PATH_PATTERN.search(text):
        stripped.extend(_PATH_PATTERN.findall(text))
        text = _PATH_PATTERN.sub("an internal file reference", text)

    unmapped: list[str] = []

    def _flag_identifier(m: re.Match) -> str:
        unmapped.append(m.group(0))
        return "an unspecified internal mechanism"

    text = _IDENTIFIER_PATTERN.sub(_flag_identifier, text)
    stripped.extend(unmapped)

    if unmapped:
        return AbstractionResult(
            original=statement,
            abstracted=text,
            stripped_terms=stripped,
            confident=False,
            flagged_reason=(
                "unrecognized identifier-shaped term(s), not in the "
                f"glossary, generalized without confidence: {', '.join(sorted(set(unmapped)))}"
            ),
        )

    return AbstractionResult(
        original=statement, abstracted=text, stripped_terms=stripped,
        confident=True, flagged_reason=None,
    )


@dataclass
class ResearchFact:
    """One fact an independent research pass produced. `source` must be a
    real citable source (a document, a URL, a named standard) -- never
    'general knowledge'. `topic` is a short slug naming which aspect of the
    abstracted question this fact addresses; diff_fact_sets pairs facts
    across the two passes by topic."""
    topic: str
    claim: str
    source: str
    confidence: str


@dataclass
class FactSet:
    question: str
    pass_label: str
    facts: list[ResearchFact] = field(default_factory=list)

    def by_topic(self) -> dict[str, ResearchFact]:
        return {f.topic: f for f in self.facts}


ResearchPass = Callable[[str], FactSet]


def run_dual_pass_research(
    question: str, pass_a: ResearchPass, pass_b: ResearchPass,
) -> tuple[FactSet, FactSet]:
    """Run two research passes over the same abstracted `question`. The two
    callables are independent by contract: each receives only `question`,
    never the other's output -- different framing of the same question
    between pass_a and pass_b is fine, and arguably strengthens
    independence, as long as neither sees the other's intermediate result.
    This function enforces that shape structurally (no channel exists for
    one pass's result to reach the other); it cannot police what a caller's
    pass_a/pass_b closures capture internally."""
    return pass_a(question), pass_b(question)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass
class DiffAgreement:
    topic: str
    claim: str
    sources: list[str]
    confidence: str


@dataclass
class DiffDisagreement:
    topic: str
    fact_a: ResearchFact
    fact_b: ResearchFact

    def describe(self) -> str:
        return (
            f"{self.topic}: {self.fact_a.claim!r} ({self.fact_a.source}) "
            f"vs {self.fact_b.claim!r} ({self.fact_b.source})"
        )


@dataclass
class DiffResult:
    agreements: list[DiffAgreement] = field(default_factory=list)
    disagreements: list[DiffDisagreement] = field(default_factory=list)
    single_source: list[str] = field(default_factory=list)

    def has_disagreement(self) -> bool:
        return bool(self.disagreements)


def diff_fact_sets(
    set_a: FactSet, set_b: FactSet,
    *, similarity_fn: Callable[[str, str], bool] | None = None,
) -> DiffResult:
    """Compare two independently-produced fact sets, paired by topic.

    Agreement (claims match, by `similarity_fn` if given, else normalized
    exact text match) promotes the fact to externally_verified evidence for
    the matching sub_claim. Disagreement (same topic, differing claim text)
    is recorded explicitly, never silently resolved -- the caller routes it
    to Stage.DIFF via diff_stage_outcome. A topic present in only one pass is
    neither agreement nor disagreement -- it stays unconfirmed, listed in
    single_source for transparency, not treated as settled either way.

    The default is a strict exact match, deliberately, not a looser
    word-overlap similarity: measured against this module's own test fixtures,
    a Jaccard-overlap heuristic rated a synthetic "30-second" vs "10-second"
    timeout disagreement as MORE similar than two real, correct, independently
    -worded paraphrases of the same documented fact -- a false positive on
    exactly the case this function exists to catch. Exact match instead
    under-matches real paraphrase agreement (a safe false negative, landing a
    fact in single_source rather than wrongly promoting it), which is the
    right failure mode for a disagreement detector. A caller with a vetted
    semantic-similarity function may pass one in via `similarity_fn`."""
    match = similarity_fn or (lambda a, b: _normalize(a) == _normalize(b))
    topics_a = set_a.by_topic()
    topics_b = set_b.by_topic()
    result = DiffResult()

    for topic in sorted(set(topics_a) | set(topics_b)):
        fact_a = topics_a.get(topic)
        fact_b = topics_b.get(topic)
        if fact_a is not None and fact_b is not None:
            if match(fact_a.claim, fact_b.claim):
                result.agreements.append(DiffAgreement(
                    topic=topic, claim=fact_a.claim,
                    sources=[fact_a.source, fact_b.source],
                    confidence=fact_a.confidence,
                ))
            else:
                result.disagreements.append(
                    DiffDisagreement(topic=topic, fact_a=fact_a, fact_b=fact_b)
                )
        else:
            result.single_source.append(topic)

    return result


def diff_stage_outcome(claim: Claim, diff_result: DiffResult) -> Claim:
    """Drive a claim at Stage.DIFF forward once the dual-pass diff has run.
    No disagreement -> advance to DECOMPOSE (the real FORWARD_EDGES wiring
    CIR-157 adds). Any disagreement -> rework back to RESEARCH, naming every
    disagreement explicitly in the rework reason -- never resolved by
    picking a side."""
    if claim.stage != Stage.DIFF:
        raise InvalidStageTransition(
            f"diff_stage_outcome called with claim at stage "
            f"{claim.stage.value!r}, not 'diff'"
        )
    if diff_result.disagreements:
        reason = "; ".join(d.describe() for d in diff_result.disagreements)
        return rework(claim, Stage.RESEARCH, reason=f"diff disagreement: {reason}")
    return advance(claim, Stage.DECOMPOSE)
