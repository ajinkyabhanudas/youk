YOUK_DIR  := $(HOME)/.claude/youk
CLAUDE_DIR := $(HOME)/.claude

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nyouk\n\n"} \
	  /^[a-zA-Z_-]+:.*?##/ { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ── Coverage ───────────────────────────────────────────────────────────────────

.PHONY: coverage-badge
coverage-badge: ## Run health.py coverage and print the badge URL with current number
	@PCT=$$(python -m pytest tests/ -q --cov=servers/core/src --cov-report=term 2>&1 \
	  | grep 'servers/core/src/health\.py' | tail -1 | awk '{print $$4}' | tr -d '%'); \
	echo "health.py coverage: $${PCT}%"; \
	echo "Badge URL: https://img.shields.io/badge/health.py%20coverage-$${PCT}%25-4CAF50"; \
	echo "Update README.md badge line with the new percentage."

# ── Core lifecycle ─────────────────────────────────────────────────────────────

.PHONY: install
install: ## First-time setup: build images, register MCP servers, patch CLAUDE.md
	@bash scripts/install.sh

.PHONY: update
update: ## Pull latest + rebuild images + prune stale containers
	git pull --rebase
	$(MAKE) rebuild
	@$(MAKE) --no-print-directory _prune-stale-containers

.PHONY: build
build: ## Build both Docker images
	docker build -t youk-core:latest -f servers/core/Dockerfile .
	docker build -t youk-code:latest -f servers/code/Dockerfile .
	@docker image prune -f --filter label!=keep 2>/dev/null | grep -v "^Total" || true
	@$(MAKE) --no-print-directory _prune-stale-containers

# Internal target — stop youk containers whose image SHA no longer matches :latest.
# Called automatically by build and update; also used by prune for manual runs.
# Safe during active sessions: containers on the current SHA are never touched.
.PHONY: _prune-stale-containers
_prune-stale-containers:
	@CORE_SHA=$$(docker image inspect youk-core:latest --format '{{.Id}}' 2>/dev/null || echo ""); \
	 CODE_SHA=$$(docker image inspect youk-code:latest --format '{{.Id}}' 2>/dev/null || echo ""); \
	 docker ps --format '{{.ID}} {{.Image}}' 2>/dev/null | grep -E 'youk-(core|code)' | \
	 while read -r cid img; do \
	   sha=$$(docker inspect $$cid --format '{{.Image}}' 2>/dev/null || echo ""); \
	   if [ -n "$$sha" ] && [ "$$sha" != "$$CORE_SHA" ] && [ "$$sha" != "$$CODE_SHA" ]; then \
	     echo "    stopping stale $$cid ($$img)"; \
	     docker stop $$cid >/dev/null 2>&1 || true; \
	   fi; \
	 done
	@docker container prune -f >/dev/null 2>&1 || true

.PHONY: rebuild
rebuild: clean build ## Full rebuild from scratch (removes cached layers)

# Note: servers/ source code is live from the volume mount — no rebuild needed for code changes.
# Only rebuild when requirements.txt or servers/shared/ changes.
# After rebuild, restart Claude Code to pick up new dependencies.



.PHONY: clean
clean: ## Remove Docker images and stopped containers
	docker rmi youk-core:latest youk-code:latest 2>/dev/null || true
	@docker container prune -f 2>/dev/null || true
	@docker image prune -f 2>/dev/null || true

.PHONY: prune
prune: ## Stop orphaned youk containers (old image SHAs) and remove dangling layers
	@echo "==> Pruning stale youk containers..."
	@$(MAKE) --no-print-directory _prune-stale-containers
	@docker image prune -f >/dev/null 2>&1 || true
	@echo "==> Done. Active youk containers:"
	@docker ps --format "  {{.Names}} ({{.Status}}) {{.Image}}" | grep youk || echo "  none"

# Default idle threshold in hours. Override: make prune-idle IDLE_HOURS=4
IDLE_HOURS ?= 8

.PHONY: prune-idle
prune-idle: ## Stop youk containers running >8h (orphaned from closed sessions). Override: IDLE_HOURS=4
	@echo "==> Scanning for idle youk containers (running >$(IDLE_HOURS)h)..."
	@NOW=$$(date +%s); \
	STOPPED=0; KEPT=0; \
	for CID in $$(docker ps --format "{{.ID}} {{.Image}}" 2>/dev/null | grep "youk-" | awk '{print $$1}'); do \
	  IMAGE=$$(docker inspect $$CID --format '{{.Config.Image}}' 2>/dev/null); \
	  STARTED=$$(docker inspect $$CID --format '{{.State.StartedAt}}' 2>/dev/null); \
	  STARTED_TRIM=$$(echo "$$STARTED" | sed 's/\.[0-9]*Z*$$//'); \
	  STARTED_S=$$(date -jf "%Y-%m-%dT%H:%M:%S" "$$STARTED_TRIM" +%s 2>/dev/null \
	              || date -d "$$STARTED_TRIM" +%s 2>/dev/null || echo 0); \
	  AGE_H=$$(( ($$NOW - $$STARTED_S) / 3600 )); \
	  NAME=$$(docker inspect $$CID --format '{{.Name}}' 2>/dev/null | sed 's|/||'); \
	  if [[ $$AGE_H -ge $(IDLE_HOURS) ]]; then \
	    echo "    stopping $$NAME ($$IMAGE, $${AGE_H}h old)"; \
	    docker stop $$CID >/dev/null 2>&1; \
	    STOPPED=$$((STOPPED+1)); \
	  else \
	    echo "    keeping  $$NAME ($$IMAGE, $${AGE_H}h old)"; \
	    KEPT=$$((KEPT+1)); \
	  fi; \
	done; \
	echo ""; \
	if [[ $$STOPPED -eq 0 ]]; then \
	  echo "    Nothing stopped — no youk containers older than $(IDLE_HOURS)h."; \
	else \
	  echo "    $$STOPPED stopped, $$KEPT kept."; \
	  echo "    Note: if any stopped container belonged to an open Claude Code window,"; \
	  echo "    restart that window to reconnect (MCP spawns a fresh container)."; \
	fi

# ── Verification ───────────────────────────────────────────────────────────────

.PHONY: doctor
doctor: ## Health check — every failure includes a Fix: line
	@bash scripts/doctor.sh

.PHONY: test
test: test-unit test-core test-code ## Run all tests: unit + MCP handshakes

.PHONY: test-unit
test-unit: ## Run unit tests (no Docker required)
	pytest tests/ -v

MCP_INIT = {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}
MCP_DONE = {"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
MCP_LIST = {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}

.PHONY: test-core
test-core: ## Test youk-core MCP handshake
	@echo "==> youk-core"
	@printf '$(MCP_INIT)\n$(MCP_DONE)\n$(MCP_LIST)\n' | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude \
	    -v $(YOUK_DIR):/youk \
	    youk-core:latest 2>/dev/null | python3 scripts/parse_mcp_tools.py
	@echo "    OK"

.PHONY: test-code
test-code: ## Test youk-code MCP handshake
	@echo "==> youk-code"
	@printf '$(MCP_INIT)\n$(MCP_DONE)\n$(MCP_LIST)\n' | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude:ro \
	    -v $(YOUK_DIR):/youk:ro \
	    youk-code:latest 2>/dev/null | python3 scripts/parse_mcp_tools.py
	@echo "    OK"

.PHONY: health-check
health-check: ## Run self_heal autonomously via Docker MCP — safe for cron
	@python3 scripts/health_check.py

.PHONY: dashboard
dashboard: ## Terminal dashboard — org score, session history, skill gaps, proposals
	@python3 scripts/dashboard.py

.PHONY: report
report: ## Write HTML dashboard to ~/.claude/youk/reports/dashboard-YYYY-MM-DD.html
	@python3 scripts/dashboard.py --html

.PHONY: export-stats
export-stats: ## Export session stats to STATS.md — shareable evidence of compounding
	@python3 scripts/export_stats.py

.PHONY: eval-routing
eval-routing: ## Routing accuracy eval — 20 labelled cases vs config/routes.yaml heuristic
	@python3 scripts/eval_routing.py

# ── Code quality ──────────────────────────────────────────────────────────────

.PHONY: verify-mcp
verify-mcp: ## Test both MCP container handshakes
	@echo "==> youk-core handshake"
	@printf '$(MCP_INIT)\n$(MCP_DONE)\n' | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude \
	    -v $(YOUK_DIR):/youk \
	    youk-core:latest 2>/dev/null \
	  | python3 -c "import sys,json; lines=[l for l in sys.stdin if l.strip()]; \
	      d=json.loads(lines[0]) if lines else {}; \
	      print('  youk-core: OK') if 'result' in d else print('  youk-core: FAIL — check docker logs')" \
	  || echo "  youk-core: FAIL — container did not start"
	@echo "==> youk-code handshake"
	@printf '$(MCP_INIT)\n$(MCP_DONE)\n' | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude:ro \
	    -v $(YOUK_DIR):/youk:ro \
	    youk-code:latest 2>/dev/null \
	  | python3 -c "import sys,json; lines=[l for l in sys.stdin if l.strip()]; \
	      d=json.loads(lines[0]) if lines else {}; \
	      print('  youk-code: OK') if 'result' in d else print('  youk-code: FAIL — check docker logs')" \
	  || echo "  youk-code: FAIL — container did not start"

.PHONY: simulate
simulate: ## Run simulate-experience skill — developer experience audit, feeds self-heal loop
	@echo "==> simulate-experience: audit youk from developer perspective"
	@echo "    Output: [SIMULATION REPORT] block + add_proposal() calls for each finding"
	@echo "    Run inside a Claude Code session: /simulate or route_to_skill('simulate-experience', 'full audit')"
	@echo ""
	@echo "    For automated MCP-based run:"
	@python3 -c "import json,sys; print(json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'route_to_skill','arguments':{'skill_name':'simulate-experience','task':'full audit — all personas'}}}))" | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude:ro \
	    -v $(YOUK_DIR):/youk:ro \
	    youk-code:latest 2>/dev/null | python3 -m json.tool || true

.PHONY: lint
lint: ## Run ruff on servers/
	ruff check servers/

.PHONY: relay-check
relay-check: ## Verify RELAY/ against Gate Packaging Manifest; prints echo block for gate message
	@bash scripts/relay_check.sh
