#!/usr/bin/env bash
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/LLM-Router/apply.sh
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

set -euo pipefail
PACK_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EXPECTED_REPO="Quantum-L9/LLM-Router"
EXPECTED_SHA="d83299bc6e81efae1eb6e6c3032cbb3e0cb77184"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Refusing: current directory is not a git worktree" >&2; exit 5; }
ACTUAL_REPO=$(git config --get remote.origin.url 2>/dev/null || true)
normalize_repo() {
  local value="$1"
  value="${value%.git}"
  value="${value#git@github.com:}"
  value="${value#ssh://git@github.com/}"
  value="${value#https://github.com/}"
  value="${value#http://github.com/}"
  printf '%s' "$value"
}
if [[ "${ALLOW_WRONG_REPO:-0}" != "1" ]]; then
  [[ -n "$ACTUAL_REPO" ]] || { echo "Refusing: remote.origin.url is missing" >&2; exit 4; }
  [[ "$(normalize_repo "$ACTUAL_REPO")" == "$EXPECTED_REPO" ]] || { echo "Refusing: origin $ACTUAL_REPO is not exactly $EXPECTED_REPO" >&2; exit 4; }
fi
if [[ "${ALLOW_UNPINNED_BASE:-0}" != "1" ]]; then
  [[ $(git rev-parse HEAD) == "$EXPECTED_SHA" ]] || { echo "Refusing: expected HEAD $EXPECTED_SHA" >&2; exit 2; }
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing: working tree is not clean" >&2; exit 3
fi
START_HEAD=$(git rev-parse HEAD)
rollback() {
  local code=$?
  trap - ERR INT TERM
  echo "Apply failed; restoring clean tree at $START_HEAD" >&2
  git reset --hard "$START_HEAD" >/dev/null
  git clean -fd >/dev/null
  exit "$code"
}
trap rollback ERR INT TERM
cp -R "$PACK_DIR/files/." .

if [[ "${SKIP_LOCKFILE:-0}" != "1" && -f package.json ]]; then
  npm install --package-lock-only --ignore-scripts --no-audit --no-fund
fi
trap - ERR INT TERM
echo "Applied $EXPECTED_REPO patch. Review git diff, run validation, then commit."
git status --short
