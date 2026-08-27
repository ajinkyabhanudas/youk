"""Coverage tests for the MCP contract verifier.

The verifier was never broken, but it only saw 6 of 35 tool references in CLAUDE.md and
the skills. Its regex required both a backtick wrapper and a server prefix
(`youk-core.route_task(...)`), while CLAUDE.md overwhelmingly writes the bare form
(`route_task(...)`). 29 references naming 18 real tools were invisible, so renaming any
of them would have reported CLEAN.

Unprefixed names are recognised by membership in the registered tool set rather than by
matching a prose syntax. The tool list is already extracted from the servers by AST and
is ground truth, so widening the regex further was the wrong fix: it would move the
blind spot to whatever spelling the next author uses.
"""
from __future__ import annotations

import pytest

pytest.importorskip("yaml")

from contract_verifier import _BARE_CALL_SITE_PATTERN, _extract_call_sites  # noqa: E402

_KNOWN = frozenset({"route_task", "check_nfr_gate", "session_start", "compact_context"})


def _write(tmp_path, text):
    f = tmp_path / "SKILL.md"
    f.write_text(text)
    return f


class TestBareReferencesAreNowSeen:
    def test_bare_reference_is_collected(self, tmp_path):
        f = _write(tmp_path, "Call `route_task(task)` before acting.")
        sites = _extract_call_sites(f, _KNOWN)
        assert [(s, t) for s, t, _ in sites] == [("", "route_task")]

    def test_bare_reference_invisible_without_known_tools(self, tmp_path):
        """Bar 7: the pre-fix behaviour, which is what missed 29 references."""
        f = _write(tmp_path, "Call `route_task(task)` before acting.")
        assert _extract_call_sites(f) == []

    def test_prefixed_reference_still_works(self, tmp_path):
        f = _write(tmp_path, "Call `youk-core.session_start(project_dir)` first.")
        sites = _extract_call_sites(f, _KNOWN)
        assert ("youk-core", "session_start") in [(s, t) for s, t, _ in sites]

    def test_same_tool_in_both_forms_counted_once(self, tmp_path):
        f = _write(tmp_path, "`youk-core.route_task(t)` and later `route_task(t)`.")
        sites = _extract_call_sites(f, _KNOWN)
        assert sum(1 for _, t, _ in sites if t == "route_task") == 1


class TestProseIsNotMistakenForTools:
    def test_unregistered_bare_name_is_ignored(self, tmp_path):
        """An unprefixed unknown name is indistinguishable from prose, so it is dropped."""
        f = _write(tmp_path, "Run `some_helper(x)` to continue.")
        assert _extract_call_sites(f, _KNOWN) == []

    def test_shell_commands_are_ignored(self, tmp_path):
        f = _write(tmp_path, "Run `make(all)` and `docker(ps)` here.")
        assert _extract_call_sites(f, _KNOWN) == []

    def test_builtin_names_are_ignored(self, tmp_path):
        f = _write(tmp_path, "Use `print(x)` and `open(f)`.")
        assert _extract_call_sites(f, _KNOWN) == []

    def test_short_names_do_not_match(self, tmp_path):
        """The pattern requires 4+ chars, so `f(x)` is not a candidate."""
        assert not _BARE_CALL_SITE_PATTERN.findall("`f(x)` and `ab(y)`")


class TestUnregisteredPrefixedToolIsFlagged:
    def test_prefixed_unknown_tool_is_collected_for_checking(self, tmp_path):
        """A prefixed name is attributed to its server, so it can be checked and fail."""
        f = _write(tmp_path, "Call `youk-core.this_tool_does_not_exist(x)`.")
        sites = _extract_call_sites(f, _KNOWN)
        assert ("youk-core", "this_tool_does_not_exist") in [(s, t) for s, t, _ in sites]
