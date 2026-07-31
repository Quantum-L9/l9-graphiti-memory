#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/test-isolated-contracts.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
run_node_tests() {
  local source_dir=$1
  local temp
  temp=$(mktemp -d)
  cp -R "$source_dir/." "$temp/"
  cat > "$temp/node-shims.d.ts" <<'SHIMS'
declare module 'node:crypto' { export function randomUUID(): string; export function createHash(algorithm: string): { update(value: string): any; digest(encoding: 'hex'): string }; }
declare module 'node:assert/strict' { const assert: any; export default assert; }
declare module 'node:test' { const test: any; export default test; }
SHIMS
  python3 - "$temp/tsconfig.json" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
data=json.loads(p.read_text())
include=data.setdefault('include', [])
if 'node-shims.d.ts' not in include: include.append('node-shims.d.ts')
p.write_text(json.dumps(data, indent=2)+'\n')
PY
  # Unlike the previous harness, compiler diagnostics are fatal. The local
  # shim only supplies unavailable Node ambient declarations; it does not
  # suppress project type errors.
  (cd "$temp" && tsc -p tsconfig.json)
  node --test "$temp"/dist/tests/*.test.js
  rm -rf "$temp"
}
command -v tsc >/dev/null || { echo 'tsc is required for isolated contract tests' >&2; exit 1; }
run_node_tests "$ROOT/repos/l9-graphiti-memory/files/clients/typescript"
run_node_tests "$ROOT/repos/Website-Bot/files/packages/bot-interop"
echo isolated-contract-tests-ok
