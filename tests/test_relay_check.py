"""
Test for scripts/relay_check.sh — Gate Packaging Manifest verifier.

Coverage:
- Exit 0 when all checks pass (MANIFEST current, files present, ledger matches HEAD)
- Exit 1 when MANIFEST gate label is stale (does not reference newest GATE-*.md)
- Exit 1 when ledger last SHA does not match git HEAD
- Exit 1 when a required file is absent
- Manifest echo block is printed on success
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parent.parent / "scripts" / "relay_check.sh"
REPO = Path(__file__).parent.parent


def _run(relay_dir: Path, repo_dir: Path | None = None) -> tuple[int, str]:
    """Run relay_check.sh with overridden dirs, return (returncode, stdout+stderr)."""
    env = os.environ.copy()
    env["RELAY_CHECK_DIR"] = str(relay_dir)
    env["RELAY_CHECK_REPO"] = str(repo_dir or REPO)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout + result.stderr


def _make_valid_relay(tmp: Path, head_sha: str) -> Path:
    """Create a minimally valid RELAY/ directory."""
    relay = tmp / "RELAY"
    relay.mkdir()
    # Required files
    (relay / "deviation-log.md").write_text("# deviation log\n")
    (relay / "elite-progress.md").write_text("# progress\n")
    (relay / "live-evidence.md").write_text("# live evidence\n")
    (relay / "elite-batch-4.diff").write_text("diff --git a/x b/x\nindex abc..def\n")
    # Newest GATE file
    (relay / "GATE-B4-2.md").write_text("# GATE B4-2\n")
    # MANIFEST referencing the gate and HEAD SHA
    (relay / "MANIFEST.md").write_text(
        f"# RELAY/MANIFEST.md\n\nGate: GATE B4-2 — Batch 4\nBranch: elite-impl @ {head_sha}\n\n"
        "## Commits (main..elite-impl)\n\n"
        f"| {head_sha} | CAP-11: compaction metrics |\n"
    )
    return relay


class TestRelayCheckPasses:
    def test_all_checks_pass_exits_zero(self, tmp_path):
        head_sha = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        relay = _make_valid_relay(tmp_path, head_sha)
        rc, out = _run(relay, REPO)
        assert rc == 0, f"Expected exit 0 but got {rc}:\n{out}"
        assert "ALL CHECKS PASSED" in out

    def test_echo_block_printed(self, tmp_path):
        head_sha = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        relay = _make_valid_relay(tmp_path, head_sha)
        _, out = _run(relay, REPO)
        assert "MANIFEST ECHO" in out
        assert "GATE-B4-2" in out
        assert "elite-batch-4.diff" in out


class TestRelayCheckFails:
    def test_stale_manifest_gate_label_exits_nonzero(self, tmp_path):
        head_sha = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        relay = _make_valid_relay(tmp_path, head_sha)
        # Overwrite MANIFEST with old gate label
        (relay / "MANIFEST.md").write_text(
            f"# RELAY/MANIFEST.md\n\nGate: GATE E3.2 — stale\nBranch: elite-impl @ {head_sha}\n\n"
            "## Commits (main..elite-impl)\n\n"
            f"| {head_sha} | CAP-11: compaction metrics |\n"
        )
        rc, out = _run(relay, REPO)
        assert rc != 0
        assert "FAIL" in out

    def test_ledger_sha_mismatch_exits_nonzero(self, tmp_path):
        relay = _make_valid_relay(tmp_path, "deadbeef")  # wrong SHA
        rc, out = _run(relay, REPO)
        assert rc != 0
        assert "FAIL" in out

    def test_absent_required_file_exits_nonzero(self, tmp_path):
        head_sha = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        relay = _make_valid_relay(tmp_path, head_sha)
        (relay / "deviation-log.md").unlink()
        rc, out = _run(relay, REPO)
        assert rc != 0
        assert "ABSENT" in out
