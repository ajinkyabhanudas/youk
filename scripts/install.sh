#!/usr/bin/env bash
# youk installer — single command, idempotent
# macOS/Linux:  bash scripts/install.sh
# Windows:      bash scripts/install.sh  (Git Bash or WSL2)
#               .\scripts\install.ps1    (PowerShell — see scripts/install.ps1)
set -euo pipefail

# Where youk is installed. YOUK_HOME overrides. An existing ~/.claude/youk keeps being used.
# Otherwise: ~/.claude/youk when Claude Code is the host (skills are linked relative to the
# Claude dir), and a host-neutral ~/.youk for any other host.
if [ -n "${YOUK_HOME:-}" ]; then
  YOUK_DIR="$YOUK_HOME"
elif [ -d "$HOME/.claude/youk" ]; then
  YOUK_DIR="$HOME/.claude/youk"
elif [ "${YOUK_HOST:-auto}" = "claude-code" ] || { [ "${YOUK_HOST:-auto}" = "auto" ] && command -v claude >/dev/null 2>&1; }; then
  YOUK_DIR="$HOME/.claude/youk"
else
  YOUK_DIR="$HOME/.youk"
fi
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
# Version to install. Empty means the default branch. Set to any tag or branch to pin:
#   YOUK_REF=v1.2.1 bash scripts/install.sh
# Only ever passed as a `git clone --branch` value, never into a URL.
YOUK_REF="${YOUK_REF:-}"
# Piped installs (`curl -sL .../install.sh | bash`) have no BASH_SOURCE, and reading it
# under `set -u` aborts with "unbound variable". Default it, and leave SCRIPT_DIR empty
# when there is no file on disk to resolve — an empty value is honest, where the old
# expression silently resolved to the caller's working directory.
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_DIR="$(dirname "$SCRIPT_DIR")"
else
  SCRIPT_DIR=""
  REPO_DIR=""
fi

# ── Platform detection ────────────────────────────────────────────────────────
OS="$(uname -s)"
IS_WINDOWS=false
if [[ "$OS" == MINGW* ]] || [[ "$OS" == MSYS* ]] || [[ "$OS" == CYGWIN* ]]; then
  IS_WINDOWS=true
fi
# WSL also appears as Linux but WSLENV or /proc/version hints are present
if [[ "$OS" == "Linux" ]] && grep -qi "microsoft\|wsl" /proc/version 2>/dev/null; then
  IS_WINDOWS=true
fi

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
warn() { echo -e "  ${YELLOW}!${NC}  $1"; }
fail() { echo -e "  ${RED}✗${NC}  $1"; }
step() { echo -e "\n${GREEN}▶${NC} $1"; }

# ── Step 0: Preflight ────────────────────────────────────────────────────────
step "Preflight checks"

if $IS_WINDOWS; then
  ok "Platform: Windows (Git Bash / WSL2)"
  # On Windows, Docker Desktop must have WSL2 backend enabled.
  # Git Bash users: Docker Desktop for Windows handles the bridge automatically.
else
  ok "Platform: $(uname -s)"
fi

if ! command -v docker &>/dev/null; then
  fail "Docker not found."
  if $IS_WINDOWS; then
    echo "  Install Docker Desktop for Windows: https://docs.docker.com/desktop/install/windows-install/"
    echo "  Enable 'Use WSL 2 based engine' in Docker Desktop → Settings → General."
  else
    echo "  Install Docker Desktop: https://docker.com"
  fi
  exit 1
fi
if ! docker info &>/dev/null 2>&1; then
  fail "Docker is not running. Start Docker Desktop and re-run."
  exit 1
fi
ok "Docker running"

# The agent host (Claude Code, Codex, or none) is chosen after the clone, in "Agent host" below.

# ── Step 1: Clone or pull ────────────────────────────────────────────────────
step "Repository"

if [[ -d "$YOUK_DIR/.git" ]]; then
  ok "youk already cloned at $YOUK_DIR"
  # A pinned install sits on a detached HEAD. Pulling there fails, and reporting that
  # failure as "Already up to date" told the operator the opposite of what happened.
  # Report the pin instead, and leave it alone — an install pinned to a tag should not
  # be moved off it by re-running the installer.
  if git -C "$YOUK_DIR" symbolic-ref -q HEAD >/dev/null; then
    # An empty REPO_DIR means a piped install with no local checkout, so there is no
    # other repo to be running from and the pull below is the right thing to do.
    if [[ -n "$REPO_DIR" && "$REPO_DIR" != "$YOUK_DIR" ]]; then
      warn "Running from $REPO_DIR, not $YOUK_DIR — skipping pull"
    elif git -C "$YOUK_DIR" pull --ff-only --quiet; then
      ok "Pulled latest"
    else
      warn "Could not fast-forward — resolve by hand in $YOUK_DIR"
    fi
  else
    ok "Pinned to $(git -C "$YOUK_DIR" describe --tags --always) — leaving it there"
    if [[ -n "$YOUK_REF" ]]; then
      warn "YOUK_REF=$YOUK_REF ignored: $YOUK_DIR already exists. To switch version:"
      warn "  git -C $YOUK_DIR fetch --tags && git -C $YOUK_DIR checkout $YOUK_REF"
    fi
  fi
else
  if [[ -n "$YOUK_REF" ]]; then
    # No fallback to the default branch on a bad ref. Installing a version other than
    # the one asked for is worse than not installing.
    # advice.detachedHead off: pinning is the intent here, so git's paragraph about
    # detached HEAD is noise in an install transcript, not a warning worth printing.
    if ! git -c advice.detachedHead=false clone --branch "$YOUK_REF" \
         https://github.com/ajinkyabhanudas/youk "$YOUK_DIR" --quiet; then
      fail "No such tag or branch: $YOUK_REF"
      fail "Available versions: https://github.com/ajinkyabhanudas/youk/releases"
      exit 1
    fi
    ok "Cloned to $YOUK_DIR at $YOUK_REF"
  else
    git clone https://github.com/ajinkyabhanudas/youk "$YOUK_DIR" --quiet
    ok "Cloned to $YOUK_DIR (latest on the default branch)"
  fi
fi

CODEX_HOME_DISPLAY="${CODEX_HOME:-~/.codex}"
# ── Step 1b: Agent host ──────────────────────────────────────────────────────
step "Agent host"
HOSTS_LIB="$YOUK_DIR/scripts/lib/hosts.sh"
if [[ ! -f "$HOSTS_LIB" ]]; then
  fail "Missing $HOSTS_LIB — the clone at $YOUK_DIR looks incomplete."
  exit 1
fi
# shellcheck source=lib/hosts.sh
. "$HOSTS_LIB"
YOUK_HOST_ID="$(youk_detect_host)" || exit 1
HOST_DIR="$(youk_host_dir "$YOUK_HOST_ID")"
case "$YOUK_HOST_ID" in
  claude-code)
    if ! command -v claude &>/dev/null; then
      # Only reachable with YOUK_HOST=claude-code: auto-detection needs the CLI to choose it.
      if command -v npm &>/dev/null; then
        warn "Claude Code not found — installing via npm..."
        npm install -g @anthropic-ai/claude-code
        ok "Claude Code installed"
      else
        fail "Claude Code not found and npm unavailable."
        echo "  Install Node.js from https://nodejs.org then run: npm install -g @anthropic-ai/claude-code"
        exit 1
      fi
    fi
    ok "Agent host: Claude Code ($(claude --version 2>/dev/null | head -1))"
    case "$YOUK_DIR" in
      "$HOST_DIR"/*) ;;
      *) fail "With Claude Code, YOUK_HOME must be inside $HOST_DIR (skills are linked relative to it). Got: $YOUK_DIR"; exit 1 ;;
    esac
    ;;
  codex)
    command -v codex &>/dev/null || { fail "YOUK_HOST=codex but the codex CLI was not found on PATH."; exit 1; }
    ok "Agent host: Codex ($(codex --version 2>/dev/null | head -1))"
    ;;
  none)
    warn "No agent host CLI found (looked for claude and codex): installing youk's servers only."
    echo "  Set YOUK_HOST=claude-code or YOUK_HOST=codex to target one, or add the MCP URLs to your host yourself."
    ;;
esac

# What the containers mount at /host. A host with no config dir gets an empty directory, so the
# mount and the paths inside the containers look the same for every install.
if [[ -z "$HOST_DIR" ]]; then
  HOST_MOUNT="$YOUK_DIR/.host"
else
  HOST_MOUNT="$HOST_DIR"
fi
mkdir -p "$HOST_MOUNT"
# Where youk's audit logs live. Claude Code installs keep them in its config dir, as before.
if [[ "$YOUK_HOST_ID" == "claude-code" ]]; then AUDIT_DIR="$HOST_DIR/audit"; SKILLS_LINKED=1; else AUDIT_DIR="$YOUK_DIR/audit"; SKILLS_LINKED=0; fi

# ── Step 2: Runtime directories ──────────────────────────────────────────────
step "Runtime directories"

mkdir -p \
  "$YOUK_DIR/state" \
  "$YOUK_DIR/knowledge/interpretation" \
  "$YOUK_DIR/knowledge/clarifications" \
  "$YOUK_DIR/knowledge/proposals" \
  "$YOUK_DIR/knowledge/projects" \
  "$AUDIT_DIR"
ok "Directories ready"

# Inference credential. The containers get no host environment, so a key has to live where they can
# read it: state/inference-keys/ (gitignored, mode 0600, mounted as /youk/state). Seed it from
# ANTHROPIC_API_KEY only when nothing is configured yet, so a re-install never overwrites a key
# the user set with scripts/configure_inference.py. Without a key, optimize_intent stays heuristic.
if [[ -n "${ANTHROPIC_API_KEY:-}" ]] && [[ ! -s "$YOUK_DIR/state/inference-keys/anthropic.key" ]] \
   && [[ ! -f "$YOUK_DIR/state/inference-provider.json" ]]; then
  if printf '%s' "$ANTHROPIC_API_KEY" | python3 "$YOUK_DIR/scripts/configure_inference.py" \
       --provider anthropic --key-stdin >/dev/null; then
    ok "Inference key saved to state/inference-keys/ (anthropic)"
  else
    warn "Could not save the inference key — run scripts/configure_inference.py yourself"
  fi
fi

# Write host→container path map so the Docker containers can translate paths passed
# by the agent host (which uses host-absolute paths) to their mounted equivalents.
# The containers mount YOUK_DIR → /youk and the host config dir → /host.
cat > "$YOUK_DIR/state/path-map.env" <<EOF
# Host→container path mappings — written by install.sh, read by state_paths.py and youk_paths.py
YOUK_AGENT_HOST=$YOUK_HOST_ID
YOUK_HOST_DIR=$YOUK_DIR
HOST_CONFIG_DIR=$HOST_MOUNT
HOST_SKILLS_LINKED=$SKILLS_LINKED
EOF
ok "path-map.env written to state/"

# ── Step 2b: Pre-install snapshot ────────────────────────────────────────────
# Capture the pre-youk state of everything below BEFORE the first host mutation,
# so scripts/uninstall.sh can restore it exactly. Idempotent — a good snapshot is
# never overwritten. See scripts/lib/snapshot.sh.
step "Pre-install snapshot"
# Source from the clone, not from SCRIPT_DIR. A piped install has no script on disk, so
# SCRIPT_DIR resolved to whatever directory the user happened to be in, and this line
# aborted the install for anyone following the README's curl command. Step 1 guarantees
# the repo is at $YOUK_DIR, which makes it the only reliable place to read this from.
if [[ "$YOUK_HOST_ID" == "claude-code" ]]; then
SNAPSHOT_LIB="$YOUK_DIR/scripts/lib/snapshot.sh"
if [[ ! -f "$SNAPSHOT_LIB" ]]; then
  fail "Missing $SNAPSHOT_LIB — the clone at $YOUK_DIR looks incomplete."
  fail "Remove $YOUK_DIR and re-run the installer."
  exit 1
fi
# shellcheck source=lib/snapshot.sh
. "$SNAPSHOT_LIB"
youk_take_snapshot
else
  ok "Skipped: the pre-install snapshot covers Claude Code files only"
fi

# ── Step 3: Symlinks ─────────────────────────────────────────────────────────
step "Symlinks"

# Skills use per-skill symlinks, not a whole-directory symlink.
# This lets youk co-exist with skills from other tools — nothing gets clobbered.
SKILLS_DIR="$CLAUDE_DIR/skills"
SKILLS_REPO="$YOUK_DIR/skills"

if [[ "$YOUK_HOST_ID" != "claude-code" ]]; then
  ok "Skipped skill links: youk serves its skills over MCP (list_skills, route_to_skill) for $YOUK_HOST_ID"
else

# Migrate legacy whole-directory symlink (→ youk/skills) to per-skill symlinks.
# The old form prevented other tools from adding skills alongside youk's.
if [[ -L "$SKILLS_DIR" ]] && [[ "$(readlink "$SKILLS_DIR")" == "youk/skills" ]]; then
  rm "$SKILLS_DIR"
  mkdir -p "$SKILLS_DIR"
  ok "Migrated: whole-directory symlink → per-skill symlinks"
fi

mkdir -p "$SKILLS_DIR"

_conflicts=()
_installed=0

# Link each skill directory
# Use relative symlinks so they resolve correctly both on the host and inside
# Docker containers (where ~/.claude → /claude, ~/.claude/youk → /youk).
# Absolute symlinks point to host paths that don't exist in the container.
for entry in "$SKILLS_REPO"/*/; do
  [[ -d "$entry" ]] || continue
  name="$(basename "$entry")"
  dst="$SKILLS_DIR/$name"
  rel_target="../youk/skills/$name"
  if [[ -L "$dst" ]]; then
    rm "$dst" && ln -s "$rel_target" "$dst"   # Remove + recreate: ln -sf on dir symlinks creates inside target on macOS
    (( _installed++ )) || true
  elif [[ -e "$dst" ]]; then
    _conflicts+=("$name")    # Real directory — collision, skip
  else
    ln -s "$rel_target" "$dst"
    (( _installed++ )) || true
  fi
done

# Link top-level files (SKILL-REGISTRY.md, FOUNDER-GUIDE.md, etc.)
for f in "$SKILLS_REPO"/*.md "$SKILLS_REPO"/*.yaml; do
  [[ -f "$f" ]] || continue
  name="$(basename "$f")"
  dst="$SKILLS_DIR/$name"
  rel_target="../youk/skills/$name"
  if [[ -L "$dst" ]]; then
    ln -sf "$rel_target" "$dst"
  elif [[ ! -e "$dst" ]]; then
    ln -s "$rel_target" "$dst"
  fi
done

if [[ ${#_conflicts[@]} -gt 0 ]]; then
  warn "Skill name conflicts — youk's version NOT installed for: ${_conflicts[*]}"
  warn "Your existing skills are untouched. To use youk's version instead:"
  for c in "${_conflicts[@]}"; do
    warn "  mv $SKILLS_DIR/$c $SKILLS_DIR/$c.bak"
  done
  warn "Then re-run install.sh."
else
  ok "$_installed skills linked → $SKILLS_REPO"
fi
fi  # claude-code skill links

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
make -C "$YOUK_DIR" build 2>&1 | grep -E "(Step|Successfully|error|DONE|naming)" | sed 's/^/    /'; [[ ${PIPESTATUS[0]} -eq 0 ]] || {
  fail "Docker build failed. Run 'make build' manually to see full output."
  exit 1
}
ok "Images built (youk-core:latest, youk-code:latest)"

# ── Step 5: Start persistent HTTP servers ────────────────────────────────────
step "Persistent youk-core and youk-code servers"

# Port conflict check — fail early before launchd tries to bind
for PORT in 8001 8002; do
  if lsof -i:$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    SERVER=$([ "$PORT" -eq 8001 ] && echo "core" || echo "code")
    warn "Port $PORT in use — stopping existing youk-${SERVER}-server if present"
    docker stop "youk-${SERVER}-server" 2>/dev/null || true
    sleep 2
    if lsof -i:$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
      fail "Port $PORT still in use after stop attempt — cannot continue"
    fi
  fi
done

# Unload any existing launchd agents and remove named containers from prior installs
for SERVER in core code; do
  PLIST="$HOME/Library/LaunchAgents/com.youk.${SERVER}-server.plist"
  launchctl unload "$PLIST" 2>/dev/null || true
  docker stop "youk-${SERVER}-server" 2>/dev/null || true
  docker rm "youk-${SERVER}-server" 2>/dev/null || true
done

# Generate plists from templates (substitute real paths) and load them
# Not an associative array: /usr/bin/env bash resolves to macOS's stock /bin/bash
# (3.2, frozen pre-GPLv3), which mishandles bareword keys in `declare -A` literals
# under `set -u` — "core: unbound variable". A case statement is 3.2-safe.
for SERVER in core code; do
  case "$SERVER" in
    core) PORT=8001 ;;
    code) PORT=8002 ;;
  esac
  sed \
    -e "s|{{HOST_DIR}}|$HOST_MOUNT|g" \
    -e "s|{{YOUK_DIR}}|$YOUK_DIR|g" \
    -e "s|{{HOST_HOME}}|$HOME|g" \
    -e "s|{{PORT}}|$PORT|g" \
    -e "s|{{SERVER}}|$SERVER|g" \
    "$YOUK_DIR/scripts/com.youk.${SERVER}-server.plist.tmpl" \
    > "$HOME/Library/LaunchAgents/com.youk.${SERVER}-server.plist"
  launchctl load "$HOME/Library/LaunchAgents/com.youk.${SERVER}-server.plist"
done
ok "launchd agents loaded (core :8001, code :8002)"

# Wait for servers to be reachable (max 30s — Docker cold-start)
echo -n "  Waiting for servers to respond"
for i in $(seq 1 30); do
  # `|| true` matters here: under `set -e`, a plain VAR=$(cmd) assignment is NOT
  # exempted — a cold-start connection-refused (curl exit 7) on the first attempt
  # would otherwise kill the whole installer before the retry loop gets to retry.
  CORE_STATUS=$(curl -o /dev/null -w "%{http_code}" -s http://127.0.0.1:8001/mcp 2>/dev/null || true)
  CODE_STATUS=$(curl -o /dev/null -w "%{http_code}" -s http://127.0.0.1:8002/mcp 2>/dev/null || true)
  # 406 = server up but needs MCP headers (correct); 200 = also fine
  if [[ "$CORE_STATUS" =~ ^(200|406)$ ]] && [[ "$CODE_STATUS" =~ ^(200|406)$ ]]; then
    echo " done"
    break
  fi
  echo -n "."
  sleep 1
  if [ "$i" -eq 30 ]; then
    echo
    fail "Servers did not respond within 30s — check /tmp/youk-core.log and /tmp/youk-code.log"
  fi
done

# Register with the selected host (or print the URLs when there is none).
youk_register_servers "$YOUK_HOST_ID"

# ── Step 5b: Register youk context hooks plugin ──────────────────────────────
step "Context hooks plugin"

if [[ "$YOUK_HOST_ID" != "claude-code" ]]; then
  ok "Skipped: the hooks plugin is Claude Code's. Codex hooks are set up in $CODEX_HOME_DISPLAY/hooks.json or config.toml (docs/getting-started.md, \"Agent-host selection\"); this installer does not edit them."
else

PLUGIN_DIR="$YOUK_DIR/plugin"
LEGACY_LINK="$CLAUDE_DIR/plugins/youk-context"

# Older installs symlinked plugin/ into ~/.claude/plugins. Current Claude Code does not discover
# plugins that way (it found 0 plugins and 0 hooks), so that link did nothing. Remove it.
if [ -L "$LEGACY_LINK" ]; then
  rm -f "$LEGACY_LINK"
fi

# Register the hooks in settings.json with absolute paths. The scripts import from servers/shared
# relative to their own location, so they must run in place. Idempotent, and it backs up first.
if python3 "$YOUK_DIR/scripts/install_hooks.py" --plugin-dir "$PLUGIN_DIR" --settings "$CLAUDE_DIR/settings.json"; then
  ok "youk hooks registered in $CLAUDE_DIR/settings.json"
else
  fail "could not register the youk hooks, so they will not run"
  warn "Manual fix: python3 $YOUK_DIR/scripts/install_hooks.py --plugin-dir $PLUGIN_DIR"
fi
fi  # claude-code hooks plugin

# ── Step 6: Patch the host's instructions file ───────────────────────────────
step "Instructions file"

INSTRUCTIONS_FILE="$(youk_host_instructions_file "$YOUK_HOST_ID")"
if [[ -z "$INSTRUCTIONS_FILE" ]]; then
  ok "Skipped: no host selected, so there is no instructions file to patch (docs/youk-lite.md covers the file-only variant)"
else
  youk_patch_instructions "$INSTRUCTIONS_FILE" "$YOUK_DIR/docs/claude-md-template.md"
fi

# ── Step 7: Seed audit log ───────────────────────────────────────────────────
step "Audit log"

MONTH=$(date +%Y-%m)
AUDIT_FILE="$AUDIT_DIR/$MONTH.md"
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
  # Render plist with actual paths (project-research.py resolves its own API key at runtime)
  sed \
    -e "s|PYTHON_PATH|$PYTHON_BIN|g" \
    -e "s|YOUK_DIR|$YOUK_DIR|g" \
    -e "s|ANTHROPIC_API_KEY_VALUE||g" \
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

# ── Step 8b: Container cleanup scheduler ─────────────────────────────────────
step "Container cleanup scheduler"

if [[ "$(uname)" == "Darwin" ]]; then
  PLIST_SRC="$YOUK_DIR/scripts/com.youk.cleanup.plist"
  PLIST_DST="$HOME/Library/LaunchAgents/com.youk.cleanup.plist"
  sed -e "s|YOUK_DIR|$YOUK_DIR|g" "$PLIST_SRC" > "$PLIST_DST"
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST" 2>/dev/null \
    && ok "Container cleanup scheduled (every Sunday 02:00)" \
    || warn "launchctl load failed — check $PLIST_DST"
elif command -v crontab &>/dev/null; then
  CRON_LINE="0 2 * * 0 YOUK_DIR=$YOUK_DIR /bin/bash $YOUK_DIR/scripts/cleanup.sh"
  ( crontab -l 2>/dev/null | grep -v "youk.*cleanup.sh"; echo "$CRON_LINE" ) | crontab -
  ok "Container cleanup scheduled via cron (every Sunday 02:00)"
else
  warn "No scheduler available — stale containers cleaned on each 'make build'. Run 'bash $YOUK_DIR/scripts/cleanup.sh' for a manual sweep."
fi

# ── Step 8c: Git hooks ────────────────────────────────────────────────────────
step "Git hooks"

PYTHON_BIN="$(command -v python3 || command -v python)"
if [[ -z "$PYTHON_BIN" ]]; then
  warn "python3 not found — skipping git hook generation"
elif [[ ! -d "$YOUK_DIR/.git" ]]; then
  warn "No .git directory found — skipping git hook generation"
else
  "$PYTHON_BIN" "$YOUK_DIR/scripts/generate_precommit_hook.py" \
    && ok "pre-commit hook written (.git/hooks/pre-commit)" \
    || warn "generate_precommit_hook.py failed — run manually: python3 scripts/generate_precommit_hook.py"
  "$PYTHON_BIN" "$YOUK_DIR/scripts/generate_commitmsg_hook.py" \
    && ok "commit-msg hook written (.git/hooks/commit-msg)" \
    || warn "generate_commitmsg_hook.py failed — run manually: python3 scripts/generate_commitmsg_hook.py"
fi

# ── Step 9: Validate ─────────────────────────────────────────────────────────
step "Validation"
YOUK_DIR="$YOUK_DIR" YOUK_HOST="$YOUK_HOST_ID" bash "$YOUK_DIR/scripts/doctor.sh"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}youk is ready.${NC}"
echo ""
case "$YOUK_HOST_ID" in
  claude-code) echo "  Open a new Claude Code session — youk starts automatically." ;;
  codex)       echo "  Open a new Codex session. For context injected at session start, add the hooks in docs/getting-started.md (Agent-host selection)." ;;
  none)        echo "  Add the two MCP servers above to your agent host, then start a session." ;;
esac
echo ""
echo "  Note: youk stores knowledge on this machine only ($YOUK_DIR/)."
echo "  Teammates using youk on the same project have separate histories."
echo "  To share context, copy $YOUK_DIR/knowledge/projects/<slug>/ to their machine."
echo ""
if [[ "$YOUK_HOST_ID" == "claude-code" ]]; then
  echo "  Skill override warning: if any project you use has .claude/skills/done,"
  echo "  .claude/skills/start, or .claude/skills/build, those files take precedence"
  echo "  over youk's versions in that project directory. Use 'ship it' (phrase) instead"
  echo "  of /done in those projects to ensure youk's session tracking still runs."
  echo "  Run: ls <project>/.claude/skills/ to check for conflicts."
  echo ""
fi
