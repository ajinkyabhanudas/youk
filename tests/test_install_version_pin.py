"""
Tests for YOUK_REF version pinning in the installers.

Two layers, because the installers cannot be executed here — a real run needs Docker,
network, MCP registration and a live HOME.

1. The git behaviours the scripts depend on, exercised against a real local repo. If
   `git clone --branch <tag>` ever stopped detaching HEAD, or `symbolic-ref -q HEAD`
   stopped distinguishing a pin from a branch, the installers would silently do the
   wrong thing and no unit test of the scripts' text would notice.

2. Drift sentinels on the script text, for the properties that cannot be executed:
   that a bad ref exits rather than falling back, that install.sh stays self-contained
   because it is curl-piped, and that install.ps1 maps $env:YOUK_REF.

The unexecuted boundary is the installers' own control flow. It is audited, not run.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO / "scripts" / "install.sh"
INSTALL_PS1 = REPO / "scripts" / "install.ps1"
MAKEFILE = REPO / "Makefile"


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def origin(tmp_path):
    """A real repo with a tag one commit behind its default branch."""
    src = tmp_path / "origin"
    src.mkdir()
    _git("init", "-q", "-b", "main", cwd=src)
    _git("config", "user.email", "t@t", cwd=src)
    _git("config", "user.name", "t", cwd=src)
    (src / "VERSION").write_text("1.0\n")
    _git("add", "-A", cwd=src)
    _git("commit", "-qm", "v1", cwd=src)
    _git("tag", "v1.0.0", cwd=src)
    (src / "VERSION").write_text("2.0\n")
    _git("add", "-A", cwd=src)
    _git("commit", "-qm", "v2", cwd=src)
    return src


class TestGitBehavioursTheInstallersRelyOn:
    def test_clone_at_tag_pins_and_detaches(self, origin, tmp_path):
        dest = tmp_path / "pinned"
        r = _git("clone", "--branch", "v1.0.0", str(origin), str(dest), cwd=tmp_path)
        assert r.returncode == 0
        assert (dest / "VERSION").read_text().strip() == "1.0"
        assert _git("symbolic-ref", "-q", "HEAD", cwd=dest).returncode != 0

    def test_plain_clone_tracks_default_branch(self, origin, tmp_path):
        dest = tmp_path / "latest"
        _git("clone", str(origin), str(dest), cwd=tmp_path)
        assert (dest / "VERSION").read_text().strip() == "2.0"
        assert _git("symbolic-ref", "-q", "HEAD", cwd=dest).returncode == 0

    def test_bad_ref_fails_rather_than_falling_back(self, origin, tmp_path):
        """The installer must not quietly hand over a different version."""
        dest = tmp_path / "bogus"
        r = _git("clone", "--branch", "v9.9.9", str(origin), str(dest), cwd=tmp_path)
        assert r.returncode != 0
        assert not (dest / "VERSION").exists()

    def test_pull_on_a_pinned_checkout_fails_and_leaves_head_alone(self, origin, tmp_path):
        """Why the installer must branch on symbolic-ref instead of reporting the failure
        of a pull as 'Already up to date'."""
        dest = tmp_path / "pinned"
        _git("clone", "--branch", "v1.0.0", str(origin), str(dest), cwd=tmp_path)
        r = _git("pull", "--ff-only", cwd=dest)
        assert r.returncode != 0
        assert "not currently on a branch" in (r.stderr + r.stdout).lower()
        assert (dest / "VERSION").read_text().strip() == "1.0"

    def test_describe_names_the_pin(self, origin, tmp_path):
        """The message the installer prints in place of the old false one."""
        dest = tmp_path / "pinned"
        _git("clone", "--branch", "v1.0.0", str(origin), str(dest), cwd=tmp_path)
        assert _git("describe", "--tags", "--always", cwd=dest).stdout.strip() == "v1.0.0"


class TestInstallShContract:
    def test_declares_youk_ref_with_a_default(self):
        """set -u is on; an undeclared YOUK_REF would abort the install."""
        assert 'YOUK_REF="${YOUK_REF:-}"' in INSTALL_SH.read_text()

    def test_passes_ref_only_as_a_branch_value(self):
        """Never concatenated into the URL, never eval'd."""
        text = INSTALL_SH.read_text()
        assert '--branch "$YOUK_REF"' in text
        assert "youk$YOUK_REF" not in text and "youk/$YOUK_REF" not in text
        assert "eval" not in text

    def test_bad_ref_exits_rather_than_cloning_the_default(self):
        text = INSTALL_SH.read_text()
        clone_block = text.split("No such tag or branch")[0].rsplit("if [[ -n \"$YOUK_REF\" ]]", 1)[-1]
        assert "exit 1" in text.split("No such tag or branch")[1][:300]
        assert "--branch" in clone_block

    def test_branches_on_symbolic_ref_not_on_pull_failure(self):
        text = INSTALL_SH.read_text()
        assert "symbolic-ref -q HEAD" in text
        assert 'warn "Already up to date"' not in text, (
            "the old message reported a failed pull on a pinned checkout as success"
        )

    def test_never_sources_relative_to_script_dir(self):
        """`curl -sL .../install.sh | bash` has no script on disk, so SCRIPT_DIR resolves
        to the caller's working directory. Sourcing from there aborted the install for
        anyone following the README — it shipped broken in v1.0.0, v1.1.0 and v1.2.0.
        Anything sourced must come from the clone, which step 1 guarantees exists."""
        text = INSTALL_SH.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("source ", ". ")):
                assert "$SCRIPT_DIR" not in stripped, (
                    f"sourced relative to SCRIPT_DIR, empty on a piped install: {stripped}"
                )
        # The path it does source must be rooted in the clone.
        assert 'SNAPSHOT_LIB="$YOUK_DIR/scripts/lib/snapshot.sh"' in text
        assert '. "$SNAPSHOT_LIB"' in text

    def test_missing_snapshot_lib_fails_loudly(self):
        """If the clone is incomplete, say so — do not source a file that is not there."""
        text = INSTALL_SH.read_text()
        assert 'if [[ ! -f "$SNAPSHOT_LIB" ]]' in text
        assert "exit 1" in text.split("$SNAPSHOT_LIB")[2][:400]

    def test_bash_source_is_defaulted_for_piped_installs(self):
        """Reading BASH_SOURCE[0] under `set -u` with no script on disk aborts with
        'unbound variable' before anything else runs."""
        text = INSTALL_SH.read_text()
        assert "${BASH_SOURCE[0]:-}" in text
        assert '"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in text, (
            "the guarded branch should still resolve normally when a script does exist"
        )

    def test_repo_dir_emptiness_is_handled(self):
        """REPO_DIR is empty on a piped install; comparing it bare would print a
        'Running from , not ...' warning and skip a pull that should happen."""
        assert '[[ -n "$REPO_DIR" && "$REPO_DIR" != "$YOUK_DIR" ]]' in INSTALL_SH.read_text()

    def test_syntax_is_valid(self):
        assert subprocess.run(["bash", "-n", str(INSTALL_SH)]).returncode == 0

    def test_no_bash4_only_constructs(self):
        """Stock macOS ships bash 3.2; #104 was a crash from exactly this."""
        code = "\n".join(
            line.split("#", 1)[0] for line in INSTALL_SH.read_text().splitlines()
        )
        for construct in ("declare -A", "readarray", "mapfile"):
            assert construct not in code, construct


class TestInstallPs1Contract:
    def test_maps_the_environment_variable(self):
        """PowerShell does not surface env vars as plain variables — without this the
        pin would be silently ignored on Windows."""
        assert "$YOUK_REF = $env:YOUK_REF" in INSTALL_PS1.read_text()

    def test_bad_ref_exits(self):
        text = INSTALL_PS1.read_text()
        assert "--branch $YOUK_REF" in text
        assert "exit 1" in text.split("No such tag or branch")[1][:300]

    def test_branches_on_symbolic_ref(self):
        text = INSTALL_PS1.read_text()
        assert "git symbolic-ref -q HEAD" in text
        assert 'warn "Already up to date"' not in text


class TestMakeUpdate:
    def test_update_guards_the_pull_on_symbolic_ref(self):
        """Split on the recipe at line start — 'update:' also appears in a comment."""
        import re
        text = MAKEFILE.read_text()
        recipe = re.split(r"^update:", text, flags=re.M)[1].split("\n\n")[0]
        assert "symbolic-ref -q HEAD" in recipe
        assert "git pull --rebase" in recipe
        assert "Pinned to" in recipe
