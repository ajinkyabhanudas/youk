"""Doc data refresh — update derivable DATA fields (counts, badges) inside any doc,
in place, while leaving prose untouched.

Load-bearing properties:
- Only computable fields change; a field whose compute() returns None is left as-is
  (never blanked, never guessed).
- Prose with no data field is byte-identical after a refresh.
- A stale count is corrected to the true value.
"""
from __future__ import annotations

from pathlib import Path

from doc_data_refresh import refresh_doc_data

_YOUK = Path(__file__).parent.parent


def test_stale_skill_count_is_corrected(tmp_path):
    (tmp_path / "skills").mkdir()
    for name in ("a", "b", "c"):
        d = tmp_path / "skills" / name
        d.mkdir()
        (d / "SKILL.md").write_text("x")
    doc = tmp_path / "doc.md"
    doc.write_text("youk ships 9 capability skills today.\n")

    result = refresh_doc_data(["doc.md"], youk_root=tmp_path)
    assert any(u["field"] == "capability_skill_count" and u["new"] == "3"
               for u in result["updated"])
    assert "3 capability skills" in doc.read_text()
    assert "9 capability skills" not in doc.read_text()


def test_prose_without_data_fields_is_untouched(tmp_path):
    doc = tmp_path / "philosophy.md"
    original = "# Philosophy\n\nAmbient over activated. No data here.\n"
    doc.write_text(original)
    result = refresh_doc_data(["philosophy.md"], youk_root=tmp_path)
    assert result["updated"] == []
    assert doc.read_text() == original  # byte-identical


def test_field_left_alone_when_not_computable(tmp_path):
    """Coverage badge with no coverage.json state -> compute returns None -> unchanged."""
    doc = tmp_path / "README.md"
    doc.write_text("![cov](badge/coverage-99%25-green)\n")  # no state file to compute from
    result = refresh_doc_data(["README.md"], youk_root=tmp_path)
    # No coverage.json => _health_coverage returns None => value preserved, not blanked.
    assert "coverage-99%25" in doc.read_text()
    assert not any(u["field"] == "health_coverage_badge" for u in result["updated"])


def test_correct_value_is_not_rewritten(tmp_path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "a").mkdir()
    (tmp_path / "skills" / "a" / "SKILL.md").write_text("x")
    doc = tmp_path / "doc.md"
    doc.write_text("1 capability skills\n")  # already correct
    result = refresh_doc_data(["doc.md"], youk_root=tmp_path)
    assert result["updated"] == []  # nothing to change


def test_non_md_and_missing_files_skipped(tmp_path):
    (tmp_path / "code.py").write_text("9 capability skills\n")  # .py, not a doc
    result = refresh_doc_data(["code.py", "ghost.md"], youk_root=tmp_path)
    assert result["updated"] == []
    assert "9 capability skills" in (tmp_path / "code.py").read_text()  # untouched


def test_real_skill_count_is_computable_and_matches_docs():
    """On the real repo, the skill count is computable, and after a refresh the docs agree
    with the computed value (no stale count remains). This stays true whether the docs were
    already fresh or just got fixed — it asserts convergence, not staleness."""
    from doc_data_refresh import _count_skills
    true_count = _count_skills(_YOUK)
    assert true_count is not None and int(true_count) > 0

    # A second refresh proposes nothing — the docs already match the computed truth.
    result = refresh_doc_data(
        ["docs/getting-started.md", "docs/well-architected.md"],
        youk_root=_YOUK, dry_run=True,
    )
    assert result["updated"] == [], "docs should already match the computed skill count"
