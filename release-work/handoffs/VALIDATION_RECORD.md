<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/handoffs/VALIDATION_RECORD.md
layer: repository_review
owner: memory-control-plane
status: active
version: 1.0.0
generated: 2026-07-26
generated_by: Manus AI pack validation
/L9_META -->
# Validation Record: l9-deploy Phase 6 Final Polished Handoff Pack

## Artifact

| Field | Value |
|---|---|
| File | `release-work/handoffs/l9-deploy-phase6-final-polished-handoff.zip` |
| SHA-256 | `babe37e1687c966b4a58791a7a3d55f1d05c82b24cd30994c2f16798e7cae32d` |
| Size | 144,850 bytes |
| Pack name | `l9-deploy-phase6-operator` |
| Pack version | 3.1.0 (SKILL.md), updated 2026-07-26 |
| Pack file count | 73 |
| Validated on | 2026-07-26 (Python 3.12.3, Ubuntu 24.04) |
| Validator | Manus AI, acting as pack validator and push agent |

## Purpose of this record

This zip is the **pristine, bit-for-bit archive** of the Phase 6 operator handoff pack for
`Quantum-L9/l9-deploy`. It is stored as an opaque binary rather than as loose files because this
repository's assurance pipeline (`tools/assurance/apply_l9_meta.py`) injects `L9_META` headers
into every tracked text file, which would rewrite 56 pack files and invalidate the pack's own
`MANIFEST.sha256` exact-state guarantee. Archiving the sealed zip preserves the exact validated
state; the pack's `references/REPO_WIRING_DECISION.md` likewise mandates out-of-repository,
portable delivery.

## Validation performed (offline, clean extraction)

All checks were executed against a clean extraction of this exact zip.

| Check | Command | Result |
|---|---|---|
| Pack checksum manifest | `sha256sum -c MANIFEST.sha256` | PASS — 72/72 files OK |
| Adversarial hardening suite | `bash scripts/self_test.sh` | PASS — 19/19 tests, 0 failed, isolated workers |
| Python compilation | via `self_test.sh` | PASS |
| Bash syntax | via `self_test.sh` | PASS |
| Exact-state pack validator | `python3 scripts/validate_pack.py .` | PASS — `{"status": "PASS", "file_count": 73, "errors": []}` |
| Secret scan (tokens, private keys, cloud keys) | independent regex sweep | PASS — no matches |
| Symlink / oversized-file sweep | `find` | PASS — 0 symlinks, 0 files > 1 MB |
| Pack self-declared validation report | `validation_report.yaml` | `APPROVED_WITH_FINDINGS`, all 20 offline checks PASS |

Adversarial coverage confirmed at runtime includes: evidence mutation rejection, rehashed-ledger
forgery rejection, wrong-key rejection, cross-run replay rejection, unledgered-file rejection,
path-traversal rejection, fake-locator rejection, immediate NO-GO on unauthorized OIDC success,
OIDC signature verification with token destruction, manual-GO rejection, workflow receipt
binding, Infisical redaction, and final health binding.

## Scope boundary

Offline PASS proves only that the pack's control plane rejects modeled bypasses and that the
package is internally consistent. Per the pack's own `validation_report.yaml`,
`safe_to_claim_phase6_go_now: false` — live staging execution, live rollback convergence, live
secret rotation, and the live negative OIDC exchange remain blocked pending authorized staging
access and an independent evidence attestor.

## Usage

```bash
unzip l9-deploy-phase6-final-polished-handoff.zip -d /path/outside/any/repo
cd /path/outside/any/repo/l9-deploy-phase6-operator
sha256sum -c MANIFEST.sha256  # then verify the zip itself against the SHA-256 recorded above
pip install -r requirements.txt
bash scripts/self_test.sh
python3 scripts/validate_pack.py .
```

Do not extract the pack into a governed repository working tree; metadata injection will break
its exact-state checksums. Follow `RUNBOOK.md` inside the pack for live Phase 6 execution.

## In-repository derivative copy

By explicit owner instruction (2026-07-27), a browsable loose-file copy of the pack is committed
at `tools/phase6/`. That copy is a **re-sealed derivative**, not the
original validated artifact:

- The repository assurance pipeline injected `L9_META` headers into 56 inline-capable pack
  files, making the tree compliant with `check_l9_meta.py`.
- The pack's internal `MANIFEST.sha256` was regenerated over the meta-injected files
  (72/72 entries, same file inventory, new digests) so the pack remains internally consistent.
- Post-reseal verification in place: `sha256sum -c MANIFEST.sha256` 72/72 OK,
  `bash scripts/self_test.sh` PASS (19/19 adversarial tests),
  `python3 scripts/validate_pack.py .` PASS (73 files, 0 errors).

The sealed zip in this directory remains the canonical bit-for-bit original
(SHA-256 `babe37e1687c966b4a58791a7a3d55f1d05c82b24cd30994c2f16798e7cae32d`). For live Phase 6
execution, prefer extracting the sealed zip; the in-repo copy is the CI-integrated working copy.

## CI integration (feat/phase6-operator-integration)

The in-repo copy lives at `tools/phase6/` following the `tools/assurance/` idiom for
operational tooling, with its internal sibling structure (`scripts/`, `schemas/`,
`references/`, `config/`, `assets/`, `tests/`, `source-evidence/`) preserved so all
`ROOT`-relative resolution and self-validation work unchanged. Wiring:

- `tests/regression/test_phase6_operator.py` executes the pack's checksum manifest,
  exact-state validator, and the full 19-test adversarial hardening suite in every CI run.
- `pyproject.toml` gains a `phase6` optional extra (`cryptography`, `jsonschema`, `PyJWT`),
  also included in `dev` so `pip install -e .[dev,server]` in CI provides the dependencies.
- `ruff.toml` scopes the vendored-artifact lint exemption to `tools/phase6/**`.
- Pack L9_META `path:` fields and the internal `MANIFEST.sha256` were re-sealed for the
  new location; `sha256sum -c` verifies 72/72 and `self_test.sh` passes in place.
