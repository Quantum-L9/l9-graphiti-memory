# ADR-105: Reviewed Remaining-Proof Classification in Release Evidence

**Date:** 2026-11-14
**Decision owner:** Quantum-L9 memory architecture, from the operator decision of 2026-11-14
**Applies to:** `tools/assurance/generate_validation_evidence.py` (the external findings and `production_release_status` of the release evidence), `release-work/remaining-proof-classification.json`, and the "3.0.0 classification" in `docs/REMAINING_PRODUCTION_PROOF.md`

## Status

Proposed

The author of this change does not accept its own decision record. Merging
this record on the default branch by the decision owner accepts it; the index
status changes in that same merge.

## Context

The release evidence generator records five external findings, B-001 to
B-005. Each one names something local evidence cannot prove: Gate, live
providers, migration, hosted controls, and secrets. Until this record, every
finding carried a hard-coded `blocks_production_release: true`, and the
report's `production_release_status` was always `BLOCKED_ON_EXTERNAL_VALIDATION`
when the local checks passed. That status dates from the 2.2.0 pack. It was in
the evidence when 2.6.0 was admitted and published.

For 3.0.0 the remaining-proof items RP-001 to RP-009 were classified per item,
separately for the package and the hosted carrier (pull request #127). The
classes are CLOSED, NOT APPLICABLE TO THIS RELEASE, OPEN — ACCEPTED RESIDUAL
RISK, and the release decision itself. A reviewer finding on #127 identified
the remaining contradiction. `publish.yml` uploads the generator's report beside
`VALIDATION.md`, so prose that called the release admissible would sit next to
executable evidence that called it blocked, and a consumer that honours the
machine-readable evidence would reject the release.

## Decision

1. The reviewed classification has one source of truth:
   `release-work/remaining-proof-classification.json`
   (`l9-graphiti-memory/remaining-proof-classification@1`). It records:
   - the release;
   - one (item, scope, class) row per remaining-proof item and scope;
   - the mapping from each external finding to the items it stands for.
   The table in `docs/REMAINING_PRODUCTION_PROOF.md` states the same rows, and
   a test fails when they disagree.
2. The generator keeps every external finding. It never deletes one because it
   has been classified. Each finding now carries its classification rows.
   `blocks_production_release` is computed from those rows. A finding is
   non-blocking only when every mapped item has at least one row and each of
   its rows is CLOSED, NOT_APPLICABLE_TO_THIS_RELEASE or
   OPEN_ACCEPTED_RESIDUAL_RISK, with a known scope.
3. The generator computes `production_release_status`:
   - `BLOCKED_ON_VALIDATION` when a local check fails or is unknown (unchanged);
   - otherwise `BLOCKED_ON_EXTERNAL_VALIDATION` when any finding blocks;
   - otherwise `ADMISSIBLE_WITH_ACCEPTED_RESIDUAL_RISK`.
   The last status claims only that every recorded external finding is
   classified as non-blocking for this release. It does not claim that
   production validation happened, and the findings remain in the report.
4. The classification fails closed. Any of the following makes every finding
   blocking and the report `BLOCKED_ON_EXTERNAL_VALIDATION`:
   - the file is missing, unreadable or invalid;
   - its schema is wrong;
   - its release differs from the generator's `RELEASE` or from
     `PACKAGE_VERSION`.

   A finding with no mapping, an item with no row, or a row with an unknown
   class or scope makes that finding blocking.
5. Acceptance is the merge. The classification file and the document are
   proposed for acceptance by the decision owner, and merging them on the
   default branch is that acceptance. The admission receipt (ADR-094) remains
   the release decision. This record does not admit a release, a service or a
   deployment.

## Alternatives Considered

- Keep the generator hard-coded and let prose take precedence. The machine
  evidence would contradict the reviewed position.
- Delete classified findings from the report. That would hide what local
  evidence cannot prove.
- Put the classification inside `release-work/product-release-binding.yaml`.
  The binding is a release-identity record checked by its own tests. The
  classification is per release and changes for each one.

## Rejected Alternatives

- Hand-editing `blocks_production_release` to `false` in the tool. It loses the
  review, and the next release would inherit it silently.
- A non-blocked status that names validation ("VALIDATED", "APPROVED",
  "PRODUCTION_READY"). No external proof ran.

## Invariants

- Every external finding is recorded whatever its classification.
- No status string claims production validation.
- Anything the classification does not settle blocks.
- The document table and the classification file state the same rows.
- A classification for one release never applies to another release.

## Consequences

Positive: the uploaded evidence agrees with the reviewed classification. Each
release needs a new reviewed classification, or its evidence reports blocked.

Negative: a version bump without a new classification makes release evidence
report `BLOCKED_ON_EXTERNAL_VALIDATION` until one is reviewed. This is
intended.

## Security Impact

No runtime change. The classification cannot hide a finding. It can only mark
a recorded finding non-blocking, through a reviewed and merged file.

## Migration Impact

None. The report keeps its schema `l9.validation-report/v1` and its existing
fields. It adds `external_findings_blocking` and `release_classification`, and
each finding adds `blocking_reasons` and `release_classification`. No consumer
in this repository reads `production_release_status`,
`blocks_production_release` or the findings file.

## Validation Requirements

`tests/regression/test_remaining_proof_classification.py`:

- the document and the file agree;
- the file is for this release;
- every finding is mapped;
- this tree's evidence is admissible with all five findings recorded;
- the generator fails closed on:
  - a missing file;
  - an unparseable file;
  - a finding with no mapping;
  - an item with no row;
  - an unknown class;
  - the release-decision class;
  - a release different from `PACKAGE_VERSION`;
  - a classification for another release.

`bash scripts/validate_release.sh` produces the report.

## Rollback Conditions

Revert this record together with the generator change. The report returns to
the hard-coded blocked status. The classification document can remain as
prose.

## Supersedes / Superseded By

Supersedes the hard-coded external-finding status of the 2.2.0 evidence
generator. It does not supersede ADR-101; V-001 is unchanged.
