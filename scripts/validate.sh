#!/bin/bash
set -euo pipefail

YOUK_DIR="$HOME/.claude/youk"
CLAUDE_DIR="$HOME/.claude"

ERRORS=0

check() {
  local desc="$1"
  local condition="$2"
  if eval "$condition" > /dev/null 2>&1; then
    echo "  [OK] $desc"
  else
    echo "  [FAIL] $desc"
    ERRORS=$((ERRORS + 1))
  fi
}

echo "Validating youk installation..."

# Docker images
check "youk-core image exists" "docker image inspect youk-core:latest"
check "youk-code image exists" "docker image inspect youk-code:latest"

# Critical directories
check "skills directory accessible" "ls $CLAUDE_DIR/skills/dev-loop/SKILL.md"
check "youk state directory exists" "ls -d $YOUK_DIR/state"
check "knowledge directory exists" "ls -d $YOUK_DIR/knowledge"
check "config files present" "ls $YOUK_DIR/config/guardrails.yaml $YOUK_DIR/config/routes.yaml"

# MCP server responds
echo "  Testing youk-core MCP response..."
CORE_RESPONSE=$(echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | \
  docker run -i --rm \
    -v "$CLAUDE_DIR:/claude" \
    -v "$YOUK_DIR:/youk" \
    youk-core:latest 2>/dev/null || echo '{}')

if echo "$CORE_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); assert 'result' in r" 2>/dev/null; then
  echo "  [OK] youk-core responds to MCP"
else
  echo "  [FAIL] youk-core did not return valid MCP response"
  ERRORS=$((ERRORS + 1))
fi

echo "  Testing youk-code MCP response..."
CODE_RESPONSE=$(echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | \
  docker run -i --rm \
    -v "$CLAUDE_DIR:/claude:ro" \
    -v "$YOUK_DIR:/youk:ro" \
    youk-code:latest 2>/dev/null || echo '{}')

if echo "$CODE_RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); assert 'result' in r" 2>/dev/null; then
  echo "  [OK] youk-code responds to MCP"
else
  echo "  [FAIL] youk-code did not return valid MCP response"
  ERRORS=$((ERRORS + 1))
fi

echo ""
if [ $ERRORS -eq 0 ]; then
  echo "All checks passed. youk is ready."
else
  echo "$ERRORS check(s) failed. Run 'make rebuild' or check docs/getting-started.md."
  exit 1
fi
