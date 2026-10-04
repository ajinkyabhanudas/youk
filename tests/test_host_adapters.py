"""scripts/lib/hosts.sh is the only place the installer learns anything about an agent host.
These drive it with stub `claude` and `codex` binaries that record their arguments, so what each
host is told to do is asserted, not assumed. No Docker, launchd or real CLI is involved."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_LIB = Path(__file__).parent.parent / "scripts" / "lib" / "hosts.sh"
_PRELUDE = 'ok(){ echo "ok: $*"; }; warn(){ echo "warn: $*"; }; fail(){ echo "fail: $*"; };'


@pytest.fixture
def sandbox(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for cli in ("claude", "codex"):
        stub = bin_dir / cli
        stub.write_text(f'#!/bin/sh\necho "{cli} $*" >> "{log}"\nexit 0\n')
        stub.chmod(0o755)

    def run(snippet: str, *, path_has=("claude", "codex"), env=None):
        keep = tmp_path / "pathbin"
        keep.mkdir(exist_ok=True)
        for cli in ("claude", "codex"):
            link = keep / cli
            if cli in path_has and not link.exists():
                link.symlink_to(bin_dir / cli)
        full_env = {"PATH": f"{keep}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), **(env or {})}
        (tmp_path / "home").mkdir(exist_ok=True)
        return subprocess.run(["bash", "-c", f'{_PRELUDE} . "{_LIB}"; {snippet}'],
                              capture_output=True, text=True, env=full_env)

    run.log = log
    run.tmp = tmp_path
    return run


def _calls(sb):
    return sb.log.read_text().splitlines() if sb.log.exists() else []


# --- host selection ---------------------------------------------------------------

@pytest.mark.parametrize("have,env,expected", [
    (("claude", "codex"), {}, "claude-code"),
    (("codex",), {}, "codex"),
    (("claude",), {}, "claude-code"),
    ((), {}, "none"),
    (("claude", "codex"), {"YOUK_HOST": "codex"}, "codex"),
    ((), {"YOUK_HOST": "claude-code"}, "claude-code"),
    (("claude",), {"YOUK_HOST": "none"}, "none"),
])
def test_host_selection(sandbox, have, env, expected):
    out = sandbox("youk_detect_host", path_has=have, env=env)
    assert out.stdout.strip() == expected


def test_an_unknown_host_is_an_error_not_a_guess(sandbox):
    out = sandbox("youk_detect_host", env={"YOUK_HOST": "cursor"})
    assert out.returncode == 2 and "unknown YOUK_HOST" in out.stderr and out.stdout == ""


def test_host_dirs_and_instructions_files(sandbox):
    home = sandbox.tmp / "home"
    assert sandbox("youk_host_dir claude-code").stdout.strip() == f"{home}/.claude"
    assert sandbox("youk_host_instructions_file claude-code").stdout.strip() == f"{home}/.claude/CLAUDE.md"
    assert sandbox("youk_host_dir codex").stdout.strip() == f"{home}/.codex"
    assert sandbox("youk_host_instructions_file codex").stdout.strip() == f"{home}/.codex/AGENTS.md"
    assert sandbox("youk_host_instructions_file codex", env={"CODEX_HOME": "/x/y"}).stdout.strip() == "/x/y/AGENTS.md"
    assert sandbox("youk_host_dir none").stdout.strip() == ""


def test_codex_override_file_wins_only_when_non_empty(sandbox):
    codex_home = sandbox.tmp / "ch"
    codex_home.mkdir()
    env = {"CODEX_HOME": str(codex_home)}
    (codex_home / "AGENTS.override.md").write_text("")
    assert sandbox("youk_host_instructions_file codex", env=env).stdout.strip() == f"{codex_home}/AGENTS.md"
    (codex_home / "AGENTS.override.md").write_text("override")
    assert sandbox("youk_host_instructions_file codex", env=env).stdout.strip() == f"{codex_home}/AGENTS.override.md"


# --- MCP registration: the exact command each host receives -----------------------

def test_claude_code_registration(sandbox):
    sandbox("youk_register_servers claude-code")
    assert _calls(sandbox) == [
        "claude mcp remove youk-core", "claude mcp remove youk-code",
        "claude mcp add --scope user youk-core --transport http http://127.0.0.1:8001/mcp",
        "claude mcp add --scope user youk-code --transport http http://127.0.0.1:8002/mcp",
    ]


def test_codex_registration(sandbox):
    sandbox("youk_register_servers codex")
    assert _calls(sandbox) == [
        "codex mcp remove youk-core", "codex mcp remove youk-code",
        "codex mcp add youk-core --url http://127.0.0.1:8001/mcp",
        "codex mcp add youk-code --url http://127.0.0.1:8002/mcp",
    ]


def test_no_host_registers_nothing_and_prints_the_urls(sandbox):
    out = sandbox("youk_register_servers none")
    assert _calls(sandbox) == []
    assert "http://127.0.0.1:8001/mcp" in out.stdout and "http://127.0.0.1:8002/mcp" in out.stdout


def test_a_failed_registration_is_reported_not_hidden(sandbox):
    bad = sandbox.tmp / "pathbin"
    bad.mkdir(exist_ok=True)
    (bad / "codex").write_text('#!/bin/sh\n[ "$2" = add ] && exit 1\nexit 0\n')
    (bad / "codex").chmod(0o755)
    out = sandbox("youk_register_servers codex", path_has=())
    assert "fail: could not register youk-core with codex" in out.stdout


# --- instructions file: one implementation of patch and unpatch, any host ---------

@pytest.fixture
def template(tmp_path):
    t = tmp_path / "template.md"
    t.write_text("# youk\nuse youk-core.session_start\n")
    return t


def test_patch_appends_a_fenced_block_and_keeps_the_users_text(sandbox, template):
    f = sandbox.tmp / "AGENTS.md"
    f.write_text("my own rules\n")
    sandbox(f'youk_patch_instructions "{f}" "{template}"')
    text = f.read_text()
    assert text.startswith("my own rules\n") and "<!-- BEGIN youk (managed) -->" in text and "<!-- END youk -->" in text


def test_patch_is_idempotent_and_refreshes_the_block(sandbox, template):
    f = sandbox.tmp / "AGENTS.md"
    sandbox(f'youk_patch_instructions "{f}" "{template}"')
    once = f.read_text()
    sandbox(f'youk_patch_instructions "{f}" "{template}"')
    assert f.read_text() == once
    template.write_text("# youk\nnew text youk-core.session_start\n")
    sandbox(f'youk_patch_instructions "{f}" "{template}"')
    assert "new text" in f.read_text() and f.read_text().count("BEGIN youk") == 1


def test_patch_wraps_a_legacy_unfenced_block_without_changing_it(sandbox, template):
    f = sandbox.tmp / "CLAUDE.md"
    f.write_text("mine\n\n# youk — old\ncall youk-core.session_start\n")
    sandbox(f'youk_patch_instructions "{f}" "{template}"')
    text = f.read_text()
    assert text.startswith("mine\n\n<!-- BEGIN youk (managed) -->\n# youk — old\ncall youk-core.session_start\n")
    assert text.rstrip().endswith("<!-- END youk -->")


def test_remove_takes_out_only_the_fenced_block(sandbox, template):
    f = sandbox.tmp / "AGENTS.md"
    f.write_text("mine above\n")
    sandbox(f'youk_patch_instructions "{f}" "{template}"')
    f.write_text(f.read_text() + "mine below\n")
    out = sandbox(f'youk_remove_fenced_block "{f}"; echo rc=$?')
    assert "rc=0" in out.stdout
    assert f.read_text() == "mine above\n\n\nmine below\n"


def test_remove_reports_no_fence_and_missing_files(sandbox):
    f = sandbox.tmp / "AGENTS.md"
    f.write_text("nothing here\n")
    assert "rc=1" in sandbox(f'youk_remove_fenced_block "{f}"; echo rc=$?').stdout
    assert "rc=1" in sandbox(f'youk_remove_fenced_block "{f}.nope"; echo rc=$?').stdout
    assert f.read_text() == "nothing here\n"


def test_a_large_instructions_file_gets_a_size_warning(sandbox, template):
    f = sandbox.tmp / "AGENTS.md"
    f.write_text("x" * 31000)
    assert "32 KiB" in sandbox(f'youk_patch_instructions "{f}" "{template}"').stdout


def test_the_library_is_syntactically_valid_bash_3_compatible():
    # `bash -n` parses without running; the file avoids associative arrays and ${var,,}.
    assert subprocess.run(["bash", "-n", str(_LIB)], capture_output=True).returncode == 0
    text = _LIB.read_text()
    assert "declare -A" not in text and ",," not in text and os.access(_LIB, os.R_OK)
