#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/install.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.4.0
#   updated: 2026-08-04

set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<'TEXT'
uv is required for checkout-based installs (ADR-069).
Install: https://docs.astral.sh/uv/getting-started/installation/
TEXT
  exit 1
fi

# Locked deps only: refuse third-party sdists (--no-build) and skip installing
# this workspace package so sync never executes foreign setup scripts.
uv sync --frozen --no-install-project --no-build --extra dev --extra server
export PATH="$ROOT/.venv/bin:$PATH"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"

"$PYTHON_BIN" -m l9_graphite_memory.cli client cursor install --dry-run >/dev/null
"$PYTHON_BIN" scripts/write_claude_config.py --dry-run >/dev/null
bash scripts/preflight.sh
cat <<'TEXT'
Installation verified (uv sync --frozen --no-install-project --no-build).

Optional next steps:
  source .venv/bin/activate
  export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
  # or: uv run --with-editable . …
  l9-memory client cursor install   # after: uv pip install -e .
  l9-memory client cursor verify
  python scripts/write_claude_config.py
  l9-memory-server --transport stdio

Published package consumers may still use: pip install l9-graphite-memory
TEXT
