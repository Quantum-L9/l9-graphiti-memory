#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/collect_run_evidence.sh
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: github_run_evidence_collector
# tags: [github-actions, logs, artifacts, evidence]
# owner: igor_beylin
# status: active
# version: 1.0.0
# updated: 2026-07-26
# Purpose: download run metadata, jobs, logs, and artifacts for a named GitHub Actions run.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "usage: $0 <repo> <run-id> <output-dir>" >&2
  exit 2
fi
repo=$1
run_id=$2
out=$3
if [[ "$repo" != "Quantum-L9/l9-deploy" ]]; then
  echo "collector is locked to Quantum-L9/l9-deploy" >&2
  exit 2
fi
mkdir -p "$out/artifacts"
gh api "repos/$repo/actions/runs/$run_id" > "$out/run.json"
gh api "repos/$repo/actions/runs/$run_id/jobs?per_page=100" > "$out/jobs.json"
gh run view "$run_id" --repo "$repo" --log > "$out/run.log"
gh run download "$run_id" --repo "$repo" --dir "$out/artifacts"
echo "$out"
