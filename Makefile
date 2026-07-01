YOUK_DIR  := $(HOME)/.claude/youk
CLAUDE_DIR := $(HOME)/.claude

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nyouk\n\n"} \
	  /^[a-zA-Z_-]+:.*?##/ { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ── Core lifecycle ─────────────────────────────────────────────────────────────

.PHONY: install
install: ## First-time setup: build images, register MCP servers, patch CLAUDE.md
	@bash scripts/install.sh

.PHONY: update
update: ## Pull latest + rebuild images
	git pull --rebase
	$(MAKE) rebuild

.PHONY: build
build: ## Build both Docker images
	docker build -t youk-core:latest -f servers/core/Dockerfile .
	docker build -t youk-code:latest -f servers/code/Dockerfile .

.PHONY: rebuild
rebuild: clean build ## Full rebuild from scratch (removes cached layers)

.PHONY: clean
clean: ## Remove Docker images
	docker rmi youk-core:latest youk-code:latest 2>/dev/null || true

# ── Verification ───────────────────────────────────────────────────────────────

.PHONY: doctor
doctor: ## Health check — every failure includes a Fix: line
	@bash scripts/doctor.sh

.PHONY: test
test: test-core test-code ## Run MCP handshake tests on both servers

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

.PHONY: dashboard
dashboard: ## Terminal dashboard — org score, session history, skill gaps, proposals
	@python3 scripts/dashboard.py

.PHONY: report
report: ## Write HTML dashboard to ~/.claude/youk/reports/dashboard-YYYY-MM-DD.html
	@python3 scripts/dashboard.py --html

# ── Code quality ──────────────────────────────────────────────────────────────

.PHONY: lint
lint: ## Run ruff on servers/
	ruff check servers/
