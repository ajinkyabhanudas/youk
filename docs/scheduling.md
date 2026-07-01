# Scheduled Health Checks

youk's compounding engine normally fires during Claude Code sessions (`self_heal` runs every 3rd
session via `health_check_due`). A scheduled health check lets it run on a fixed cadence —
once a week, without a session being open — so the audit loop stays active even during quiet periods.

## What it does

`make health-check` calls `self_heal()` via the Docker MCP server directly (no Claude Code
session required), prints an org score + top findings, and queues any improvement proposals to
`knowledge/proposals/PENDING.md` for your review next session.

## Manual run

```bash
make health-check
# youk health  org: 5.8/10
#   Session-close cluster skipped 100% of sessions (0/2 completed).
```

## Cron (macOS / Linux)

```bash
crontab -e
```

Add:
```
# youk weekly health check — every Monday at 9am
0 9 * * 1 cd /Users/YOUR_NAME/.claude/youk && make health-check >> /Users/YOUR_NAME/.claude/audit/cron.log 2>&1
```

Replace `/Users/YOUR_NAME` with your actual home path (`echo $HOME`).

## launchd (macOS — runs even after reboot)

Create `~/Library/LaunchAgents/com.youk.health.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.youk.health</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/make</string>
    <string>-C</string>
    <string>/Users/YOUR_NAME/.claude/youk</string>
    <string>health-check</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer>
    <key>Hour</key><integer>9</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/YOUR_NAME/.claude/audit/cron.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOUR_NAME/.claude/audit/cron.log</string>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.youk.health.plist
```

## Prerequisites

- Docker Desktop must be running (the health check calls `docker run`)
- `youk-core:latest` image must be built (`make build`)
- `ANTHROPIC_API_KEY` must be accessible if health generates API-calling proposals

## Reviewing results

After a scheduled run, proposals appear in `knowledge/proposals/PENDING.md`. Review them in your
next Claude Code session with `/health` or `get_proposals()`. No proposals auto-apply —
`confirmed=True` is always required.
