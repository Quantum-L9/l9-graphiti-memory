# ADR-062: L9 Metadata and File Provenance

**Date:** 2026-07-22
**Decision owner:** Quantum-L9 architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.2+

## Status

Accepted

## Context

The recursive-alignment contract requires every tracked file to carry L9 metadata. v2.1 had no file-level metadata, so ownership, layer, status, and release identity could not be mechanically verified.

## Decision

Comment-safe tracked files carry an inline `L9_META` block. Every packaged file, including legal, JSON, binary, and generated evidence files, carries canonical metadata through its cryptographic `manifest.json` entry. The manifest itself carries top-level metadata and intentionally excludes only its own digest.

## Alternatives Considered

- Add metadata only to Python files
- Store provenance only in Git history
- Insert comments into JSON and other non-commentable formats

## Rejected Alternatives

Partial metadata fails coverage, Git history is not present in release ZIPs, and invalid comments would break machine-readable artifacts.

## Invariants

- Every packaged file has a manifest metadata carrier
- Comment-safe tracked source also has inline metadata
- Metadata path equals the manifested path
- Manifest hashes validate after packaging

## Consequences

Positive: release ownership and layer provenance are independently inspectable. Negative: broad source edits occur when the metadata schema changes.

## Security Impact

Metadata does not contain credentials, user data, or mutable authorization claims.

## Migration Impact

Existing source files receive metadata without changing runtime semantics. Manifest schema advances to v2.

## Validation Requirements

- Inline metadata scan
- Manifest metadata coverage scan
- Size and SHA-256 verification
- Clean-room ZIP validation

## Rollback Conditions

A superseding metadata carrier may replace this design only if it preserves complete packaged-file coverage.

## Supersedes / Superseded By

Supersedes incomplete file provenance in prior releases. No later ADR supersedes this decision.
