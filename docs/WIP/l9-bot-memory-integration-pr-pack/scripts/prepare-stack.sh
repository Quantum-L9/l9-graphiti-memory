#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/prepare-stack.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORKSPACE=${1:-}
[[ -n "$WORKSPACE" ]] || { echo "Usage: $0 <workspace-containing-repo-clones>" >&2; exit 64; }
"$ROOT/scripts/preflight-stack.sh" "$WORKSPACE"
python3 - "$ROOT" "$WORKSPACE" <<'PY'
import json, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]); workspace=pathlib.Path(sys.argv[2]); stack=json.loads((root/'PR_STACK.yaml').read_text())
for pr in stack['prs']:
    repo=workspace/pr['directory']; overlay=root/'repos'/pr['directory']
    subprocess.run(['git','-C',str(repo),'switch','-c',pr['branch']],check=True)
    subprocess.run([str(overlay/'apply.sh')],cwd=repo,check=True)
    subprocess.run(['git','-C',str(repo),'add','-A'],check=True)
    if subprocess.run(['git','-C',str(repo),'diff','--cached','--quiet']).returncode == 0: raise SystemExit(f"{pr['id']}: overlay produced no staged change")
    subprocess.run(['git','-C',str(repo),'commit','-m',(overlay/'commit-message.txt').read_text().strip()],check=True)
    print(f"PREPARED {pr['id']} on {pr['branch']}")
PY
echo "Local stack prepared. Run native validation before publication. Nothing was pushed."
