#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: hooks/graphiti_common.sh
#   layer: hook
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# Shared, package-agnostic helpers for L9 memory hooks.
set -u

l9_memory_cli() {
  if command -v l9-memory >/dev/null 2>&1; then
    command l9-memory "$@"
  else
    python3 -m l9_graphite_memory "$@"
  fi
}

l9_memory_enabled() {
  case "${L9_MEMORY_ENABLED:-${GRAPHITI_MEMORY_ENABLED:-1}}" in
    0|false|False|no|NO) return 1 ;;
    *) return 0 ;;
  esac
}

l9_memory_gates_enabled() {
  case "${L9_MEMORY_WRITE_GATES:-${GRAPHITI_WRITE_GATES:-0}}" in
    1|true|True|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

l9_memory_state_dir() {
  printf '%s\n' "${L9_MEMORY_STATE_DIR:-$HOME/.local/state/l9-memory}"
}

l9_memory_state_file() {
  local conversation="${CURSOR_CONVERSATION_ID:-${L9_SESSION_ID:-default}}"
  printf '%s/%s.json\n' "$(l9_memory_state_dir)" "$conversation"
}

l9_memory_scaffold_bank() {
  local repo="${1:-${CURSOR_PROJECT_DIR:-}}"
  [ -n "$repo" ] || return 0
  local bank="$repo/memory-bank"
  mkdir -p "$bank"
  for name in activeContext.md tasks.md progress.md tech-debt.md; do
    if [ ! -f "$bank/$name" ]; then
      printf '# %s\n\n' "$name" > "$bank/$name"
    fi
  done
}
