# ADR-022: Release, Publishing, and Rollback

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-022-release-publishing-and-rollback.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

The prior publish workflow could publish any buildable tag without requiring the full validation suite.

## Decision

Publishing is gated by tests, compile checks, assurance scanners, ADR validation, wheel build, and installed-wheel smoke tests. Tags use semantic versioning. Releases include source ZIP, wheel, sdist, manifest, change summary, and validation report.

## Alternatives Considered

- Publish from a developer laptop after manual checks
- Use mutable latest artifacts
- Treat wheel build success as release proof

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No tag publish bypasses validation
- Artifacts have SHA-256 digests
- Rollback instructions and migration compatibility accompany every major release

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- CI workflow dependency graph
- Artifact digest verification
- Clean-environment install test

## Rollback Conditions

Reinstall the prior version and restore from the pre-migration database copy; v2 exports remain available for forward recovery.

## Supersedes / Superseded By

Supersedes build-only publishing.

No later ADR supersedes this decision as of 2026-07-21.

## Amendment — exact-release admission gates publication (2026-10-15)

**Decision date:** 2026-10-15 (campaign L9-MEMORY-3.0-PREDEPLOY, finding F2).

### The gap

ADR-094 makes release admission an explicit authority decision bound to the
exact frozen candidate subject set (version, source revision, wheel sha256,
sdist sha256), and `release-work/product-release-binding.yaml` states that
publication requires it and that published digests equal admitted digests.
`publish.yml` enforced neither. Its only human gate is the `release`
environment approval, which names no version or digest and which repository
admins can bypass. It approves a run, not a release.

The gap is observable: PyPI's `l9-graphite-memory` 2.6.0 sdist has sha256
7507070e9eb974bc53df9e3ca90b27755284b99375d8a396b72bbb4cc4e893cc, while
`docs/receipts/l9-memory-release-2.6.0.md` admitted
537ff040a096a5adbc075fa3871cd1099d2bf93315e4ec3b5e5987acb638ff98. The wheel
matches; the published sdist was never admitted.

### Decision

1. Publication requires the admission receipt
   `docs/receipts/l9-memory-release-<version>.md`, the form the 2.6.0 receipt
   established. Its `Package`, `Admitted source`, `Wheel`, `Wheel sha256`,
   `Sdist` and `Sdist sha256` coordinates must equal the version, the published
   commit and the files actually in `dist/`, and the tag must be `v<version>`.
2. The receipt is read from the protected default branch, never from the
   candidate's own tree. The admission decision is the merge of that receipt
   under the repository's merge authority; a receipt removed from the default
   branch admits nothing.
3. `tools/assurance/verify_release_admission.py` checks it in `publish.yml`
   after the validated-set proof and before the PyPI step, under the same
   condition as the PyPI step. Any missing, malformed, duplicated or different
   coordinate stops the job before PyPI and prints the observed tuple, which
   admits nothing.
4. The `release` environment approval, validation and reproducible builds stay
   as they are. None of them substitutes for the receipt.

### Consequences

The admitted digests must be the digests of the bytes publication builds. The
sdist is not byte-identical across build hosts (a local and a CI build of the
same commit differed), so the authority admits the tuple the publish job
reports: a first `v<version>` run stops at this gate and prints it; after the
receipt merges, the release is re-run through `workflow_dispatch` with the same
tag, and it publishes only if the rebuilt bytes still match. A runner change
that alters the bytes fails closed.

No new authority, schema or approval is introduced: the authority, the subject
set and the receipt form already exist (ADR-094, the release binding, the
2.6.0 receipt). This amendment adds enforcement only.

