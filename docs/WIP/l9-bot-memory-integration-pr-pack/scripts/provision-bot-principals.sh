#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/provision-bot-principals.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-30

# Generates a fresh L9_MEMORY_AUTH_TOKENS_FILE mapping for the two consumer
# bots that build a GraphitiMemoryClient directly (Website-Bot, SEO-Bot).
# LLM-Router never authenticates on its own: it receives an
# already-constructed client from its caller (see
# repos/LLM-Router/files/src/memory.ts), so it needs no principal here.
#
# Never writes tokens into this repository or the pack. Output goes only to
# the path you supply, which must live outside any git worktree you intend
# to commit.
#
# Usage: ./provision-bot-principals.sh /path/outside/repo/tokens.json
set -euo pipefail
OUT=${1:-}
[[ -n "$OUT" ]] || { echo "Usage: $0 <output-json-path-outside-any-repo>" >&2; exit 64; }
case "$OUT" in
  "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"/*)
    echo "Refusing: output path is inside this repository" >&2; exit 65 ;;
esac

WEBSITE_TOKEN=$(openssl rand -hex 32)
SEO_TOKEN=$(openssl rand -hex 32)

# Shared tenant_id is deliberate, not an oversight: AUTHORITY.md states
# l9-graphiti-memory is "the sole shared cognitive-memory authority for
# Website-Bot, SEO-Bot, and LLM-Router." Authorization here is enforced at
# two independent layers -- NamespacePolicy (per-action namespace globs) and
# a hard tenant_id equality check on every record (services/memory_service.py,
# ADR-006: "no cross-tenant record is returned even if record ID is known").
# Different tenant_id values would silo each bot's writes from the other
# even inside the identical client:<id> namespace. Verified live on
# 2026-07-30: with a shared tenant_id, seo-bot could memory.get a record
# website-bot wrote into client:acme-corp; with distinct tenant_ids the
# same call failed closed with "record belongs to a different tenant".
#
# promote_namespaces is intentionally empty for website-bot: only SEO-Bot's
# services/memory.ts calls memory.promote. Granting it to website-bot would
# widen its authority for no functional reason (AUTHORITY.md invariant 11:
# "No overlay may silently widen principal scope").
cat > "$OUT" <<JSON
{
  "$WEBSITE_TOKEN": {
    "principal_id": "website-bot",
    "tenant_id": "l9-bot-trio",
    "organization_id": "quantum-l9",
    "workspace_id": "website-bot",
    "agent_id": "website-bot",
    "roles": ["consumer-bot"],
    "read_namespaces": ["client:*"],
    "write_namespaces": ["client:*"],
    "promote_namespaces": []
  },
  "$SEO_TOKEN": {
    "principal_id": "seo-bot",
    "tenant_id": "l9-bot-trio",
    "organization_id": "quantum-l9",
    "workspace_id": "seo-bot",
    "agent_id": "seo-bot",
    "roles": ["consumer-bot"],
    "read_namespaces": ["client:*"],
    "write_namespaces": ["client:*"],
    "promote_namespaces": ["client:*"]
  }
}
JSON
chmod 600 "$OUT"
echo "Wrote principal mapping to $OUT (mode 600)." >&2
echo "Set L9_MEMORY_AUTH_TOKENS_FILE=$OUT on the memory server process." >&2
echo "Distribute these two values as secrets, never as committed files:" >&2
echo "  Website-Bot  L9_MEMORY_TOKEN=$WEBSITE_TOKEN" >&2
echo "  SEO-Bot      L9_MEMORY_TOKEN=$SEO_TOKEN" >&2
