#!/usr/bin/env bash
# youk health check — actionable diagnostics with Fix: lines for every failure
# Exit code: 0 = all pass, 1 = any failure
set -uo pipefail

YOUK_DIR="${YOUK_DIR:-$HOME/.claude/youk}"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

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
echo ""

# ── API key ───────────────────────────────────────────────────────────────────
echo "API key"

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  pass "ANTHROPIC_API_KEY: set in environment"
elif [[ -f "$CLAUDE_DIR/.anthropic/api_key" ]]; then
  pass "api_key: found at ~/.claude/.anthropic/api_key (Docker volume fallback)"
else
  fail "api_key: not found in environment or at ~/.claude/.anthropic/api_key" \
    "re-run install.sh with ANTHROPIC_API_KEY set: export ANTHROPIC_API_KEY=sk-ant-... && bash $YOUK_DIR/scripts/install.sh"
fi
echo ""

# ── MCP registration ──────────────────────────────────────────────────────────
echo "MCP servers"

if ! command -v claude &>/dev/null; then
  fail "claude: Claude Code not found" \
    "install from https://claude.ai/code"
else
  if claude mcp list 2>/dev/null | grep -q "youk-core"; then
    pass "youk-core: registered"
  else
    fail "youk-core: not registered with Claude Code" \
      "bash $YOUK_DIR/scripts/install.sh"
  fi

  if claude mcp list 2>/dev/null | grep -q "youk-code"; then
    pass "youk-code: registered"
  else
    fail "youk-code: not registered with Claude Code" \
      "bash $YOUK_DIR/scripts/install.sh"
  fi
fi
echo ""

# ── Runtime directories ───────────────────────────────────────────────────────
echo "Runtime directories"

for dir in \
  "$YOUK_DIR/state" \
  "$YOUK_DIR/knowledge/proposals" \
  "$YOUK_DIR/knowledge/projects" \
  "$CLAUDE_DIR/audit"
do
  if [[ -d "$dir" ]]; then
    pass "exists: ${dir/$HOME/~}"
  else
    fail "missing: ${dir/$HOME/~}" \
      "mkdir -p $dir"
  fi
done
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

if [[ -d "$CLAUDE_DIR/skills" ]]; then
  SKILL_COUNT=$(ls "$CLAUDE_DIR/skills" 2>/dev/null | wc -l | tr -d ' ')
  MISSING_SKILL_MD=$(find "$CLAUDE_DIR/skills" -maxdepth 1 -mindepth 1 -type d \
    -exec test ! -f {}/SKILL.md \; -print 2>/dev/null | wc -l | tr -d ' ')
  pass "skills directory: $SKILL_COUNT skills found"
  if [[ "$MISSING_SKILL_MD" -gt 0 ]]; then
    warn "skills: $MISSING_SKILL_MD skill directories missing SKILL.md (run list_skills() to identify)"
  fi
else
  warn "~/.claude/skills/ not found (optional — youk-code route_to_skill requires it)"
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
  printf '%s\n%s\n%s\n' "$MCP_INIT" "$MCP_DONE" "$MCP_LIST" | \
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
" 2>/dev/null || echo "0"
}

if docker image inspect youk-core:latest &>/dev/null 2>&1; then
  CORE_COUNT=$(_handshake_tool_count youk-core:latest \
    -v "$CLAUDE_DIR:/claude" -v "$YOUK_DIR:/youk")
  if [[ "${CORE_COUNT:-0}" -gt 0 ]]; then
    pass "youk-core: $CORE_COUNT tools"
  else
    fail "youk-core: did not return valid MCP response" \
      "make rebuild — then re-run: bash $YOUK_DIR/scripts/doctor.sh"
  fi

  CODE_COUNT=$(_handshake_tool_count youk-code:latest \
    -v "$CLAUDE_DIR:/claude:ro" -v "$YOUK_DIR:/youk:ro")
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

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS+FAIL+WARN))
echo "────────────────────────────────────"
echo "  $PASS/$TOTAL passed  |  $FAIL failed  |  $WARN warnings"
echo ""

if [[ $FAIL -eq 0 ]]; then
  echo "  youk is healthy."
  exit 0
else
  echo "  $FAIL check(s) failed. Fix the items above, then re-run:"
  echo "  bash $YOUK_DIR/scripts/doctor.sh"
  exit 1
fi
