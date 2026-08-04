# ADR-069: uv as Canonical Python Package Manager

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-069-uv-package-manager.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-08-04
/L9_META -->

## Status

Accepted (2026-08-04)

Related: ADR-020 (package layout), ADR-022 (release publishing and rollback)

## Context

Developer and CI installs used unpinned `pip install -e '.[extras]'` resolution
against `pyproject.toml` ranges. That left local environments and CI matrix
runs free to drift across transitive versions, while an untracked local
`uv.lock` already existed from ad-hoc `uv` use. The repository already treats
`clients/typescript/package-lock.json` as authoritative for Node; Python had
no equivalent locked contract.

## Decision

Adopt **uv** as the canonical Python dependency manager for this repository:

1. Track `uv.lock` in git and regenerate it only via `uv lock` (committed with
   any dependency change in `pyproject.toml`).
2. Developer and CI environments sync with
   `uv sync --frozen --extra dev --extra server` (add further `--extra` flags
   when a workflow needs them).
3. Prefer `uv run <command>` for repo-local tools (ruff, mypy, pytest, scripts).
4. Keep **pip** for end-user installs of the published distribution and for the
   hermetic installed-wheel smoke in `scripts/validate_release.sh` (that path
   proves the wheel artifact, not the uv workspace).

## Alternatives Considered

- Continue unpinned pip installs in CI and leave `uv.lock` untracked
- Switch to Poetry or PDM lockfiles
- Replace the wheel-smoke path with `uv sync` only

## Rejected Alternatives

Unpinned pip allows silent transitive drift and fails the “no release claim
without executable validation” invariant for dependency identity. Poetry/PDM
would introduce a second toolchain without benefit over uv, which the org
already standardizes on for Python TDD. Replacing wheel-smoke with uv sync
would stop proving installed-wheel behavior required by ADR-020 and ADR-022.

## Invariants

- `uv.lock` is present on `main` and matches `pyproject.toml` under `uv lock`
- CI and publish jobs install via `uv sync --frozen` before validation
- Dependency bumps update `pyproject.toml` and `uv.lock` in the same change
- Installed-wheel validation remains a clean pip target install of the built
  wheel with `--no-deps` where required by the smoke contract

## Consequences

Positive: reproducible developer/CI environments; one lockfile authority;
alignment with org uv skills and Node lockfile discipline.

Negative: contributors need `uv` installed; CI must fetch `astral-sh/setup-uv`;
lockfile churn accompanies dependency updates.

## Security Impact

Pinned resolution reduces supply-chain surprise between plan and CI. Lockfile
hashes are reviewable. Wheel-smoke still isolates the packaged artifact from
the workspace environment.

## Migration Impact

Existing pip one-liners remain valid for installing a published wheel or sdist.
Checkout-based development switches to `uv sync --frozen` (or
`bash scripts/install.sh`, which prefers uv when available). No data migration.

## Validation Requirements

- `uv lock` is a no-op against committed `uv.lock` (or the updated lock is
  committed)
- `uv sync --frozen --extra dev --extra server` succeeds
- `uv run ruff` / `uv run mypy` / `uv run pytest` (or PATH via `.venv`) succeed
- `bash scripts/validate_release.sh` still passes wheel build + installed smoke

## Rollback Conditions

Revert the ADR, delete or stop requiring `uv.lock`, and restore pip-only
install steps in CI/docs. Prior tags remain installable via pip.

## Supersedes / Superseded By

Extends ADR-020/ADR-022 tooling practice; does not change package layout or
release artifact contracts.
