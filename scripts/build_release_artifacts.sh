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
# Fails closed when SOURCE_DATE_EPOCH is unset or not an integer, when the
# output directory is not empty, or when the interpreter is not the release
# build interpreter (RELEASE_BUILD_PYTHON below): the canonical archives are
# deflate streams, and their bytes are only claimed for the zlib a pinned
# interpreter ships with.
set -euo pipefail

# Every release workflow builds with this interpreter minor version. Change it
# here and in publish.yml / release-container.yml together.
RELEASE_BUILD_PYTHON="3.13"

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

[[ $# -eq 1 ]] || { echo "usage: $0 <output-dir>" >&2; exit 2; }
OUT="$1"

if [[ ! "${SOURCE_DATE_EPOCH:-}" =~ ^[0-9]+$ ]]; then
  echo "build_release_artifacts: SOURCE_DATE_EPOCH must be set to an integer (got '${SOURCE_DATE_EPOCH:-<unset>}')" >&2
  exit 1
fi
export SOURCE_DATE_EPOCH

PY_MINOR="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [[ "$PY_MINOR" != "$RELEASE_BUILD_PYTHON" ]]; then
  echo "build_release_artifacts: release artifacts are built with Python $RELEASE_BUILD_PYTHON; $PY is $PY_MINOR" >&2
  exit 1
fi

mkdir -p "$OUT"
if [[ -n "$(ls -A -- "$OUT")" ]]; then
  echo "build_release_artifacts: output directory $OUT is not empty" >&2
  exit 1
fi

"$PY" -m build --outdir "$OUT" "$ROOT"
"$PY" "$ROOT/tools/assurance/reproducible_artifacts.py" canonicalize "$OUT"
"$PY" "$ROOT/tools/assurance/reproducible_artifacts.py" check "$OUT"
