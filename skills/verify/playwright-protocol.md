# Playwright MCP — UI Testing Protocol
*Reference for /verify skill. Use this whenever verifying a Gradio or browser-rendered UI.*

---

## When to Use Playwright MCP

Use Playwright MCP (not just `pytest`) when:
- The task involves a UI change (layout, tab labels, status messages, history sidebar)
- The task affects streaming output or timing-sensitive behaviour
- You need to confirm behaviour a non-technical user would experience
- You are testing the golden path AND edge cases before reporting a task complete

Do NOT use Playwright MCP when:
- The change is purely in library code with no UI surface (cache, history, schema)
- Tests already cover the behaviour end-to-end

---

## Test Setup

### Start the UI
```bash
source .env 2>/dev/null; python scripts/run_ui.py &
# Verify it's up:
curl -s http://localhost:7860 | head -3
```

### Load Playwright tools
Before any Playwright call, load the schema:
```
ToolSearch: select:mcp__playwright__browser_navigate,mcp__playwright__browser_snapshot,
            mcp__playwright__browser_take_screenshot,mcp__playwright__browser_click,
            mcp__playwright__browser_type,mcp__playwright__browser_evaluate,
            mcp__playwright__browser_wait_for
```

---

## Standard Test Sequence (Canopy)

Run these in order. Each tests a distinct layer.

### 1. First-open state
```
Navigate → http://localhost:7860
Screenshot (fullPage=true) → verify:
  - No eval test artifacts in history sidebar
  - Idle prompt / example questions visible in Answer tab
  - No blank right panel
```

### 2. Happy path — factual query
```
Type: "How many confirmed species were detected at each reserve in 2023?"
Click: Run Query
Wait: 35s (browser_wait_for 35000)
Screenshot → verify:
  - Status bar showed intent, then cleared
  - Answer tab: headline answer in bold, bullet findings, ⚠️ Data notes at bottom
  - Results tab: row count visible, data table with readable column headers
  - Database query tab: SQL shown with timing comment at bottom
  - History sidebar: query appears, sidebar deselects
```

### 3. Cache hit
```
Click: Run Query (same question still in box)
Wait: 3s
Screenshot → verify:
  - "⚡ Loaded from your recent queries" in timing footer
  - Result renders immediately (< 2s)
  - No status bar activity
```

### 4. Out-of-scope question (conservation/trend)
```
Type: "Is the [species] population declining?"
Click: Run Query
Wait: 35s
Evaluate: document.querySelectorAll('[role="tabpanel"]')[0].innerText
Verify:
  - Response structured as ✅ / ⚠️ / → blocks
  - No conversational question asking user to choose options
  - "For external reports, ask the science team" closing line present
```

### 5. Common-name / ambiguous query
```
Type: "which sites recorded the most birds last year?"
Click: Run Query
Wait: 20s
Evaluate: response text
Verify:
  - Model ran a broad species query (not a follow-up question)
  - Explains common names not in DB
  - Shows sample species names
  - Instructs user to re-ask with scientific name
```

### 6. Empty query guard
```
Clear textbox
Click: Run Query
Wait: 2s
Verify: "Please enter a question." appears in Answer tab
```

### 7. History click auto-run
```
Click a history item in sidebar
Wait: 5s
Verify:
  - Textbox pre-fills with question text
  - Answer tab auto-populates (cached result loads)
  - Sidebar item deselects after result renders
```

### 8. Clear history
```
Click: Clear history
Verify:
  - Sidebar empty
  - Right panel shows idle prompt / example questions (not blank)
  - Textbox cleared
```

### 10. Rendering environment — dark mode check

```
Evaluate: document.documentElement.classList.contains('dark')
Verify:
  - Returns false (dark class was removed by _JS before first paint)

Evaluate: getComputedStyle(document.documentElement).colorScheme
Verify:
  - Returns 'light' (CSS color-scheme override is active)

Evaluate: getComputedStyle(document.querySelector('#canopy-status')).backgroundColor
Verify:
  - Returns rgba(0,0,0,0) or transparent (no background fill on status bar)
```

Run this test after ANY CSS change. A returning value of `'dark'` or a non-transparent
background on `#canopy-status` means the light-mode pin has broken.

---

### 9. Time-relative / live-count cache staleness
```
Type: "How many AI detections are awaiting human review at each site?"
Click: Run Query. Wait: 35s.
Evaluate: document.querySelectorAll('[role="tabpanel"]')[0].innerText
Note: the pending count shown in the Answer tab (e.g. "22,757 pending")

Click: Run Query again (same question still in box). Wait: 3s.
Verify:
  - ⚡ "Loaded from your recent queries" appears in timing footer
  - Count is IDENTICAL to first run
  - ⚠️ Data notes mentions cache / 24-hour freshness caveat
  - Screenshot both Answer tab results side-by-side

This demonstrates the staleness window: any validation work done between the
two clicks is not reflected. This is expected behaviour within the 24h TTL,
but must be noted in ⚠️ Data notes for live-count queries.
```

---

## Reading Results

### Get full response text
```javascript
// All three tab panels:
document.querySelectorAll('[role="tabpanel"]')[0].innerText  // Answer tab
document.querySelectorAll('[role="tabpanel"]')[1].innerText  // Full data table tab
document.querySelectorAll('[role="tabpanel"]')[2].innerText  // Database query tab
```

### Click tabs
```
[role='tab']:has-text('Answer')
[role='tab']:has-text('Full data table')
[role='tab']:has-text('Database query')
```

### Wait for query completion
```
browser_wait_for: 35000   ← first run (cold, no cache)
browser_wait_for: 5000    ← cache hit
```

---

## What to Screenshot

| Screenshot name | What it checks |
|---|---|
| `initial.png` | First-open state, history clean, idle prompt visible |
| `q1-answer.png` | Response tab after happy path query |
| `q1-results.png` | Full data table tab |
| `q1-sql.png` | Database query tab with dev timing comment |
| `cache-hit.png` | "⚡ Loaded" timing footer |
| `oos-response.png` | Out-of-scope structured response |
| `empty-query.png` | Guard for blank input |
| `history-click.png` | Auto-run from history |

---

## Cleanup After Testing
```bash
# Kill background UI process
kill $(lsof -ti:7860) 2>/dev/null || true
# Remove screenshots from project root
rm -f canopy-*.png *.png .playwright-mcp/ 2>/dev/null || true
```

---

## Skills That Should Trigger This Protocol

| Skill | When to invoke Playwright |
|---|---|
| `/verify` | Always when UI files changed (app.py, schema.py) |
| `/dev-loop` | After any UI-touching implementation step |
| `/code-review` | Optionally, to validate reviewer findings against live behaviour |
| `/ux-designer` | After applying UX spec changes to confirm layout matches spec |

---

## Known Playwright MCP Limitations (Canopy context)

- `browser_wait_for` uses wall-clock time, not event-based — always overshoot by 10s for safety
- `ref=eXXX` element selectors are session-specific — use CSS selectors or `:has-text()` instead
- Screenshots capture CSS pixels at 1x scale — full-page screenshots may be small; use `browser_evaluate` for text content verification
- Tab panel selector `[role="tabpanel"]` resolves to 3 elements — use `[0]`, `[1]`, `[2]` index in JS
