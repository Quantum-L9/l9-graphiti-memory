#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/preflight.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
export L9_MEMORY_DATA_DIR="$TMP_ROOT/data"
export L9_MEMORY_STATE_DIR="$TMP_ROOT/state"
export L9_MEMORY_PROJECTION_BACKEND=none

pass=0
run_gate() {
  label="$1"; shift
  if "$@"; then
    printf 'PASS  %s\n' "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL  %s\n' "$label" >&2
    exit 1
  fi
}

run_gate "Python >= 3.10" python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)'
run_gate "package import" python3 -c 'import l9_graphite_memory; assert l9_graphite_memory.__version__ == "2.2.0"'
run_gate "packaged registry" python3 -c 'from importlib.resources import files; assert files("l9_graphite_memory").joinpath("resources/group_registry.yaml").is_file()'
run_gate "schema upcast" python3 -c 'from l9_graphite_memory.schema import schema_registry; r=schema_registry.read_record({"episode_body":"legacy","group_id":"l9-graphiti-memory","kind":"observation","reference_time":"2026-01-01T00:00:00+00:00"}); assert r.schema_version=="2.1.0"'
run_gate "SQLite service write/search" python3 - <<'PY'
from l9_graphite_memory.runtime import build_runtime
from l9_graphite_memory.authz import build_local_principal
from l9_graphite_memory.contracts import MemoryWriteRequest, MemorySearchRequest, Provenance
runtime=build_runtime()
try:
 p=build_local_principal(runtime.settings,read_namespaces=("preflight",),write_namespaces=("preflight",),promote_namespaces=())
 w=runtime.service.write(p,MemoryWriteRequest(namespace="preflight",content="preflight memory",provenance=Provenance(source="preflight")))
 s=runtime.service.search(p,MemorySearchRequest(query="preflight",namespaces=("preflight",)))
 assert w.record_id and len(s.hits)==1
finally:
 runtime.close()
PY
run_gate "MCP inventory" python3 -c 'from l9_graphite_memory.mcp_tools import tool_definitions; names={x["name"] for x in tool_definitions()}; assert {"memory.ingest","memory.search","memory.delete","memory.distill","memory.synthesize_procedures","write","search"} <= names'
run_gate "cursor client dry-run" python3 -m l9_graphite_memory.cli client cursor install --dry-run --path "$TMP_ROOT/cursor/mcp.json"
run_gate "cursor instantiation probe" python3 -m l9_graphite_memory.cli client cursor verify --timeout 60
for hook in "$ROOT"/hooks/*.sh; do run_gate "shell syntax $(basename "$hook")" bash -n "$hook"; done
run_gate "ADR ledger" python3 "$ROOT/tools/assurance/validate_adrs.py"
run_gate "harvest coverage" python3 "$ROOT/tools/assurance/validate_harvest_coverage.py"
run_gate "L9 metadata coverage" python3 "$ROOT/tools/assurance/check_l9_meta.py"
run_gate "layer boundary alignment" python3 "$ROOT/tools/assurance/check_layer_boundaries.py"
run_gate "recursive L9 alignment" python3 "$ROOT/tools/assurance/check_recursive_alignment.py"
run_gate "release manifest" python3 "$ROOT/tools/assurance/validate_manifest.py"
run_gate "write bypass assurance" python3 "$ROOT/tools/assurance/check_memory_write_bypass.py"
run_gate "configuration drift assurance" python3 "$ROOT/tools/assurance/check_config_drift.py"
run_gate "committed secret assurance" python3 "$ROOT/tools/assurance/check_secrets.py"
run_gate "local SLO benchmark" python3 "$ROOT/tools/assurance/benchmark_local.py" --iterations 20
printf 'Preflight complete: %d gates passed.\n' "$pass"
