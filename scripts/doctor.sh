#!/usr/bin/env bash
# youk health check — actionable diagnostics with Fix: lines for every failure
# Exit code: 0 = all pass, 1 = any failure
set -uo pipefail

YOUK_DIR="${YOUK_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=lib/hosts.sh
. "$YOUK_DIR/scripts/lib/hosts.sh"

# Which agent host this install targets and where its config lives, as the installer recorded
# them. Installs made before the host was recorded were all Claude Code.
_map() { sed -n "s/^$1=//p" "$YOUK_DIR/state/path-map.env" 2>/dev/null | head -1; }
YOUK_HOST_ID="${YOUK_HOST:-}"
if [[ -z "$YOUK_HOST_ID" || "$YOUK_HOST_ID" == "auto" ]]; then YOUK_HOST_ID="$(_map YOUK_AGENT_HOST)"; fi
if [[ -z "$YOUK_HOST_ID" ]]; then YOUK_HOST_ID="claude-code"; fi
HOST_DIR="$(_map HOST_CONFIG_DIR)"
if [[ -z "$HOST_DIR" ]]; then HOST_DIR="$(youk_host_dir "$YOUK_HOST_ID")"; fi
if [[ -z "$HOST_DIR" ]]; then HOST_DIR="$YOUK_DIR/.host"; fi
case "$YOUK_HOST_ID" in
  claude-code) export CLAUDE_DIR="$HOST_DIR"; AUDIT_DIR="$HOST_DIR/audit"; SKILLS_PATH="$HOST_DIR/skills" ;;
  codex)       export CODEX_HOME="$HOST_DIR"; AUDIT_DIR="$YOUK_DIR/audit"; SKILLS_PATH="$YOUK_DIR/skills" ;;
  *)           AUDIT_DIR="$YOUK_DIR/audit"; SKILLS_PATH="$YOUK_DIR/skills" ;;
esac

# ── Platform detection ────────────────────────────────────────────────────────
OS="$(uname -s)"
IS_WINDOWS=false
if [[ "$OS" == MINGW* ]] || [[ "$OS" == MSYS* ]] || [[ "$OS" == CYGWIN* ]]; then
  IS_WINDOWS=true
fi
if [[ "$OS" == "Linux" ]] && grep -qi "microsoft\|wsl" /proc/version 2>/dev/null; then
  IS_WINDOWS=true
fi

PASS=0; FAIL=0; WARN=0

pass() { echo "  PASS  $1"; PASS=$((PASS+1)); }
warn() { echo "  WARN  $1"; WARN=$((WARN+1)); }
fail() {
  echo "  FAIL  $1"
  echo "        Fix: $2"
  FAIL=$((FAIL+1))
}

echo "youk doctor"
echo ""

# ── Docker ────────────────────────────────────────────────────────────────────
echo "Docker"

if ! command -v docker &>/dev/null; then
  fail "docker: not installed" \
    "install Docker Desktop from https://docker.com"
else
  if ! docker info &>/dev/null 2>&1; then
    fail "docker: not running" \
      "start Docker Desktop, then re-run: bash $YOUK_DIR/scripts/doctor.sh"
  else
    pass "docker: running"
  fi
fi

if docker image inspect youk-core:latest &>/dev/null 2>&1; then
  pass "youk-core image: built"
else
  fail "youk-core image: not found" \
    "cd $YOUK_DIR && make build"
fi

if docker image inspect youk-code:latest &>/dev/null 2>&1; then
  pass "youk-code image: built"
else
  fail "youk-code image: not found" \
    "cd $YOUK_DIR && make build"
fi

# Detect stale image: servers/shared/ changed after the image was built
# servers/shared/ is baked into both images at build time — not live-mounted.
# Docker returns Created in UTC (ISO 8601 with trailing Z). Parse explicitly as UTC
# so local timezone offsets don't skew the epoch calculation on macOS.
IMAGE_BUILT=$(docker image inspect youk-code:latest --format '{{.Created}}' 2>/dev/null | sed 's/\.[0-9]*Z*$//')
IMAGE_BUILT_S=$(TZ=UTC date -jf "%Y-%m-%dT%H:%M:%S" "${IMAGE_BUILT:-1970-01-01T00:00:00}" +%s 2>/dev/null \
               || date -d "${IMAGE_BUILT:-1970-01-01T00:00:00}Z" +%s 2>/dev/null || echo 0)
if [[ "${IMAGE_BUILT_S:-0}" -gt 0 ]] && command -v git &>/dev/null && [[ -d "$YOUK_DIR/.git" ]]; then
  SHARED_CHANGED=$(git -C "$YOUK_DIR" log --since="@${IMAGE_BUILT_S}" --format="%h" -- servers/shared/ 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${SHARED_CHANGED:-0}" -gt 0 ]]; then
    fail "image stale: servers/shared/ has ${SHARED_CHANGED} commit(s) since last build" \
      "cd $YOUK_DIR && make build  (shared code is baked into image — rebuild required)"
  else
    pass "image freshness: servers/shared/ up to date"
  fi
fi
echo ""

echo ""

# ── MCP registration ──────────────────────────────────────────────────────────
echo "MCP servers"

if [[ "$YOUK_HOST_ID" == "none" ]]; then
  pass "agent host: none selected (add the MCP URLs to your host yourself: $YOUK_MCP_CORE_URL, $YOUK_MCP_CODE_URL)"
else
  _host_cli="claude"; [[ "$YOUK_HOST_ID" == "codex" ]] && _host_cli="codex"
  if ! command -v "$_host_cli" &>/dev/null; then
    fail "$_host_cli: agent host CLI for '$YOUK_HOST_ID' not found" \
      "install it, or reinstall with YOUK_HOST=none"
  else
    for _server in youk-core youk-code; do
      if youk_host_mcp_registered "$YOUK_HOST_ID" "$_server"; then
        pass "$_server: registered with $YOUK_HOST_ID"
      else
        fail "$_server: not registered with $YOUK_HOST_ID" \
          "bash $YOUK_DIR/scripts/install.sh"
      fi
    done
  fi
fi
echo ""

# ── Runtime directories ───────────────────────────────────────────────────────
echo "Runtime directories"

for dir in \
  "$YOUK_DIR/state" \
  "$YOUK_DIR/knowledge/proposals" \
  "$YOUK_DIR/knowledge/projects" \
  "$AUDIT_DIR"
do
  if [[ -d "$dir" ]]; then
    pass "exists: ${dir/$HOME/~}"
  else
    fail "missing: ${dir/$HOME/~}" \
      "mkdir -p $dir"
  fi
done
echo ""

# ── API key ───────────────────────────────────────────────────────────────────
echo "API key"

# Priority 1: env var (CI / explicit export)
# Priority 2: Claude Code's own key file (set when you sign in with 'claude'), which the
# container reads from the mounted host dir. Other hosts provide the key through the env var.
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  pass "ANTHROPIC_API_KEY: set in environment"
elif [[ -f "$HOST_DIR/.anthropic/api_key" ]] && [[ -s "$HOST_DIR/.anthropic/api_key" ]]; then
  pass "API key: found at $HOST_DIR/.anthropic/api_key (Claude Code signin — auto-mounted into container)"
else
  warn "API key: not found — optimize_intent and nfr_check will fall back to fast-path (no API call)" \
    "Export ANTHROPIC_API_KEY=sk-ant-... before running install.sh (or sign in with 'claude' on Claude Code)"
fi
echo ""

# ── Config files ──────────────────────────────────────────────────────────────
echo "Config files"

for f in \
  "$YOUK_DIR/config/guardrails.yaml" \
  "$YOUK_DIR/config/routes.yaml" \
  "$YOUK_DIR/config/variants.yaml"
do
  if [[ -f "$f" ]]; then
    pass "$(basename $f)"
  else
    fail "$(basename $f): missing" \
      "re-clone: git clone https://github.com/ajinkyabhanudas/youk $YOUK_DIR"
  fi
done
echo ""

# ── Skills ────────────────────────────────────────────────────────────────────
echo "Skills"

if [[ -d "$SKILLS_PATH" ]]; then
  SKILL_COUNT=$(ls "$SKILLS_PATH" 2>/dev/null | wc -l | tr -d ' ')
  MISSING_SKILL_MD=$(find "$SKILLS_PATH" -maxdepth 1 -mindepth 1 -type d \
    -exec test ! -f {}/SKILL.md \; -print 2>/dev/null | wc -l | tr -d ' ')
  pass "skills directory: $SKILL_COUNT skills found"
  if [[ "$MISSING_SKILL_MD" -gt 0 ]]; then
    warn "skills: $MISSING_SKILL_MD skill directories missing SKILL.md (run list_skills() to identify)"
  fi
else
  warn "$SKILLS_PATH not found (youk-code route_to_skill requires a skills directory)"
fi
echo ""

# ── MCP handshake ─────────────────────────────────────────────────────────────
echo "MCP handshake"

MCP_INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"doctor","version":"0"}}}'
MCP_DONE='{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
MCP_LIST='{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

_handshake_tool_count() {
  local image="$1"; shift
  local mount_opts=("$@")
  local count=0 attempt
  for attempt in 1 2 3; do
    count=$(printf '%s\n%s\n%s\n' "$MCP_INIT" "$MCP_DONE" "$MCP_LIST" | \
      docker run -i --rm "${mount_opts[@]}" "$image" 2>/dev/null | \
      python3 -c "
import sys, json
count = 0
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
        tools = msg.get('result', {}).get('tools', [])
        if tools:
            count = len(tools)
    except Exception:
        pass
print(count)
" 2>/dev/null || echo "0")
    [[ "${count:-0}" -gt 0 ]] && break
    sleep 1
  done
  echo "${count:-0}"
}

if docker image inspect youk-core:latest &>/dev/null 2>&1; then
  CORE_COUNT=$(_handshake_tool_count youk-core:latest \
    -v "$HOST_DIR:/host" -v "$YOUK_DIR:/youk")
  if [[ "${CORE_COUNT:-0}" -gt 0 ]]; then
    pass "youk-core: $CORE_COUNT tools"
  else
    fail "youk-core: did not return valid MCP response" \
      "make rebuild — then re-run: bash $YOUK_DIR/scripts/doctor.sh"
  fi

  CODE_COUNT=$(_handshake_tool_count youk-code:latest \
    -v "$HOST_DIR:/host:ro" -v "$YOUK_DIR:/youk:ro")
  if [[ "${CODE_COUNT:-0}" -gt 0 ]]; then
    pass "youk-code: $CODE_COUNT tools"
  else
    fail "youk-code: did not return valid MCP response" \
      "make rebuild — then re-run: bash $YOUK_DIR/scripts/doctor.sh"
  fi
else
  warn "handshake: skipped (images not built)"
fi
echo ""

# ── Context hooks plugin ──────────────────────────────────────────────────────
echo "Context hooks plugin"

PLUGIN_LINK="$HOME/.claude/plugins/youk-context"
PLUGIN_SRC="$YOUK_DIR/plugin"
if [ -L "$PLUGIN_LINK" ] && [ -d "$PLUGIN_LINK" ]; then
  pass "youk-context plugin linked ($PLUGIN_LINK)"
elif [ -d "$PLUGIN_LINK" ]; then
  warn "youk-context plugin dir exists but is not a symlink — hooks may be stale" \
    "Run: rm -rf $PLUGIN_LINK && ln -sf $PLUGIN_SRC $PLUGIN_LINK"
else
  fail "youk-context plugin not linked — hooks not active" \
    "Run: mkdir -p $HOME/.claude/plugins && ln -sf $PLUGIN_SRC $PLUGIN_LINK"
fi

HOOK_FILE="$PLUGIN_SRC/hooks/hooks.json"
if [ -f "$HOOK_FILE" ]; then
  pass "hooks/hooks.json present"
else
  fail "hooks/hooks.json missing at $HOOK_FILE" \
    "Re-run: bash $YOUK_DIR/scripts/install.sh"
fi

for script in pre_compact.py user_prompt_submit.py post_tool_use.py pre_tool_use.py youk_hook_utils.py; do
  SCRIPT_PATH="$PLUGIN_SRC/scripts/$script"
  if [ -f "$SCRIPT_PATH" ]; then
    pass "hook script: $script"
  else
    fail "hook script missing: $script" \
      "Re-run: bash $YOUK_DIR/scripts/install.sh"
  fi
done
echo ""

# ── Container health ──────────────────────────────────────────────────────────
echo "Container health"

YOUK_COUNT=$(docker ps --format "{{.Image}}" 2>/dev/null | grep -c "youk-" || true)
if [[ "${YOUK_COUNT:-0}" -le 2 ]]; then
  pass "youk containers: ${YOUK_COUNT:-0} running (normal — 2 per active Claude Code session)"
elif [[ "${YOUK_COUNT:-0}" -le 4 ]]; then
  warn "youk containers: ${YOUK_COUNT:-0} running — more than one session pair. Close unused Claude Code tabs or run: make prune-idle"
else
  fail "youk containers: ${YOUK_COUNT:-0} running — likely orphaned from closed sessions" \
    "cd $YOUK_DIR && make prune-idle"
fi
echo ""

# ── Revert readiness ──────────────────────────────────────────────────────────
echo "Revert readiness"

if [[ "$YOUK_HOST_ID" != "claude-code" ]]; then
  pass "pre-install snapshot: not used for $YOUK_HOST_ID (it covers Claude Code files only)"
elif [[ -f "$HOST_DIR/youk-restore/latest/manifest.json" ]]; then
  pass "pre-install snapshot: present (uninstall can restore pre-youk state)"
else
  warn "pre-install snapshot: missing — a pre-youk install predates snapshots. It will be created on next 'make update' (or 'make install')"
fi

INSTRUCTIONS_FILE="$(youk_host_instructions_file "$YOUK_HOST_ID")"
if [[ -n "$INSTRUCTIONS_FILE" && -f "$INSTRUCTIONS_FILE" ]] && grep -q "youk-core.session_start" "$INSTRUCTIONS_FILE" 2>/dev/null; then
  if grep -qF "<!-- BEGIN youk (managed) -->" "$INSTRUCTIONS_FILE" 2>/dev/null; then
    pass "$(basename "$INSTRUCTIONS_FILE") youk block: fenced (clean surgical removal available)"
  else
    warn "$(basename "$INSTRUCTIONS_FILE") youk block: unfenced (legacy) — run 'make update' to add fence markers"
  fi
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS+FAIL+WARN))
echo "────────────────────────────────────"
echo "  $PASS/$TOTAL passed  |  $FAIL failed  |  $WARN warnings"
echo ""

if [[ $FAIL -eq 0 ]]; then
  echo "  youk is healthy."
  echo ""
  echo "  Workflow note:"
  echo "  • servers/ code changes are live immediately (no rebuild needed)."
  echo "  • After changing requirements.txt or servers/shared/, run: make build"
  echo "  • After make build, restart your agent host to pick up new dependencies."
  exit 0
else
  echo "  $FAIL check(s) failed. Fix the items above, then re-run:"
  echo "  bash $YOUK_DIR/scripts/doctor.sh"
  exit 1
fi
