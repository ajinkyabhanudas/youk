# youk uninstaller for Windows — reverses what install.ps1 created.
#
# Run in PowerShell (Administrator recommended, to match install):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\uninstall.ps1
#
# By default reverts the SYSTEM integration (MCP servers, skill junctions,
# hooks plugin, CLAUDE.md block, scheduled tasks, Docker images) and PRESERVES
# accumulated knowledge (~\.claude\youk\knowledge, state, and ~\.claude\audit).
#
#   .\scripts\uninstall.ps1              # revert integration, keep knowledge
#   .\scripts\uninstall.ps1 -Purge       # also delete knowledge/state/audit + snapshot
#   .\scripts\uninstall.ps1 -KeepImages  # leave Docker images in place
#   .\scripts\uninstall.ps1 -DryRun      # print every action, change nothing
#
# The youk repo at ~\.claude\youk is left in place (remove with: Remove-Item -Recurse).
# This mirrors scripts/uninstall.sh — keep the two in sync.

param(
    [switch]$Purge,
    [switch]$KeepImages,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$YOUK_DIR   = "$env:USERPROFILE\.claude\youk"
$CLAUDE_DIR = "$env:USERPROFILE\.claude"

function ok($msg)   { Write-Host "  [OK]  $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "  [!]   $msg" -ForegroundColor Yellow }
function fail($msg) { Write-Host "  [X]   $msg" -ForegroundColor Red }
function step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function dry($msg)  { Write-Host "  dry-run: $msg" -ForegroundColor Yellow }

if ($DryRun) { Write-Host "DRY RUN — no changes will be made." -ForegroundColor Yellow }

$RESTORE_ROOT = "$CLAUDE_DIR\youk-restore"
$SNAP         = "$RESTORE_ROOT\latest"
$FENCE_BEGIN  = "<!-- BEGIN youk (managed) -->"
$FENCE_END    = "<!-- END youk -->"

# Return the reparse target of a junction/symlink, or $null if not a link.
function Get-LinkTarget($path) {
    $item = Get-Item $path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return $null }
    if ($item.LinkType -in @("Junction", "SymbolicLink")) { return $item.Target }
    return $null
}

# ── Step 1: Deregister MCP servers ───────────────────────────────────────────
step "MCP server deregistration"
if (Get-Command claude -ErrorAction SilentlyContinue) {
    foreach ($srv in @("youk-core", "youk-code")) {
        if ($DryRun) { dry "claude mcp remove $srv"; continue }
        claude mcp remove $srv 2>&1 | Out-Null
    }
    ok "youk-core / youk-code deregistered"
} else {
    warn "claude CLI not found — skipping MCP deregistration"
}

# ── Step 2: Remove hooks plugin junction ─────────────────────────────────────
step "Context hooks plugin"
$PLUGIN_LINK = "$CLAUDE_DIR\plugins\youk-context"
$pluginTarget = Get-LinkTarget $PLUGIN_LINK
if ($pluginTarget) {
    if (($pluginTarget -replace '/', '\') -like "*\youk\plugin*") {
        if ($DryRun) { dry "remove $PLUGIN_LINK" } else { Remove-Item $PLUGIN_LINK -Force -Recurse }
        ok "youk-context plugin junction removed"
    } else {
        warn "plugins\youk-context points elsewhere ($pluginTarget) — leaving it"
    }
} elseif (Test-Path $PLUGIN_LINK) {
    warn "plugins\youk-context is a real directory, not a youk junction — leaving it"
} else {
    warn "plugins\youk-context already absent"
}

# ── Step 3: Remove skill junctions ───────────────────────────────────────────
# Remove ONLY junctions whose target resolves under this install's youk\skills.
# Real dirs and foreign links are never touched.
step "Skill junctions"
$SKILLS_DIR = "$CLAUDE_DIR\skills"
$youkSkillsPrefix = (Resolve-Path "$YOUK_DIR\skills" -ErrorAction SilentlyContinue)?.Path
if (-not $youkSkillsPrefix) { $youkSkillsPrefix = "$YOUK_DIR\skills" }
$removed = 0
if (Test-Path $SKILLS_DIR) {
    Get-ChildItem $SKILLS_DIR -Force | ForEach-Object {
        $tgt = Get-LinkTarget $_.FullName
        if ($tgt) {
            # Literal prefix check (StartsWith, not -like) so a path containing
            # [ ] wildcard chars can't misclassify. Mirrors the bash version's
            # absolute-path-under-YOUK_DIR check — only THIS install's links go.
            $tgtNorm = ($tgt -replace '/', '\').TrimEnd('\')
            if ($tgtNorm.StartsWith($youkSkillsPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                if ($DryRun) { dry "remove $($_.FullName)" } else { Remove-Item $_.FullName -Force -Recurse }
                $removed++
            }
        }
    }
    ok "$removed youk skill junction(s) removed (real dirs & foreign links untouched)"
} else {
    warn "skills dir absent"
}

# ── Step 4: CLAUDE.md ────────────────────────────────────────────────────────
# Surgical fence removal first (preserves post-install edits); snapshot restore
# fallback; never blind-truncate.
step "CLAUDE.md"
$CLAUDE_MD = "$CLAUDE_DIR\CLAUDE.md"
if (-not (Test-Path $CLAUDE_MD)) {
    warn "CLAUDE.md absent — nothing to do"
} else {
    $lines = Get-Content $CLAUDE_MD
    $hasBegin = $lines -contains $FENCE_BEGIN
    $hasEnd   = $lines -contains $FENCE_END
    if ($hasBegin -and $hasEnd) {
        if ($DryRun) {
            dry "remove fenced youk block from CLAUDE.md"
        } else {
            $out = New-Object System.Collections.Generic.List[string]
            $skip = $false
            foreach ($ln in $lines) {
                if ($ln -eq $FENCE_BEGIN) { $skip = $true; continue }
                if ($ln -eq $FENCE_END)   { $skip = $false; continue }
                if (-not $skip) { $out.Add($ln) }
            }
            # Guard against truncation: only write if non-empty.
            if ($out.Count -gt 0) {
                $out -join "`n" | Set-Content $CLAUDE_MD -Encoding UTF8 -NoNewline
                ok "youk block removed from CLAUDE.md (fenced region deleted, your edits preserved)"
            } else {
                fail "Fence removal produced an empty file — CLAUDE.md left unchanged."
            }
        }
    } elseif (Test-Path "$SNAP\CLAUDE.md.orig") {
        if ($DryRun) { dry "restore CLAUDE.md from snapshot" } else { Copy-Item "$SNAP\CLAUDE.md.orig" $CLAUDE_MD -Force }
        warn "CLAUDE.md had no fence markers — restored the pre-install snapshot verbatim."
        warn "  Any edits you made to CLAUDE.md after installing youk were reverted."
    } elseif ($lines -match "youk-core.session_start") {
        warn "youk block present but no fences and no snapshot — NOT auto-editing."
        warn "  Manually remove the youk section (from the '# youk' heading to EOF) in $CLAUDE_MD"
    } else {
        ok "no youk block in CLAUDE.md — nothing to remove"
    }
}

# ── Step 5: Scheduled tasks ──────────────────────────────────────────────────
step "Scheduled tasks"
foreach ($task in @("youk-project-research", "youk-container-cleanup")) {
    $exists = Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
    if ($exists) {
        if ($DryRun) { dry "unregister scheduled task $task" }
        else { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
        ok "$task removed"
    } else {
        warn "$task absent"
    }
}

# ── Step 6: Docker images ────────────────────────────────────────────────────
step "Docker images"
if ($KeepImages) {
    warn "-KeepImages — leaving youk-core / youk-code in place"
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    if ($DryRun) { dry "docker rmi youk-core:latest youk-code:latest" }
    else { docker rmi youk-core:latest youk-code:latest 2>&1 | Out-Null }
    ok "youk Docker images removed"
} else {
    warn "docker not found — skipping image removal"
}

# ── Step 7: Accumulated knowledge ────────────────────────────────────────────
step "Accumulated knowledge"
if ($Purge) {
    foreach ($p in @("$YOUK_DIR\knowledge", "$YOUK_DIR\state", "$CLAUDE_DIR\audit", $RESTORE_ROOT)) {
        if (Test-Path $p) {
            if ($DryRun) { dry "remove $p" } else { Remove-Item $p -Recurse -Force }
            ok "purged $p"
        }
    }
    warn "-Purge: all youk knowledge, state, audit, and the restore snapshot are gone."
} else {
    ok "Preserved: $YOUK_DIR\knowledge, $YOUK_DIR\state, $CLAUDE_DIR\audit"
    ok "  Snapshot kept at $RESTORE_ROOT — re-installing resumes with full history."
    Write-Host "  To remove everything: .\scripts\uninstall.ps1 -Purge"
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "youk integration reverted." -ForegroundColor Green
Write-Host "  The youk repo itself is untouched at $YOUK_DIR (remove with: Remove-Item -Recurse -Force `"$YOUK_DIR`")."
Write-Host "  Restart Claude Code so it stops loading youk's MCP servers and hooks."
