#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/install.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "$ROOT"
"$PYTHON_BIN" -m pip install "$ROOT"
"$PYTHON_BIN" -m l9_graphite_memory.cli client cursor install --dry-run >/dev/null
"$PYTHON_BIN" scripts/write_claude_config.py --dry-run >/dev/null
bash scripts/preflight.sh
cat <<'TEXT'
Installation verified.

Optional next steps:
  l9-memory client cursor install
  l9-memory client cursor verify
  python scripts/write_claude_config.py
  l9-memory-server --transport stdio
TEXT
