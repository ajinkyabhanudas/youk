YOUK_DIR := $(HOME)/.claude/youk
CLAUDE_DIR := $(HOME)/.claude

.PHONY: build rebuild clean test test-core test-code install update

build:
	docker build -t youk-core:latest -f servers/core/Dockerfile .
	docker build -t youk-code:latest -f servers/code/Dockerfile .

rebuild: clean build

clean:
	docker rmi youk-core:latest youk-code:latest 2>/dev/null || true

test: test-core test-code

MCP_HANDSHAKE = printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}\n{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
MCP_PARSE = python3 -c "import sys,json; [print('Tools:', [t['name'] for t in json.loads(l).get('result',{}).get('tools',[])]) for l in sys.stdin if '\"id\":2' in l]"

test-core:
	@echo "==> Testing youk-core tools/list..."
	@$(MCP_HANDSHAKE) | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude \
	    -v $(YOUK_DIR):/youk \
	    youk-core:latest 2>/dev/null | $(MCP_PARSE)
	@echo "    youk-core OK"

test-code:
	@echo "==> Testing youk-code tools/list..."
	@$(MCP_HANDSHAKE) | \
	  docker run -i --rm \
	    -v $(CLAUDE_DIR):/claude:ro \
	    -v $(YOUK_DIR):/youk:ro \
	    youk-code:latest 2>/dev/null | $(MCP_PARSE)
	@echo "    youk-code OK"

install: build
	@bash scripts/install.sh

update:
	git pull --rebase
	$(MAKE) rebuild
