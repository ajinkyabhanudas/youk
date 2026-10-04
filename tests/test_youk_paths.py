"""youk_paths picks audit and skills locations without naming a host, and never moves an
existing install's data."""
from __future__ import annotations

import importlib

import youk_paths


def test_legacy_audit_dir_wins_when_it_exists(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    (host / "audit").mkdir(parents=True)
    assert youk_paths.resolve_audit_dir(host, youk) == host / "audit"


def test_new_installs_keep_audit_under_youk(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    assert youk_paths.resolve_audit_dir(host, youk) == youk / "audit"        # no host dir at all
    host.mkdir()
    assert youk_paths.resolve_audit_dir(host, youk) == youk / "audit"        # host dir without audit/


def test_skills_come_from_the_host_dir_when_linked_else_from_youk(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    assert youk_paths.resolve_skills_dir(host, youk) == youk / "skills"
    (host / "skills").mkdir(parents=True)
    assert youk_paths.resolve_skills_dir(host, youk) == host / "skills"


def test_host_root_env_override_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUK_HOST_ROOT", str(tmp_path))
    assert youk_paths.resolve_host_root() == tmp_path
    monkeypatch.delenv("YOUK_HOST_ROOT")
    assert youk_paths.resolve_host_root().name in {"host", "claude"}
    importlib.reload(youk_paths)


def test_every_host_adapter_has_an_instructions_file_name():
    import agent_host
    assert set(youk_paths.INSTRUCTIONS_FILES) == set(agent_host.all_host_ids())


# --- a install on a host with no config dir to mount ---------------------------

def test_a_fresh_container_resolves_everything_under_youk(tmp_path):
    """The way a container started with only the /youk mount sees it: import-time constants
    in the shared skill loader point into youk's own tree, not a host dir."""
    import subprocess
    import sys
    from pathlib import Path
    (tmp_path / "youk" / "skills").mkdir(parents=True)
    out = subprocess.run(
        [sys.executable, "-c",
         "import skill_loader, youk_paths; print(skill_loader.SKILLS_DIR); "
         "print(youk_paths.resolve_audit_dir(youk_paths.HOST_ROOT, youk_paths.YOUK_ROOT))"],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent.parent / "servers" / "shared"),
             "YOUK_ROOT": str(tmp_path / "youk"), "YOUK_HOST_ROOT": str(tmp_path / "no-host-dir")},
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert out == [str(tmp_path / "youk" / "skills"), str(tmp_path / "youk" / "audit")]


def test_write_roots_for_proposals_follow_the_resolved_skills_dir(tmp_path, monkeypatch):
    import health
    host, youk = tmp_path / "host", tmp_path / "youk"
    host.mkdir()
    monkeypatch.setattr(health, "HOST_ROOT", host)
    monkeypatch.setattr(health, "YOUK_ROOT", youk)
    assert health._allowed_write_roots() == [youk, youk / "skills"]
    (host / "skills").mkdir()
    assert health._allowed_write_roots() == [youk, host / "skills"]


# --- youk://context/{project} reads youk's own notes, not a host's private folder -

def _code_server():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "youk_code_server_for_paths", Path(__file__).parent.parent / "servers" / "code" / "src" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_project_context_serves_the_projects_markdown(tmp_path, monkeypatch):
    srv = _code_server()
    monkeypatch.setattr(srv, "YOUK_ROOT", tmp_path)
    d = tmp_path / "knowledge" / "projects" / "shop"
    d.mkdir(parents=True)
    (d / "contracts.md").write_text("- always run tests")
    (d / "decisions.md").write_text("- chose postgres")
    (d / "notes.txt").write_text("ignored")
    text = srv.get_project_context("shop")
    assert "always run tests" in text and "chose postgres" in text and "ignored" not in text


def test_project_context_rejects_a_name_that_is_not_a_slug(tmp_path, monkeypatch):
    srv = _code_server()
    monkeypatch.setattr(srv, "YOUK_ROOT", tmp_path)
    (tmp_path / "secret.md").write_text("do not leak")
    assert srv.get_project_context("../../..").startswith("No context found")
    assert srv.get_project_context("nope").startswith("No context found")


def test_path_map_accepts_the_neutral_key_and_the_old_one(tmp_path, monkeypatch):
    import state_paths
    host, youk = tmp_path / "host", tmp_path / "youk"
    (host / "work").mkdir(parents=True)
    (youk / "state").mkdir(parents=True)
    monkeypatch.setattr(state_paths, "HOST_ROOT", host)
    monkeypatch.setattr(state_paths, "YOUK_ROOT", youk)
    for key in ("HOST_CONFIG_DIR", "CLAUDE_HOST_DIR"):
        (youk / "state" / "path-map.env").write_text(f"YOUK_HOST_DIR=/h/youk\n{key}=/h/cfg\n")
        assert state_paths.resolve_project_path("/h/cfg/work") == host / "work", key


def test_skills_are_read_from_youk_when_the_installer_did_not_link_them(tmp_path):
    host, youk = tmp_path / "host", tmp_path / "youk"
    (host / "skills" / "someone-elses-skill").mkdir(parents=True)     # another tool's skills dir
    (youk / "state").mkdir(parents=True)
    # no path-map.env: legacy rule, the host dir wins
    assert youk_paths.resolve_skills_dir(host, youk) == host / "skills"
    (youk / "state" / "path-map.env").write_text("HOST_SKILLS_LINKED=0\n")
    assert youk_paths.resolve_skills_dir(host, youk) == youk / "skills"
    (youk / "state" / "path-map.env").write_text("# c\nHOST_SKILLS_LINKED=1\n")
    assert youk_paths.resolve_skills_dir(host, youk) == host / "skills"


# --- host-side scripts locate the install without assuming ~/.claude ----------------

def test_locate_install_uses_the_script_location_and_the_recorded_host_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUK_HOME", raising=False)
    install = tmp_path / "somewhere" / "youk"
    (install / "scripts").mkdir(parents=True)
    (install / "state").mkdir()
    (install / "state" / "path-map.env").write_text("HOST_CONFIG_DIR=/cfg/.codex\n")
    youk_dir, host_dir, audit = youk_paths.locate_install(install / "scripts" / "dashboard.py")
    assert (youk_dir, host_dir) == (install.resolve(), __import__("pathlib").Path("/cfg/.codex"))
    assert audit == install.resolve() / "audit"          # no legacy audit dir under the host dir


def test_locate_install_falls_back_to_the_claude_dir_and_honours_youk_home(tmp_path, monkeypatch):
    install = tmp_path / "youk"
    (install / "scripts").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    (tmp_path / "h" / ".claude" / "audit").mkdir(parents=True)
    _, host_dir, audit = youk_paths.locate_install(install / "scripts" / "x.py")
    assert host_dir == tmp_path / "h" / ".claude" and audit == host_dir / "audit"   # legacy layout
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("YOUK_HOME", str(other))
    assert youk_paths.locate_install(install / "scripts" / "x.py")[0] == other


# --- checks that read "the routing loop" see AGENTS.md as well as CLAUDE.md ------------

def test_instruction_files_lists_whichever_exist(tmp_path):
    assert youk_paths.instruction_files(tmp_path) == []
    (tmp_path / "AGENTS.md").write_text("a")
    (tmp_path / "CLAUDE.md").write_text("c")
    assert [p.name for p in youk_paths.instruction_files(tmp_path)] == ["AGENTS.md", "CLAUDE.md"]


def test_wiring_pulse_reads_a_codex_routing_loop(tmp_path):
    import wiring_pulse
    (tmp_path / "AGENTS.md").write_text("call youk-core.route_task before work")
    assert "route_task" in wiring_pulse._routing_loop_text(tmp_path)
    assert wiring_pulse._routing_loop_text(tmp_path / "nothing") == ""


def test_skill_route_check_resolves_routes_named_in_agents_md(tmp_path):
    import skill_route_check
    host, youk = tmp_path / "host", tmp_path / "youk"
    (host / "skills" / "dev-loop").mkdir(parents=True)
    (host / "skills" / "dev-loop" / "SKILL.md").write_text("# dev loop\nreal content here\n")
    (host / "AGENTS.md").write_text("route_to_skill('dev-loop', task)\n")
    out = skill_route_check.check_skill_routes(host, youk)
    assert out["checked"] == 1 and out["healthy"] is True


def test_project_context_scan_loads_a_projects_agents_md(tmp_path):
    import knowledge_loader
    (tmp_path / "AGENTS.md").write_text("project rules for any agent")
    result = knowledge_loader._scan_project_context_files(str(tmp_path))
    assert result["claude_md"] == "project rules for any agent" and result["context_level"] == "L5"
