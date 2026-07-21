"""L5 — Gate Correctness + Guardrails.

Tests call Python functions directly (no Docker for most cases) using
real path constants pointing at the actual repo. Gate logic has no
external dependencies beyond reading/writing state files.
"""
import json
import sys
from pathlib import Path


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
    # check_challenge_gate is pure — takes challenge_ran:bool directly, no state dir.

    def test_m_blocked_when_challenge_not_ran(self):
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("implement retry logic", "M", False)
        assert r["blocked"] is True

    def test_m_unblocked_when_challenge_ran(self):
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("implement retry logic", "M", True)
        assert r["blocked"] is False

    def test_xs_always_passes_regardless_of_challenge(self):
        from challenge_gate import check_challenge_gate
        r = check_challenge_gate("fix typo", "XS", False)
        assert r["blocked"] is False

    def test_l_blocked_when_challenge_not_ran(self):
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
        import datetime
        import task_contract
        contracts_dir = tmp_path / "task-contracts"
        contracts_dir.mkdir()
        monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", contracts_dir)
        # File must match glob *{today}*.md and have as_approved set with no unresolved_provocations
        today = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
        record = {
            "contract_id": "checkup-test",
            "task": "checkup synthetic task",
            "size": "L",
            "date": today,
            "as_presented": "synthetic contract text",
            "as_approved": "synthetic test contract",
        }
        contract_file = contracts_dir / f"{today}-checkup-test-contract.md"
        contract_file.write_text(f"---\n{json.dumps(record, indent=2)}\n---\n\nsynthetic contract text\n")
        from task_contract import check_task_contract_gate
        r = check_task_contract_gate("L")
        assert r["blocked"] is False


# ---------------------------------------------------------------------------
# Guardrails — apply_proposal review_required gate
# ---------------------------------------------------------------------------

class TestGuardrails:

    def _write_pending(self, proposals_file, pid, target, content="# test\n", review_required=True):
        """Write a PENDING.md in the format _load_pending_proposals expects."""
        from models import Proposal
        import datetime
        p = Proposal(
            id=pid,
            target=target,
            change_description=f"test proposal {pid}",
            reason="integration test",
            before="",
            after=content[:300],
            status="PENDING",
            proposed_date=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
            change_type="FILE_CREATE",
            content=content,
            review_required=review_required,
        )
        proposals_file.write_text("# youk Self-Heal Proposals\n\nPending founder review.\n\n\n" + p.to_markdown())

    def test_apply_proposal_blocked_on_review_required(self, tmp_path, monkeypatch):
        import health
        proposals_file = tmp_path / "PENDING.md"
        self._write_pending(proposals_file, "PENDING-TEST-001",
                            "skills/test-skill/SKILL.md", review_required=True)
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
        target = str(skills_dir / "SKILL.md")
        self._write_pending(proposals_file, "PENDING-TEST-002", target,
                            content="# test skill checkup\n\nContent here.\n", review_required=True)
        monkeypatch.setattr(health, "PROPOSALS_FILE", proposals_file)
        monkeypatch.setattr(health, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(health, "_ALLOWED_WRITE_ROOTS", [tmp_path])
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
        assert r.blocked is True

    def test_commit_quality_blocks_secrets_yaml(self):
        from review import check_commit_quality
        r = check_commit_quality("add config", ["secrets.yaml"])
        assert r.blocked is True

    def test_commit_quality_passes_clean_commit(self):
        from review import check_commit_quality
        r = check_commit_quality(
            "fix: resolve session slug mismatch when session-open.json absent",
            ["servers/core/src/session_slug.py"],
        )
        assert r.blocked is not True


# ---------------------------------------------------------------------------
# Proposal Lifecycle — add → list → apply → verify on disk
# ---------------------------------------------------------------------------

class TestProposalLifecycle:
    """Tests for self_heal, add_proposal, get_proposals, apply_proposal.

    All tests patch health.PROPOSALS_FILE to a sandbox path and
    health.YOUK_ROOT to tmp_path so FILE_CREATE writes stay isolated.
    """

    def _patch(self, monkeypatch, tmp_path):
        import health
        proposals_file = tmp_path / "PENDING.md"
        monkeypatch.setattr(health, "PROPOSALS_FILE", proposals_file)
        monkeypatch.setattr(health, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(health, "_ALLOWED_WRITE_ROOTS", [tmp_path])
        return proposals_file

    def test_self_heal_returns_org_score(self, tmp_path, monkeypatch):
        import health
        self._patch(monkeypatch, tmp_path)
        # audit dir must exist so _read_recent_audit_logs doesn't crash
        audit_dir = tmp_path / "knowledge" / "audit"
        audit_dir.mkdir(parents=True)
        monkeypatch.setattr(health, "CLAUDE_ROOT", tmp_path)
        r = health.run_health_check_with_skill_signals()
        assert "org_score" in r, f"self_heal missing org_score: {list(r.keys())}"
        assert isinstance(r["org_score"], int | float)
        assert "findings" in r

    def _make_proposal(self, pid: str, title: str, change_type: str, target: str, content: str = ""):
        from models import Proposal
        from datetime import datetime
        return Proposal(
            id=pid,
            target=target,
            change_description=title,
            reason="integration test",
            before="",
            after=content[:300],
            status="PENDING",
            proposed_date=datetime.utcnow().strftime("%Y-%m-%d"),
            change_type=change_type,
            content=content,
        )

    def test_add_proposal_creates_entry(self, tmp_path, monkeypatch):
        import health
        proposals_file = self._patch(monkeypatch, tmp_path)
        proposal = self._make_proposal(
            "PENDING-20260721000001", "checkup test proposal",
            "FILE_CREATE", "skills/checkup-test/SKILL.md", "# Checkup Test\n",
        )
        health.add_proposal(proposal)
        assert proposals_file.exists(), "PENDING.md must be created by add_proposal"

        proposals = health._load_pending_proposals()
        assert len(proposals) >= 1
        ids = [p.id for p in proposals]
        assert proposal.id in ids, f"proposal id {proposal.id} not found in PENDING.md"

    def test_add_proposal_deduplication(self, tmp_path, monkeypatch):
        import health
        self._patch(monkeypatch, tmp_path)
        p1 = self._make_proposal(
            "PENDING-20260721000002", "dup test proposal",
            "FILE_CREATE", "skills/dup-test/SKILL.md", "x",
        )
        p2 = self._make_proposal(
            "PENDING-20260721000003", "dup test proposal",
            "FILE_CREATE", "skills/dup-test/SKILL.md", "x",
        )
        health.add_proposal(p1)
        health.add_proposal(p2)  # should be skipped — same change_description
        proposals = health._load_pending_proposals()
        matching = [p for p in proposals if p.change_description == "dup test proposal"]
        assert len(matching) == 1, f"Deduplication failed — found {len(matching)} entries"

    def test_apply_proposal_file_create(self, tmp_path, monkeypatch):
        """Subsequent updates can be made — FILE_CREATE writes the file to disk."""
        import health
        self._patch(monkeypatch, tmp_path)
        skill_dir = tmp_path / "skills" / "checkup-write-test"
        skill_dir.mkdir(parents=True)
        target_path = str(skill_dir / "SKILL.md")
        proposal = self._make_proposal(
            "PENDING-20260721000004", "write test skill for checkup",
            "FILE_CREATE", target_path, "# Write Test\nContent here.\n",
        )
        health.add_proposal(proposal)
        r_apply = health.apply_proposal(
            proposal_id="PENDING-20260721000004",
            confirmed=True,
            safe_types=["FILE_CREATE"],
            review_required_override=True,
        )
        assert r_apply.get("applied") is True, f"apply_proposal failed: {r_apply}"
        written = skill_dir / "SKILL.md"
        assert written.exists(), "FILE_CREATE must write the file to disk"
        assert "Write Test" in written.read_text()
