#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: hooks/graphiti-session-end.sh
#   layer: hook
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# Persist a session summary through the canonical CLI; no direct LLM or database calls.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=graphiti_common.sh
. "$SCRIPT_DIR/graphiti_common.sh"
l9_memory_enabled || exit 0
REPO="${CURSOR_PROJECT_DIR:-}"
[ -n "$REPO" ] || exit 0
l9_memory_scaffold_bank "$REPO"
INPUT="$(cat 2>/dev/null || true)"
SUMMARY="$(INPUT="$INPUT" python3 - <<'PYCODE'
import json
import os
import sys
raw = os.environ.get("INPUT", "")
try:
    data = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    sys.stdout.write(raw[:4000] + "\n")
else:
    sys.stdout.write(str(data.get("summary") or data.get("session_summary") or data.get("message") or data.get("text") or "") + "\n")
PYCODE
)"
[ -n "$SUMMARY" ] || exit 0
TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
BANK="$REPO/memory-bank"
cat > "$BANK/activeContext.md" <<EOF
# Active Context

- Last session: $TIMESTAMP
- Repository: $REPO
- Branch: $(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || printf 'unknown')

## Summary

$SUMMARY
EOF
if ! (cd "$REPO" && l9_memory_cli write "$SUMMARY" --kind episodic --source cursor-session --source-id "${CURSOR_CONVERSATION_ID:-default}" --tag session-summary >/dev/null); then
  printf '%s\n' 'L9 memory session write failed; local memory-bank was still updated' >&2
fi
