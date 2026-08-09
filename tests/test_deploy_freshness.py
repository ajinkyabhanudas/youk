"""Tests for deploy_freshness — the merged-≠-in-effect gate.

Uses a real temporary git repo so the git subprocess path is exercised, not mocked. Central
guarantees: a runtime-touching merge since last session warns; a docs-only merge stays silent;
schema/gate changes flag HIGH-RISK; and the gate NEVER claims 'verified fresh' (it warns or is
silent — honest limit).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers" / "core" / "src"))

from deploy_freshness import check_freshness, current_head  # noqa: E402


def _run(d: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(d), *args], check=True,
                   capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    _run(d, "init", "-q")
    _run(d, "config", "user.email", "t@t.t")
    _run(d, "config", "user.name", "t")
    (d / "README.md").write_text("x")
    _run(d, "add", "-A")
    _run(d, "commit", "-qm", "init")
    return d


def _commit(d: Path, rel: str, content: str = "x") -> None:
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    _run(d, "add", "-A")
    _run(d, "commit", "-qm", f"touch {rel}")


def test_first_run_no_baseline_is_silent(tmp_path):
    d = _repo(tmp_path)
    v = check_freshness(str(d), last_head=None)
    assert not v.stale_risk
    assert v.warning() is None


def test_head_unchanged_is_silent(tmp_path):
    d = _repo(tmp_path)
    head = current_head(str(d))
    v = check_freshness(str(d), last_head=head)
    assert v.commits_since == 0
    assert not v.stale_risk
    assert v.warning() is None


def test_docs_only_merge_is_silent(tmp_path):
    d = _repo(tmp_path)
    base = current_head(str(d))
    _commit(d, "docs/guide.md")
    _commit(d, "knowledge/notes.md")
    v = check_freshness(str(d), last_head=base)
    assert v.commits_since == 2
    assert not v.stale_risk  # nothing runtime-sensitive
    assert v.warning() is None


def test_server_code_merge_warns(tmp_path):
    d = _repo(tmp_path)
    base = current_head(str(d))
    _commit(d, "servers/core/src/tokens.py")
    v = check_freshness(str(d), last_head=base)
    assert v.stale_risk
    assert v.warning() is not None
    assert "restart" in v.warning().lower()


def test_schema_change_is_high_risk(tmp_path):
    d = _repo(tmp_path)
    base = current_head(str(d))
    _commit(d, "servers/core/src/graph.py")  # matches graph.py high-risk marker
    v = check_freshness(str(d), last_head=base)
    assert v.stale_risk
    assert v.high_risk
    assert "HIGH-RISK" in v.warning()


def test_never_claims_verified_fresh(tmp_path):
    # The honest-limit guarantee: the gate has no 'verified/fresh/ok' positive claim — it only
    # warns or is silent. A None warning means 'nothing to flag', not 'proven current'.
    d = _repo(tmp_path)
    base = current_head(str(d))
    _commit(d, "docs/x.md")
    v = check_freshness(str(d), last_head=base)
    assert v.warning() is None  # silent, not a false 'verified' string


def test_bogus_last_head_warns_not_silent(tmp_path):
    # ADVERSARY FINDING: a rebased/bogus last_head makes git diff fail. That must NOT read as
    # 'nothing merged' (false-green) — HEAD moved, contents unknown → warn.
    d = _repo(tmp_path)
    _commit(d, "servers/core/src/x.py")  # move HEAD forward
    v = check_freshness(str(d), last_head="0" * 40)  # non-existent SHA
    assert v.stale_risk is True
    assert v.warning() is not None
    assert "cannot verify" in v.warning().lower() or "rebased" in v.warning().lower()


def test_non_repo_dir_cannot_check(tmp_path):
    # ADVERSARY FINDING: a non-repo dir was an untested branch.
    d = tmp_path / "notarepo"
    d.mkdir()
    v = check_freshness(str(d), last_head="abc123")
    assert v.current_head is None
    assert not v.stale_risk  # can't check ≠ stale; but also never claims fresh
    assert v.warning() is None


def test_mixed_merge_reports_only_runtime_files(tmp_path):
    d = _repo(tmp_path)
    base = current_head(str(d))
    _commit(d, "docs/x.md")
    _commit(d, "servers/core/src/session.py")
    v = check_freshness(str(d), last_head=base)
    assert v.stale_risk and v.high_risk  # session.py is a high-risk marker
    assert all(p.startswith(("servers/", "skills/")) for p in v.runtime_files_changed)
    assert "docs/x.md" not in v.runtime_files_changed
