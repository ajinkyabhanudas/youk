"""Task 1.5 — the machine-checked seam.

The store-rework's boundary (state-store-rework.md): a state file that holds a MUTABLE
CLAIM (something that can silently diverge from truth) must be registered with a schema
in MUTABLE_CLAIM_SCHEMAS; an append-only log or monotonic counter must NOT be. This test
enforces that boundary in CI so the store cannot rot back into unvalidated loose files:
if someone adds a new mutable-claim state file without registering it, this fails.

The check is intentionally conservative — it asserts the KNOWN mutable-claim files are
registered and that append-only/counter files are NOT registered. A genuinely new state
file forces a human decision (register it or justify why it's exempt), which is the point.
"""
from __future__ import annotations

from state_schema import MUTABLE_CLAIM_SCHEMAS

# Files that hold a mutable claim — MUST be registered with a validating schema.
_KNOWN_MUTABLE_CLAIM_FILES = {
    "active_task.json",
    "session-plan.json",
    "pending-action.json",
    "challenge-ran.json",
    "challenge-gate-passed.json",
    "nfr-check-ran.json",
    "route-task-ran.json",
    "intake-ran.json",
}

# Files that are append-only logs or monotonic counters — MUST NOT be registered
# (they cannot lie, only grow; validating them is the speculative completeness the
# contract forbids).
_KNOWN_NON_CLAIM_FILES = {
    "skill-signals.jsonl",
    "risk-ledger.jsonl",
    "ab-bench-results.jsonl",
    "knowledge-usage.jsonl",
    "task-checkpoints.jsonl",
    "tool-call-count.json",
    "compact-count.json",
    "current-session-tokens.json",
}


def test_every_known_mutable_claim_file_is_registered():
    missing = _KNOWN_MUTABLE_CLAIM_FILES - set(MUTABLE_CLAIM_SCHEMAS)
    assert not missing, (
        f"Mutable-claim state files missing a schema: {missing}. "
        f"Register them in MUTABLE_CLAIM_SCHEMAS (state_schema.py) or the store can "
        f"silently accept malformed writes to them."
    )


def test_append_only_and_counter_files_are_not_registered():
    wrongly_registered = _KNOWN_NON_CLAIM_FILES & set(MUTABLE_CLAIM_SCHEMAS)
    assert not wrongly_registered, (
        f"Append-only/counter files must NOT be schema-registered: {wrongly_registered}. "
        f"They cannot diverge from truth; validating them is speculative completeness."
    )


def test_registry_is_non_empty_and_maps_to_schema_types():
    assert MUTABLE_CLAIM_SCHEMAS, "the seam registry must not be empty"
    for name, schema in MUTABLE_CLAIM_SCHEMAS.items():
        assert hasattr(schema, "from_dict"), f"{name} -> schema needs from_dict (read validation)"
        assert hasattr(schema, "to_dict"), f"{name} -> schema needs to_dict (write serialization)"
