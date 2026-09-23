"""End-to-end contracts for explicit information-governance metadata."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
for _path in [str(_REPO / "servers" / "shared"), str(_REPO / "servers" / "core" / "src")]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

import file_index as FI


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "source.md").write_text("# Source\n\nCanonical facts.\n")
    (project / "docs" / "derived.md").write_text("# Derived\n\nRendered facts.\n")
    (project / "docs" / "information-governance.yaml").write_text(
        "version: 1\nfiles:\n"
        "  - path: docs/source.md\n    role: source_of_truth\n"
        "  - path: docs/derived.md\n    role: derived\n    authority: docs/source.md\n"
    )
    return project


def test_hash_lineage_detects_stale_derived_file(tmp_path):
    project = _project(tmp_path)
    db = tmp_path / "index.db"
    first = FI.index_project(project, "project", db_path=db)
    assert first["governance"]["status"] == "valid"
    assert FI.find_stale_relations("project", db_path=db)["stale_count"] == 0

    (project / "docs" / "source.md").write_text("# Source\n\nChanged canonical facts.\n")
    FI.index_project(project, "project", db_path=db)
    stale = FI.find_stale_relations("project", db_path=db)
    assert stale["stale_count"] == 1
    assert stale["stale"][0]["to_path"] == "docs/derived.md"
    assert stale["stale"][0]["rel_type"] == "derives_from"


def test_forced_rebuild_does_not_clear_staleness_without_derived_change(tmp_path):
    project = _project(tmp_path)
    db = tmp_path / "index.db"
    FI.index_project(project, "project", db_path=db)
    (project / "docs" / "source.md").write_text("# Source\n\nChanged canonical facts.\n")
    FI.index_project(project, "project", db_path=db)
    assert FI.find_stale_relations("project", db_path=db)["stale_count"] == 1
    FI.index_project(project, "project", force=True, db_path=db)
    assert FI.find_stale_relations("project", db_path=db)["stale_count"] == 1


def test_registry_rejects_missing_or_unsafe_authority(tmp_path):
    project = _project(tmp_path)
    db = tmp_path / "index.db"
    (project / "docs" / "information-governance.yaml").write_text(
        "version: 1\nfiles:\n"
        "  - path: docs/derived.md\n    role: derived\n    authority: ../outside.md\n"
    )
    result = FI.index_project(project, "project", db_path=db)
    assert result["error"] == "governance_registry_invalid"
    assert result["governance"]["status"] == "invalid"


def test_registry_rejects_unknown_lifecycle(tmp_path):
    project = _project(tmp_path)
    db = tmp_path / "index.db"
    (project / "docs" / "information-governance.yaml").write_text(
        "version: 1\nfiles:\n  - path: docs/source.md\n"
        "    role: source_of_truth\n    lifecycle: invented\n"
    )
    assert FI.index_project(project, "project", db_path=db)["error"] == "governance_registry_invalid"


def test_invalid_registry_after_successful_index_fails_health_closed(tmp_path):
    project = _project(tmp_path)
    db = tmp_path / "index.db"
    FI.index_project(project, "project", db_path=db)
    (project / "docs" / "information-governance.yaml").write_text("version: 2\nfiles: []\n")
    assert FI.index_project(project, "project", db_path=db)["error"] == "governance_registry_invalid"
    health = FI.get_information_governance_health("project", db_path=db)
    assert health["status"] == "invalid"
    assert health["coverage"] == "unknown"


def test_registry_rejects_symlink_escape(tmp_path):
    project = _project(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("not project content")
    (project / "docs" / "escaped.md").symlink_to(outside)
    (project / "docs" / "information-governance.yaml").write_text(
        "version: 1\nfiles:\n  - path: docs/escaped.md\n    role: source_of_truth\n"
    )
    result = FI.index_project(project, "project", db_path=tmp_path / "index.db")
    assert result["error"] == "governance_registry_invalid"


def test_index_reconciles_deleted_files_and_governance_records(tmp_path):
    project = _project(tmp_path)
    db = tmp_path / "index.db"
    FI.index_project(project, "project", db_path=db)
    (project / "docs" / "derived.md").unlink()
    (project / "docs" / "information-governance.yaml").write_text(
        "version: 1\nfiles:\n  - path: docs/source.md\n    role: source_of_truth\n"
    )
    result = FI.index_project(project, "project", db_path=db)
    assert result["removed_count"] == 1
    health = FI.get_information_governance_health("project", db_path=db)
    assert health["declared"] == 1
    assert health["derived"] == 0


def test_retrieval_rejects_unbounded_inputs_and_does_not_create_db(tmp_path):
    db = tmp_path / "absent.db"
    absent = FI.find_relevant("governance", db_path=db)
    assert absent["status"] == "absent"
    assert not db.exists()
    project = _project(tmp_path)
    FI.index_project(project, "project", db_path=db)
    assert FI.find_relevant("x " * 33, db_path=db)["error"] == "query_too_many_terms"
    assert FI.find_relevant("governance", limit=0, db_path=db)["error"] == "invalid_limit"
    assert FI.find_related_docs("governance", limit=51, db_path=db)["error"] == "limit_exceeds_maximum"
