"""youk_paths picks audit and skills locations without naming a host, and never moves an
existing install's data."""
from __future__ import annotations

import importlib

import youk_paths


def test_legacy_audit_dir_wins_when_it_exists(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    (host / "audit").mkdir(parents=True)
    assert youk_paths.audit_dir(host, youk) == host / "audit"


def test_new_installs_keep_audit_under_youk(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    assert youk_paths.audit_dir(host, youk) == youk / "audit"        # no host dir at all
    host.mkdir()
    assert youk_paths.audit_dir(host, youk) == youk / "audit"        # host dir without audit/


def test_skills_come_from_the_host_dir_when_linked_else_from_youk(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    assert youk_paths.skills_dir(host, youk) == youk / "skills"
    (host / "skills").mkdir(parents=True)
    assert youk_paths.skills_dir(host, youk) == host / "skills"


def test_host_root_env_override_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUK_HOST_ROOT", str(tmp_path))
    assert youk_paths.resolve_host_root() == tmp_path
    monkeypatch.delenv("YOUK_HOST_ROOT")
    assert youk_paths.resolve_host_root().name in {"host", "claude"}
    importlib.reload(youk_paths)


def test_every_host_adapter_has_an_instructions_file_name():
    import agent_host
    assert set(youk_paths.INSTRUCTIONS_FILES) == set(agent_host.all_host_ids())
