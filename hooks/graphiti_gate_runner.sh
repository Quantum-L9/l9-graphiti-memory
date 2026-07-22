#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: hooks/graphiti_gate_runner.sh
#   layer: hook
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# Run the local-only memory receipt guard; fail closed only when enforcement is enabled.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=graphiti_common.sh
. "$SCRIPT_DIR/graphiti_common.sh"
MODE="${1:?mode required}"
INPUT="$(cat)"
if command -v python3 >/dev/null 2>&1 && OUT="$(printf '%s' "$INPUT" | python3 -m l9_graphite_memory.memory_guard "$MODE" 2>/dev/null)"; then
  printf '%s\n' "$OUT"
  exit 0
fi
if l9_memory_gates_enabled; then
  printf '%s\n' '{"permission":"deny","user_message":"L9 memory guard unavailable; enforcement is fail-closed"}'
else
  printf '%s\n' '{"permission":"allow"}'
fi
