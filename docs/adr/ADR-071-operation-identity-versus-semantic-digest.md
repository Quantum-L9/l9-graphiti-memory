# ADR-071: Operation Identity Versus Semantic Digest

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-071-operation-identity-versus-semantic-digest.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-08-20
/L9_META -->


**Date:** 2026-08-20
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted

## Context

ADR-008 allowed a write without an explicit idempotency key to fall back to a
key derived from the normalized content digest: `memory:{namespace}:{digest}`.
That single fallback conflated two unrelated questions.

*Is this the same operation?* is a transport question. It is answered by the
caller, who alone knows whether a call is a first attempt or a retry after a
timeout.

*Does this mean the same thing as something we already know?* is a semantic
question. It depends on temporal validity, contradiction, evidence strength,
and the surrounding namespace, and it cannot be settled by string equality on
one field.

Deriving retry identity from content answered the second question with the
first question's machinery. Two agents that independently observed the same
fact were told the second observation was a duplicate, so the corroborating
observation, its distinct provenance, and its distinct evidence were silently
discarded. Meanwhile a genuine retry whose content re-normalized differently
produced a second record, which is the failure the key was meant to prevent.

## Decision

Retry identity is explicit. `MemoryWriteRequest.idempotency_key` names an
operation: two calls carrying the same key in the same tenant and namespace are
the same operation, and the later one returns `DUPLICATE` with the original
record ID.

Omitting the key means "this is a new operation". `MemoryService` mints a
per-call identity, `operation:{namespace}:{uuid4}`, which is unique by
construction and carries no content. Identical content submitted twice without
a key is admitted twice.

The normalized digest keeps its place on the record and its index, but only as
a maintenance candidate signal. Semantic duplication is resolved after the fact
by scheduled maintenance (ADR-075), which can weigh temporal validity and
contradiction, not at admission where none of that context is available.

`WriteReceipt.idempotency_key_supplied` reports whether the caller supplied
retry identity, so a caller can tell an operation-scoped receipt from a
call-scoped one.

## Alternatives Considered

- Keep the digest-derived fallback and add an opt-out flag
- Derive the fallback from provenance instead of content
- Require an explicit key on every write
- Mint a per-call identity when no key is supplied

## Rejected Alternatives

- An opt-out flag keeps content-based collapse as the default, so the silent
  loss of corroborating observations remains the normal outcome.
- Provenance-derived keys are still implicit identity: two calls with the same
  provenance may be independent observations, and a retry may legitimately
  carry different provenance.
- Requiring a key on every write breaks every existing caller and offers no
  benefit over minting one, since a caller with no retry semantics has nothing
  meaningful to supply.

## Invariants

- The same explicit key in one tenant and namespace resolves to one record
- Identical content under distinct operations is admitted independently
- No default admission identity contains a content digest
- The duplicate lookup runs only when the caller supplied a key
- `normalized_digest` is persisted and indexed but never governs admission

## Consequences

Positive: Corroborating observations survive. Retry semantics are honest and
controlled by the only party that knows them. Semantic consolidation moves to a
stage that has the temporal context to do it correctly.

Negative: Callers that relied on content-based collapse now write duplicates
until maintenance consolidates them, so a namespace holds more raw records
between maintenance runs. Callers that want retry protection must supply a key.

## Security Impact

None directly. Removing content from the default admission identity slightly
reduces content exposure in receipts and audit logs, since an operation
identity no longer embeds a digest of the memory it admitted.

## Migration Impact

Existing records keep their stored `idempotency_key`, including legacy
`memory:{namespace}:{digest}` values, and a caller that still supplies such a
key still dedupes against them. No data migration is required. Callers that
depended on the implicit fallback must either supply a key or accept duplicate
admission pending maintenance.

## Validation Requirements

- Paired tests prove same-key retries dedupe across store backends
- Paired tests prove identical content under distinct operations is admitted
- Tests prove the default identity contains neither digest
- Tests prove duplicate content stays discoverable by digest for maintenance

## Rollback Conditions

Restoring the digest-derived fallback re-enables content collapse at admission.
Records admitted under this decision are already distinct and would not be
merged retroactively by that rollback; consolidating them requires maintenance.

## Supersedes / Superseded By

Amends ADR-008: the digest-derived idempotency fallback described there is
withdrawn. Every other ADR-008 invariant, including supersession semantics,
remains in force.

No later ADR supersedes this decision as of 2026-08-20.
