# ADR-064: Cursor Client Instantiation and Proof Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-064-cursor-client-instantiation-and-proof-boundary.md
layer: architecture_decisions
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-07-27
/L9_META -->

## Status

Accepted (2026-07-27)

## Context

Wiring the memory control plane into Cursor previously relied on
`scripts/write_cursor_config.py`, a standalone script that rewrote
`~/.cursor/mcp.json` with a plain, non-atomic `write_text` call, produced
no durable evidence, could not report drift, and had no uninstall or
verification path. The repository's recursive design requires that every
mutation of external state be contract-governed, atomic, evidence-bearing,
and fail-closed, and that "memory is on" claims be provable rather than
asserted. Editor configuration is external state exactly like the canonical
store: an unmanaged write path is a bypass of the control plane.

Instantiation also lacked a proof boundary. Installing a config entry only
proves that JSON was written; it does not prove that the generated command
launches, completes the MCP handshake, exposes the required tool inventory,
and reports a healthy service. Without that proof, the activation loop in
Cursor cannot be closed.

## Decision

Introduce `l9_graphite_memory.client_config` as the single canonical
control plane for client instantiation, exposed through the CLI as
`l9-memory client cursor {inspect,install,verify,status,uninstall}`.

The configurator owns exactly one key (`l9-graphite-memory`) inside
`mcpServers` and never modifies unmanaged servers or unknown top-level
keys. Every mutation is preceded by a fail-closed inspection, guarded
against TOCTOU divergence by SHA-256 digest re-verification, written
through a fsynced sibling temporary file with `os.replace`, permissioned
at 0600, preceded by a digest-bound timestamped backup, and emitted as a
frozen `ClientConfigReceipt` carrying pre/post digests, backup binding,
preserved keys, and the policy version `client-config/v1`.

Proof of instantiation is obtained exclusively through
`client_config.mcp_probe`, which launches the exact generated argv and
drives the real JSON-RPC handshake (`initialize`,
`notifications/initialized`, `tools/list`, `tools/call memory.health`),
asserting the canonical tool inventory and a healthy service status, and
returning a frozen `ProbeReceipt` with redacted stderr evidence. The probe
never imports store or projection layers; the wire protocol of the spawned
process is the only evidence channel, which is the same channel Cursor
itself uses.

`scripts/write_cursor_config.py` becomes a compatibility wrapper that
preserves its pinned `server_entry`/`write_config` interface while
delegating every mutation to the configurator, so exactly one write path
exists. The generated entry remains secret-free by construction: an argv
array with no `env` block, consistent with the stdio secret model where
credentials are resolved at runtime by the server process.

## Alternatives Considered

Extending the existing script in place with backups and verification was
considered, as was shipping a separate standalone installer package, and
documenting a manual editing procedure for `~/.cursor/mcp.json` in the
runbook.

## Rejected Alternatives

Extending the script was rejected because operations-layer scripts cannot
host contracts or be imported by the CLI without inverting layer
boundaries, and the logic would remain untestable as a unit. A standalone
installer package was rejected because it would duplicate version, contract,
and policy definitions outside the control plane. Manual editing guidance
was rejected because unmanaged writes produce no receipts, cannot be
drift-checked, and violate the fail-closed mutation invariant.

## Invariants

The configurator mutates only the managed `l9-graphite-memory` key and
preserves all other bytes of user intent. Every non-dry-run mutation
produces a digest-bound backup and a frozen receipt with pre/post SHA-256
evidence. Malformed, symlinked, or concurrently modified targets block the
operation without partial writes. The managed entry never contains an
`env` block or any secret material. Probe success requires the full
handshake, the complete required tool inventory, and a healthy
`memory.health` status; anything less is a failed probe. Restore accepts
only backups whose content digest matches the digest fragment embedded in
their filename.

## Consequences

Cursor instantiation becomes a first-class, testable control-plane
capability with a closed activation loop: install produces a receipt,
verify produces proof, status detects drift, and uninstall restores prior
state. The CLI gains a `client` command group that future clients (Claude
Desktop, other MCP hosts) can extend under the same contracts. The
compatibility wrapper keeps existing automation and the pinned regression
suite working unchanged. Preflight and release validation grow one gate
each, increasing runtime marginally.

## Security Impact

The attack surface of config mutation shrinks: symlink redirection is
blocked, permissions tighten to 0600, TOCTOU races fail closed, and backups
are tamper-evident through digest binding. Secret hygiene improves because
probe stderr is redacted against process-environment secret values before
entering any receipt, and the secret-free entry invariant is now enforced
by contract and covered by unit, integration, and regression tests rather
than convention.

## Migration Impact

No stored data, schema, or wire contract changes. Existing configs written
by the legacy script are recognized as current when they match the
canonical entry and are repaired in place (with backup) when drifted.
Consumers of `scripts/write_cursor_config.py` keep the same interface and
output shape. The ADR ledger extends to ADR-064 and the assurance
validator's expected range advances accordingly.

## Validation Requirements

Unit tests must cover idempotent install, scope preservation of unmanaged
servers and unknown keys, drift repair, dry-run purity, blocked states for
malformed JSON, non-object roots, non-object `mcpServers`, and symlinked
targets, digest-bound backup creation, restore verification including
tamper rejection, status derivation, and secret-free receipts. Integration
tests must prove the full stdio handshake against the generated command,
fail-closed behavior for a broken interpreter, stderr redaction, and the
CLI lifecycle round trip. `scripts/preflight.sh` must gate on a dry-run
install, and `scripts/validate_release.sh` must capture installed-package
lifecycle evidence.

## Rollback Conditions

Revert to the standalone script if the configurator is shown to corrupt
user configs, if receipts leak secret material, or if the probe produces
false-positive proofs. Rollback consists of restoring the previous script
body and removing the `client` CLI group; on-disk configs remain valid
because the managed entry shape is unchanged.

## Supersedes / Superseded By

Supersedes the unmanaged write path of `scripts/write_cursor_config.py`
introduced with the packaging baseline. Not superseded.
