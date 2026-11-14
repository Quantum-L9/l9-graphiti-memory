#!/usr/bin/env bash
# The one build recipe for the release artifact set (wheel and sdist).
#
#   SOURCE_DATE_EPOCH=<integer> [PYTHON=<interpreter>] \
#     bash scripts/build_release_artifacts.sh <output-dir>
#
# For one commit and one SOURCE_DATE_EPOCH this yields byte-identical files on
# any machine, at any checkout time, under any umask: setuptools builds them
# (python -m build, with the [build-system] backend pinned exactly in
# pyproject.toml), then tools/assurance/reproducible_artifacts.py rewrites both
# archives into a canonical form, proves no member's content changed, and
# checks the result. publish.yml, release-container.yml and
# scripts/validate_release.sh all build through this file; nothing else in the
# repository builds a release artifact. An authority obtains the digests to
# admit (ADR-094) by running it at the release commit with the release epoch.
#
# Fails closed when SOURCE_DATE_EPOCH is unset or not an integer, or when the
# output directory is not empty. The bytes were proven identical under Python
# 3.10 through 3.13 (zlib 1.3 and 1.3.2); the release workflows (publish.yml,
# release-container.yml admission) both build with the same pinned Python,
# which tests/regression/test_reproducible_release_artifacts.py enforces, and
# the interpreter and zlib used are printed with the digests.
#
# setuptools packs files from the working tree, not from the commit: a tracked
# modification or an untracked, non-ignored file changes the sdist. The build
# still runs (local `make validate` builds uncommitted work), but says loudly
# that its digests are not those of the commit and must not be admitted.
set -euo pipefail

ROOT="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

[[ $# -eq 1 ]] || { echo "usage: $0 <output-dir>" >&2; exit 2; }
OUT="$1"

if [[ ! "${SOURCE_DATE_EPOCH:-}" =~ ^[0-9]+$ ]]; then
  echo "build_release_artifacts: SOURCE_DATE_EPOCH must be set to an integer (got '${SOURCE_DATE_EPOCH:-<unset>}')" >&2
  exit 1
fi
export SOURCE_DATE_EPOCH

if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "build_release_artifacts: source $(git -C "$ROOT" rev-parse HEAD) SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
  DIRTY="$(git -C "$ROOT" status --porcelain --untracked-files=all)"
  if [[ -n "$DIRTY" ]]; then
    {
      echo "build_release_artifacts: WARNING: the working tree differs from HEAD; these digests are NOT"
      echo "build_release_artifacts: WARNING: the commit's and must not be admitted. Differences:"
      printf '%s\n' "$DIRTY" | sed 's/^/  /'
    } >&2
  fi
fi

mkdir -p "$OUT"
if [[ -n "$(ls -A -- "$OUT")" ]]; then
  echo "build_release_artifacts: output directory $OUT is not empty" >&2
  exit 1
fi

"$PY" -m build --outdir "$OUT" "$ROOT"
"$PY" "$ROOT/tools/assurance/reproducible_artifacts.py" canonicalize "$OUT"
"$PY" "$ROOT/tools/assurance/reproducible_artifacts.py" check "$OUT"
