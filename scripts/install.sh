#!/bin/bash
set -euo pipefail

YOUK_DIR="$HOME/.claude/youk"
CLAUDE_DIR="$HOME/.claude"

echo "Installing youk..."

# Scaffold runtime directories
mkdir -p "$YOUK_DIR/state"
mkdir -p "$CLAUDE_DIR/briefs"
mkdir -p "$YOUK_DIR/knowledge/clarifications"
mkdir -p "$YOUK_DIR/knowledge/proposals"
mkdir -p "$CLAUDE_DIR/hooks"

# Symlinks: skills and domain knowledge
if [ ! -L "$YOUK_DIR/skills" ]; then
  ln -sf "$CLAUDE_DIR/skills" "$YOUK_DIR/skills"
  echo "  Linked skills → $CLAUDE_DIR/skills"
fi

if [ ! -L "$YOUK_DIR/knowledge/domain" ]; then
  ln -sf "$CLAUDE_DIR/skills/learn/knowledge" "$YOUK_DIR/knowledge/domain"
  echo "  Linked knowledge/domain → $CLAUDE_DIR/skills/learn/knowledge"
fi

# Build Docker images from repo root
echo "Building Docker images (this takes 1-2 minutes on first run)..."
cd "$YOUK_DIR"
make build

# Validate
bash scripts/validate.sh

echo ""
echo "youk installed successfully."
echo "Next steps:"
echo "  1. Add MCP servers to ~/.claude/settings.json (see docs/getting-started.md)"
echo "  2. Open a new Claude Code session"
echo "  3. Run: /mcp to verify youk-core and youk-code appear"
