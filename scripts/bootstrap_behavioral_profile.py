#!/usr/bin/env python3
"""Bootstrap behavioral profile from existing audit history.

Scans all monthly audit files in ~/.claude/audit/ and populates
state/dev-behavioral-profile.json with observed skill-timing patterns.

Run once after install, or re-run to catch up after a gap.
"""
import sys
from pathlib import Path

root = Path(__file__).parent.parent
sys.path.insert(0, str(root / "servers" / "core" / "src"))

from behavioral_profile import load_active_hints, scan_audit_for_patterns

audit_dir = Path.home() / ".claude" / "audit"
profile_path = root / "state" / "dev-behavioral-profile.json"

if not audit_dir.exists():
    print(f"No audit directory at {audit_dir} — nothing to scan.")
    sys.exit(0)

total_sessions = 0
total_patterns = 0
for audit_file in sorted(audit_dir.glob("*.md")):
    result = scan_audit_for_patterns(audit_file, profile_path=profile_path)
    print(f"  {audit_file.name}: {result['sessions_scanned']} sessions, {result['patterns_found']} patterns")
    total_sessions += result["sessions_scanned"]
    total_patterns += result["patterns_found"]

print(f"\nTotal: {total_sessions} sessions scanned, {total_patterns} patterns observed")

hints = load_active_hints(profile_path)
if hints:
    print(f"Active hints ({len(hints)}):")
    for h in hints:
        print(f"  {h['skill']}:{h['event']} — {h['count']} sessions, last {h['last_seen']}")
else:
    print("No active hints yet (need more session history).")
