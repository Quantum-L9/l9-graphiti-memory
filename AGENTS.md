<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: AGENTS.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# AGENTS.md

## Repository law

Read `docs/adr/README.md` before changing contracts, authorization, storage, MCP tools, temporal semantics, or release workflows.

## Sacred behavior, not sacred files

No file is immune from correction. These invariants are protected:

1. MemoryService is the canonical control plane.
2. Caller identity is server-derived.
3. Canonical persistence is atomic and evidence-bearing.
4. Valid time and transaction time remain distinct.
5. Graph and semantic systems are projections.
6. No direct store/provider write bypass.
7. No secret persistence in generated config.
8. No release claim without executable validation.

## Change requirements

Every material change includes:

- contract impact
- migration impact
- exact wiring path
- tests or validation
- ADR update when a decision changes
- rollback condition

Run `bash scripts/validate_release.sh` before proposing a merge.

## CI and lint contract

Blocking merge gates — all must pass:

| Workflow · job | Commands |
|---|---|
| CI · validate (3.10, 3.13) | `ruff check .`, `mypy src/l9_graphite_memory`, `bash scripts/validate_release.sh` |
| L9 Lint and Test · Lint and Type Check | `ruff check src/`, `ruff format --check src/`, `mypy src/` |
| L9 Lint and Test · Test Suite | `pytest tests/` |
| CodeQL · analyze | GitHub CodeQL security analysis |
| L9 Analysis · Governed Semgrep Analysis | governed SDK pipeline, published as checks |

Advisory / non-blocking: the raw `semgrep scan` step (`|| true`); external SonarCloud.

Lint and type configuration is authoritative in the top-level `ruff.toml` (the
`[tool.ruff]` table was removed from `pyproject.toml` so a bare `ruff.toml`
cannot shadow it):

- Ruff: `select = E,F,W,I,UP,B,S`, `line-length = 88`, `target-version = py310`, `exclude = validation,dist`.
- mypy: `disallow_untyped_defs`, `disallow_incomplete_defs`, `no_implicit_optional`, `warn_return_any`, `warn_unused_ignores`, plugin `pydantic.mypy`. CI installs `requirements-ci.txt` (pydantic, pyyaml) before mypy so the plugin loads.

Intentional exclusions — these are false positives here, do not "fix" them:

- `E501` — line length is owned by `ruff format`, not the linter.
- `S101`, `S311` — asserts and non-crypto randomness are acceptable.
- `S310`, `S603`, `S607`, `S608` — audited urllib / subprocess / SQL call sites.
- `E402` — assurance tools set `sys.dont_write_bytecode` before their imports.
- Per-file: `tests/**` (`S101/S105/S106`), `secrets.py` (`S110`), `schema/__init__.py` (`F401`).
- Assurance scans ignore `.git`, `.venv`, `.mypy_cache`, `.ruff_cache`, `__pycache__`, `*.egg-info`, `build`, `dist`, `validation`; structural checks operate on git-tracked paths only, so transient tool artifacts are never flagged.

No `.pre-commit-config.yaml` on this branch — parity is enforced by CI, not local hooks.

## Adding or renaming files

Every tracked file must carry L9 metadata inline or through the manifest, or
`check_l9_meta` and `check_recursive_alignment` fail. After adding files, run:

- `python3 tools/assurance/apply_l9_meta.py` — inject inline headers into comment-safe files
- `python3 tools/assurance/generate_manifest.py` — rebuild `manifest.json` and `MANIFEST.md`

`scripts/validate_release.sh` runs both automatically. A new top-level entry must
also be added to `ALLOWED_TOP_LEVEL` in `tools/assurance/check_recursive_alignment.py`.
