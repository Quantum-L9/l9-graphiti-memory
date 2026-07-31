#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/apply-all-source-only.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
if [[ $# -ne 4 ]]; then
  echo "Usage: $0 /path/l9-graphiti-memory /path/LLM-Router /path/Website-Bot /path/SEO-Bot" >&2
  exit 64
fi
PACK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
repos=(l9-graphiti-memory LLM-Router Website-Bot SEO-Bot)
paths=("$1" "$2" "$3" "$4")
for i in 0 1 2 3; do
  echo "Applying ${repos[$i]} source overlay..."
  (cd "${paths[$i]}" && SKIP_LOCKFILE=1 "$PACK_DIR/repos/${repos[$i]}/apply.sh")
done
echo "Source overlays applied. Publish dependencies in the PACK_CONTRACT.yaml merge order before regenerating consumer lockfiles."
