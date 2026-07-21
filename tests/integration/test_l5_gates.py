"""L5 — Gate Correctness + Guardrails.

Tests call Python functions directly (no Docker for most cases) using
real path constants pointing at the actual repo. Gate logic has no
external dependencies beyond reading/writing state files.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

YOUK_DIR = Path.home() / ".claude" / "youk"

# Ensure server modules are importable (already done in conftest, but belt+suspenders)
for _p in [
    str(YOUK_DIR / "servers" / "shared"),
    str(YOUK_DIR / "servers" / "core" / "src"),
    str(YOUK_DIR / "servers" / "code" / "src"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# NFR Gate
# ---------------------------------------------------------------------------

class TestNfrGate:

    def test_m_task_blocked_without_nfr(self):
        from nfr_gate import check_nfr_gate
        r = check_nfr_gate("implement retry logic", "M", None)
        assert r["blocked"] is True

    def test_xs_task_always_passes(self):
        from nfr_gate import check_nfr_gate
        r = check_nfr_gate("fix typo", "XS", None)
        assert r["blocked"] is False

    def test_s_task_always_passes(self):
        from nfr_gate import check_nfr_gate
        r = check_nfr_gate("fix login bug", "S", None)
        assert r["blocked"] is False

    def test_m_task_unblocked_with_nfr_block(self):
        from nfr_gate import check_nfr_gate
        nfr_block = "[NFR — QUICK_4Q] Q1: latency <200ms. Q2: retry 3x. Q3: idempotent. Q4: log request_id."
        r = check_nfr_gate("implement retry logic", "M", nfr_block)
        assert r["blocked"] is False

    def test_l_task_blocked_without_nfr(self):
        from nfr_gate import check_nfr_gate
        r = check_nfr_gate("design auth module", "L", None)
        assert r["blocked"] is True

    def test_xl_task_blocked_without_nfr(self):
        from nfr_gate import check_nfr_gate
        r = check_nfr_gate("new platform", "XL", None)
        assert r["blocked"] is True

    def test_result_always_has_required_keys(self):
        from nfr_gate import check_nfr_gate
        for size in ("XS", "S", "M", "L", "XL"):
            r = check_nfr_gate("task", size, None)
            assert "blocked" in r, f"check_nfr_gate({size}) missing 'blocked' key"


# ---------------------------------------------------------------------------
# Challenge Gate
# ---------------------------------------------------------------------------

class TestChallengeGate:

    def test_m_blocked_when_challenge_not_ran(self, tmp_path, monkeypatch):
        import challenge_gate
        monkeypatch.setattr(challenge_gate, "STATE_DIR", tmp_path)
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("implement retry logic", "M", False)
        assert r["blocked"] is True

    def test_m_unblocked_when_challenge_ran(self, tmp_path, monkeypatch):
        import challenge_gate
        monkeypatch.setattr(challenge_gate, "STATE_DIR", tmp_path)
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("implement retry logic", "M", True)
        assert r["blocked"] is False

    def test_xs_always_passes_regardless_of_challenge(self, tmp_path, monkeypatch):
        import challenge_gate
        monkeypatch.setattr(challenge_gate, "STATE_DIR", tmp_path)
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("fix typo", "XS", False)
        assert r["blocked"] is False

    def test_l_blocked_when_challenge_not_ran(self, tmp_path, monkeypatch):
        import challenge_gate
        monkeypatch.setattr(challenge_gate, "STATE_DIR", tmp_path)
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("design auth module", "L", False)
        assert r["blocked"] is True


# ---------------------------------------------------------------------------
# Task Contract Gate
# ---------------------------------------------------------------------------

class TestTaskContractGate:

    def test_m_not_blocked(self, tmp_path, monkeypatch):
        import task_contract
        contracts_dir = tmp_path / "task-contracts"
        contracts_dir.mkdir()
        monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", contracts_dir)
        from task_contract import check_task_contract_gate
        r = check_task_contract_gate("M")
        assert r["blocked"] is False

    def test_s_not_blocked(self, tmp_path, monkeypatch):
        import task_contract
        contracts_dir = tmp_path / "task-contracts"
        contracts_dir.mkdir()
        monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", contracts_dir)
        from task_contract import check_task_contract_gate
        r = check_task_contract_gate("S")
        assert r["blocked"] is False

    def test_l_blocked_without_approved_contract(self, tmp_path, monkeypatch):
        import task_contract
        contracts_dir = tmp_path / "task-contracts"
        contracts_dir.mkdir()
        monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", contracts_dir)
        from task_contract import check_task_contract_gate
        r = check_task_contract_gate("L")
        assert r["blocked"] is True

    def test_xl_blocked_without_approved_contract(self, tmp_path, monkeypatch):
        import task_contract
        contracts_dir = tmp_path / "task-contracts"
        contracts_dir.mkdir()
        monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", contracts_dir)
        from task_contract import check_task_contract_gate
        r = check_task_contract_gate("XL")
        assert r["blocked"] is True

    def test_l_unblocked_with_approved_contract(self, tmp_path, monkeypatch):
        import datetime, task_contract
        contracts_dir = tmp_path / "task-contracts"
        contracts_dir.mkdir()
        monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", contracts_dir)
        # Write a synthetic approved contract file
        (contracts_dir / "task-contract-checkup.json").write_text(json.dumps({
            "contract_id": "checkup-test",
            "size": "L",
            "approved": True,
            "as_approved": "synthetic test contract",
            "approved_at": datetime.datetime.utcnow().isoformat(),
        }))
        from task_contract import check_task_contract_gate
        r = check_task_contract_gate("L")
        assert r["blocked"] is False


# ---------------------------------------------------------------------------
# Guardrails — apply_proposal review_required gate
# ---------------------------------------------------------------------------

class TestGuardrails:

    def test_apply_proposal_blocked_on_review_required(self, tmp_path, monkeypatch):
        import health
        proposals_file = tmp_path / "PENDING.md"
        # Write a proposal with ReviewRequired: true
        proposals_file.write_text(
            "### PROPOSAL PENDING-TEST-001\n"
            "- Title: test skill\n"
            "- Action: FILE_CREATE\n"
            "- Target: skills/test-skill/SKILL.md\n"
            "- ReviewRequired: true\n"
            "- Content: # test\n"
            "\n---\n"
        )
        monkeypatch.setattr(health, "PROPOSALS_FILE", proposals_file)
        monkeypatch.setattr(health, "YOUK_ROOT", tmp_path)
        from health import apply_proposal
        r = apply_proposal(
            proposal_id="PENDING-TEST-001",
            confirmed=True,
            safe_types=["FILE_CREATE"],
            review_required_override=False,
        )
        assert r.get("blocked") is True
        assert r.get("review_required") is True

    def test_apply_proposal_unblocked_with_override(self, tmp_path, monkeypatch):
        import health
        skills_dir = tmp_path / "skills" / "test-skill-checkup"
        skills_dir.mkdir(parents=True)
        proposals_file = tmp_path / "PENDING.md"
        proposals_file.write_text(
            "### PROPOSAL PENDING-TEST-002\n"
            "- Title: test skill checkup\n"
            "- Action: FILE_CREATE\n"
            "- Target: skills/test-skill-checkup/SKILL.md\n"
            "- ReviewRequired: true\n"
            "- Content: # test skill checkup\n\nContent here.\n"
            "\n---\n"
        )
        monkeypatch.setattr(health, "PROPOSALS_FILE", proposals_file)
        monkeypatch.setattr(health, "YOUK_ROOT", tmp_path)
        from health import apply_proposal
        r = apply_proposal(
            proposal_id="PENDING-TEST-002",
            confirmed=True,
            safe_types=["FILE_CREATE"],
            review_required_override=True,
        )
        assert r.get("blocked") is not True

    def test_commit_quality_blocks_credential_files(self):
        from review import check_commit_quality
        r = check_commit_quality("add config", [".env"])
        assert r.get("blocked") is True

    def test_commit_quality_blocks_secrets_yaml(self):
        from review import check_commit_quality
        r = check_commit_quality("add config", ["secrets.yaml"])
        assert r.get("blocked") is True

    def test_commit_quality_passes_clean_commit(self):
        from review import check_commit_quality
        r = check_commit_quality(
            "fix: resolve session slug mismatch when session-open.json absent",
            ["servers/core/src/session_slug.py"],
        )
        assert r.get("blocked") is not True
