# ADR-058: Graphiti Repository Name and Graphite Package Compatibility

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-058-graphiti-repository-name-and-graphite-package-compatibility.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.1+

## Status

Accepted

## Context

The repository is named l9-graphiti-memory while the published Python distribution and import package historically use graphite. Renaming either surface without a migration plan would break installers, imports, scripts, and consumers.

## Decision

Keep the repository and product term Graphiti because it describes the graph-memory integration. Preserve the distribution name l9-graphite-memory and import package l9_graphite_memory through the v2 compatibility window. Documentation must state the distinction. A future rename requires a new major-version ADR, redirect packages, import shims, and consumer telemetry.

## Alternatives Considered

- Rename the package immediately
- Rename the repository to match the typo
- Leave the inconsistency undocumented

## Rejected Alternatives

- Immediate rename breaks consumers
- Repository renaming erases product meaning
- Undocumented divergence causes repeated operator error

## Invariants

- Existing entrypoints and imports remain stable in v2
- New documentation uses Graphiti for architecture and graphite only for literal package identifiers
- No second implementation package is created

## Consequences

Positive: Compatibility is preserved without duplicating code

Negative: The historical naming distinction remains visible

## Security Impact

Avoiding duplicate packages prevents dependency confusion. Package publishing must use the canonical project identity and signed release process.

## Migration Impact

No data migration is required. Install and import documentation is clarified.

## Validation Requirements

- Installed-wheel entrypoint tests
- Package metadata tests
- Documentation drift scan for incorrect commands

## Rollback Conditions

Revert documentation-only clarifications; package and repository identities remain unchanged.

## Supersedes / Superseded By

Clarifies ADR-001, ADR-020, and ADR-023.

No later ADR supersedes this decision as of 2026-07-22.
