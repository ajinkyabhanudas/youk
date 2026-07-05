#!/usr/bin/env bash
# youk installer — single command, idempotent, run from repo root or via curl
# Usage: bash scripts/install.sh
set -euo pipefail

YOUK_DIR="$HOME/.claude/youk"
CLAUDE_DIR="$HOME/.claude"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
warn() { echo -e "  ${YELLOW}!${NC}  $1"; }
fail() { echo -e "  ${RED}✗${NC}  $1"; }
step() { echo -e "\n${GREEN}▶${NC} $1"; }

# ── Step 0: Preflight ────────────────────────────────────────────────────────
step "Preflight checks"

if ! command -v docker &>/dev/null; then
  fail "Docker not found. Install Docker Desktop from https://docker.com and re-run."
  exit 1
fi
if ! docker info &>/dev/null 2>&1; then
  fail "Docker is not running. Start Docker Desktop and re-run."
  exit 1
fi
ok "Docker running"

if ! command -v claude &>/dev/null; then
  fail "Claude Code not found. Install from https://claude.ai/code and re-run."
  exit 1
fi
ok "Claude Code found ($(claude --version 2>/dev/null | head -1))"

_api_key_file="$CLAUDE_DIR/.anthropic/api_key"
# Auto-load from .env in repo root if present and key not already set
_env_file="$REPO_DIR/.env"
if [[ -z "${ANTHROPIC_API_KEY:-}" && -s "$_env_file" ]]; then
  # shellcheck source=/dev/null
  set -a; source "$_env_file"; set +a
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] && ok "ANTHROPIC_API_KEY loaded from .env"
fi

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  ok "ANTHROPIC_API_KEY found"
  mkdir -p "$CLAUDE_DIR/.anthropic"
  printf '%s' "$ANTHROPIC_API_KEY" > "$_api_key_file"
  chmod 600 "$_api_key_file"
  ok "API key persisted to ~/.claude/.anthropic/api_key"
elif [[ -s "$_api_key_file" ]]; then
  ok "API key already saved at ~/.claude/.anthropic/api_key — reusing"
  ANTHROPIC_API_KEY="$(cat "$_api_key_file")"
else
  # Interactive prompt — no pre-exported key needed
  echo "  youk uses this key for quality checks (nfr_check) and skill execution."
  echo "  Without it, basic session tracking still works — you can add it later by re-running this script."
  echo -n "  Enter your ANTHROPIC_API_KEY (sk-ant-..., blank to skip): "
  read -rs ANTHROPIC_API_KEY
  echo ""
  if [[ -n "$ANTHROPIC_API_KEY" ]]; then
    mkdir -p "$CLAUDE_DIR/.anthropic"
    printf '%s' "$ANTHROPIC_API_KEY" > "$_api_key_file"
    chmod 600 "$_api_key_file"
    ok "API key saved to ~/.claude/.anthropic/api_key"
  else
    warn "No API key — nfr_check and skill execution unavailable until you re-run with the key set."
  fi
fi

# ── Step 1: Clone or pull ────────────────────────────────────────────────────
step "Repository"

if [[ -d "$YOUK_DIR/.git" ]]; then
  ok "youk already cloned at $YOUK_DIR"
  if [[ "$REPO_DIR" != "$YOUK_DIR" ]]; then
    warn "Running from $REPO_DIR, not $YOUK_DIR — skipping pull"
  else
    git -C "$YOUK_DIR" pull --ff-only --quiet && ok "Pulled latest" || warn "Already up to date"
  fi
else
  git clone https://github.com/ajinkyabhanudas/youk "$YOUK_DIR" --quiet
  ok "Cloned to $YOUK_DIR"
fi

# ── Step 2: Runtime directories ──────────────────────────────────────────────
step "Runtime directories"

mkdir -p \
  "$YOUK_DIR/state" \
  "$YOUK_DIR/knowledge/interpretation" \
  "$YOUK_DIR/knowledge/clarifications" \
  "$YOUK_DIR/knowledge/proposals" \
  "$YOUK_DIR/knowledge/projects" \
  "$CLAUDE_DIR/audit"
ok "Directories ready"

# Write host→container path map so the Docker containers can translate paths passed
# by Claude Code (which uses host-absolute paths) to their mounted equivalents.
# The containers mount YOUK_DIR → /youk and CLAUDE_DIR → /claude.
cat > "$YOUK_DIR/state/path-map.env" <<EOF
# Host→container path mappings — written by install.sh, read by session.py
YOUK_HOST_DIR=$YOUK_DIR
CLAUDE_HOST_DIR=$CLAUDE_DIR
EOF
ok "path-map.env written to state/"

# ── Step 3: Symlinks ─────────────────────────────────────────────────────────
step "Symlinks"

# Skills are owned by the youk repo (skills/ directory). ~/.claude/skills is a
# relative symlink into the repo so Docker can follow it inside the container.
# Relative symlink (not absolute) required for Docker bind-mount compatibility.
SKILLS_LINK="$CLAUDE_DIR/skills"
SKILLS_REPO="$YOUK_DIR/skills"

if [[ -L "$SKILLS_LINK" ]] && [[ "$(readlink "$SKILLS_LINK")" == "youk/skills" ]]; then
  ok "skills symlink already in place (→ youk/skills)"
elif [[ ! -e "$SKILLS_LINK" ]]; then
  # Create relative symlink from ~/.claude/skills → youk/skills
  ln -sf "youk/skills" "$SKILLS_LINK"
  ok "Linked ~/.claude/skills → youk/skills"
elif [[ -d "$SKILLS_LINK" ]] && [[ ! -L "$SKILLS_LINK" ]]; then
  # Real directory exists from old setup — warn, don't overwrite
  warn "~/.claude/skills is a real directory, not a symlink."
  warn "To migrate: mv $SKILLS_LINK $SKILLS_LINK.bak && ln -sf youk/skills $SKILLS_LINK"
else
  ok "skills symlink exists (may point elsewhere — check readlink ~/.claude/skills)"
fi

if [[ -d "$SKILLS_REPO/learn/knowledge" ]]; then
  if [[ ! -L "$YOUK_DIR/knowledge/domain" ]]; then
    ln -sf "$SKILLS_REPO/learn/knowledge" "$YOUK_DIR/knowledge/domain"
    ok "Linked knowledge/domain → youk/skills/learn/knowledge"
  else
    ok "knowledge/domain symlink already in place"
  fi
fi

# ── Step 4: Build Docker images ──────────────────────────────────────────────
step "Docker images"

echo "  Building youk-core and youk-code (first run: ~2 min, cached afterwards)..."
make -C "$YOUK_DIR" build 2>&1 | grep -E "(Step|Successfully|error)" | sed 's/^/    /' || {
  fail "Docker build failed. Run 'make build' manually to see full output."
  exit 1
}
ok "Images built (youk-core:latest, youk-code:latest)"

# ── Step 5: Register MCP servers ─────────────────────────────────────────────
step "MCP server registration"

# Remove stale registrations first (idempotent — no-op if not registered)
claude mcp remove youk-core 2>/dev/null || true
claude mcp remove youk-code 2>/dev/null || true

claude mcp add --scope user youk-core --transport stdio -- \
  docker run -i --rm \
    -v "$CLAUDE_DIR:/claude" \
    -v "$YOUK_DIR:/youk" \
    -v "$YOUK_DIR/servers/shared:/shared" \
    -v "$HOME:/host-home:ro" \
    -e ANTHROPIC_API_KEY \
    youk-core:latest
ok "youk-core registered"

claude mcp add --scope user youk-code --transport stdio -- \
  docker run -i --rm \
    -v "$CLAUDE_DIR:/claude:ro" \
    -v "$YOUK_DIR:/youk:ro" \
    -v "$YOUK_DIR/servers/shared:/shared" \
    -v "$HOME:/host-home:ro" \
    -e ANTHROPIC_API_KEY \
    youk-code:latest
ok "youk-code registered"

# ── Step 6: Patch CLAUDE.md ──────────────────────────────────────────────────
step "CLAUDE.md"

CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
TEMPLATE="$YOUK_DIR/docs/claude-md-template.md"

if [[ ! -f "$CLAUDE_MD" ]]; then
  touch "$CLAUDE_MD"
fi

if grep -q "youk-core.session_start" "$CLAUDE_MD" 2>/dev/null; then
  ok "CLAUDE.md already contains youk block — skipping"
else
  printf "\n\n%s\n" "$(cat "$TEMPLATE")" >> "$CLAUDE_MD"
  ok "youk block appended to $CLAUDE_MD"
fi

# ── Step 7: Seed audit log ───────────────────────────────────────────────────
step "Audit log"

MONTH=$(date +%Y-%m)
AUDIT_FILE="$CLAUDE_DIR/audit/$MONTH.md"
if [[ ! -f "$AUDIT_FILE" ]]; then
  touch "$AUDIT_FILE"
fi

if ! grep -q "youk install complete" "$AUDIT_FILE" 2>/dev/null; then
  {
    echo ""
    echo "### Session — $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo "youk install complete. Baseline session."
    echo "Skills: install"
    echo "CloseCluster: yes"
    echo "Commits: no"
  } >> "$AUDIT_FILE"
  ok "Audit log seeded"
else
  ok "Audit log already seeded"
fi

# ── Step 8: Project research scheduler ──────────────────────────────────────
step "Project research scheduler"

PYTHON_BIN="$(command -v python3 || command -v python)"
if [[ -z "$PYTHON_BIN" ]]; then
  warn "python3 not found — skipping project research scheduler"
elif [[ "$(uname)" == "Darwin" ]]; then
  PLIST_SRC="$YOUK_DIR/scripts/com.youk.project-research.plist"
  PLIST_DST="$HOME/Library/LaunchAgents/com.youk.project-research.plist"
  API_KEY_VALUE="${ANTHROPIC_API_KEY:-$(cat "$CLAUDE_DIR/.anthropic/api_key" 2>/dev/null || echo "")}"

  # Render plist with actual paths
  sed \
    -e "s|PYTHON_PATH|$PYTHON_BIN|g" \
    -e "s|YOUK_DIR|$YOUK_DIR|g" \
    -e "s|ANTHROPIC_API_KEY_VALUE|$API_KEY_VALUE|g" \
    "$PLIST_SRC" > "$PLIST_DST"

  # Unload stale job if present, load the new one
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST" 2>/dev/null && ok "Project research scheduled (every Wednesday 09:00)" \
    || warn "launchctl load failed — check $PLIST_DST"
elif command -v crontab &>/dev/null; then
  CRON_LINE="0 9 * * 3 $PYTHON_BIN $YOUK_DIR/scripts/project-research.py >> $YOUK_DIR/state/project-research.log 2>&1"
  # Idempotent: remove old entry then add new
  ( crontab -l 2>/dev/null | grep -v "project-research.py"; echo "$CRON_LINE" ) | crontab -
  ok "Project research scheduled via cron (every Wednesday 09:00)"
else
  warn "No scheduler available — run manually: python3 $YOUK_DIR/scripts/project-research.py"
fi

# ── Step 9: Validate ─────────────────────────────────────────────────────────
step "Validation"
bash "$YOUK_DIR/scripts/doctor.sh"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}youk is ready.${NC}"
echo ""
echo "  Open a new Claude Code session — youk starts automatically."
echo ""
echo "  Note: youk stores knowledge on this machine only (~/.claude/youk/)."
echo "  Teammates using youk on the same project have separate histories."
echo "  To share context, copy ~/.claude/youk/knowledge/projects/<slug>/ to their machine."
echo ""
echo "  Tip: pair with headroom for 60-95% token cost reduction"
echo "       brew install headroom && headroom wrap claude"
echo ""
