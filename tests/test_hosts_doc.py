"""docs/hosts.md carries a capability matrix. It is only worth having if it cannot
drift from servers/shared/agent_host.py, so this parses the table and compares."""
from __future__ import annotations

from pathlib import Path

import agent_host
from agent_host import HostCapability

_DOC = Path(__file__).parent.parent / "docs" / "hosts.md"


def _table() -> tuple[list[str], dict[str, dict[str, str]]]:
    rows = [ln for ln in _DOC.read_text().splitlines() if ln.startswith("|")]
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    out: dict[str, dict[str, str]] = {}
    for ln in rows[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if cells[0].startswith(tuple("abcdefghijklmnopqrstuvwxyz")) and len(cells) == len(header):
            if cells[0] in {c.value for c in HostCapability}:
                out[cells[0]] = dict(zip(header, cells))
    return header, out


def test_every_capability_and_host_is_in_the_table():
    header, rows = _table()
    assert set(rows) == {c.value for c in HostCapability}
    assert set(header[2:]) == set(agent_host.all_host_ids())


def test_table_cells_match_what_each_host_declares_and_the_policy_class():
    _, rows = _table()
    for cap in HostCapability:
        row = rows[cap.value]
        assert row["Class"] == agent_host._REQUIREMENTS[cap].value
        for host_id, caps in agent_host._HOSTS.items():
            expected = "yes" if cap in caps.supported else "no"
            assert row[host_id] == expected, f"{cap.value}/{host_id}"
