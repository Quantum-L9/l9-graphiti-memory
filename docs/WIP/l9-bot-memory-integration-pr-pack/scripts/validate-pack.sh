#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/scripts/validate-pack.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
find "$ROOT" -name '*.sh' -print0 | while IFS= read -r -d '' f; do bash -n "$f"; done
python3 - "$ROOT" <<'PY'
import ast, json, pathlib, sys
root=pathlib.Path(sys.argv[1])
for p in root.rglob('*.py'):
    ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
for p in root.rglob('*.json'):
    json.loads(p.read_text())
for p in root.rglob('*.yaml'):
    json.loads(p.read_text(encoding='utf-8'))  # strict JSON-compatible YAML
for p in root.rglob('*'):
    if p.is_file() and b'\r\n' in p.read_bytes():
        raise SystemExit(f'CRLF not allowed: {p.relative_to(root)}')
    if p.is_file() and (p.suffix == '.pyc' or '__pycache__' in p.parts):
        raise SystemExit(f'compiled cache forbidden in pack: {p.relative_to(root)}')
print('json-python-json-compatible-yaml-and-hygiene-ok')
PY
python3 - "$ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
contract = json.loads((root / 'PACK_CONTRACT.yaml').read_text(encoding='utf-8'))
convergence = json.loads((root / 'CONVERGENCE_REPORT.yaml').read_text(encoding='utf-8'))
expected_repos = [
    'Quantum-L9/l9-graphiti-memory',
    'Quantum-L9/LLM-Router',
    'Quantum-L9/Website-Bot',
    'Quantum-L9/SEO-Bot',
]
if contract['scope']['repositories'] != expected_repos:
    raise SystemExit('PACK_CONTRACT repository scope/order drift')
if contract['merge_order'] != expected_repos:
    raise SystemExit('PACK_CONTRACT merge order drift')
if contract['authority']['canonical_memory_repository'] != expected_repos[0]:
    raise SystemExit('canonical memory authority drift')
sha = contract['authority']['pinned_memory_base_sha']
if convergence['canonical_authority']['pinned_sha'] != sha:
    raise SystemExit('convergence pinned SHA disagrees with PACK_CONTRACT')
apply = (root / 'repos/l9-graphiti-memory/apply.sh').read_text(encoding='utf-8')
if sha not in apply:
    raise SystemExit('memory apply script does not enforce the normative pinned SHA')
for key, value in contract['invariants'].items():
    if value is not True:
        raise SystemExit(f'normative invariant is not true: {key}')
for forbidden in [
    'ARCHITECTURE.md', 'ORDER.md', 'AUDIT_REPORT.md', 'BUILD_REPORT.md',
    'IMPROVEMENT_REPORT.md', 'REALIGNMENT_REPORT.md'
]:
    if (root / forbidden).exists():
        raise SystemExit(f'redundant top-level report restored: {forbidden}')
required = [
    'AUTHORITY.md', 'PACK_CONTRACT.yaml', 'RUNBOOK.md', 'VALIDATION.md',
    'RECURSIVE_AUDIT_REPORT.md', 'CONVERGENCE_REPORT.yaml', 'DELTA_REPORT.md'
]
for name in required:
    if not (root / name).is_file():
        raise SystemExit(f'required authority/evidence artifact missing: {name}')
print('authority-contract-ok')
PY
python3 - "$ROOT" <<'PYSTACK'
import json, pathlib, sys
root=pathlib.Path(sys.argv[1])
stack=json.loads((root/'PR_STACK.yaml').read_text())
contract=json.loads((root/'PACK_CONTRACT.yaml').read_text())
expected=contract['merge_order']
if [p['repo'] for p in stack['prs']] != expected:
    raise SystemExit('PR stack order disagrees with PACK_CONTRACT')
if [p['order'] for p in stack['prs']] != list(range(1, len(stack['prs'])+1)):
    raise SystemExit('PR stack order is not contiguous')
seen=set()
for pr in stack['prs']:
    if any(dep not in seen for dep in pr['depends_on']):
        raise SystemExit(f"{pr['id']}: dependency is absent or forward-referenced")
    seen.add(pr['id'])
    d=root/'repos'/pr['directory']
    meta=json.loads((d/'PR_METADATA.json').read_text())
    for key in ('order','id','repo','base_sha','branch','title','depends_on','release_gate'):
        if meta[key] != pr[key]:
            raise SystemExit(f"{pr['id']}: PR_METADATA drift for {key}")
    checks={'branch.txt':pr['branch'],'pr-title.txt':pr['title'],'base-branch.txt':'main','base-sha.txt':pr['base_sha']}
    for name,value in checks.items():
        if (d/name).read_text().strip() != value:
            raise SystemExit(f"{pr['id']}: {name} drift")
    apply=(d/'apply.sh').read_text()
    if pr['repo'] not in apply or pr['base_sha'] not in apply:
        raise SystemExit(f"{pr['id']}: apply script is not bound to stack repo/base")
    body=(d/'pr-body.md').read_text()
    for required in (pr['base_sha'],pr['branch'],'## Stack Position','## Push Contract'):
        if required not in body:
            raise SystemExit(f"{pr['id']}: PR body missing {required}")
if stack['publication_policy']['push_disabled_by_default'] is not True:
    raise SystemExit('push must be disabled by default')
push=(root/'scripts/push-stack.sh').read_text()
if 'PUSH_STACK:-0' not in push or "'--draft'" not in push or 'force' in push.lower():
    raise SystemExit('push script authorization/draft/no-force contract drift')
print('pr-stack-contract-ok')
PYSTACK
for f in $(find "$ROOT/repos" -name '*.ts'); do
  node --experimental-strip-types --check "$f" >/dev/null
done
(cd "$ROOT" && sha256sum -c MANIFEST.sha256 >/dev/null)
grep -q "reservationId && !providerCompleted" "$ROOT/repos/LLM-Router/files/src/index.ts"
grep -q "explicit_confirmation: input.explicitConfirmation ?? false" "$ROOT/repos/l9-graphiti-memory/files/clients/typescript/src/index.ts"
grep -q "this.initialized = true" "$ROOT/repos/l9-graphiti-memory/files/clients/typescript/src/index.ts"
grep -q "session propagation is opportunistic" "$ROOT/repos/l9-graphiti-memory/files/clients/typescript/src/index.ts"
grep -q "works against the pinned stateless canonical HTTP server" "$ROOT/repos/l9-graphiti-memory/files/clients/typescript/tests/client.test.ts"
grep -q "group.length < 2" "$ROOT/repos/SEO-Bot/files/src/services/memory.ts"
grep -q "supportingRecordIds: support.map" "$ROOT/repos/SEO-Bot/files/src/services/memory.ts"
grep -q "client.hydrate" "$ROOT/repos/LLM-Router/files/src/memory.ts"
python3 - "$ROOT" <<'PY'
import json, pathlib, sys
root=pathlib.Path(sys.argv[1])
expected='^2.0.0'
client=json.loads((root/'repos/l9-graphiti-memory/files/clients/typescript/package.json').read_text())
if client['version'] != '2.0.0': raise SystemExit('client package version must be 2.0.0')
for rel in ['repos/LLM-Router/files/package.json','repos/Website-Bot/files/package.json','repos/SEO-Bot/files/package.json']:
    data=json.loads((root/rel).read_text())
    got=data.get('dependencies',{}).get('@quantum-l9/graphiti-memory-client')
    if got != expected: raise SystemExit(f'{rel}: graphiti client dependency {got!r} != {expected!r}')
PY
if find "$ROOT/repos" -type f \( -name '*.ts' -o -name '*.sql' \) -print0 | xargs -0 grep -nE 'postgres-budget-store|CREATE TABLE llm_budget_|vector\(' ; then
  echo 'ERROR: shadow PostgreSQL/pgvector memory or budget layer remains' >&2
  exit 1
fi
if grep -RInE '(BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})' "$ROOT"; then
  echo 'Potential secret detected' >&2; exit 1
fi
if grep -RInE '\b(TODO|FIXME|PLACEHOLDER)\b' "$ROOT/repos"; then
  echo 'Placeholder marker detected in repo payload' >&2; exit 1
fi
"$ROOT/scripts/test-isolated-contracts.sh"
"$ROOT/scripts/test-apply-safety.sh"
echo pack-validation-ok
