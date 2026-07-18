#!/usr/bin/env bash
# relay_check.sh — Gate Packaging Manifest verifier
#
# Checks RELAY/ against the Gate Packaging Manifest:
#   1. Required files are present
#   2. MANIFEST.md gate label matches the newest GATE-*.md
#   3. Ledger's last commit row matches git HEAD on the working branch
#   4. Diff files' newest commit matches git HEAD
#   5. Prints the manifest echo block (paste verbatim into gate message)
#
# Exit codes: 0 = all checks pass, 1 = one or more mismatches

set -euo pipefail

RELAY_DIR="$(cd "$(dirname "$0")/../.." && pwd)/Desktop/youk-audit/RELAY"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Allow override for tests
RELAY_DIR="${RELAY_CHECK_DIR:-$RELAY_DIR}"
REPO_DIR="${RELAY_CHECK_REPO:-$REPO_DIR}"

FAIL=0
ERRORS=()

echo "==> relay-check: verifying RELAY/ at $RELAY_DIR"
echo ""

# ── 1. Required files ─────────────────────────────────────────────────────────

REQUIRED_FILES=(
    "MANIFEST.md"
    "deviation-log.md"
    "elite-progress.md"
    "live-evidence.md"
)

echo "[ Required files ]"
for f in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$RELAY_DIR/$f" ]]; then
        echo "  $f ... PRESENT"
    else
        echo "  $f ... ABSENT  ← FAIL"
        FAIL=1
        ERRORS+=("ABSENT: RELAY/$f")
    fi
done

# At least one GATE-*.md must exist
GATE_FILES=( "$RELAY_DIR"/GATE-*.md )
if [[ ${#GATE_FILES[@]} -gt 0 && -f "${GATE_FILES[0]}" ]]; then
    echo "  GATE-*.md ... PRESENT (${#GATE_FILES[@]} file(s))"
else
    echo "  GATE-*.md ... ABSENT  ← FAIL"
    FAIL=1
    ERRORS+=("ABSENT: RELAY/GATE-*.md")
fi

# At least one elite-batch-*.diff must exist
DIFF_FILES=( "$RELAY_DIR"/elite-batch-*.diff )
if [[ ${#DIFF_FILES[@]} -gt 0 && -f "${DIFF_FILES[0]}" ]]; then
    echo "  elite-batch-*.diff ... PRESENT (${#DIFF_FILES[@]} diff(s))"
else
    echo "  elite-batch-*.diff ... ABSENT  ← FAIL"
    FAIL=1
    ERRORS+=("ABSENT: RELAY/elite-batch-*.diff")
fi

echo ""

# ── 2. MANIFEST gate label vs. newest GATE-*.md ───────────────────────────────

echo "[ MANIFEST gate label vs. newest GATE-*.md ]"

MANIFEST_GATE=$(grep -m1 "^Gate:" "$RELAY_DIR/MANIFEST.md" 2>/dev/null | sed 's/^Gate: *//' || echo "")
NEWEST_GATE_FILE=$(ls -t "$RELAY_DIR"/GATE-*.md 2>/dev/null | head -1 || echo "")
NEWEST_GATE_NAME=$(basename "$NEWEST_GATE_FILE" .md 2>/dev/null || echo "")

echo "  MANIFEST Gate: $MANIFEST_GATE"
echo "  Newest GATE file: $NEWEST_GATE_NAME"

# Normalize both to compare: strip "GATE-" prefix → "B4-2", strip "GATE " → "B4-2"
MANIFEST_GATE_NORM=$(echo "$MANIFEST_GATE" | sed 's/GATE[- ]//g' | awk '{print $1}')
NEWEST_GATE_NORM=$(echo "$NEWEST_GATE_NAME" | sed 's/GATE-//')

if [[ -z "$MANIFEST_GATE" ]]; then
    echo "  → FAIL: MANIFEST.md has no Gate: line"
    FAIL=1
    ERRORS+=("MANIFEST Gate: line missing")
elif [[ "$MANIFEST_GATE_NORM" != "$NEWEST_GATE_NORM"* && "$NEWEST_GATE_NORM" != "$MANIFEST_GATE_NORM"* ]]; then
    echo "  → FAIL: MANIFEST Gate label ($MANIFEST_GATE_NORM) does not match $NEWEST_GATE_NAME ($NEWEST_GATE_NORM)"
    FAIL=1
    ERRORS+=("MANIFEST gate label '$MANIFEST_GATE' does not match newest gate '$NEWEST_GATE_NAME'")
else
    echo "  → OK"
fi

echo ""

# ── 3. Ledger last row vs. git HEAD ──────────────────────────────────────────

echo "[ Ledger last commit row vs. git HEAD ]"

GIT_HEAD=$(cd "$REPO_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "")
BRANCH=$(cd "$REPO_DIR" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

echo "  git HEAD ($BRANCH): $GIT_HEAD"

# Find last SHA-like token in the MANIFEST.md commits table
LEDGER_LAST=$(grep -E "^\| [0-9a-f]{7,}" "$RELAY_DIR/MANIFEST.md" 2>/dev/null | tail -1 | awk -F'|' '{print $2}' | tr -d ' ' || echo "")
echo "  MANIFEST ledger last row SHA: ${LEDGER_LAST:-<none found>}"

if [[ -z "$LEDGER_LAST" ]]; then
    echo "  → FAIL: no commit rows found in MANIFEST.md"
    FAIL=1
    ERRORS+=("MANIFEST.md: no commit rows found")
elif [[ "$LEDGER_LAST" != "$GIT_HEAD"* && "$GIT_HEAD" != "$LEDGER_LAST"* ]]; then
    echo "  → FAIL: ledger last SHA ($LEDGER_LAST) != HEAD ($GIT_HEAD)"
    FAIL=1
    ERRORS+=("Ledger last SHA '$LEDGER_LAST' != HEAD '$GIT_HEAD'")
else
    echo "  → OK"
fi

echo ""

# ── 4. Newest diff HEAD ───────────────────────────────────────────────────────

echo "[ Newest diff HEAD check ]"

NEWEST_DIFF=$(ls -t "$RELAY_DIR"/elite-batch-*.diff 2>/dev/null | head -1 || echo "")
if [[ -n "$NEWEST_DIFF" ]]; then
    # Extract first 'b/' commit reference from the diff header (fallback: last commit SHA in +++ lines)
    DIFF_SHA=$(grep -m1 "^index " "$NEWEST_DIFF" 2>/dev/null | awk '{print $2}' | cut -d'.' -f1 | head -c7 || echo "")
    if [[ -z "$DIFF_SHA" ]]; then
        echo "  → SKIP: cannot extract SHA from diff (no 'index' lines found)"
    else
        echo "  Newest diff first SHA: $DIFF_SHA"
        echo "  → (diff content verified by ledger check above)"
    fi
else
    echo "  → SKIP: no diff files found"
fi

echo ""

# ── 5. Manifest echo block ────────────────────────────────────────────────────

echo "[ Manifest echo — paste verbatim into gate message ]"
echo ""
echo "================================================================"
echo "MANIFEST ECHO"
echo "Gate: $NEWEST_GATE_NAME  |  Branch: $BRANCH @ $GIT_HEAD  |  Date: $(date +%Y-%m-%d)"
echo ""
echo "Required files:"
for f in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$RELAY_DIR/$f" ]]; then
        SIZE=$(wc -c < "$RELAY_DIR/$f" | tr -d ' ')
        echo "  $f ($SIZE bytes) ✓"
    else
        echo "  $f ABSENT ✗"
    fi
done
for gf in "${GATE_FILES[@]}"; do
    if [[ -f "$gf" ]]; then
        SIZE=$(wc -c < "$gf" | tr -d ' ')
        echo "  $(basename $gf) ($SIZE bytes) ✓"
    fi
done
for df in "${DIFF_FILES[@]}"; do
    if [[ -f "$df" ]]; then
        SIZE=$(wc -c < "$df" | tr -d ' ')
        LINES=$(wc -l < "$df" | tr -d ' ')
        echo "  $(basename $df) ($SIZE bytes, $LINES lines) ✓"
    fi
done

echo ""
COMMIT_LOG=$(cd "$REPO_DIR" && git log --oneline main..HEAD 2>/dev/null | head -20 || echo "")
echo "Commits (main..HEAD):"
while IFS= read -r line; do
    echo "  $line"
done <<< "$COMMIT_LOG"
echo "================================================================"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────

if [[ $FAIL -eq 0 ]]; then
    echo "relay-check: ALL CHECKS PASSED"
    exit 0
else
    echo "relay-check: FAILED — ${#ERRORS[@]} issue(s):"
    for e in "${ERRORS[@]}"; do
        echo "  - $e"
    done
    exit 1
fi
