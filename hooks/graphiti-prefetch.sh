#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: hooks/graphiti-prefetch.sh
#   layer: hook
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# Hydrate task context and write an evidence-bearing local gate state.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=graphiti_common.sh
. "$SCRIPT_DIR/graphiti_common.sh"
l9_memory_enabled || exit 0
l9_memory_scaffold_bank "${CURSOR_PROJECT_DIR:-}"
TASK="${1:-session start}"
REPO="${CURSOR_PROJECT_DIR:-$PWD}"
if (cd "$REPO" && l9_memory_cli inject "$TASK" >/dev/null); then
  exit 0
fi
printf '%s\n' 'L9 memory prefetch failed' >&2
if l9_memory_gates_enabled; then
  exit 1
fi
exit 0
