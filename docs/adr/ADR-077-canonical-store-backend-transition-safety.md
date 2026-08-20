# ADR-077: Canonical Store Backend Transition Safety

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-077-canonical-store-backend-transition-safety.md
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

ADR-072 added a shared canonical backend and deliberately excluded data
migration between backends: moving canonical records is an irreversible
operation that needs its own evidence and rollback contract, and folding it
into a configuration flag would have made a destructive act look like a setting.

That exclusion is still right. What it left behind is an operational trap.

Changing `store_backend` points the control plane at a different canonical
store. The new store initializes cleanly, reports `healthy: true`, and holds
zero records. Nothing is destroyed — the prior store keeps everything — but the
running system has no idea it exists. An operator adopting the shared backend,
which is exactly the move ADR-072 invites, gets a green health check over an
empty namespace and no indication that their memory is somewhere else.

The failure is quiet and it is worst precisely when the system looks fine.
Agents hydrate empty context, write new records into the new store, and the
divergence compounds until someone notices the namespace is thin.

Documentation was the only guard. Documentation is not a guard.

## Decision

Startup fails closed on an unacknowledged backend transition.

After a store initializes, `build_store` checks whether the configured store is
empty while a prior canonical ledger belonging to this deployment still holds
records. When both hold, construction raises `ConfigurationError` naming the
prior ledger, its location, and its record count, and states plainly that
nothing has been lost and that migration is a separate operation.

A deliberate fresh start is permitted once it is stated:
`L9_MEMORY_ACKNOWLEDGE_BACKEND_TRANSITION=1`
(`acknowledge_backend_transition` in configuration). The escape hatch is
explicit and per-deployment, so adopting a new backend intentionally costs one
environment variable while doing it by accident costs nothing but a clear error.

Detection is bounded by what can be established without credentials. A local
SQLite ledger is discoverable, so the common and dangerous direction — adopting
the shared backend while a local ledger holds the deployment's memory — is
caught. A postgres-to-postgres or postgres-to-sqlite move is not detectable
this way and is not claimed to be. The guard reduces a silent failure to a loud
one in the case that actually occurs; it is not a general migration checker.

Only a ledger with records blocks. An empty prior file, an unrelated SQLite
file, and reopening the configured store itself are all correctly not
transitions.

## Alternatives Considered

- Document the risk and rely on operator care
- Warn on startup but continue
- Migrate the data automatically when a transition is detected
- Fail closed with an explicit acknowledgement escape hatch

## Rejected Alternatives

- Documentation was already the state of the world and did not prevent a
  healthy-looking empty store. A trap that only a careful reader avoids is
  still a trap.
- A warning is swallowed by log aggregation and by every automated deployment
  that does not read startup output. The condition is serious enough that
  continuing is the wrong default.
- Automatic migration is precisely what ADR-072 declined, and for good reason:
  it is irreversible, it needs evidence, and inferring intent from a config
  change is how data gets moved by accident.

## Invariants

- A populated configured store is never treated as a transition
- Only a prior ledger holding at least one record blocks startup
- The configured store is never mistaken for its own prior store
- A file that is not a canonical ledger is ignored
- Blocking is bypassed only by explicit acknowledgement
- The guard reads prior ledgers read-only and never mutates them
- No data is moved between backends by this decision

## Consequences

Positive: The most likely way to lose sight of canonical memory now fails
loudly at startup with an actionable message, instead of succeeding into a
misleading healthy state.

Negative: A deliberate backend adoption requires one additional environment
variable, which will surprise the first operator who hits it. The guard reads
candidate SQLite files in the data directory at startup, a small fixed cost.
Transitions between two remote backends remain undetectable and unguarded.

## Security Impact

The guard opens prior ledgers read-only (`mode=ro`) and reads only a row count.
It reports a filesystem path and a count, never memory content. It is exempt
from the direct-SQLite-connect rule in `check_memory_write_bypass.py` for the
connect call alone; the mutation-marker rule still applies to it in full, so it
cannot acquire a write path without failing that check.

## Migration Impact

No data migration, by design. Deployments already running on a single backend
are unaffected. A deployment that has *already* switched backends and is
running on an empty store will now fail on its next start until it either
points back at the populated store or acknowledges the transition — which
surfaces a problem that already existed rather than creating one.

## Validation Requirements

- Tests prove switching to an empty backend beside a populated ledger fails
  closed, and that the message names the ledger, its record count, and the
  acknowledgement variable
- Tests prove acknowledgement permits startup
- Tests prove reopening the same ledger is not a transition
- Tests prove a populated configured store is never a transition
- Tests prove a first run with no prior ledger starts normally
- Tests prove an empty prior ledger and a non-ledger SQLite file do not block
- Tests prove the shared backend is guarded when a local ledger holds records

## Rollback Conditions

Reverting restores silent startup on an empty backend. Deployments that added
the acknowledgement variable are unaffected by the revert; the variable simply
stops being read.

## Supersedes / Superseded By

Completes ADR-072 by guarding the operational trap its scope boundary left
open. It does not change that boundary: cross-backend data migration remains
out of scope and unauthorized.

No later ADR supersedes this decision as of 2026-08-20.
