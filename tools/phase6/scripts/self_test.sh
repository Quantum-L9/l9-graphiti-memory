#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/phase6/scripts/self_test.sh
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: offline_validation_entrypoint
# tags: [validation, adversarial-tests, packaging]
# owner: igor_beylin
# status: active
# version: 3.2.0
# updated: 2026-07-26
# Purpose: execute the exact offline validation suite with isolated bounded adversarial tests.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
root=$(cd "$(dirname "$0")/.." && pwd)
report=${PHASE6_TEST_REPORT:-"${TMPDIR:-/tmp}/phase6-adversarial-tests.json"}
trap 'rm -rf "$root/scripts/__pycache__" "$root/tests/__pycache__"' EXIT

python3 "$root/scripts/run_adversarial_tests.py" \
  --timeout-seconds "${PHASE6_TEST_TIMEOUT_SECONDS:-90}" \
  --report "$report"
python3 -B -m py_compile "$root"/scripts/*.py "$root"/tests/*.py
rm -rf "$root/scripts/__pycache__" "$root/tests/__pycache__"
bash -n "$root"/scripts/*.sh
python3 "$root/scripts/validate_pack.py" "$root"
echo "PASS: Phase 6 offline self-test; adversarial report: $report"
