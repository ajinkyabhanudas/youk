# youk installer for Windows
# Run in PowerShell (Administrator recommended for symlinks):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\install.ps1
#
# Requirements: WSL2 + Docker Desktop for Windows + Node.js + Git
# Docker Desktop must have "Use WSL 2 based engine" enabled (Settings → General).

$ErrorActionPreference = "Stop"

$YOUK_DIR  = "$env:USERPROFILE\.claude\youk"
$CLAUDE_DIR = "$env:USERPROFILE\.claude"

function ok($msg)   { Write-Host "  [OK]  $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "  [!]   $msg" -ForegroundColor Yellow }
function fail($msg) { Write-Host "  [X]   $msg" -ForegroundColor Red }
function step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }

# ── Step 0: Preflight ────────────────────────────────────────────────────────
step "Preflight checks"

# WSL2
$wslOut = wsl --status 2>&1
if ($LASTEXITCODE -ne 0 -or ($wslOut -notmatch "Default Version: 2")) {
    warn "WSL2 not detected. youk's Docker images require Linux containers."
    Write-Host ""
    Write-Host "  Install WSL2:  wsl --install" -ForegroundColor White
    Write-Host "  Then re-run this script." -ForegroundColor White
    Write-Host ""
    Write-Host "  Docs: https://learn.microsoft.com/en-us/windows/wsl/install" -ForegroundColor DarkGray
    exit 1
}
ok "WSL2 available"

# Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    fail "Docker not found. Install Docker Desktop for Windows from https://docker.com"
    Write-Host "  Enable 'Use WSL 2 based engine' in Docker Desktop Settings → General." -ForegroundColor DarkGray
    exit 1
}
$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    fail "Docker is not running. Start Docker Desktop and re-run."
    exit 1
}
ok "Docker running"

# Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    fail "Git not found. Install from https://git-scm.com/download/win and re-run."
    exit 1
}
ok "Git found"

# Node / npm (needed for claude CLI)
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    fail "Node.js not found. Install from https://nodejs.org and re-run."
    exit 1
}
ok "Node.js found"

# Claude Code
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    warn "Claude Code not found — installing now..."
    npm install -g @anthropic-ai/claude-code
    if ($LASTEXITCODE -ne 0) {
        fail "npm install failed. Run manually: npm install -g @anthropic-ai/claude-code"
        exit 1
    }
    ok "Claude Code installed"
} else {
    ok "Claude Code found"
}

# ── Step 1: Clone or pull ────────────────────────────────────────────────────
step "Repository"

if (Test-Path "$YOUK_DIR\.git") {
    ok "youk already cloned at $YOUK_DIR"
    Push-Location $YOUK_DIR
    git pull --ff-only --quiet
    if ($LASTEXITCODE -eq 0) { ok "Pulled latest" } else { warn "Already up to date" }
    Pop-Location
} else {
    git clone https://github.com/ajinkyabhanudas/youk $YOUK_DIR --quiet
    ok "Cloned to $YOUK_DIR"
}

# ── Step 2: Runtime directories ──────────────────────────────────────────────
step "Runtime directories"

@(
    "$YOUK_DIR\state",
    "$YOUK_DIR\knowledge\interpretation",
    "$YOUK_DIR\knowledge\clarifications",
    "$YOUK_DIR\knowledge\proposals",
    "$YOUK_DIR\knowledge\projects",
    "$CLAUDE_DIR\audit"
) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}
ok "Directories ready"

# path-map.env — containers mount YOUK_DIR→/youk and CLAUDE_DIR→/claude
# On Windows, Docker volume mounts use the WSL path. Convert backslashes.
$youkWsl   = ($YOUK_DIR  -replace "\\", "/") -replace "^([A-Za-z]):", { "/mnt/$($_.Groups[1].Value.ToLower())" }
$claudeWsl = ($CLAUDE_DIR -replace "\\", "/") -replace "^([A-Za-z]):", { "/mnt/$($_.Groups[1].Value.ToLower())" }
@"
# Host→container path mappings — written by install.ps1, read by session.py
YOUK_HOST_DIR=$youkWsl
CLAUDE_HOST_DIR=$claudeWsl
"@ | Set-Content "$YOUK_DIR\state\path-map.env" -Encoding UTF8
ok "path-map.env written (WSL paths)"

# ── Step 3: Skills symlinks ──────────────────────────────────────────────────
step "Skills"

$SKILLS_DIR  = "$CLAUDE_DIR\skills"
$SKILLS_REPO = "$YOUK_DIR\skills"

if (-not (Test-Path $SKILLS_DIR)) {
    New-Item -ItemType Directory -Path $SKILLS_DIR -Force | Out-Null
}

Get-ChildItem $SKILLS_REPO -Directory | ForEach-Object {
    $skillName = $_.Name
    $target = "$SKILLS_DIR\$skillName"
    $source = "$SKILLS_REPO\$skillName"
    if (Test-Path $target) {
        ok "skill/$skillName — already linked"
    } else {
        # Requires Developer Mode or Administrator for symlinks on Windows
        try {
            New-Item -ItemType Junction -Path $target -Target $source | Out-Null
            ok "skill/$skillName — linked (junction)"
        } catch {
            warn "skill/$skillName — could not create junction: $_"
            warn "Run as Administrator to enable symlinks, or enable Developer Mode."
        }
    }
}

# ── Step 4: Context hooks plugin ─────────────────────────────────────────────
step "Context hooks plugin"

$PLUGIN_SRC  = "$YOUK_DIR\plugin"
$PLUGINS_DIR = "$CLAUDE_DIR\plugins"
$PLUGIN_LINK = "$PLUGINS_DIR\youk-context"

if (-not (Test-Path $PLUGINS_DIR)) {
    New-Item -ItemType Directory -Path $PLUGINS_DIR -Force | Out-Null
}

if (Test-Path $PLUGIN_LINK) {
    ok "youk-context plugin already linked"
} else {
    try {
        New-Item -ItemType Junction -Path $PLUGIN_LINK -Target $PLUGIN_SRC | Out-Null
        ok "youk-context plugin linked"
        ok "Hooks registered: PreCompact, UserPromptSubmit, PostToolUse"
    } catch {
        warn "Could not create plugin junction: $_"
        warn "Run as Administrator or manually: mklink /J `"$PLUGIN_LINK`" `"$PLUGIN_SRC`""
    }
}

# ── Step 5: Build Docker images ──────────────────────────────────────────────
step "Docker images"

Write-Host "  Building youk-core:latest..." -ForegroundColor DarkGray
docker build -t youk-core:latest -f "$YOUK_DIR\servers\core\Dockerfile" $YOUK_DIR 2>&1 | Select-String "error|ERROR|Step" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
if ($LASTEXITCODE -ne 0) { fail "youk-core build failed"; exit 1 }
ok "youk-core:latest built"

Write-Host "  Building youk-code:latest..." -ForegroundColor DarkGray
docker build -t youk-code:latest -f "$YOUK_DIR\servers\code\Dockerfile" $YOUK_DIR 2>&1 | Select-String "error|ERROR|Step" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
if ($LASTEXITCODE -ne 0) { fail "youk-code build failed"; exit 1 }
ok "youk-code:latest built"

# ── Step 6: Register MCP servers ─────────────────────────────────────────────
step "MCP server registration"

# On Windows, Docker volume mounts need WSL-style paths OR Windows paths with forward slashes.
# Use the WSL path form: /mnt/c/Users/...
$mcpList = claude mcp list 2>&1

if ($mcpList -match "youk-core") {
    ok "youk-core already registered"
} else {
    claude mcp add --scope user youk-core --transport stdio -- `
        docker run -i --rm `
        -v "${claudeWsl}:/claude" `
        -v "${youkWsl}:/youk" `
        youk-core:latest
    if ($LASTEXITCODE -eq 0) { ok "youk-core registered" } else { fail "youk-core registration failed" }
}

if ($mcpList -match "youk-code") {
    ok "youk-code already registered"
} else {
    claude mcp add --scope user youk-code --transport stdio -- `
        docker run -i --rm `
        -v "${claudeWsl}:/claude:ro" `
        -v "${youkWsl}:/youk:ro" `
        youk-code:latest
    if ($LASTEXITCODE -eq 0) { ok "youk-code registered" } else { fail "youk-code registration failed" }
}

# ── Step 7: Patch CLAUDE.md ──────────────────────────────────────────────────
step "CLAUDE.md"

$CLAUDE_MD = "$CLAUDE_DIR\CLAUDE.md"
$TEMPLATE  = "$YOUK_DIR\docs\claude-md-template.md"

if (-not (Test-Path $CLAUDE_MD)) {
    New-Item -ItemType File -Path $CLAUDE_MD -Force | Out-Null
}

$existing = Get-Content $CLAUDE_MD -Raw -ErrorAction SilentlyContinue
if ($existing -match "youk") {
    ok "CLAUDE.md already contains youk block — skipping"
} else {
    Add-Content $CLAUDE_MD "`n`n$(Get-Content $TEMPLATE -Raw)"
    ok "youk block appended to CLAUDE.md"
}

# ── Step 8: Seed audit log ───────────────────────────────────────────────────
step "Audit log"

$MONTH      = (Get-Date).ToString("yyyy-MM")
$AUDIT_FILE = "$CLAUDE_DIR\audit\$MONTH.md"

if (-not (Test-Path $AUDIT_FILE)) { New-Item -ItemType File -Path $AUDIT_FILE -Force | Out-Null }

$auditContent = Get-Content $AUDIT_FILE -Raw -ErrorAction SilentlyContinue
if ($auditContent -notmatch "youk install complete") {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm")
    Add-Content $AUDIT_FILE @"

### Session — $timestamp UTC
youk install complete. Baseline session.
Skills: install
CloseCluster: yes
Commits: no
"@
    ok "Audit log seeded"
} else {
    ok "Audit log already seeded"
}

# ── Step 9: Scheduled tasks (Windows Task Scheduler) ─────────────────────────
step "Scheduled tasks"

$pythonBin = (Get-Command python -ErrorAction SilentlyContinue)?.Source `
          ?? (Get-Command python3 -ErrorAction SilentlyContinue)?.Source

if (-not $pythonBin) {
    warn "Python not found — skipping project research scheduler"
    warn "Install from https://python.org then run: python $YOUK_DIR\scripts\project-research.py"
} else {
    # Project research — every Wednesday at 09:00
    $taskName = "youk-project-research"
    $existing = schtasks /Query /TN $taskName 2>&1
    if ($LASTEXITCODE -ne 0) {
        $action  = New-ScheduledTaskAction -Execute $pythonBin -Argument "$YOUK_DIR\scripts\project-research.py"
        $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Wednesday -At "09:00"
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Force | Out-Null
        ok "Project research scheduled (every Wednesday 09:00)"
    } else {
        ok "Project research already scheduled"
    }

    # Container cleanup — every Sunday at 02:00
    $cleanupTask = "youk-container-cleanup"
    $existingCleanup = schtasks /Query /TN $cleanupTask 2>&1
    if ($LASTEXITCODE -ne 0) {
        $cleanupAction  = New-ScheduledTaskAction -Execute "docker" -Argument "container prune -f"
        $cleanupTrigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Sunday -At "02:00"
        Register-ScheduledTask -TaskName $cleanupTask -Action $cleanupAction -Trigger $cleanupTrigger -Force | Out-Null
        ok "Container cleanup scheduled (every Sunday 02:00)"
    } else {
        ok "Container cleanup already scheduled"
    }
}

# ── Step 10: doctor ──────────────────────────────────────────────────────────
step "Validation"

# Run doctor via WSL (doctor.sh is bash)
wsl bash "$youkWsl/scripts/doctor.sh"

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "youk is ready." -ForegroundColor Green
Write-Host ""
Write-Host "  Open a new Claude Code session — youk starts automatically." -ForegroundColor White
Write-Host ""
Write-Host "  Note: youk stores knowledge on this machine only (~\.claude\youk\)."
Write-Host "  Teammates using youk on the same project have separate histories."
Write-Host ""
Write-Host "  Windows note: symlinks require Developer Mode or Administrator."
Write-Host "  If skill junctions failed above, run PowerShell as Administrator and re-run."
Write-Host ""
