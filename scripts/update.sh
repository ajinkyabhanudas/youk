#!/bin/bash
set -euo pipefail

YOUK_DIR="$HOME/.claude/youk"

echo "Updating youk..."
cd "$YOUK_DIR"

git pull --rebase
make rebuild
bash scripts/validate.sh

echo "youk updated."
