#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/test-apply-safety.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TEST=$(mktemp -d)
trap 'rm -rf "$TEST"' EXIT
init_repo() {
  local dir=$1 remote=$2
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" config user.email test@example.com
  git -C "$dir" config user.name pack-test
  git -C "$dir" remote add origin "https://github.com/$remote.git"
}
commit_base() { git -C "$1" add . && git -C "$1" commit -qm base; }
init_repo "$TEST/memory" Quantum-L9/l9-graphiti-memory; echo x > "$TEST/memory/README.md"; commit_base "$TEST/memory"
(cd "$TEST/memory" && ALLOW_UNPINNED_BASE=1 SKIP_LOCKFILE=1 "$ROOT/repos/l9-graphiti-memory/apply.sh" >/dev/null)
test -f "$TEST/memory/clients/typescript/src/index.ts"
init_repo "$TEST/router" Quantum-L9/LLM-Router; echo x > "$TEST/router/README.md"; commit_base "$TEST/router"
(cd "$TEST/router" && ALLOW_UNPINNED_BASE=1 SKIP_LOCKFILE=1 "$ROOT/repos/LLM-Router/apply.sh" >/dev/null)
test -f "$TEST/router/src/index.ts"
init_repo "$TEST/website" Quantum-L9/Website-Bot; mkdir -p "$TEST/website/src/services"; echo '{}' > "$TEST/website/package.json"; echo '# env' > "$TEST/website/.env.example"; echo stub > "$TEST/website/src/services/llm-stub.ts"; commit_base "$TEST/website"
(cd "$TEST/website" && ALLOW_UNPINNED_BASE=1 SKIP_LOCKFILE=1 "$ROOT/repos/Website-Bot/apply.sh" >/dev/null)
test ! -e "$TEST/website/src/services/llm-stub.ts"; grep -q L9_MEMORY_MODE "$TEST/website/.env.example"
init_repo "$TEST/seo" Quantum-L9/SEO-Bot; mkdir -p "$TEST/seo/src/core/database" "$TEST/seo/src/contracts"; echo '{}' > "$TEST/seo/package.json"; echo '# env' > "$TEST/seo/.env.example"; printf "  PERPLEXITY_API_KEY: z.string().min(1),\n" > "$TEST/seo/src/core/config.ts"; printf "  learnings: text('learnings'),\n});\n" > "$TEST/seo/src/core/database/schema.ts"; printf "  registerHandler(jobName: string, handler: (job: Job) => Promise<void>): void {\n" > "$TEST/seo/src/core/scheduler.ts"; echo old > "$TEST/seo/src/contracts/website_factory_v2.ts"; commit_base "$TEST/seo"
(cd "$TEST/seo" && ALLOW_UNPINNED_BASE=1 SKIP_LOCKFILE=1 "$ROOT/repos/SEO-Bot/apply.sh" >/dev/null)
test ! -e "$TEST/seo/src/contracts/website_factory_v2.ts"; grep -q L9_MEMORY_MODE "$TEST/seo/src/core/config.ts"; grep -q memoryRecordId "$TEST/seo/src/core/database/schema.ts"
init_repo "$TEST/wrong" Quantum-L9/SEO-Bot-evil; echo x > "$TEST/wrong/x"; commit_base "$TEST/wrong"
if (cd "$TEST/wrong" && ALLOW_UNPINNED_BASE=1 SKIP_LOCKFILE=1 "$ROOT/repos/SEO-Bot/apply.sh" >/dev/null 2>&1); then echo 'wrong remote accepted' >&2; exit 1; fi
init_repo "$TEST/rollback" Quantum-L9/SEO-Bot; echo x > "$TEST/rollback/keep.txt"; commit_base "$TEST/rollback"
if (cd "$TEST/rollback" && ALLOW_UNPINNED_BASE=1 SKIP_LOCKFILE=1 "$ROOT/repos/SEO-Bot/apply.sh" >/dev/null 2>&1); then echo 'expected transform failure' >&2; exit 1; fi
test -z "$(git -C "$TEST/rollback" status --porcelain)"; test -f "$TEST/rollback/keep.txt"; test ! -e "$TEST/rollback/src"
echo apply-safety-tests-ok
