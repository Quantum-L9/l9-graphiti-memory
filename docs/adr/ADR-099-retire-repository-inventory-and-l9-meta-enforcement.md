# ADR-099: Retire the Repository File Inventory and L9_META Enforcement

**Date:** 2026-10-15
**Decision owner:** Quantum-L9 architecture (explicit operator decision, 2026-10-15)
**Applies to:** `Quantum-L9/l9-graphiti-memory` 3.0.0+

## Status

Accepted

## Context

ADR-062 made every tracked file carry an inline `L9_META` block and every
packaged file a canonical entry in a cryptographic root inventory
(`manifest.json`, rendered as `MANIFEST.md`). Four tools carried that
contract: `tools/assurance/apply_l9_meta.py` and `generate_manifest.py`
(preparation), `check_l9_meta.py` and `validate_manifest.py` (enforcement),
all on the shared `tools/assurance/l9_meta.py`. Release validation, preflight
and the recursive-alignment pass ran the enforcement half.

In practice the inventory listed every file in the repository, so any source
change had to regenerate both root files. Every open pull request therefore
touched the same two files, and stacked or parallel pull requests conflicted
on them even when their real changes were disjoint. The PR stack for Memory
3.0.0 (#96, #97, #98) regenerated both inventories on each head. The per-file
header added edits of its own whenever metadata fields drifted.

The inventory was never the release-integrity control. The exact-release
identity is the version, source revision, wheel sha256 and sdist sha256
(ADR-022), validated by `scripts/validate_release.sh` and admitted by
`tools/assurance/verify_release_admission.py` before publication. The
governed product contract is the derived ProductManifest
(`release-work/product-manifest.json`, ADR-094), which is a different artifact.

## Decision

1. The repository-wide file inventory is retired. `MANIFEST.md` and
   `manifest.json` are deleted from the repository root and are no longer
   generated, validated, uploaded with release artifacts, or declared as a
   topology `generated_surface`.
2. Per-file `L9_META` metadata is no longer required. No CI job, preflight
   gate, release step or alignment pass fails on a missing, stale or
   malformed header. `apply_l9_meta.py`, `check_l9_meta.py`,
   `generate_manifest.py`, `validate_manifest.py` and `l9_meta.py` are
   deleted; they had no other consumer.
3. Existing inline headers stay as inert historical text. They are not
   mass-removed, not maintained, and not added to new files. Generators stop
   emitting them where their projection contract allows: the repository-corpus
   projector (ADR-096) now renders its YAML without a header and is
   regenerated, not patched.
4. The changed-file inventory of a change belongs in its pull request body,
   produced by the canonical Cursor-Governance PR composer. No replacement
   repository inventory, metadata registry, checksum listing or renamed
   enforcement mechanism is introduced.
5. Unchanged: exact wheel and sdist sha256 identity, the read-only candidate
   digest comparison in release validation, installed-wheel smoke, the
   ProductManifest and its derivation check, the product-topology validation,
   release admission (ADR-022, ADR-094), and the security, architecture and
   runtime conformance checks.

## Alternatives Considered

- Keep the inventory but exclude it from conflict resolution with a merge driver
- Narrow the inventory to packaged files only
- Move the inventory into a generated, untracked release artifact
- Keep `L9_META` enforcement while retiring only the inventory

## Rejected Alternatives

A merge driver hides the churn without removing it and still forces every
change to regenerate the inventory. A narrowed inventory keeps the same
regeneration obligation for every packaged-source change. An untracked
release-time inventory would be a second, unreviewed artifact beside the
wheel and sdist digests that already identify the release. `L9_META`
enforcement without the inventory keeps the per-file edit churn and ADR-062's
"every packaged file has a manifest carrier" invariant could no longer hold.

## Invariants

- No tracked root file inventory exists; `check_recursive_alignment.py`
  rejects a tracked `MANIFEST.md` or `manifest.json` at the root as a
  forbidden top-level entry.
- No release, preflight, CI or alignment step invokes the retired tools or
  fails on `L9_META` content.
- Release validation remains observational and still fails when tracked
  candidate bytes change during validation.
- Published artifact sha256 equals validated and admitted artifact sha256.
- `MANIFEST.in` (sdist packaging) and the ProductManifest are not the retired
  inventory and remain in force.

## Consequences

Positive: an ordinary source change no longer touches root files, so parallel
and stacked pull requests stop conflicting on them; release validation is
shorter. Negative: file-level layer and ownership metadata is no longer
mechanically verified; existing headers may drift from reality and are not
authoritative. Ownership and layer are carried by the architecture documents,
the layer-boundary check and the topology instead.

## Security Impact

None on runtime behavior. Release integrity is carried by the artifact
digests, the candidate-digest comparison and release admission, all retained.
The retired inventory hashed source files, which never gated publication on
its own.

## Migration Impact

The root inventory files and five assurance tools are deleted. The
repository-corpus projection resources are regenerated without a header; their
source revision and source digests are unchanged and only the output digest
moves. The product topology and ProductManifest are reissued (ADR-094
amendment of 2026-10-15). Historical receipts and audit evidence under
`validation/`, `docs/audits/` and `release-work/` are left as produced.

## Validation Requirements

- `tests/regression/test_manifest_retirement.py`
- `tests/regression/test_release_shell.py`
- `tests/regression/test_release_version_consistency.py`
- `tests/regression/test_recursive_alignment.py`
- `tests/regression/test_product_release_governance.py`
- `scripts/validate_release.sh` and `scripts/preflight.sh` run without the retired tools

## Rollback Conditions

Reinstating a repository inventory or file-level metadata requires a new ADR
that supersedes this one and that shows the obligation no longer forces every
change to edit a shared file.

## Supersedes / Superseded By

Supersedes ADR-062 (L9 Metadata and File Provenance). Amends ADR-094 only by
reissuing its topology digest. Superseded by none.
