#!/usr/bin/env bash
# youk host adapters — sourced by install.sh, uninstall.sh and doctor.sh.
#
# Everything an agent host needs from the installer is behind these functions, so the
# installer itself names no vendor: which host, where its config lives, which file holds
# its project instructions, how an MCP server is registered with it, and how youk's block
# is added to and removed from that instructions file.
#
# Hosts: claude-code, codex, none. "none" means no host CLI: youk's two servers are started
# and their URLs printed, and nothing is written into any host's config.
# Select with YOUK_HOST=claude-code|codex|none (default: auto-detect from PATH).
#
# Facts about Codex used here, from OpenAI's docs: `codex mcp add|get|remove <name>`,
# `codex mcp add <name> --url <http-url>` for a streamable-HTTP server, config under
# $CODEX_HOME (default ~/.codex), and global instructions read from $CODEX_HOME/AGENTS.md
# unless AGENTS.override.md is present and non-empty, which takes precedence.
#
# Requires the caller to define ok/warn/fail (they only print). Bash 3.2 safe (macOS).

YOUK_HOSTS="claude-code codex none"
YOUK_MCP_CORE_URL="http://127.0.0.1:8001/mcp"
YOUK_MCP_CODE_URL="http://127.0.0.1:8002/mcp"
YOUK_FENCE_BEGIN="<!-- BEGIN youk (managed) -->"
YOUK_FENCE_END="<!-- END youk -->"

youk_valid_host() { case " $YOUK_HOSTS " in *" $1 "*) return 0 ;; esac; return 1; }

# Prints the selected host id. Auto-detect prefers claude-code when both CLIs exist, which
# is what installs did before other hosts were supported; YOUK_HOST=codex overrides.
youk_detect_host() {
  local want="${YOUK_HOST:-auto}"
  if [ "$want" != "auto" ]; then
    if ! youk_valid_host "$want"; then
      echo "unknown YOUK_HOST '$want' (expected one of: $YOUK_HOSTS, or auto)" >&2
      return 2
    fi
    echo "$want"
    return 0
  fi
  if command -v claude >/dev/null 2>&1; then echo "claude-code"
  elif command -v codex >/dev/null 2>&1; then echo "codex"
  else echo "none"
  fi
}

# The host's config directory ("" for none).
youk_host_dir() {
  case "$1" in
    claude-code) echo "${CLAUDE_DIR:-$HOME/.claude}" ;;
    codex)       echo "${CODEX_HOME:-$HOME/.codex}" ;;
    *)           echo "" ;;
  esac
}

# The file the host reads global project instructions from ("" for none).
youk_host_instructions_file() {
  local dir
  dir="$(youk_host_dir "$1")"
  case "$1" in
    claude-code) echo "$dir/CLAUDE.md" ;;
    codex)
      # Codex uses only the first non-empty file at this level, override first.
      if [ -s "$dir/AGENTS.override.md" ]; then echo "$dir/AGENTS.override.md"; else echo "$dir/AGENTS.md"; fi ;;
    *) echo "" ;;
  esac
}

youk_host_mcp_remove() { # host name
  case "$1" in
    claude-code) claude mcp remove "$2" 2>/dev/null || true ;;
    codex)       codex mcp remove "$2" 2>/dev/null || true ;;
  esac
}

youk_host_mcp_add() { # host name url
  case "$1" in
    claude-code) claude mcp add --scope user "$2" --transport http "$3" ;;
    codex)       codex mcp add "$2" --url "$3" ;;
    *)           return 0 ;;
  esac
}

youk_host_mcp_registered() { # host name -> 0 when the host lists it
  case "$1" in
    claude-code) claude mcp list 2>/dev/null | grep -q "$2" ;;
    codex)       codex mcp get "$2" >/dev/null 2>&1 ;;
    *)           return 1 ;;
  esac
}

# Register both servers with the host, replacing any earlier registration.
youk_register_servers() { # host
  local host="$1"
  if [ "$host" = "none" ]; then
    warn "No agent host selected: add these MCP servers to your host yourself"
    echo "    youk-core  $YOUK_MCP_CORE_URL"
    echo "    youk-code  $YOUK_MCP_CODE_URL"
    return 0
  fi
  youk_host_mcp_remove "$host" youk-core
  youk_host_mcp_remove "$host" youk-code
  youk_host_mcp_add "$host" youk-core "$YOUK_MCP_CORE_URL" && ok "youk-core registered with $host" \
    || fail "could not register youk-core with $host"
  youk_host_mcp_add "$host" youk-code "$YOUK_MCP_CODE_URL" && ok "youk-code registered with $host" \
    || fail "could not register youk-code with $host"
}

# Add or refresh youk's fenced block in an instructions file. Fence markers let
# youk_remove_fenced_block take it out again without touching the user's own text.
youk_patch_instructions() { # file template
  local file="$1" template="$2" tmp
  mkdir -p "$(dirname "$file")"
  [ -f "$file" ] || touch "$file"

  if grep -qF "$YOUK_FENCE_BEGIN" "$file" 2>/dev/null; then
    # (1) Already fenced: replace the fenced region with the current template.
    tmp="$(mktemp)"
    awk -v begin="$YOUK_FENCE_BEGIN" -v end="$YOUK_FENCE_END" -v tpl="$template" '
      $0 == begin { print; while ((getline line < tpl) > 0) print line; skip=1; next }
      $0 == end   { print; skip=0; next }
      !skip       { print }
    ' "$file" > "$tmp"
    if [ -s "$tmp" ]; then mv "$tmp" "$file"; else rm -f "$tmp"; fail "refresh produced empty output; $file left unchanged"; return 1; fi
    ok "youk block in $(basename "$file") refreshed"
  elif grep -q "youk-core.session_start" "$file" 2>/dev/null; then
    # (2) Unfenced youk block from an older install: wrap it in place, content untouched.
    tmp="$(mktemp)"
    awk -v begin="$YOUK_FENCE_BEGIN" -v end="$YOUK_FENCE_END" '
      !wrapped && /^# youk( |$|—)/ { print begin; wrapped=1 }
      { print }
      END { if (wrapped) print end }
    ' "$file" > "$tmp"
    if [ -s "$tmp" ]; then mv "$tmp" "$file"; else rm -f "$tmp"; fail "wrap produced empty output; $file left unchanged"; return 1; fi
    if grep -qF "$YOUK_FENCE_END" "$file" 2>/dev/null; then
      ok "legacy youk block in $(basename "$file") wrapped in fence markers"
    else
      warn "could not find the youk heading to fence; $file left unchanged"
    fi
  else
    # (3) No youk block: append the template, fenced.
    { printf "\n\n%s\n" "$YOUK_FENCE_BEGIN"; cat "$template"; printf "%s\n" "$YOUK_FENCE_END"; } >> "$file"
    ok "youk block appended to $file"
  fi

  # Codex stops adding instruction files once their combined size reaches 32 KiB.
  if [ "$(wc -c < "$file" | tr -d ' ')" -gt 30000 ]; then
    warn "$(basename "$file") is over 30 KB; a host with a 32 KiB instructions limit may truncate it"
  fi
}

# Remove youk's fenced block. Returns 0 when removed, 1 when the file has no fence, 2 on failure.
youk_remove_fenced_block() { # file
  local file="$1" tmp
  [ -f "$file" ] || return 1
  grep -qF "$YOUK_FENCE_BEGIN" "$file" && grep -qF "$YOUK_FENCE_END" "$file" || return 1
  tmp="$(mktemp)"
  # A file that was only youk's block may legitimately become empty, but a failed awk (disk
  # full, interrupted) must not replace the file with a partial result: require a clean exit.
  if awk -v begin="$YOUK_FENCE_BEGIN" -v end="$YOUK_FENCE_END" '
    $0 == begin { skip=1; next }
    $0 == end   { skip=0; next }
    !skip       { print }
  ' "$file" > "$tmp"; then
    mv "$tmp" "$file"
    return 0
  fi
  rm -f "$tmp"
  return 2
}
