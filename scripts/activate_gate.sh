#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/activate_gate.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# Deprecated compatibility wrapper. The implementation is a local receipt guard, not constellation Gate.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "$ROOT/scripts/activate_guard.sh" "$@"
