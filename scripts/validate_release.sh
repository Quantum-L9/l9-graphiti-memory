#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/validate_release.sh
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

# Release validation is OBSERVATIONAL. It reads, hashes, builds into an
# untracked workspace, runs tests, installs temporary artifacts, emits
# temporary evidence, compares, and fails. It never rewrites tracked metadata,
# manifests, validation evidence or source, and never repairs candidate drift.
# Preparation (tools/assurance/apply_l9_meta.py, generate_manifest.py in apply
# mode) is an explicit, separate step that runs before the candidate is frozen.
#
#   L9_RELEASE_EVIDENCE_DIR   evidence workspace (default build/release-validation;
#                             never the tracked validation/ tree)
#   L9_RELEASE_ARTIFACT_DIR   publication mode: validate the wheel/sdist already
#                             present there and build nothing. Unset: build the
#                             artifact set once into the evidence workspace.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
# Prefer the uv-managed venv when present (ADR-069). Wheel-smoke below still
# uses an isolated pip --target install and must not rely on this PATH.
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

# GNU realpath -m is not on Darwin (BSD realpath rejects -m). Same semantics:
# absolute form, collapse . and .., resolve symlinks on the longest existing
# prefix, and keep a not-yet-existing suffix. A string prefix of the raw path
# is not the guard.
canon_path() {
  python3 - "$1" <<'PY'
import os
import sys

path = os.path.abspath(sys.argv[1])
rest = path
missing = []
while rest and rest != os.sep and not os.path.lexists(rest):
    rest, tail = os.path.split(rest)
    missing.append(tail)
if rest and os.path.lexists(rest):
    resolved = os.path.realpath(rest)
else:
    resolved = rest or os.sep
for tail in reversed(missing):
    resolved = os.path.join(resolved, tail)
print(os.path.normpath(resolved))
PY
}

# --- Evidence workspace -------------------------------------------------------
OUT="${L9_RELEASE_EVIDENCE_DIR:-$ROOT/build/release-validation}"
case "$OUT" in
  /*) ;;
  *) OUT="$ROOT/$OUT" ;;
esac
# Canonicalize lexically even when components do not exist yet, so a path such
# as "$ROOT/missing/../validation" is recognized as the tracked tree before
# anything is created or deleted.
OUT="$(canon_path "$OUT")"
ROOT_REAL="$(canon_path "$ROOT")"
case "$OUT" in
  "$ROOT_REAL"/validation|"$ROOT_REAL"/validation/*)
    fail "tracked validation/ is candidate content, not an evidence workspace (set L9_RELEASE_EVIDENCE_DIR elsewhere)" ;;
  "$ROOT_REAL") fail "evidence workspace must not be the repository root" ;;
  *) ;;
esac
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  case "$OUT" in
    "$ROOT_REAL"/*)
      OUT_REL="${OUT#"$ROOT_REAL"/}"
      if [[ -n "$(git -C "$ROOT" ls-files -- "$OUT_REL" | head -n 1)" ]]; then
        fail "evidence workspace $OUT_REL overlaps tracked content"
      fi ;;
    *) ;;
  esac
fi

# --- Release artifact input ---------------------------------------------------
if [[ -n "${L9_RELEASE_ARTIFACT_DIR:-}" ]]; then
  [[ -d "$L9_RELEASE_ARTIFACT_DIR" ]] || fail "L9_RELEASE_ARTIFACT_DIR is not a directory: $L9_RELEASE_ARTIFACT_DIR"
  ART="$(cd -- "$L9_RELEASE_ARTIFACT_DIR" && pwd)"
  ARTIFACT_MODE="publication"
  WHEEL_COUNT="$(find "$ART" -maxdepth 1 -name 'l9_graphite_memory-*.whl' | wc -l | tr -d ' ')"
  [[ "$WHEEL_COUNT" == "1" ]] || fail "publication mode needs exactly one release wheel in $ART (found $WHEEL_COUNT)"
else
  ART="$OUT/dist"
  ARTIFACT_MODE="self-contained"
fi

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
rm -rf "$OUT" "$ROOT/.pytest_cache"
find "$ROOT/src" -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +
find "$ROOT" -path "$ROOT/.venv" -prune -o -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -path "$ROOT/.venv" -prune -o -type f -name '*.pyc' -exec rm -f {} +
mkdir -p "$OUT/logs"
[[ "$ARTIFACT_MODE" == "self-contained" ]] && mkdir -p "$ART"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1784592000}"

run() {
  name="$1"; shift
  printf '== %s ==\n' "$name"
  "$@" >"$OUT/logs/$name.txt" 2>&1
  cat "$OUT/logs/$name.txt"
}

# Digest of every tracked byte: proves the candidate is identical before and
# after validation. Only possible where git can enumerate the candidate.
candidate_digest() {
  if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT" ls-files -z | LC_ALL=C sort -z \
      | while IFS= read -r -d '' entry; do
          [[ -f "$ROOT/$entry" ]] && sha256sum -- "$ROOT/$entry"
        done | sha256sum | cut -d' ' -f1
  else
    printf 'unavailable\n'
  fi
}

# Read-only candidate checks: metadata identity, manifest purity, manifest
# digests. Run before and after substantive validation; a difference is drift
# the candidate owner must repair through explicit preparation, never here.
candidate_integrity() {
  label="$1"
  log="$OUT/logs/candidate_integrity_$label.txt"
  printf '== candidate_integrity_%s ==\n' "$label"
  # Explicit && chaining: `set -e` is suspended inside a list that feeds `||`,
  # so a plain sequence would mask a failing check behind the final printf.
  {
    python3 tools/assurance/apply_l9_meta.py --check \
      && python3 tools/assurance/generate_manifest.py --check \
      && python3 tools/assurance/check_l9_meta.py \
      && python3 tools/assurance/validate_manifest.py \
      && printf 'PASS: candidate integrity (%s)\n' "$label"
  } >"$log" 2>&1 || { cat "$log"; fail "candidate integrity ($label): tracked metadata or manifest drift; prepare and refreeze the candidate"; }
  cat "$log"
}

DIGEST_BEFORE="$(candidate_digest)"
printf 'candidate digest before: %s\n' "$DIGEST_BEFORE" | tee "$OUT/logs/candidate_digest.txt"
candidate_integrity pre

run pytest pytest -q
run compileall python3 -m compileall -q src tests tools scripts
find "$ROOT" -path "$ROOT/.venv" -prune -o -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -path "$ROOT/.venv" -prune -o -type f -name '*.pyc' -exec rm -f {} +
run adr_validation python3 tools/assurance/validate_adrs.py
run projection_manifests python3 tools/assurance/validate_projection_manifests.py config/projections/facts-v8.yaml
run harvest_coverage python3 tools/assurance/validate_harvest_coverage.py
# Product contract (ADR-094): the topology and its derived ProductManifest are
# checked against the bound Quantum-L9/.github semantics when a checkout of it
# is supplied (CI pins one). Global law is read from that checkout, never
# copied into this repository; the manifest check renders, compares, writes nothing.
if [[ -n "${L9_SEMANTIC_AUTHORITY_ROOT:-}" ]]; then
  run product_topology python3 tools/assurance/validate_product_topology.py --authority-root "$L9_SEMANTIC_AUTHORITY_ROOT"
  run product_manifest python3 tools/assurance/generate_product_manifest.py --authority-root "$L9_SEMANTIC_AUTHORITY_ROOT" --check
else
  printf '== product_contract ==\nSKIP: L9_SEMANTIC_AUTHORITY_ROOT not set; topology and ProductManifest not checked against global law\n'
fi
run l9_meta python3 tools/assurance/check_l9_meta.py
run layer_boundaries python3 tools/assurance/check_layer_boundaries.py
run recursive_alignment python3 tools/assurance/check_recursive_alignment.py
run bypass_check python3 tools/assurance/check_memory_write_bypass.py
run config_drift python3 tools/assurance/check_config_drift.py
run wiring_audit python3 tools/assurance/audit_package_wiring.py
run source_quality python3 tools/assurance/check_source_quality.py
run committed_secrets python3 tools/assurance/check_secrets.py
run local_benchmark python3 tools/assurance/benchmark_local.py --iterations 40
run preflight bash scripts/preflight.sh
for hook in hooks/*.sh scripts/*.sh; do bash -n "$hook"; done
printf 'All shell files parse.\n' > "$OUT/logs/shell_syntax.txt"

# --- Release artifact set ------------------------------------------------------
if [[ "$ARTIFACT_MODE" == "self-contained" ]]; then
  # Build the wheel and sdist once with the locked `build` package (dev extra)
  # into the untracked evidence workspace. uv-managed environments do not ship
  # pip by default (ADR-069).
  run wheel_build python3 -m build --outdir "$ART"
  rm -rf "$ROOT/build/lib" "$ROOT/build/bdist".*
  find "$ROOT/src" -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +
fi
WHEEL="$(find "$ART" -maxdepth 1 -name 'l9_graphite_memory-*.whl' -print -quit)"
[[ -n "$WHEEL" ]] || fail "no release wheel in $ART"
(cd "$ART" && LC_ALL=C sha256sum -- *) > "$OUT/SHA256SUMS"
{
  printf 'artifact mode: %s\n' "$ARTIFACT_MODE"
  printf 'artifact directory: %s\n' "$ART"
  cat "$OUT/SHA256SUMS"
} > "$OUT/logs/release_artifacts.txt"
printf '== release_artifacts ==\n'; cat "$OUT/logs/release_artifacts.txt"

# The wheel installed for smoke and consumer proof is the exact file from the
# selected artifact set; record its digest and prove it is in the set.
SITE="$TMP_ROOT/wheel-site"
RUN_DIR="$TMP_ROOT/installed-run"
mkdir -p "$SITE" "$RUN_DIR"
install_wheel() {
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python python3 --target "$SITE" --reinstall --no-deps "$WHEEL"
  else
    python3 -m pip install --target "$SITE" --force-reinstall --no-deps "$WHEEL"
  fi
}
install_wheel >"$OUT/logs/wheel_install.txt" 2>&1
WHEEL_DIGEST="$(sha256sum -- "$WHEEL" | cut -d' ' -f1)"
if grep -q "^$WHEEL_DIGEST  $(basename -- "$WHEEL")\$" "$OUT/SHA256SUMS"; then
  printf 'installed wheel: %s\ninstalled wheel sha256: %s\ninstalled wheel digest matches validated artifact set\n' \
    "$(basename -- "$WHEEL")" "$WHEEL_DIGEST" > "$OUT/logs/installed_wheel_digest.txt"
else
  fail "installed wheel digest is not in the validated artifact set"
fi
printf '== installed_wheel_digest ==\n'; cat "$OUT/logs/installed_wheel_digest.txt"
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
assert files('l9_graphite_memory').joinpath('resources/projections/schema.json').is_file()
assert GateMemoryBridge.__name__ == 'GateMemoryBridge'
eps={ep.name for ep in distribution('l9-graphite-memory').entry_points}
assert {'l9-memory','l9-memory-server','l9-memory-worker'} <= eps
sys.stdout.write(f'{len(names)} tools loaded; entrypoints, constellation bridge, and resources present\n')
PYSMOKE
  PYTHONPATH="$SITE" HOME="$TMP_DATA/home" L9_MEMORY_DATA_DIR="$TMP_DATA/data" L9_MEMORY_STATE_DIR="$TMP_DATA/state" \
    python3 -m l9_graphite_memory.cli client cursor install --dry-run >"$OUT/logs/installed_cursor_client.txt"
  PYTHONPATH="$SITE" HOME="$TMP_DATA/home" L9_MEMORY_DATA_DIR="$TMP_DATA/data" L9_MEMORY_STATE_DIR="$TMP_DATA/state" \
    python3 -m l9_graphite_memory.cli client cursor install --path "$TMP_DATA/home/.cursor/mcp.json" >>"$OUT/logs/installed_cursor_client.txt"
  PYTHONPATH="$SITE" HOME="$TMP_DATA/home" L9_MEMORY_DATA_DIR="$TMP_DATA/data" L9_MEMORY_STATE_DIR="$TMP_DATA/state" L9_MEMORY_PROJECTION_BACKEND=none \
    python3 -m l9_graphite_memory.cli client cursor verify --timeout 60 >"$OUT/logs/installed_cursor_probe.txt"
)

# --- Candidate integrity after substantive validation -------------------------
find "$ROOT" -path "$ROOT/.venv" -prune -o -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT" -path "$ROOT/.venv" -prune -o -type f -name '*.pyc' -exec rm -f {} +
rm -rf "$ROOT/.pytest_cache"
candidate_integrity post
run validation_evidence python3 tools/assurance/generate_validation_evidence.py --evidence-dir "$OUT"
DIGEST_AFTER="$(candidate_digest)"
printf 'candidate digest after:  %s\n' "$DIGEST_AFTER" | tee -a "$OUT/logs/candidate_digest.txt"
if [[ "$DIGEST_BEFORE" != "$DIGEST_AFTER" ]]; then
  fail "tracked candidate bytes changed during validation ($DIGEST_BEFORE -> $DIGEST_AFTER)"
fi
printf 'Release validation complete (%s artifacts). Evidence: %s\n' "$ARTIFACT_MODE" "$OUT"
