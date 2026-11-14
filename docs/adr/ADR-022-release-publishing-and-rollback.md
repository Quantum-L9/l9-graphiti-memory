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
   candidate's own tree. The verifier locates it itself from a plain
   `MAJOR.MINOR.PATCH` version and refuses any path that resolves outside that
   checkout, so a candidate's version string cannot point it elsewhere. The admission decision is the merge of that receipt
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

## Amendment — one reproducible build recipe for the admitted artifacts (2026-11-14)

**Decision date:** 2026-11-14 (#125).

### The gap

The admission gate of the 2026-10-15 amendment passes only when the receipt's
wheel and sdist sha256 equal the files a workflow builds from the tag. Two
workflows build them independently from a fresh checkout: `publish.yml` and the
`admission` job of `release-container.yml`. setuptools' sdist was not
reproducible: each member carried its checkout mtime and its umask-dependent
mode (0644 or 0664), the build-time members (PKG-INFO, SOURCES.txt, setup.cfg)
carried the build time, and pax records carried both as fractional seconds. The
wheel carried umask-dependent modes. For commit `78d2205` one wheel came with
four different sdist digests (two CI matrix legs, a worktree build, a
`git archive` export build) whose extracted contents were identical. The build
backend also floated: `setuptools>=68` resolved to whatever release was current
at build time. So no receipt written before a run could match the sdist that
run built, the two workflows could not match each other, and the
"admit the tuple the publish job reports, then re-run" consequence above could
not hold either: the re-run rebuilds and gets new bytes. This is also why the
2.6.0 sdist on PyPI differs from the admitted one.

### Decision

1. `scripts/build_release_artifacts.sh` is the single build recipe for the
   release artifact set. `publish.yml`, the `release-container.yml` admission
   job and `scripts/validate_release.sh` build only through it; none calls
   `python -m build` directly.
2. It requires an integer `SOURCE_DATE_EPOCH` (fail closed), builds with the
   exactly pinned backend (`[build-system] requires = ["setuptools==84.2.1"]`),
   then `tools/assurance/reproducible_artifacts.py` rewrites both archives into
   a canonical form: sdist members sorted, mtime = `SOURCE_DATE_EPOCH`,
   uid/gid 0 with empty names, modes 0644 / 0755 by executable bit, no pax time
   records, gzip header mtime 0 and no file name, deflate level 9; wheel entries
   in build order with `SOURCE_DATE_EPOCH` timestamps and 0100644 / 0100755
   attributes. The rewrite proves the member set, types, executable bits and
   bytes unchanged, and the result is checked to be a fixed point.
3. For one commit and one epoch the bytes are identical across checkout time,
   umask and Python 3.10 through 3.13 (proven in #125). Both release workflows
   still build with the same pinned Python, and a contract test keeps them
   equal.
4. setuptools packs the working tree, so the recipe prints the source commit
   and warns, naming the paths, when the tree differs from it; such digests are
   not admissible.
5. The authority obtains the digests to admit before the tag by running
   `SOURCE_DATE_EPOCH=1784592000 bash scripts/build_release_artifacts.sh <dir>`
   on a clean checkout of the release commit. The receipt can then merge before
   the tag is pushed, and the tag-push run publishes in one pass. The two-pass
   sequence of the 2026-10-15 amendment remains valid when the receipt is not
   yet merged at tag time.

### Consequences

Changing the build backend version, the canonical form or the compression
level changes the digests of every later build of a commit; a receipt binds the
recipe of the commit it admits. The admission verifier, its semantics and the
receipt form are unchanged.

### Rollback

Revert the recipe and route the three build sites back to `python -m build`.
The admission gate then returns to the pre-amendment state, in which the sdist
digest cannot be predicted.

### Validation

`tests/regression/test_reproducible_release_artifacts.py`: canonical form on
synthetic archives, an end-to-end build of two copies of the tracked tree
under different mtimes and umasks with identical digests, fail-closed epoch
handling, and workflow contract checks (single recipe, same Python and epoch,
exactly pinned backend).
