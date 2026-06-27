# Building a youk Variant

A variant is a domain-specialized MCP server that shares youk's core infrastructure. Each variant is one Docker image, one server.py, and one registration.

---

## The pattern

Every variant follows the same structure:

```
servers/
└── {variant-name}/
    ├── Dockerfile
    ├── requirements.txt
    └── src/
        └── server.py
```

The `servers/shared/` modules are available in every container at `/shared/`. This gives all variants access to:
- `models.py` — shared dataclasses
- `guardrails.py` — hard/soft rule enforcement
- `skill_loader.py` — reads SKILL.md files from the volume mount

---

## Example: building youk-pm

### 1. Create the server directory

```bash
mkdir -p ~/.claude/youk/servers/pm/src
```

### 2. Write the server

```python
# servers/pm/src/server.py
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from mcp.server.fastmcp import FastMCP
from skill_loader import load_skill, list_skills

mcp = FastMCP("youk-pm")

@mcp.tool()
def pm_review(task: str, context: dict | None = None) -> dict:
    """Run the pm-review skill against a task."""
    skill_content = load_skill("pm-review")
    # ... API call with skill_content as system prompt
    return {"result": output}

@mcp.tool()
def write_spec(task: str, context: dict | None = None) -> str:
    """Generate a product spec for a feature."""
    skill_content = load_skill("write-spec")
    # ... API call
    return output

@mcp.tool()
def create_adr(decision: str, context: dict | None = None) -> str:
    """Create an Architecture Decision Record."""
    skill_content = load_skill("adr")
    # ... API call
    return output

if __name__ == "__main__":
    mcp.run()
```

### 3. Write the Dockerfile

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY servers/pm/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY servers/shared/ /shared/
COPY servers/pm/src/ .
CMD ["python", "server.py"]
```

### 4. Add to Makefile

In the `build` target, add:
```makefile
docker build -t youk-pm:latest -f servers/pm/Dockerfile .
```

### 5. Add to variants.yaml

```yaml
variants:
  - name: youk-pm
    status: active
    description: Product management — specs, ADRs, pm-review
    skills: [pm-review, write-spec, adr, stress-test]
    volume_access: read-only
```

### 6. Build and register

```bash
cd ~/.claude/youk
make build  # builds all variants including youk-pm

claude mcp add --scope user youk-pm --transport stdio -- \
  docker run -i --rm \
  -v "$HOME/.claude:/claude:ro" \
  -v "$HOME/.claude/youk:/youk:ro" \
  -e ANTHROPIC_API_KEY \
  youk-pm:latest
```

That's it. youk-pm's tools are now available in every Claude Code session alongside youk-core and youk-code.

---

## Volume access

**Read-write** (only youk-core should need this):
```
-v "$HOME/.claude:/claude"
-v "$HOME/.claude/youk:/youk"
```

**Read-only** (all other variants):
```
-v "$HOME/.claude:/claude:ro"
-v "$HOME/.claude/youk:/youk:ro"
```

If a variant needs to write (e.g., to a per-variant state directory), discuss it first. Uncontrolled writes to the shared volume break the audit trail.

---

## Planned variants

| Variant | Domain | Key tools |
|---|---|---|
| youk-pm | Product management | pm_review, write_spec, create_adr, stress_test |
| youk-research | Research + synthesis | web_search, synthesize, learn |
| youk-design | UX + design systems | ux_review, accessibility_check, component_spec |
| youk-analytics | Production feedback | query_metrics, error_analysis, performance_report |

If you build one of these, open a PR.
