# S00 Move dependency management to uv

Size M. Depends: none. Status: todo. Metric: V3 (setup time), reproducibility.

**Goal.** One source of truth for dependencies (`pyproject.toml`), a committed lockfile (`uv.lock`), and every entry point
(local, pre-commit, CI, both Dockerfiles) running through uv.

**Why.** Dependencies live in two `requirements.txt` files, inline `pip install` lines in CI, and the Dockerfiles, with no lockfile.
That drift is what broke commits on 2026-10-05: the local environment had `mcp` 2.x while CI pins `<2`, and the pre-commit contract
runs the whole suite. A lockfile makes the environment the same everywhere. uv still reads `pyproject.toml`; it replaces pip,
venv and requirements files, not TOML.

**Load.** `pyproject.toml`, `servers/core/requirements.txt`, `servers/code/requirements.txt`, both Dockerfiles,
`.github/workflows/ci.yml`, `scripts/generate_precommit_hook.py`, `Makefile` (python and pytest lines), any test that reads `requirements.txt`.

**Verify first.** Docker daemon is running for an image build. The CPU-only torch index works for linux through uv sources, and macOS resolves from PyPI.

**Build.**
- `[project]` with `requires-python >=3.13`, `package = false`, shared deps, and dependency groups: `dev` (pytest, pytest-cov, ruff), `core-server` (adds langfuse, torch, sentence-transformers), `code-server`.
- torch from the PyTorch CPU index on linux only; keep the `mcp<2` pin and its comment.
- Commit `uv.lock`. Python is pinned once, by `requires-python` in `pyproject.toml`.
- Dockerfiles install with `uv sync --frozen --no-install-project --only-group ...` using the uv image copy.
- CI uses `astral-sh/setup-uv`, `uv sync --frozen`, `uv run`.
- Pre-commit hook generator runs `uv run --frozen` when uv exists, else the old commands.
- Delete both `requirements.txt` files and update references in docs and scripts.

**Tests.** Full suite green under `uv run`; both Docker images build; CI config parses; a test that `uv lock --check` passes (lock matches pyproject).

**Out of scope.** Changing any dependency version beyond what the lock resolves.

**DoD.** Standard DoD. Cold setup is `uv sync` and `uv run pytest`.

**Kill criterion.** If an image build gets slower or larger than the pip build by more than 20%, tune layers before merging.

**Handoff.** Setup time before and after; image sizes.
