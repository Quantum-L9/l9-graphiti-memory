#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/push-stack.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORKSPACE=${1:-}
[[ -n "$WORKSPACE" ]] || { echo "Usage: PUSH_STACK=1 $0 <workspace-containing-prepared-repo-clones>" >&2; exit 64; }
[[ "${PUSH_STACK:-0}" == "1" ]] || { echo "Refusing: set PUSH_STACK=1 for explicit publication authorization" >&2; exit 65; }
command -v gh >/dev/null || { echo "Refusing: gh CLI is required" >&2; exit 69; }
gh auth status >/dev/null
python3 - "$ROOT" "$WORKSPACE" <<'PY'
import json, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]); workspace=pathlib.Path(sys.argv[2]); stack=json.loads((root/'PR_STACK.yaml').read_text())
for pr in stack['prs']:
    repo=workspace/pr['directory']; overlay=root/'repos'/pr['directory']
    branch=subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip()
    if branch != pr['branch']: raise SystemExit(f"{pr['id']}: current branch {branch!r} != {pr['branch']!r}")
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip(): raise SystemExit(f"{pr['id']}: working tree dirty")
    parent=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD^'],text=True).strip()
    if parent != pr['base_sha']: raise SystemExit(f"{pr['id']}: commit parent {parent} != pinned base {pr['base_sha']}")
    subprocess.run(['git','-C',str(repo),'push','--set-upstream','origin',pr['branch']],check=True)
    exists=subprocess.run(['gh','pr','view',pr['branch'],'--repo',pr['repo']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if exists: print(f"EXISTS {pr['id']}: PR already present"); continue
    subprocess.run(['gh','pr','create','--repo',pr['repo'],'--base','main','--head',pr['branch'],'--title',pr['title'],'--body-file',str(overlay/'pr-body.md'),'--draft'],check=True)
    print(f"PUSHED {pr['id']}: draft PR created")
PY
