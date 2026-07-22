#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/activate_guard.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TARGET="${HOME}/.local/share/l9-memory/hooks"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    -h|--help) printf 'Usage: %s [--target DIRECTORY]\n' "$0"; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
mkdir -p "$TARGET"
cp "$ROOT"/hooks/*.sh "$TARGET"/
chmod 0755 "$TARGET"/*.sh
printf 'Installed L9 memory receipt-guard hooks to %s\n' "$TARGET"
printf 'Start with L9_MEMORY_WRITE_GATES=0; enable only after hydration and phase-lock evidence checks pass.\n'
