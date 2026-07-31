#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/preflight-stack.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORKSPACE=${1:-}
[[ -n "$WORKSPACE" ]] || { echo "Usage: $0 <workspace-containing-repo-clones>" >&2; exit 64; }
python3 - "$ROOT" "$WORKSPACE" <<'PY'
import json, pathlib, subprocess, sys
root=pathlib.Path(sys.argv[1]); workspace=pathlib.Path(sys.argv[2]); stack=json.loads((root/'PR_STACK.yaml').read_text())
failed=False
for pr in stack['prs']:
    repo=workspace/pr['directory']
    def git(*args): return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
    if not repo.is_dir(): print(f"FAIL {pr['id']}: missing {repo}"); failed=True; continue
    try:
        origin=git('config','--get','remote.origin.url').removesuffix('.git')
        normalized=origin.replace('git@github.com:','').replace('ssh://git@github.com/','').replace('https://github.com/','').replace('http://github.com/','')
        head=git('rev-parse','HEAD'); dirty=git('status','--porcelain')
    except Exception as exc: print(f"FAIL {pr['id']}: {exc}"); failed=True; continue
    problems=[]
    if normalized != pr['repo']: problems.append(f"origin={normalized}")
    if head != pr['base_sha']: problems.append(f"HEAD={head}, expected={pr['base_sha']}")
    if dirty: problems.append('working tree dirty')
    if problems: print(f"FAIL {pr['id']}: " + '; '.join(problems)); failed=True
    else: print(f"PASS {pr['id']}: {pr['repo']}@{head}")
raise SystemExit(1 if failed else 0)
PY
