"""Read MCP stdio output, print tool names — skips non-JSON lines."""
import json
import sys

for raw in sys.stdin:
    line = raw.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    tools = msg.get("result", {}).get("tools", [])
    if tools:
        print("    Tools:", [t["name"] for t in tools])
