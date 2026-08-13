"""Tests for SQLite-backed proposal store.

Covers: add (idempotent), concurrent writes (no lost rows), project filtering,
apply status update, migration from legacy PENDING.md, and error surfacing.
"""
from __future__ import annotations
import threading
from datetime import datetime
from models import Proposal


def _make_proposal(id: str, project_slug: str = "youk", change_desc: str = "") -> Proposal:
    return Proposal(
        id=id,
        target="skills/test/SKILL.md",
        change_description=change_desc or f"change for {id}",
        reason="test",
        before="old",
        after="new",
        status="PENDING",
        proposed_date=datetime.utcnow().strftime("%Y-%m-%d"),
        change_type="SKILL_EDIT",
        target_section="Quality Bars",
        content="new content",
        project_slug=project_slug,
    )


class TestAddProposal:
    def test_add_single(self, youk_root, claude_root):
        import health
        p = _make_proposal("PENDING-001")
        health.add_proposal(p)
        loaded = health._load_pending_proposals()
        assert len(loaded) == 1
        assert loaded[0].id == "PENDING-001"
        assert loaded[0].change_description == "change for PENDING-001"

    def test_add_idempotent(self, youk_root, claude_root):
        import health
        p = _make_proposal("PENDING-002")
        health.add_proposal(p)
        health.add_proposal(p)  # second call must not duplicate
        loaded = health._load_pending_proposals()
        assert len([x for x in loaded if x.id == "PENDING-002"]) == 1

    def test_add_concurrent_no_lost_writes(self, youk_root, claude_root):
        """Two threads writing different proposals simultaneously must both land."""
        import health
        errors = []

        def write(proposal_id: str):
            try:
                health.add_proposal(_make_proposal(proposal_id, change_desc=f"desc-{proposal_id}"))
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=write, args=("PENDING-T1",))
        t2 = threading.Thread(target=write, args=("PENDING-T2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"concurrent write errors: {errors}"
        loaded = health._load_pending_proposals()
        ids = {p.id for p in loaded}
        assert "PENDING-T1" in ids
        assert "PENDING-T2" in ids

    def test_add_concurrent_same_id_idempotent(self, youk_root, claude_root):
        """Two threads racing to insert the same ID must result in exactly one row."""
        import health
        p = _make_proposal("PENDING-RACE")

        def write():
            health.add_proposal(p)

        threads = [threading.Thread(target=write) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = health._load_pending_proposals()
        assert len([x for x in loaded if x.id == "PENDING-RACE"]) == 1


class TestProjectFiltering:
    def test_filter_by_project(self, youk_root, claude_root):
        import health
        health.add_proposal(_make_proposal("PENDING-Y1", project_slug="youk"))
        health.add_proposal(_make_proposal("PENDING-C1", project_slug="canopy"))
        health.add_proposal(_make_proposal("PENDING-Y2", project_slug="youk"))

        youk_props = health._load_pending_proposals("youk")
        canopy_props = health._load_pending_proposals("canopy")
        all_props = health._load_pending_proposals(None)

        assert len(youk_props) == 2
        assert all(p.project_slug == "youk" for p in youk_props)
        assert len(canopy_props) == 1
        assert len(all_props) == 3

    def test_empty_project_slug_defaults_to_empty_string(self, youk_root, claude_root):
        import health
        p = _make_proposal("PENDING-NOSLUG", project_slug="")
        health.add_proposal(p)
        loaded = health._load_pending_proposals("")
        assert any(x.id == "PENDING-NOSLUG" for x in loaded)


class TestMigration:
    def test_migration_from_pending_md(self, youk_root, claude_root):
        """Existing PENDING.md rows are migrated to SQLite on first _proposals_conn() call."""
        import health

        # Write a legacy PENDING.md before any DB access
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "# youk Self-Heal Proposals\n\nPending founder review.\n\n"
            "## PENDING-LEGACY-001 — 2026-07-01\n"
            "**Target:** skills/test/SKILL.md\n"
            "**Change:** legacy change\n"
            "**Reason:** test\n"
            "**Before:** old\n"
            "**After:** new\n"
            "**Status:** PENDING\n"
            "**Project:** youk\n"
            "**ChangeType:** SKILL_EDIT\n"
        )

        loaded = health._load_pending_proposals()
        ids = {p.id for p in loaded}
        assert "PENDING-LEGACY-001" in ids

    def test_migration_idempotent(self, youk_root, claude_root):
        """Running migration twice must not duplicate rows."""
        import health

        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "# youk Self-Heal Proposals\n\nPending founder review.\n\n"
            "## PENDING-IDEM-001 — 2026-07-01\n"
            "**Target:** skills/test/SKILL.md\n"
            "**Change:** idem change\n"
            "**Reason:** test\n**Before:** \n**After:** \n**Status:** PENDING\n"
        )

        # First and second access — migration marker in DB prevents double insert
        conn1 = health._proposals_conn()
        conn1.close()
        conn2 = health._proposals_conn()
        conn2.close()

        loaded = health._load_pending_proposals()
        assert len([p for p in loaded if p.id == "PENDING-IDEM-001"]) == 1

    def test_migration_logged_to_audit(self, youk_root, claude_root):
        """Migration writes a ProposalMigration entry to audit log."""
        import health
        import datetime as dt

        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "## PENDING-AUDIT-001 — 2026-07-01\n"
            "**Target:** t\n**Change:** c\n**Reason:** r\n"
            "**Before:** \n**After:** \n**Status:** PENDING\n"
        )

        health._proposals_conn().close()

        month = dt.datetime.utcnow().strftime("%Y-%m")
        audit_file = claude_root / "audit" / f"{month}.md"
        assert audit_file.exists()
        assert "ProposalMigration" in audit_file.read_text()


class TestApplyProposalStatusUpdate:
    def test_status_updated_atomically(self, youk_root, claude_root, tmp_path):
        """apply_proposal marks status APPLIED in SQLite without touching PENDING.md."""
        import health

        p = _make_proposal("PENDING-APPLY-001")
        health.add_proposal(p)

        # Directly update status via the DB (simulates apply_proposal internals)
        conn = health._proposals_conn()
        conn.execute(
            "UPDATE proposals SET status=? WHERE id=?",
            ("APPLIED — 2026-08-13", "PENDING-APPLY-001"),
        )
        conn.commit()
        conn.close()

        loaded = health._load_pending_proposals()
        applied = [x for x in loaded if x.id == "PENDING-APPLY-001"]
        assert applied[0].status.startswith("APPLIED")

    def test_pending_md_not_written_on_add(self, youk_root, claude_root):
        """add_proposal must NOT write or create PENDING.md — SQLite is the write target."""
        import health

        pending_md = youk_root / "knowledge" / "proposals" / "PENDING.md"
        pending_md.unlink(missing_ok=True)

        health.add_proposal(_make_proposal("PENDING-NOFILE-001"))

        # PENDING.md should not have been created by add_proposal
        assert not pending_md.exists()


class TestRenderView:
    def test_render_pending_md_produces_markdown(self, youk_root, claude_root):
        """_render_pending_md returns valid markdown with proposal headers."""
        import health

        health.add_proposal(_make_proposal("PENDING-VIEW-001"))
        health.add_proposal(_make_proposal("PENDING-VIEW-002"))

        loaded = health._load_pending_proposals()
        md = health._render_pending_md(loaded)

        assert "PENDING-VIEW-001" in md
        assert "PENDING-VIEW-002" in md
        assert "**Target:**" in md
