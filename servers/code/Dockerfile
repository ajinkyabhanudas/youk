FROM python:3.13-slim@sha256:bffeb7bd6a85767587059c6ba23e1e9122078e3aa3fa836099171b9bb5a9bb00 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

# Base dependencies only (no dev, no core-server group: no torch, no langfuse).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock /build/
RUN cd /build && uv sync --frozen --no-default-groups --no-install-project

FROM python:3.13-slim@sha256:bffeb7bd6a85767587059c6ba23e1e9122078e3aa3fa836099171b9bb5a9bb00

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY servers/shared/ /shared/

# Source is NOT baked in — read live from /youk volume mount.
# Code changes take effect on next Claude Code restart without rebuild.
# Only rebuild when pyproject.toml, uv.lock or servers/shared/ changes.
WORKDIR /youk/servers/code/src

CMD ["python", "server.py"]
