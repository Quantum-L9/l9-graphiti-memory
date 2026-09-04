# ADR-080: Automated Quarantine Review

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-080-automated-quarantine-review.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-09-04
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted

## Context

ADR-007 quarantines a record when admission sees a safety signal or, under a
stricter policy, redacted PII. Quarantine is durable and excluded from default
retrieval, which is right for the moment of admission: nothing in the write
path can tell a benign mention of "ignore previous instructions" from an
attack, and admission must stay deterministic.

Until this decision the only exits from quarantine were administrator
promotion, which requires a class change and produces a new record, and
verified deletion. A record a person had read and judged harmless had no
honest path back into retrieval, and nobody was reading them: the forensic
codebase audit of 2026-09-04 listed the missing transition as an UNKNOWN. The
operator's answer was that review should be automated, with a person asked
only when something is genuinely serious, so that quarantine does not become
a bottleneck.

## Decision

Quarantine review is a scheduled maintenance operation, `REVIEW_QUARANTINE`,
performed by an injected reviewer under a review policy, and applied through
the governed lifecycle path with the verdict recorded as evidence.

**The reviewer is a port.** `ports.QuarantineReviewer` returns a
`QuarantineReviewVerdict` for one record: RELEASE, HOLD, or ESCALATE, with a
confidence, reasons, optional blockers, and the reviewer and model identity.
It never mutates canonical state. The model binding is injected the way
provider-backed extraction already is: `curation.EvidenceBoundProviderReviewer`
wraps any `StructuredReviewProvider` (an object with `review(payload) -> dict`),
validates its answer strictly, and fails closed. A malformed answer becomes
ESCALATE carrying the validation error, so a misbehaving reviewer is seen by
a person; a raised exception becomes HOLD, because an outage is not a finding
about the record. A deployment names its provider with
`L9_MEMORY_QUARANTINE_REVIEW_PROVIDER` as `package.module:factory`. With no
provider, `NullQuarantineReviewer` holds everything and the run reports each
quarantined record as unreviewed rather than leaving it silently in place.

**The policy decides, not the verdict.** `QuarantineReviewPolicy` turns an
opinion into an act: a record that carried a credential-shaped value
(`blocker_pii_types`) or an exfiltration signal (`blocker_safety_signals`) is
escalated whatever the reviewer said; a RELEASE below `release_min_confidence`
becomes a HOLD, never an ESCALATE, because uncertainty is not a serious blocker
and must not interrupt anyone; one run performs at most
`max_reviews_per_run` reviews.

**Release is a governed transition.** `MemoryService.transition_lifecycle`
gains `(QUARANTINED, ACTIVE)` under ADMIN. When a RELEASE verdict for that
exact record with no blocker accompanies the call, MAINTAIN suffices and the
verdict is written to the lifecycle receipt as `INFERENCE` evidence naming the
reviewer and model. Any other verdict never lowers the authority required. The
transition emits projection intent like any reactivation (ADR-074), so a
released record becomes retrievable in the provider too.

**Outcomes and idempotence.** RELEASE and ESCALATE are applied actions: their
digest is recorded and the reviewer is not asked about that record again.
HOLD stays unapplied, so the record is planned again next run. Escalated
record ids are carried on `MaintenanceRunReceipt.escalated_record_ids`, the
one place a person has to look. A dry run plans reviews without calling the
reviewer.

## Alternatives Considered

- Require a person to release every quarantined record
- Let the reviewer release records directly through the store
- Re-run admission with a laxer policy instead of reviewing

## Rejected Alternatives

- A person on every record is the bottleneck the operator named; the signals
  that cause quarantine fire far more often than they find an attack.
- A reviewer with store access would be a second write authority beside the
  service, which ADR-036 forbids; the reviewer returns evidence and the
  service acts on it under the review policy.
- Re-admitting with a laxer policy discards the signal instead of judging it,
  and leaves no evidence of who decided the record was safe.

## Invariants

- Only `MemoryService.transition_lifecycle` releases a record from quarantine
- A release under MAINTAIN carries a RELEASE verdict for that record as evidence on the lifecycle receipt
- A verdict that is not a clean RELEASE never lowers the required authority
- A credential-bearing record or an exfiltration signal is escalated regardless of the verdict
- A malformed reviewer answer is never read as a release
- A dry run calls no reviewer
- Admission itself remains deterministic and unchanged (ADR-007)

## Consequences

Positive: quarantine stops being a dead end; the common case clears without
a person; the rare serious case reaches one with reasons attached; every
release is evidenced.

Negative: scheduled maintenance now depends on an external reviewer for one
operation, so its receipts carry model identity and confidence that
governance must be willing to read; a held record costs a review on each run
until it is released or escalated.

## Security Impact

Releasing content that admission flagged is exactly the act an attacker would
want automated. The policy therefore escalates every credential-shaped value
and every exfiltration signal to a person, requires high confidence for a
release, treats reviewer failure as hold and reviewer malformation as
escalate, and records the reviewer and model on the receipt. Prompt-injection
text is passed to the reviewer as data inside a structured payload, never as
an instruction. The provider binding is operator configuration with the same
trust as any other setting.

## Migration Impact

No schema change. `MaintenanceOperation` gains a member, so the default
operation set for `l9-memory maintain` now includes review; with no provider
configured every quarantined record appears in the run receipt as unreviewed.
`LifecycleTransitionReceipt` and `MaintenanceRunReceipt` gain optional fields
with empty defaults, so stored receipts remain valid.

## Validation Requirements

- `tests/unit/test_quarantine_review.py`: verdict validation, policy
  thresholds and blockers, null reviewer, provider loading
- `tests/integration/test_quarantine_review_maintenance.py`, parameterized
  over `STORE_BACKENDS`: release, hold, escalate, and unreviewed outcomes;
  authority rules for maintainer and administrator; dry run calls no reviewer
- The bypass scanner keeps `transition_state` and `commit_lifecycle` guarded

## Rollback Conditions

Remove `REVIEW_QUARANTINE` from the configured operations or unset the
provider; released records stay released with their evidence, and quarantined
records stay quarantined. Reverting the code restores the pre-decision state
in which administrator promotion and deletion are the only exits.

## Supersedes / Superseded By

Extends ADR-007 (admission and quarantine) with the review path it lacked, and
uses the governed lifecycle transition introduced by the ADR-074 amendment of
2026-09-04.

No later ADR supersedes this decision as of 2026-09-04.
