"""Tests for servers/shared/capability_ledger.py (CIR-156 item 2)."""
from __future__ import annotations


from agent_host import HostCapability
from capability_ledger import (
    REPO_ROOT,
    investigated_pairs,
    load_ledger,
    missing_investigations,
    record_investigation,
)


class TestRecordAndLoad:
    def test_record_investigation_appends_a_line(self, tmp_path):
        record_investigation(tmp_path, "claude-code", HostCapability.SESSION_CONTEXT, "unit test")
        rows = load_ledger(tmp_path)
        assert len(rows) == 1
        assert rows[0]["host"] == "claude-code"
        assert rows[0]["capability"] == "session_context"
        assert rows[0]["how_found"] == "unit test"

    def test_load_ledger_empty_when_file_does_not_exist(self, tmp_path):
        assert load_ledger(tmp_path) == []

    def test_repeat_investigations_both_persist(self, tmp_path):
        """Append-only, like the pattern library -- re-checking a pair later
        (e.g. after a host's hook surface changes) is a real event, not a
        dedup target."""
        record_investigation(tmp_path, "codex", HostCapability.PROMPT_CONTEXT, "first check")
        record_investigation(tmp_path, "codex", HostCapability.PROMPT_CONTEXT, "second check")
        assert len(load_ledger(tmp_path)) == 2

    def test_investigated_pairs_reflects_recorded_rows(self, tmp_path):
        record_investigation(tmp_path, "claude-code", HostCapability.PRE_TOOL_GUARD, "x")
        assert investigated_pairs(tmp_path) == {("claude-code", "pre_tool_guard")}


class TestMissingInvestigations:
    def test_empty_ledger_flags_every_pair(self, tmp_path):
        missing = missing_investigations(
            tmp_path, host_ids=frozenset({"claude-code"}), capabilities=["session_context", "pre_tool_guard"]
        )
        assert set(missing) == {
            ("claude-code", "session_context"),
            ("claude-code", "pre_tool_guard"),
        }

    def test_recorded_pair_is_not_flagged(self, tmp_path):
        record_investigation(tmp_path, "claude-code", HostCapability.SESSION_CONTEXT, "x")
        missing = missing_investigations(
            tmp_path, host_ids=frozenset({"claude-code"}), capabilities=["session_context"]
        )
        assert missing == []

    def test_a_new_capability_value_with_no_ledger_entry_is_flagged_for_every_host(self, tmp_path):
        """Simulates 'a new HostCapability enum value is added without a
        corresponding ledger entry for every existing host' -- the exact
        case CIR-156's DONE-MEANS asks the check to catch. Passing an
        explicit extra capability name (rather than monkeypatching the
        StrEnum) is the testable surface; missing_investigations never
        hardcodes the capability list internally, so this exercises the
        real code path a real new enum member would hit."""
        record_investigation(tmp_path, "claude-code", HostCapability.SESSION_CONTEXT, "x")
        record_investigation(tmp_path, "codex", HostCapability.SESSION_CONTEXT, "x")
        missing = missing_investigations(
            tmp_path,
            host_ids=frozenset({"claude-code", "codex"}),
            capabilities=["session_context", "brand_new_capability"],
        )
        assert set(missing) == {
            ("claude-code", "brand_new_capability"),
            ("codex", "brand_new_capability"),
        }

    def test_a_new_host_with_no_ledger_entry_is_flagged_for_every_capability(self, tmp_path):
        record_investigation(tmp_path, "claude-code", HostCapability.SESSION_CONTEXT, "x")
        missing = missing_investigations(
            tmp_path, host_ids=frozenset({"claude-code", "new-host"}), capabilities=["session_context"]
        )
        assert missing == [("new-host", "session_context")]


class TestLedgerCoversTheRealCodebase:
    """The CI-shaped check CIR-156's DONE-MEANS asks for: fails when a new
    HostCapability enum value (or a new host) is added to agent_host.py
    without a matching ledger entry for every existing host. Runs against
    the real, committed state/capability-investigation-ledger.jsonl and the
    real HostCapability enum/host registry -- not a tmp_path fixture."""

    def test_every_declared_host_capability_pair_has_a_real_ledger_entry(self):
        missing = missing_investigations(REPO_ROOT)
        assert missing == [], (
            f"undeclared (host, capability) investigations: {missing} -- add a "
            f"record_investigation() entry to "
            f"{REPO_ROOT / 'state' / 'capability-investigation-ledger.jsonl'} for each"
        )

    def test_repo_root_resolves_to_the_real_checkout(self):
        assert (REPO_ROOT / "servers" / "shared" / "agent_host.py").exists()
        assert (REPO_ROOT / "state" / "capability-investigation-ledger.jsonl").exists()
