#!/usr/bin/env bash
# youk uninstaller — reverses the host integration install.sh created.
#
# Mirrors install.sh section order, in reverse. Idempotent: safe to run twice;
# a missing artifact warns rather than aborting.
#
# By default this reverts the SYSTEM integration (MCP servers, skill symlinks,
# hooks plugin, CLAUDE.md block, schedulers, Docker images) and PRESERVES your
# accumulated knowledge (~/.claude/youk/knowledge, state, and ~/.claude/audit),
# so a later re-install resumes with full history.
#
#   bash scripts/uninstall.sh              # revert integration, keep knowledge
#   bash scripts/uninstall.sh --purge      # also delete knowledge/state/audit + snapshot
#   bash scripts/uninstall.sh --keep-images  # leave Docker images in place
#   bash scripts/uninstall.sh --dry-run    # print every action, change nothing
#
# The youk repo at ~/.claude/youk is left in place — removing it is `rm -rf`, your call.
set -euo pipefail

YOUK_DIR="$HOME/.claude/youk"
CLAUDE_DIR="$HOME/.claude"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Flags ─────────────────────────────────────────────────────────────────────
PURGE=false
KEEP_IMAGES=false
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --purge)       PURGE=true ;;
    --keep-images) KEEP_IMAGES=true ;;
    --dry-run)     DRY_RUN=true ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -n 18
      exit 0 ;;
    *) echo "Unknown flag: $arg (see --help)"; exit 2 ;;
  esac
done

# ── UI helpers (inline — same as install.sh) ─────────────────────────────────
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; NC=''
fi
ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
warn() { echo -e "  ${YELLOW}!${NC}  $1"; }
fail() { echo -e "  ${RED}✗${NC}  $1"; }
step() { echo -e "\n${GREEN}▶${NC} $1"; }
# run CMD... — execute, or just print under --dry-run.
run()  { if $DRY_RUN; then echo -e "  ${YELLOW}dry-run:${NC} $*"; else "$@"; fi; }

if $DRY_RUN; then
  echo -e "${YELLOW}DRY RUN — no changes will be made.${NC}"
fi

RESTORE_ROOT="$CLAUDE_DIR/youk-restore"
SNAP="$RESTORE_ROOT/latest"

# ── Step 1: Stop persistent servers + deregister MCP ────────────────────────
step "Stopping persistent servers and deregistering MCP"

# Stop launchd agents and remove generated plists
for SERVER in core code; do
  PLIST="$HOME/Library/LaunchAgents/com.youk.${SERVER}-server.plist"
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
done

# Stop and remove named containers (in case launchd didn't clean them up)
docker stop youk-core-server youk-code-server 2>/dev/null || true
docker rm youk-core-server youk-code-server 2>/dev/null || true
ok "Persistent servers stopped"

if command -v claude >/dev/null 2>&1; then
  run claude mcp remove youk-core  2>/dev/null || warn "youk-core not registered (already removed)"
  run claude mcp remove youk-code  2>/dev/null || warn "youk-code not registered (already removed)"
  ok "youk-core / youk-code deregistered"
else
  warn "claude CLI not found — skipping MCP deregistration"
fi

# ── Step 2: Remove hooks plugin symlink ──────────────────────────────────────
step "Context hooks plugin"
LINK_TARGET="$CLAUDE_DIR/plugins/youk-context"
if [ -L "$LINK_TARGET" ]; then
  # Only remove if it points at youk's plugin.
  tgt="$(readlink "$LINK_TARGET" || echo "")"
  case "$tgt" in
    *"/youk/plugin"|*"youk/plugin") run rm -f "$LINK_TARGET"; ok "youk-context plugin symlink removed" ;;
    *) warn "plugins/youk-context points elsewhere ($tgt) — leaving it" ;;
  esac
elif [ -e "$LINK_TARGET" ]; then
  warn "plugins/youk-context is a real directory, not a youk symlink — leaving it"
else
  warn "plugins/youk-context already absent"
fi

# ── Step 3: Remove skill symlinks ────────────────────────────────────────────
# Remove ONLY symlinks that resolve to a path under THIS install's youk/skills
# directory. Real dirs and foreign symlinks are never touched. We resolve to an
# absolute path (not a bare substring match) so a user's fork whose path merely
# contains "youk/skills" is not caught.
step "Skill symlinks"
SKILLS_DIR="$CLAUDE_DIR/skills"
# Canonical prefix for youk's own skills, trailing slash for prefix comparison.
YOUK_SKILLS_PREFIX="$YOUK_DIR/skills/"
_removed=0
if [ -d "$SKILLS_DIR" ]; then
  for entry in "$SKILLS_DIR"/* "$SKILLS_DIR"/.[!.]*; do
    [ -L "$entry" ] || continue
    # Resolve the link target to an absolute path, relative to the link's dir.
    tgt="$(readlink "$entry" || echo "")"
    case "$tgt" in
      /*) abs="$tgt" ;;                      # already absolute
      *)  abs="$SKILLS_DIR/$tgt" ;;          # relative → resolve against link location
    esac
    # Normalise ../ segments without requiring the target to exist (broken links
    # must still be classifiable). Python handles this portably.
    abs="$(python3 -c 'import os,sys; print(os.path.normpath(sys.argv[1]))' "$abs" 2>/dev/null || echo "$abs")"
    case "$abs/" in
      "$YOUK_SKILLS_PREFIX"*) run rm -f "$entry"; _removed=$((_removed+1)) ;;
    esac
  done
  ok "$_removed youk skill symlink(s) removed (real dirs & foreign symlinks untouched)"
else
  warn "skills dir absent"
fi

# ── Step 4: CLAUDE.md ────────────────────────────────────────────────────────
# Surgical fence removal first; snapshot restore as fallback; never blind-truncate.
step "CLAUDE.md"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
FENCE_BEGIN="<!-- BEGIN youk (managed) -->"
FENCE_END="<!-- END youk -->"
if [ ! -f "$CLAUDE_MD" ]; then
  warn "CLAUDE.md absent — nothing to do"
elif grep -qF "$FENCE_BEGIN" "$CLAUDE_MD" && grep -qF "$FENCE_END" "$CLAUDE_MD"; then
  # Preferred: surgical fence removal. Deletes ONLY youk's fenced block and
  # preserves everything else — including edits the user made to their own
  # content after install. This is why fences exist; snapshot restore (below)
  # would revert those post-install edits too.
  if $DRY_RUN; then
    echo -e "  ${YELLOW}dry-run:${NC} remove fenced youk block from $CLAUDE_MD"
  else
    tmp="$(mktemp)"
    awk -v begin="$FENCE_BEGIN" -v end="$FENCE_END" '
      $0 == begin { skip=1; next }
      $0 == end   { skip=0; next }
      !skip       { print }
    ' "$CLAUDE_MD" > "$tmp"
    # Guard against truncation: only overwrite if the result is non-empty. A
    # disk-full or interrupted awk would otherwise clobber CLAUDE.md with an
    # empty file. (An all-youk CLAUDE.md legitimately becoming empty is fine —
    # but that never happens here since the file always has the user's content
    # or at minimum the H1 the block sat under.)
    if [ -s "$tmp" ]; then
      mv "$tmp" "$CLAUDE_MD"
      ok "youk block removed from CLAUDE.md (fenced region deleted, your edits preserved)"
    else
      rm -f "$tmp"
      fail "Fence removal produced an empty file (disk full?) — CLAUDE.md left unchanged."
    fi
  fi
elif [ -f "$SNAP/CLAUDE.md.orig" ]; then
  # Fallback: fences missing/corrupt (e.g. a pre-fence legacy install, or the
  # markers were hand-deleted). Restore the pre-install snapshot verbatim.
  # NOTE: this also reverts any edits made to CLAUDE.md after install.
  run cp "$SNAP/CLAUDE.md.orig" "$CLAUDE_MD"
  warn "CLAUDE.md had no fence markers — restored the pre-install snapshot verbatim."
  warn "  Any edits you made to CLAUDE.md after installing youk were reverted."
elif grep -q "youk-core.session_start" "$CLAUDE_MD" 2>/dev/null; then
  warn "youk block present but no fences and no snapshot — NOT auto-editing."
  warn "  Manually remove the youk section (from the '# youk' heading to EOF) in $CLAUDE_MD"
else
  ok "no youk block in CLAUDE.md — nothing to remove"
fi

# ── Step 5: Schedulers ───────────────────────────────────────────────────────
step "Schedulers"
if [ "$(uname)" = "Darwin" ]; then
  for job in com.youk.project-research com.youk.cleanup; do
    plist="$HOME/Library/LaunchAgents/$job.plist"
    if [ -f "$plist" ]; then
      run launchctl unload "$plist" 2>/dev/null || true
      run rm -f "$plist"
      ok "$job unloaded and removed"
    else
      warn "$job.plist absent"
    fi
  done
elif command -v crontab >/dev/null 2>&1; then
  if crontab -l 2>/dev/null | grep -qE "project-research.py|youk.*cleanup.sh"; then
    if $DRY_RUN; then
      echo -e "  ${YELLOW}dry-run:${NC} strip youk cron lines"
    else
      crontab -l 2>/dev/null | grep -vE "project-research.py|youk.*cleanup.sh" | crontab -
    fi
    ok "youk cron entries removed"
  else
    warn "no youk cron entries"
  fi
fi

# ── Step 6: Docker images ────────────────────────────────────────────────────
step "Docker images"
if $KEEP_IMAGES; then
  warn "--keep-images — leaving youk-core / youk-code in place"
elif command -v docker >/dev/null 2>&1; then
  run docker rmi youk-core:latest youk-code:latest 2>/dev/null || warn "images already removed or in use"
  ok "youk Docker images removed"
else
  warn "docker not found — skipping image removal"
fi

# ── Step 7: Accumulated knowledge ────────────────────────────────────────────
step "Accumulated knowledge"
if $PURGE; then
  for p in "$YOUK_DIR/knowledge" "$YOUK_DIR/state" "$CLAUDE_DIR/audit" "$RESTORE_ROOT"; do
    if [ -e "$p" ]; then run rm -rf "$p"; ok "purged $p"; fi
  done
  warn "--purge: all youk knowledge, state, audit, and the restore snapshot are gone."
else
  ok "Preserved: $YOUK_DIR/knowledge, $YOUK_DIR/state, $CLAUDE_DIR/audit"
  ok "  Snapshot kept at $RESTORE_ROOT — re-installing resumes with full history."
  echo "  To remove everything: bash scripts/uninstall.sh --purge"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}youk integration reverted.${NC}"
echo "  The youk repo itself is untouched at $YOUK_DIR (remove with: rm -rf $YOUK_DIR)."
echo "  Restart Claude Code so it stops loading youk's MCP servers and hooks."
