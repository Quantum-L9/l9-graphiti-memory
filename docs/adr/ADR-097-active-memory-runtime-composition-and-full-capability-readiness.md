# ADR-097: Active-Memory Runtime Composition and Full-Capability Readiness

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-097-active-memory-runtime-composition-and-full-capability-readiness.md
layer: adr
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-10-09
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.6+

## Status
Accepted

## Context
ADR-065 through ADR-068 delivered the active-memory subsystem: deployment
identity, secret-file credential resolution, the `ActiveAgentClient` public
SDK with its lifecycle state machine, and the Redis ACL contract. ADR-067
states that consumers receive an already-constructed client from "the runtime
factory" and never instantiate adapters. The census bound to source revision
`24a579b` found that no such factory existed: `MemorySettings` carried no
active-memory field, `build_runtime()` composed the canonical store, the
projection runtime and graph intelligence only, nothing under `src/` imported
`l9_graphite_memory.active`, the Redis awareness bus was never instantiated
even by a test, and no health or readiness surface reported the Redis leg.
The `ActiveMemoryBinding` the SDK promised was a docstring. A consumer that
selected the full-capability shared deployment (one PostgreSQL canonical store,
Graphiti projection plus Neo4j graph intelligence, Redis active store plus
awareness bus) could therefore install the symbol and never reach the
capability, and nothing would say so.

Two further defects surfaced in the same census. The session's recovery path
took an edge the ADR-067 state machine forbids (`DEGRADED -> RE_REGISTERING`),
so an outage longer than the lease TTL ended the heartbeat loop permanently.
And the adapters' `health()` was a bare `PING` returning hard-coded
"authenticated", while `docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md` item 6
requires a startup capability probe over scalar, sorted-set and publish
commands.

The package remains a locally composed L9 Dependency whose providers are
optional. "Optional" describes package portability; it must not describe the
acceptance criteria of a deployment that selected the capability.

## Decision
1. **Active memory is composed from settings by the runtime factory.**
   `MemorySettings` gains an `active_memory_backend` (`none` | `redis`), an
   `active_memory_required` flag, the deployment identity (`active_deployment_id`,
   `active_trust_domain`, `active_environment`), exactly one ADR-066 credential
   source (`active_redis_url_env`, `active_redis_url_file`,
   `active_redis_password_file` with host/port/database/tls/username, or
   `active_redis_secret_reference`), the key prefix, and the TTL, heartbeat
   and lease parameters, each with an `L9_MEMORY_ACTIVE_*` environment
   binding. The credential itself is never a settings value; only the source
   name is recorded in receipts.
2. **`adapters.factory.build_active_memory(settings)` is the one construction
   path.** It yields an `ActiveMemoryBinding` holding the adapters, the
   deployment identity, the `required` policy and the session parameters.
   `none` binds `NullActiveStore` and `NullAwarenessBus`; `redis` resolves the
   credential through `resolve_redis_credential` and binds `RedisActiveStore`
   and `RedisAwarenessBus` to the deployment. `ActiveMemoryBinding.client()`
   is how a consumer obtains an `ActiveAgentClient`; the adapter classes stay
   out of `active.__all__` (ADR-067). `build_runtime()` composes the binding
   into `MemoryRuntime.active_memory` beside canonical memory, never inside it.
3. **Readiness is reported per capability family, with an aggregate verdict.**
   `MemoryRuntime.readiness()` returns a `ReadinessReport` of five
   `ReadinessFamily` entries: `canonical`, `projection`, `graph`,
   `active_store`, `awareness_bus`. Each family is probed on its own evidence
   and carries `selected`, `required`, `healthy` and `ready`. A required
   family is ready only when it is selected and healthy; an optional family is
   always ready and only degrades the status. `ready` is the aggregate;
   `full_capability` is true only when every family is selected and healthy.
   `GET /readyz` and `l9-memory readiness` expose the report; `/readyz`
   returns 503 whenever the aggregate is not ready. `memory.health` and
   `/healthz` keep their canonical-plus-projection shape (ADR-090).
4. **The Redis adapters run the deployment-contract capability probe.** The
   store's `health()` performs `PING`, a scalar write/read/unlink and a
   sorted-set add/range/remove under the deployment prefix; the bus's
   `health()` performs `PING` and `PUBLISH` on a probe channel. Each reports
   the steps that completed, classifies an authentication refusal, raises the
   typed unavailable error when the server is unreachable, and never returns a
   hard-coded verdict.
5. **The session recovers through the ADR-067 state machine.** A lease
   rejected while the session is `DEGRADED` transitions through
   `RESYNCHRONIZING` to `RE_REGISTERING`; a lease rejected while `DRAINING`
   is the expected end state and is not re-registered. Registration, context
   replacement, draining and unregistration publish lifecycle pointer events
   on the awareness bus, best effort, so a peer subscribed to the deployment
   or a group sees the change and re-reads current state; a bus failure never
   fails the store operation it follows. `ActiveAgentSession.get_peer_context`
   reads a peer's committed context.
6. **The Redis awareness bus is a conformance subject.** The
   `tests/conformance/active` bus fixture is parameterized like the store
   fixture, so every AwarenessBus contract runs against Redis whenever
   `L9_MEMORY_TEST_REDIS_URL` is set, and the Redis bus applies the same
   deployment and role filters as the reference adapter.
7. **Live proof is a CI obligation, not a developer-machine memory.** The
   `full-capability-live` job provisions PostgreSQL, Redis and Neo4j with GDS,
   runs the composed-runtime suite and the live active-memory suite, stops and
   restarts its own Redis for the outage case, and fails if any case skips.
   A Graphiti MCP endpoint is not provisioned in CI; the projection family is
   proven in composition against the official-dialect in-process server and
   its live proof remains an external obligation recorded in the capability
   closure matrix.

## Alternatives Considered
- **Leave construction to the consumer and document it.** Rejected: that is
  the state ADR-067 was written to end; consumers must import internal adapter
  modules to do it, and no readiness surface can then describe what they built.
- **Report active memory inside `memory.health` / `HealthReport`.** Rejected:
  `HealthReport` is a bound control-plane contract that consumers already
  parse; widening it would force every consumer to change, and ADR-090 already
  keeps graph out of it for the same reason. A separate readiness report keeps
  the health shape stable and adds the aggregate verdict beside it.
- **Make the Redis leg mandatory for every installation.** Rejected: the
  package stays a portable dependency with optional providers; the selected
  deployment expresses its obligation through `required` flags, and readiness
  enforces them.
- **Treat an installed symbol or a `PING` as proof.** Rejected: the
  deployment contract requires a capability probe, and a hard-coded
  "authenticated" is precisely the false green this ADR exists to remove.

## Rejected Alternatives
Consumer-side construction and a `PING`-only health were rejected because
each produces a deployment that can report green while the capability it
selected is unreachable, and neither can be checked from the package's own
assurance surfaces. Widening `HealthReport` was rejected because it changes
a contract consumers bind to by version without changing the version.

## Invariants
- Active memory is composed beside canonical memory; a `MemoryService` read or
  write never depends on, waits for, or fails because of the active-memory
  binding.
- `build_active_memory` is the only path that binds a Redis adapter in this
  package; `active.__all__` exports no adapter class
  (`tools/assurance/check_active_memory_public_api.py`).
- A credential never appears in `MemorySettings` repr, in a receipt, in the
  readiness report or in a log; only `credential_source` does.
- A required family that is absent or unhealthy makes `ReadinessReport.ready`
  false and `/readyz` 503. `full_capability` is never true while any family
  is unselected or unhealthy.
- Every edge the session takes exists in the ADR-067 diagram.
- The Redis adapters' `health()` reports the probe steps that actually ran.

## Consequences
- Positive: a consumer binds the full-capability deployment with settings
  alone and proves it with `l9-memory readiness` or `/readyz`.
- Positive: the Redis awareness bus is now covered by the conformance suite and
  by a live two-consumer test; the session recovery bug is fixed with a
  regression test that fails on the previous edge.
- Negative: `MemoryRuntime.close()` must release async Redis clients from a
  synchronous caller; it runs the teardown on a fresh loop when none is
  running and tolerates connections already torn down.
- Negative: the full-capability CI job adds a three-service run to every push.

## Security Impact
Credentials are resolved by the ADR-066 resolver at construction time and
never persisted in settings, generated configuration or receipts; the probe
key and channel live under the deployment prefix the ACL contract (ADR-068)
already grants, so a restricted ACL is exercised by the probe exactly as by
production traffic. Deployment identity is validated (placeholder values are
refused in production) before any connection is opened. A readiness report
exposes connectivity and authentication classification only.

## Migration Impact
No stored data changes. Existing deployments default to
`active_memory_backend: none`, which binds the null adapters and reports the
families as not selected; `/readyz` keeps returning 200 for them. Consumers
that constructed adapters by hand should move to `build_active_memory` or
`build_runtime().active_memory.client()`; the hand-built path keeps working
but is outside the SDK compatibility policy.

## Validation Requirements
- `tests/unit/test_active_memory_runtime.py`: settings validation and
  environment binding, factory outcomes without a connection, readiness
  aggregation (required-absent, required-unhealthy, optional-unhealthy),
  `/readyz` carrying the families, the CLI command, the lifecycle regression
  and two in-memory sessions sharing presence, context and awareness.
- `tests/conformance/active`: the bus contract on the in-memory and Redis
  adapters.
- `tests/integration/test_active_memory_redis_live.py`: two independent
  bindings over one Redis, deployment isolation, an unreachable backend
  reported not assumed, and a real stop/start outage with recovery through
  re-registration.
- `tests/integration/test_full_capability_readiness_live.py`: one
  `build_runtime()` over PostgreSQL, Neo4j and Redis with every family
  required; canonical writes reaching graph intelligence through the composed
  runtime; `/readyz`; the projection family joining the verdict against the
  official-dialect server; a required outage failing readiness while
  canonical memory keeps working; a required unconfigured family never green.
- CI job `full-capability-live` fails if any of those cases skips.

## Rollback Conditions
Revert this ADR if composing active memory in `build_runtime()` is shown to
couple canonical memory availability to Redis availability in any code path,
or if the readiness families cannot be made to agree with the deployment
contract for a real consumer. Rollback removes the settings fields, the
factory function, `MemoryRuntime.active_memory`, the readiness report and the
CI job; the lifecycle fix and the capability probe stand on ADR-067 and the
deployment contract and are not rolled back with it.

## Supersedes / Superseded By
Supersedes no prior ADR; realizes the runtime-factory construction ADR-067
describes and the capability probe `docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md`
requires. Not superseded.
