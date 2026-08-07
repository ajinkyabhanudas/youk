"""Personal-data pulse — catches committed personal-identifier leaks. Design survived a
challenge pass: zero-config auto-seed, email detection, honest known-identifier boundary,
prevention (pre-commit) over advisory-only.

Load-bearing: it must catch a leak, ignore legitimate attribution, and never scan gitignored
local files.
"""
from __future__ import annotations

from personal_data_pulse import (
    _ATTRIBUTION_ALLOW,
    check_personal_data,
    format_leak_warnings,
)


def _mk(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _seed(tmp_path, name="Jane Dev"):
    # give the auto-seed something deterministic: a plugin.json author.
    _mk(tmp_path, "plugin/.claude-plugin/plugin.json", f'{{"author": "{name}"}}')


def test_catches_a_name_leak_in_committed_skill(tmp_path):
    _seed(tmp_path)
    _mk(tmp_path, "skills/demo/SKILL.md", "This maps Jane Dev's voice to output.")
    r = check_personal_data(youk_root=tmp_path)
    assert not r["clean"]
    assert any(x["hit"] == "Jane Dev" and x["kind"] == "name" for x in r["leaks"])


def test_attribution_line_is_allowed(tmp_path):
    _seed(tmp_path)
    # the plugin.json author line itself must NOT count as a leak (it's attribution)
    r = check_personal_data(youk_root=tmp_path)
    assert r["clean"], f"attribution flagged as leak: {r['leaks']}"


def test_catches_email(tmp_path):
    _seed(tmp_path)
    _mk(tmp_path, "docs/guide.md", "Contact jane@example.com for access.")
    r = check_personal_data(youk_root=tmp_path)
    assert any(x["kind"] == "email" and "jane@example.com" in x["hit"] for x in r["leaks"])


def test_commit_trailer_email_is_ignored(tmp_path):
    _seed(tmp_path)
    _mk(tmp_path, "docs/x.md", "Co-Authored-By: Claude <noreply@anthropic.com>")
    r = check_personal_data(youk_root=tmp_path)
    assert r["clean"]


def test_gitignored_local_files_never_scanned(tmp_path):
    _seed(tmp_path)
    # a personal profile in knowledge/ is LOCAL by design — must not be flagged
    _mk(tmp_path, "knowledge/global/voice-profile.md", "Jane Dev's real voice fingerprint")
    r = check_personal_data(youk_root=tmp_path)
    assert r["clean"], "scanned a gitignored local file"


def test_clean_repo_reports_clean(tmp_path):
    _seed(tmp_path)
    _mk(tmp_path, "skills/demo/SKILL.md", "The developer's voice maps to output.")
    r = check_personal_data(youk_root=tmp_path)
    assert r["clean"]
    assert format_leak_warnings(r) == []


def test_warnings_name_the_leak(tmp_path):
    _seed(tmp_path)
    _mk(tmp_path, "skills/demo/SKILL.md", "Jane Dev built this.")
    warnings = format_leak_warnings(check_personal_data(youk_root=tmp_path))
    assert any("Jane Dev" in w for w in warnings)


def test_zero_config_still_seeds_from_git_author(tmp_path):
    # no plugin.json, no config file — auto-seed must still try git author.
    # In a tmp dir with no git, names may be empty; that's acceptable (no false positives),
    # but the function must not crash and must return a well-formed result.
    r = check_personal_data(youk_root=tmp_path)
    assert "names_checked" in r and "leaks" in r and "clean" in r


def test_attribution_allow_list_is_small_and_justified():
    # guard against the allow-list quietly growing into a way to hide leaks.
    assert len(_ATTRIBUTION_ALLOW) <= 6
