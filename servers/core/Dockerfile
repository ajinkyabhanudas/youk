FROM python:3.13-slim@sha256:bffeb7bd6a85767587059c6ba23e1e9122078e3aa3fa836099171b9bb5a9bb00 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

# Install from the lockfile into /opt/venv. torch resolves to the CPU-only wheel on linux
# (see pyproject.toml), so this runs no-GPU, offline, no vendor API.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock /build/
RUN cd /build && uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim@sha256:bffeb7bd6a85767587059c6ba23e1e9122078e3aa3fa836099171b9bb5a9bb00

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Bake the embedding model weights into the image so semantic_similarity.py
# never needs network access at runtime -- local-first, not a hidden API call.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY servers/shared/ /shared/

# Source is NOT baked in — read live from /youk volume mount.
# Code changes take effect on next Claude Code restart without rebuild.
# Only rebuild when pyproject.toml, uv.lock or servers/shared/ changes.
WORKDIR /youk/servers/core/src

CMD ["python", "server.py"]
