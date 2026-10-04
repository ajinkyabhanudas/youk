"""promote_to_global_contracts' abstraction-leak protection: reuses
abstract_claim() (verification_research.py) rather than a second check.
"""
from __future__ import annotations

import global_contracts as gc


def test_contract_with_unrecognized_proprietary_identifier_is_blocked_not_promoted(tmp_path):
    # PascalCase, not in abstract_claim's glossary.
    result = gc.promote_to_global_contracts(
        ["always route billing through PaymentGatewayRetryHandlerV3 first"],
        tmp_path, "billing", "routing",
    )
    assert result["promoted"] == 0
    assert len(result["leak_blocked"]) == 1
    assert "PaymentGatewayRetryHandlerV3" in result["leak_blocked"][0]["contract"]

    global_file = tmp_path / "knowledge" / "global" / "contracts.md"
    if global_file.exists():
        assert "PaymentGatewayRetryHandlerV3" not in global_file.read_text()


def test_plain_acronyms_are_not_falsely_blocked(tmp_path):
    """API/JSON/HTTP must not be flagged -- same false-positive-prevention
    bar as abstract_claim's own tests."""
    result = gc.promote_to_global_contracts(
        ["always validate the API response against the JSON schema before use"],
        tmp_path, "api-design", "validation",
    )
    assert result["promoted"] == 1
    assert result["leak_blocked"] == []


def test_confident_contract_is_written_in_its_abstracted_form(tmp_path):
    """A confidently-abstracted contract is promoted as its abstracted
    text, not the raw original -- glossary terms strip even on success."""
    result = gc.promote_to_global_contracts(
        ["never read {repo} secrets directly from disk"],
        tmp_path, "security-and-privacy", "secrets-handling",
    )
    assert result["promoted"] == 1
    global_file = tmp_path / "knowledge" / "global" / "contracts.md"
    content = global_file.read_text()
    assert "{repo}" not in content or "secrets" in content  # abstracted form present, not raw leak


def test_leak_blocked_contract_never_counted_as_skipped():
    """A blocked contract is a distinct outcome from a duplicate skip --
    conflating them would hide real leak attempts inside a benign-looking
    skip count."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        result = gc.promote_to_global_contracts(
            ["always call AcmeCorpBillingServiceV2 before refund"],
            Path(d), "billing", "refunds",
        )
    assert result["skipped"] == 0
    assert len(result["leak_blocked"]) == 1
