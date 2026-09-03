"""
Drift sentinel: a skill that exists on disk must exist in the repo.

.gitignore excludes skills/{name}/{name}, the self-referential symlink install.sh
creates, using the pattern skills/*/*. That pattern also matched SKILL.md, so every
skill added after the rule landed was dropped from the repo without a warning. Nine
of them accumulated, all listed ACTIVE in SKILL-REGISTRY.md, none present in a clone.

Nothing failed while that was true. Git does not report a file it was told to ignore,
and the registry describes disk, not the repo, so both surfaces looked healthy. This
test is the thing that fails.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "skills/"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return set(out.splitlines())


def _skill_dirs() -> list[Path]:
    return sorted(d for d in SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())


@pytest.mark.skipif(not SKILLS.is_dir(), reason="skills/ not present")
def test_every_skill_on_disk_is_tracked():
    tracked = _tracked_files()
    missing = [
        f"skills/{d.name}/SKILL.md"
        for d in _skill_dirs()
        if f"skills/{d.name}/SKILL.md" not in tracked
    ]
    assert not missing, (
        f"SKILL.md files present on disk but absent from the repo: {missing}. "
        "Check .gitignore — skills/*/* matches SKILL.md unless the negation "
        "!skills/*/SKILL.md is present."
    )


@pytest.mark.skipif(not SKILLS.is_dir(), reason="skills/ not present")
def test_skill_md_is_not_gitignored():
    """Direct assertion on the rule, so the cause is named even if no skill is missing yet."""
    probe = "skills/__sentinel_probe__/SKILL.md"
    result = subprocess.run(
        ["git", "check-ignore", "-q", probe], cwd=REPO, capture_output=True
    )
    assert result.returncode != 0, (
        f"{probe} is gitignored — a newly generated skill would be silently dropped. "
        "The negation !skills/*/SKILL.md must sit after the skills/*/* rule."
    )


@pytest.mark.skipif(not SKILLS.is_dir(), reason="skills/ not present")
def test_install_symlink_stays_ignored():
    """The negation must not be so broad that it re-admits the install.sh symlink, whose
    target is a machine-absolute path and is not portable across installs."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "skills/adr/adr"], cwd=REPO, capture_output=True
    )
    assert result.returncode == 0, (
        "skills/{name}/{name} is no longer ignored — the install.sh symlink would be "
        "committed, which is what the skills/*/* rule exists to prevent."
    )


@pytest.mark.skipif(not SKILLS.is_dir(), reason="skills/ not present")
def test_no_machine_absolute_paths_in_skills():
    """A SKILL.md ships to every install, so a path from one developer's machine is both
    a portability bug and a leak of their directory layout."""
    offenders = []
    for d in _skill_dirs():
        text = (d / "SKILL.md").read_text(errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "/Users/" in line or "/home/" in line:
                offenders.append(f"skills/{d.name}/SKILL.md:{lineno}")
    assert not offenders, f"machine-absolute paths in shipped skills: {offenders}"


@pytest.mark.skipif(not SKILLS.is_dir(), reason="skills/ not present")
def test_sentinel_sees_actual_skills():
    """Guards the sentinel itself — a glob that matched nothing would pass everything."""
    assert len(_skill_dirs()) > 20, (
        f"only {len(_skill_dirs())} skill dirs found; the discovery glob is likely stale"
    )
