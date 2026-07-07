#!/usr/bin/env bash
# Automatic container cleanup — called by launchd/cron weekly.
# Stops youk containers running on stale image SHAs (left over from crashes
# or if Docker didn't honour --rm on ungraceful shutdown), then prunes
# stopped containers and dangling images.
#
# Safe to run while a Claude Code session is open: active containers on the
# current :latest SHA are never touched.
set -uo pipefail

YOUK_DIR="${YOUK_DIR:-$HOME/.claude/youk}"
LOG="$YOUK_DIR/state/cleanup.log"

mkdir -p "$(dirname "$LOG")"
echo "[$(date '+%Y-%m-%d %H:%M')] cleanup start" >> "$LOG"

if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
  echo "[$(date '+%Y-%m-%d %H:%M')] docker not available — skipping" >> "$LOG"
  exit 0
fi

# Resolve current image SHAs — containers on these are live sessions, skip them
CORE_SHA=$(docker image inspect youk-core:latest --format '{{.Id}}' 2>/dev/null || echo "")
CODE_SHA=$(docker image inspect youk-code:latest --format '{{.Id}}' 2>/dev/null || echo "")

# Stop any youk container whose image SHA no longer matches :latest
docker ps --format '{{.ID}} {{.Image}}' 2>/dev/null | grep -E 'youk-(core|code)' | \
while read -r cid img; do
  sha=$(docker inspect "$cid" --format '{{.Image}}' 2>/dev/null || echo "")
  if [ -n "$sha" ] && [ "$sha" != "$CORE_SHA" ] && [ "$sha" != "$CODE_SHA" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M')] stopping stale $cid ($img sha=${sha:0:12})" >> "$LOG"
    docker stop "$cid" >/dev/null 2>&1 || true
  fi
done

# Prune stopped containers (includes any --rm containers that didn't self-clean)
PRUNED=$(docker container prune -f 2>&1 || true)
echo "[$(date '+%Y-%m-%d %H:%M')] container prune: $PRUNED" >> "$LOG"

# Prune dangling image layers
IMG_PRUNED=$(docker image prune -f 2>&1 || true)
echo "[$(date '+%Y-%m-%d %H:%M')] image prune: $IMG_PRUNED" >> "$LOG"

echo "[$(date '+%Y-%m-%d %H:%M')] cleanup done" >> "$LOG"
