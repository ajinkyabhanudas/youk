"""
Validates docs/system-map.yaml (CIR-178, Phase 2 of
docs/system-observability-design.md): the Stage Registry listing every real
stage across the three subsystems built this session.

This runs against the real repo file, same discipline as
test_doc_map_tool_coverage.py -- a fixture would test the parsing and let
real drift (a stage with a `reads`/`writes` path to a file that was since
renamed or removed) through.

`reads`/`writes` paths under state/ or knowledge/ are runtime-created or
instance-local-gitignored data files (see .gitignore) -- a fresh checkout
never has them until the real stage actually fires, which is the exact
"never fired vs. never logged" distinction the design doc asks this
initiative to preserve. Only paths naming a real, committed module/doc file
are checked for existence.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SYSTEM_MAP_PATH = REPO / "docs" / "system-map.yaml"

REQUIRED_FIELDS = {"name", "grounding", "subsystem", "triggers_on", "reads", "writes", "real_log"}
VALID_GROUNDINGS = {"deterministic", "llm_judgment", "hybrid"}
VALID_SUBSYSTEMS = {
    "verification-pipeline",
    "problem-space-modeling",
    "pattern-learning-architecture",
    "system-observability",
}
# Runtime-created (state/) or instance-local-gitignored (knowledge/) -- never
# guaranteed to exist in a fresh checkout, by design.
_RUNTIME_PREFIXES = ("state/", "knowledge/")


def _load_stages() -> list[dict]:
    return yaml.safe_load(SYSTEM_MAP_PATH.read_text(encoding="utf-8"))


def test_system_map_exists_and_is_a_nonempty_list():
    assert SYSTEM_MAP_PATH.exists(), "docs/system-map.yaml is missing"
    stages = _load_stages()
    assert isinstance(stages, list) and stages, "docs/system-map.yaml must be a non-empty list"


def test_every_entry_has_all_required_fields():
    stages = _load_stages()
    missing = {
        stage.get("name", f"<unnamed index {i}>"): sorted(REQUIRED_FIELDS - stage.keys())
        for i, stage in enumerate(stages)
        if REQUIRED_FIELDS - stage.keys()
    }
    assert not missing, f"stages missing required fields: {missing}"


def test_every_grounding_value_is_valid():
    stages = _load_stages()
    bad = {
        stage["name"]: stage.get("grounding")
        for stage in stages
        if stage.get("grounding") not in VALID_GROUNDINGS
    }
    assert not bad, f"stages with invalid grounding (must be one of {sorted(VALID_GROUNDINGS)}): {bad}"


def test_every_subsystem_value_is_valid():
    stages = _load_stages()
    bad = {
        stage["name"]: stage.get("subsystem")
        for stage in stages
        if stage.get("subsystem") not in VALID_SUBSYSTEMS
    }
    assert not bad, f"stages with invalid subsystem (must be one of {sorted(VALID_SUBSYSTEMS)}): {bad}"


def test_names_are_unique():
    stages = _load_stages()
    names = [stage["name"] for stage in stages]
    duplicates = {name for name in names if names.count(name) > 1}
    assert not duplicates, f"docs/system-map.yaml has duplicate stage names: {duplicates}"


def test_every_real_module_path_in_reads_and_writes_exists():
    """A reads/writes path naming a real committed file that doesn't exist is
    worse than no path at all -- it looks verified but isn't. Runtime/instance-
    local paths (state/, knowledge/) are exempt; see module docstring."""
    stages = _load_stages()
    broken = []
    for stage in stages:
        for field_name in ("reads", "writes"):
            for path in stage.get(field_name) or []:
                if path.startswith(_RUNTIME_PREFIXES):
                    continue
                if not (REPO / path).exists():
                    broken.append(f"{stage['name']}.{field_name} -> {path}")
    assert not broken, f"system-map.yaml paths point at missing real files: {broken}"


def test_triggers_on_and_name_are_non_empty_strings():
    stages = _load_stages()
    bad = [
        stage.get("name", "<unnamed>")
        for stage in stages
        if not isinstance(stage.get("name"), str)
        or not stage["name"].strip()
        or not isinstance(stage.get("triggers_on"), str)
        or not stage["triggers_on"].strip()
    ]
    assert not bad, f"stages with empty/non-string name or triggers_on: {bad}"


def test_reads_and_writes_are_lists():
    stages = _load_stages()
    bad = [
        stage["name"]
        for stage in stages
        if not isinstance(stage.get("reads"), list) or not isinstance(stage.get("writes"), list)
    ]
    assert not bad, f"stages whose reads/writes are not lists: {bad}"


def test_every_subsystem_from_the_design_doc_has_at_least_one_stage():
    """The registry's whole point is covering all three subsystems (plus the
    observability mechanism itself) -- a subsystem with zero entries would
    mean this phase silently skipped a third of its own scope."""
    stages = _load_stages()
    present = {stage["subsystem"] for stage in stages}
    missing = VALID_SUBSYSTEMS - present
    assert not missing, f"no stage entries at all for subsystem(s): {missing}"
