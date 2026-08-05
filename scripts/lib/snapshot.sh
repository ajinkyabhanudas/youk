#!/usr/bin/env bash
# youk pre-install snapshot — sourced by install.sh BEFORE any host mutation.
#
# Captures a verifiable, one-time record of the pre-youk state of every host
# artifact install.sh is about to change, so uninstall.sh can restore it exactly.
# The snapshot is the recovery floor; fence markers in CLAUDE.md are the day-to-day
# clean path. See scripts/uninstall.sh.
#
# Idempotent: if a snapshot already exists (latest/manifest.json present), this is
# a no-op — a good snapshot is never overwritten by a later, already-youk-fied state.
#
# Secret safety: only the two youk MCP server blocks are copied out of ~/.claude.json,
# never the whole file (it may hold auth tokens). No secret values are ever printed.
#
# Requires ui.sh-style helpers (ok/warn/step) to be defined by the caller (install.sh
# defines them inline). Requires: CLAUDE_DIR, YOUK_DIR set by the caller.

# youk_snapshot_sha256 FILE -> prints hex digest, or "" if file missing.
youk_snapshot_sha256() {
  local f="$1"
  [ -f "$f" ] || { echo ""; return 0; }
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$f" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
  else
    echo ""
  fi
}

# youk_take_snapshot — writes the snapshot tree under $CLAUDE_DIR/youk-restore/.
youk_take_snapshot() {
  local restore_root="$CLAUDE_DIR/youk-restore"
  local latest="$restore_root/latest"

  if [ -f "$latest/manifest.json" ]; then
    ok "Pre-install snapshot already exists — preserving it (idempotent)"
    return 0
  fi

  local ts
  ts="$(date -u '+%Y-%m-%dT%H-%M-%SZ')"
  local snap="$restore_root/$ts"
  mkdir -p "$snap"

  local claude_md="$CLAUDE_DIR/CLAUDE.md"
  local claude_md_state
  # CLAUDE.md: only snapshot a genuinely pre-youk file. If youk is already present,
  # record that and do NOT capture — capturing a youk-fied file as ".orig" would
  # make uninstall restore youk's own block.
  if [ ! -f "$claude_md" ]; then
    claude_md_state="absent"
  elif grep -q "youk-core.session_start" "$claude_md" 2>/dev/null; then
    claude_md_state="pre-existing"   # youk already in it — nothing clean to snapshot
  else
    cp "$claude_md" "$snap/CLAUDE.md.orig"
    claude_md_state="captured"
  fi

  # MCP: extract ONLY the two youk server entries from ~/.claude.json (never the
  # whole file). Absent = record "none". Uses python3 for safe JSON handling.
  local claude_json="$HOME/.claude.json"
  local mcp_state="none"
  if [ -f "$claude_json" ] && command -v python3 >/dev/null 2>&1; then
    if python3 - "$claude_json" "$snap/claude.json.mcp.orig" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
try:
    with open(src) as f:
        data = json.load(f)
except Exception:
    sys.exit(3)
# youk MCP servers may live under top-level "mcpServers" (user scope).
servers = data.get("mcpServers", {}) or {}
youk = {k: v for k, v in servers.items() if k in ("youk-core", "youk-code")}
if not youk:
    sys.exit(4)
with open(dst, "w") as f:
    json.dump(youk, f, indent=2)
sys.exit(0)
PY
    then
      mcp_state="captured"
    else
      mcp_state="none"   # no youk entries yet, or unreadable — nothing to restore
    fi
  fi

  # Skills: record the pre-link state so uninstall can tell youk symlinks from
  # the user's own real dirs / foreign symlinks.
  local skills_state="absent"
  if [ -d "$CLAUDE_DIR/skills" ]; then
    ls -la "$CLAUDE_DIR/skills" > "$snap/skills-before.txt" 2>/dev/null || true
    skills_state="captured"
  fi

  # Schedulers: record pre-existing LaunchAgents / crontab so uninstall only
  # removes what youk added.
  ls -1 "$HOME/Library/LaunchAgents" 2>/dev/null | grep -i youk > "$snap/launchagents-before.txt" 2>/dev/null || true
  crontab -l 2>/dev/null | grep -E "project-research.py|youk.*cleanup.sh" > "$snap/crontab-before.txt" 2>/dev/null || true

  # youk version, for the manifest.
  local youk_version="unknown"
  local plugin_json="$YOUK_DIR/plugin/.claude-plugin/plugin.json"
  if [ -f "$plugin_json" ] && command -v python3 >/dev/null 2>&1; then
    youk_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("version","unknown"))' "$plugin_json" 2>/dev/null || echo unknown)"
  fi

  # manifest.json — the machine-checkable contract uninstall verifies against.
  local claude_md_sha
  claude_md_sha="$(youk_snapshot_sha256 "$snap/CLAUDE.md.orig")"
  cat > "$snap/manifest.json" <<EOF
{
  "youk_version": "$youk_version",
  "timestamp": "$ts",
  "claude_dir": "$CLAUDE_DIR",
  "youk_dir": "$YOUK_DIR",
  "captured": {
    "claude_md": "$claude_md_state",
    "claude_md_sha256": "$claude_md_sha",
    "mcp": "$mcp_state",
    "skills": "$skills_state"
  },
  "artifacts_youk_adds": [
    "mcp:youk-core",
    "mcp:youk-code",
    "symlink:~/.claude/skills/<youk skills>",
    "symlink:~/.claude/plugins/youk-context",
    "claude_md:youk-block",
    "launchagent:com.youk.project-research",
    "launchagent:com.youk.cleanup"
  ]
}
EOF

  # Stable pointer to the latest snapshot.
  rm -f "$latest" 2>/dev/null || true
  ln -s "$ts" "$latest" 2>/dev/null || true

  ok "Pre-install snapshot written → $snap"
  ok "  CLAUDE.md: $claude_md_state · MCP: $mcp_state · skills: $skills_state"
}
