#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/validate_release.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/validation"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
rm -rf "$OUT" "$ROOT/build" "$ROOT/dist" "$ROOT/.pytest_cache"
find "$ROOT/src" -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +
find "$ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
mkdir -p "$OUT/dist" "$OUT/logs"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1784592000}"

run() {
  name="$1"; shift
  printf '== %s ==\n' "$name"
  "$@" >"$OUT/logs/$name.txt" 2>&1
  cat "$OUT/logs/$name.txt"
}

# Metadata and manifest are generated before tests so recursive regression tests
# inspect the exact source tree under validation.
python3 tools/assurance/apply_l9_meta.py >"$OUT/logs/l9_meta_apply.txt"
python3 tools/assurance/generate_manifest.py >/dev/null

run pytest pytest -q
run compileall python3 -m compileall -q src tests tools scripts
find "$ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
run adr_validation python3 tools/assurance/validate_adrs.py
run harvest_coverage python3 tools/assurance/validate_harvest_coverage.py
run l9_meta python3 tools/assurance/check_l9_meta.py
run layer_boundaries python3 tools/assurance/check_layer_boundaries.py
run recursive_alignment python3 tools/assurance/check_recursive_alignment.py
run bypass_check python3 tools/assurance/check_memory_write_bypass.py
run config_drift python3 tools/assurance/check_config_drift.py
run wiring_audit python3 tools/assurance/audit_package_wiring.py
run source_quality python3 tools/assurance/check_source_quality.py
run committed_secrets python3 tools/assurance/check_secrets.py
run local_benchmark python3 tools/assurance/benchmark_local.py --iterations 40
python3 tools/assurance/generate_manifest.py >/dev/null
run preflight bash scripts/preflight.sh
for hook in hooks/*.sh scripts/*.sh; do bash -n "$hook"; done
printf 'All shell files parse.\n' > "$OUT/logs/shell_syntax.txt"

run wheel_build python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir "$OUT/dist"
WHEEL="$(find "$OUT/dist" -maxdepth 1 -name '*.whl' -print -quit)"
[ -n "$WHEEL" ]
SITE="$TMP_ROOT/wheel-site"
RUN_DIR="$TMP_ROOT/installed-run"
mkdir -p "$SITE" "$RUN_DIR"
python3 -m pip install --target "$SITE" --force-reinstall --no-deps "$WHEEL" >"$OUT/logs/wheel_install.txt" 2>&1
TMP_DATA="$TMP_ROOT/installed-smoke"
(
  cd "$RUN_DIR"
  PYTHONPATH="$SITE" L9_MEMORY_DATA_DIR="$TMP_DATA/data" L9_MEMORY_STATE_DIR="$TMP_DATA/state" \
    python3 -m l9_graphite_memory resolve --group-id l9-graphiti-memory >"$OUT/logs/installed_resolve.txt"
  PYTHONPATH="$SITE" L9_MEMORY_DATA_DIR="$TMP_DATA/data" L9_MEMORY_STATE_DIR="$TMP_DATA/state" \
    python3 -m l9_graphite_memory health >"$OUT/logs/installed_health.txt"
  PYTHONPATH="$SITE" L9_MEMORY_DATA_DIR="$TMP_DATA/data" L9_MEMORY_STATE_DIR="$TMP_DATA/state" \
    python3 - <<'PYSMOKE' >"$OUT/logs/installed_mcp.txt"
import sys
from importlib.metadata import distribution
from importlib.resources import files
from l9_graphite_memory.integrations import GateMemoryBridge
from l9_graphite_memory.mcp_tools import tool_definitions
names={item['name'] for item in tool_definitions()}
assert {'memory.ingest','memory.delete','memory.distill','memory.synthesize_procedures','write'} <= names
assert files('l9_graphite_memory').joinpath('resources/group_registry.yaml').is_file()
assert GateMemoryBridge.__name__ == 'GateMemoryBridge'
eps={ep.name for ep in distribution('l9-graphite-memory').entry_points}
assert {'l9-memory','l9-memory-server','l9-memory-worker'} <= eps
sys.stdout.write(f'{len(names)} tools loaded; entrypoints, constellation bridge, and resources present\n')
PYSMOKE
)
(cd "$OUT/dist" && sha256sum *.whl) > "$OUT/SHA256SUMS"
run validation_evidence python3 tools/assurance/generate_validation_evidence.py
rm -rf "$ROOT/build"
find "$ROOT/src" -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +
find "$ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
rm -rf "$ROOT/.pytest_cache"

# Seal all evidence, validate it, add the validation log, and reseal.
python3 tools/assurance/generate_manifest.py >/dev/null
python3 tools/assurance/validate_manifest.py >"$OUT/logs/manifest_validation.txt"
python3 tools/assurance/generate_manifest.py >/dev/null
python3 tools/assurance/validate_manifest.py
printf 'Release validation complete. Evidence: %s\n' "$OUT"
