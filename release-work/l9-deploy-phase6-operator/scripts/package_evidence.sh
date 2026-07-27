#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/package_evidence.sh
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: evidence_packager
# tags: [evidence, package, checksums, redaction, authority]
# owner: igor_beylin
# status: active
# version: 3.0.0
# updated: 2026-07-26
# Purpose: validate and package a completed Phase 6 evidence directory using independent ledger and evidence trust anchors.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <run-dir> <trusted-ledger-public-key> <trusted-evidence-public-key> <output.zip>" >&2
  exit 2
fi
run_dir=$(cd "$1" && pwd)
ledger_public=$(realpath "$2")
evidence_public=$(realpath "$3")
output=$4

python3 "$(dirname "$0")/phase6ctl.py" validate-evidence \
  --run-dir "$run_dir" \
  --trusted-ledger-public-key "$ledger_public" \
  --trusted-evidence-public-key "$evidence_public"

for forbidden in runtime.env .env id_rsa id_ed25519 oidc.jwt token.txt; do
  if find "$run_dir" -type f -name "$forbidden" -print -quit | grep -q .; then
    echo "forbidden evidence file detected: $forbidden" >&2
    exit 3
  fi
done
if find "$run_dir" -type f \( -name '*private*.pem' -o -name '*signing*.pem' \) -print -quit | grep -q .; then
  echo "private signing material detected in evidence directory" >&2
  exit 3
fi

(
  cd "$run_dir"
  find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256
)
rm -f "$output" "$output.sha256"
parent=$(dirname "$run_dir")
base=$(basename "$run_dir")
(
  cd "$parent"
  zip -qr "$output" "$base"
)
sha256sum "$output" > "$output.sha256"
unzip -tq "$output" >/dev/null
echo "$output"
