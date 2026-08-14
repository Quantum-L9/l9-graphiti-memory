You are taking over the final repository integration phase for:

`Quantum-L9/l9-graphiti-memory`

You have both repositories available:

```text
WRITE REPOSITORY:
  Quantum-L9/l9-graphiti-memory

READ-ONLY CONTRACT REPOSITORY:
  Quantum-L9/Cursor-Governance
```

Assume the Cursor-Governance generated-data control-plane work is merged.

Assume the following deployment and verification assets have already been built in `l9-graphiti-memory`:

```text
deployment/generated-data/
├── capability-manifest.yaml
├── principal-policy.yaml
├── namespace-mapping.yaml
├── retention-policy.yaml
├── cursor-command-env.example
├── migration-runbook.md
├── activation-runbook.md
├── rollback-runbook.md
├── verify_generated_data_tools.py
├── verify_cross_repo_contract.py
├── verify_migration.py
├── verify_backup_restore.py
├── verify_selector_indexes.py
├── load_test_generated_data.py
├── live_end_to_end_proof.py
└── fixtures/
    ├── governed-candidate.json
    ├── reuse-event.json
    ├── path-invalidation.json
    └── capability-response.json

tests/deployment/generated_data/
├── test_capability_manifest.py
├── test_principal_policy.py
├── test_namespace_mapping.py
├── test_command_protocols.py
├── test_cross_repo_contract.py
├── test_migration_verifier.py
├── test_backup_restore.py
├── test_selector_indexes.py
├── test_load_harness.py
└── test_live_proof_fail_closed.py
```

These files are not merely documentation. Treat them as an executable integration contract, activation specification, compatibility oracle, and acceptance suite.

Your task is to surgically bind those assets into the existing production architecture.

Do not redesign the repository.
Do not create parallel owners.
Do not create a second memory subsystem.
Do not weaken tests.
Do not modify Cursor-Governance.
Do not commit or push unless separately authorized.

# Primary objective

Make the deployed `l9-graphiti-memory` runtime actually support:

```text
Cursor-Governance governed memory candidate
→ public command or MCP operation
→ strict candidate contract
→ existing MemoryWriteRequest
→ existing MemoryService.write(...)
→ existing admission and canonical store
→ existing search and hydration
→ reuse-event persistence
→ source invalidation through existing lifecycle machinery
→ capability and health reporting
```

The canonical invariant is:

```text
Every durable memory write must continue through the existing authorized
MemoryService write path.
```

# Mandatory first step: inspect before modifying

Inspect the actual repository and identify the current owners for:

```text
MemoryService
MemoryService.write
MemoryWriteRequest
MemoryPrincipal
MemoryRecord
MemoryState
MemoryReceipt
OperationOutcome
EvidenceRef
Provenance
TemporalCoordinates
RecordStore
canonical store implementation
migration registry
CLI parser and command registration
MCP server and tool registration
health and capability reporting
metrics and observability
search
hydration
archive or quarantine lifecycle transitions
serialization and schema upcasting
ADR registry and assurance tooling
```

Also inspect the built files under:

```text
deployment/generated-data/
tests/deployment/generated_data/
```

Do not infer implementation names from this prompt when the repository uses different names.

Create a preflight report:

```text
.l9/generated-data-repository-binding-preflight.json
```

Include:

```json
{
  "canonical_write_service": "",
  "canonical_write_method": "",
  "canonical_write_request": "",
  "canonical_principal": "",
  "canonical_record": "",
  "canonical_receipt": "",
  "canonical_store_protocol": "",
  "canonical_store_implementations": [],
  "migration_owner": "",
  "command_owner": "",
  "mcp_owner": "",
  "health_owner": "",
  "observability_owner": "",
  "search_owner": "",
  "hydrate_owner": "",
  "lifecycle_owner": "",
  "serialization_owner": "",
  "existing_candidate_ingress": [],
  "existing_reuse_support": [],
  "existing_invalidation_support": [],
  "files_to_create": [],
  "files_to_modify": [],
  "collisions": [],
  "blocking_incompatibilities": []
}
```

Abort before source modification when:

* the canonical write path cannot be identified;
* more than one production write path exists;
* an equivalent governed-candidate ingress already exists and should be extended;
* reuse persistence already exists under another name;
* source invalidation already exists under another owner;
* the migration system cannot be identified;
* the requested work would require direct adapter-to-store writes;
* the deployment assets conflict materially with actual merged Cursor-Governance contracts.

Extend equivalent capabilities in place.

# Repository ownership boundaries

Cursor-Governance owns:

```text
packet emission
packet validation
harvesting
classification
cross-domain routing
governance promotion eligibility
campaign orchestration
learning closure
context selection
repository change event production
```

`l9-graphiti-memory` owns:

```text
memory candidate ingress
memory admission
canonical storage
memory authorization
search
hydration
reuse persistence
memory lifecycle
source invalidation
memory receipts
memory capability reporting
```

Do not move control-plane behavior into this repository.

# How to treat the already-built output

Treat the built deployment files as follows.

## `capability-manifest.yaml`

This is the declared public compatibility contract.

Bind runtime capability reporting to it, but do not return static readiness merely because the file exists.

Runtime capability responses must combine:

```text
declared support from the manifest
+
actual store readiness
+
actual migration state
+
actual command registration
+
actual MCP tool registration
+
actual search and hydration readiness
+
actual reuse and invalidation readiness
```

The manifest is authoritative for:

```text
supported schema majors
supported generated-data classes
rejected generated-data classes
reuse outcomes
invalidation event types
non-deletion rules
projection optionality
```

## `principal-policy.yaml`

Compile or map this into the existing authorization owner.

Do not create a second authorization engine.

The service principal:

```text
cursor-governance-generated-data
```

must be able to:

```text
ingest governed candidates
search
hydrate
record reuse
invalidate by source
read capabilities
```

It must not be able to:

```text
delete memory
promote memory
override policy
widen namespaces
override repository state
override canonical authority
```

The original subagent identity remains provenance, not the authenticated canonical writer.

## `namespace-mapping.yaml`

Bind it into the existing namespace/group authorization model.

Required behavior:

```text
campaign_local → campaign/{campaign_id}
repository_local → repository/{repository}
project_group → project-group/{project_group}
constellation_internal → constellation/internal
restricted → restricted/{policy_id}
```

Reject unknown visibility.

Permit narrowing.

Reject widening.

Do not make cross-repository search implicit.

Reuse inherits the referenced record namespace.

Invalidation requires authority over every matched record namespace.

## `retention-policy.yaml`

Map it into the existing retention owner.

Do not store raw subagent packets in Graphiti memory.

Cursor-Governance owns raw packets.

Graphiti may retain the governed candidate body for the configured audit window.

Reuse events, invalidation events, receipts, selectors, evidence, and lineage must follow the declared retention semantics.

## Fixtures

Treat fixtures as canonical examples and test inputs, not as the only contract source.

Cross-repository compatibility must still inspect the actual merged Cursor-Governance producer files.

## Verification scripts

Treat the scripts as acceptance tooling.

Do not rewrite them to match an incomplete implementation.

Modify them only when the actual repository API differs while preserving their original assertions and failure semantics.

## Wave 2 tests

Treat the tests as required acceptance tests.

Do not skip, xfail, weaken, or convert them into pass-only checks.

Where a test exposes a genuine mismatch between the deployment asset and actual repository architecture, fix the production binding first.

# Surgical modification instructions

## 1. `src/l9_graphite_memory/contracts/`

Create or extend repository-standard contracts for:

```text
GovernedMemoryCandidate
GovernedCandidateSource
GovernedCandidateKnowledge
GovernedCandidateGovernance
GovernedCandidateProvenance
MemoryCandidateIngestionStatus
MemoryCandidateIngestionResult

MemoryReuseConsumer
MemoryReuseUse
MemoryReuseEvidence
MemoryReuseOutcome
MemoryReuseEvent
MemoryReuseStatus
MemoryReuseReceipt

SourceInvalidationEventType
SourceInvalidationSelector
SourceInvalidationRequest
SourceInvalidationMatch
SourceInvalidationDecision
SourceInvalidationStatus
SourceInvalidationReceipt

GeneratedDataCapabilityResponse
```

Use the repository’s current dataclass, Pydantic, attrs, or typed-contract convention.

Do not introduce another model framework.

Candidate validation must enforce:

```text
kind == MemoryCandidate
supported schema major
authority_class == advisory
route == memory
promotion_decision == promote
override flags are false
candidate ID present
source SHA equals freshness SHA
confidence within [0, 1]
observed and derived units include evidence
invalidation conditions are present
visibility is explicit
repository scope is explicit
```

Accept only:

```text
repository_fact
dependency_finding
implementation_surface
rejected_approach
context_requirement
artifact_lineage
```

Reject all other generated-data classes.

Ensure exports are added only where contracts are intended to be public.

Do not export internal translation helpers.

## 2. `src/l9_graphite_memory/services/`

Add the narrowest service operations:

```text
ingest_governed_candidate
record_reuse
invalidate_by_source
generated_data_capabilities
list_revalidation_candidates, only when aligned with current service design
```

`ingest_governed_candidate` must ultimately call the existing canonical:

```text
MemoryService.write(...)
```

exactly once per new candidate attempt.

Do not directly call the store from the candidate adapter.

Do not call Graphiti memory promotion because Cursor-Governance included a governance `promotion_id`.

Governance promotion means the unit is eligible to enter memory admission.

Memory promotion remains owned by the memory service and its existing policy.

Reuse recording must:

```text
authorize against the referenced record
reject missing records
reject deleted records
preserve the memory body
persist one immutable event
return duplicate for identical event ID and body
reject same event ID with different body
produce a typed receipt
```

Source invalidation must:

```text
authorize the request
match structured selectors only
preserve evidence and lineage
avoid deletion
avoid automatic replacement
transition through existing archive or quarantine machinery
exclude the record from ordinary search and hydration
retain authorized historical or audit visibility
produce a revalidation requirement
return typed per-record decisions
```

Negative reuse outcomes must not immediately mutate records.

Required flow:

```text
stale or incorrect reuse
→ invalidation candidate
→ policy evaluation
→ explicit invalidation request
→ lifecycle mutation
```

## 3. `src/l9_graphite_memory/stores/`

Extend the existing canonical store protocol and implementation only.

Do not create another store implementation or another database.

Add persistence for:

```text
reuse events
source invalidation events
structured source selectors
revalidation requirements, when required
candidate idempotency metadata, when not already represented
```

Required reuse constraints:

```text
event_id unique
record_id references an existing record
event body immutable
duplicate identical event is idempotent
same event ID with different body is a collision
timestamps preserved
namespace remains authoritative
```

Required selector fields should include the existing equivalents of:

```text
selector_id
record_id
repository
selector_type
selector_value
active
created_at
deactivated_at
```

Index at least:

```text
(repository, selector_type, selector_value, active)
(record_id, active)
(selector_type, selector_value, active)
```

Populate selectors transactionally during governed candidate admission.

Deactivate selectors when their owning record leaves ordinary active lifecycle.

Do not infer selectors from the natural-language memory statement.

Do not add direct SQL outside the existing store and migration owners.

## 4. `src/l9_graphite_memory/migrations/`

Use the repository’s current migration registry and versioning.

Add the smallest migration needed for:

```text
reuse events
source invalidation events
source selector indexes
revalidation metadata
candidate idempotency metadata, if needed
```

Migration requirements:

```text
idempotent
restart safe
old records remain readable
mixed lifecycle states remain intact
fresh stores work
previous supported stores upgrade
production-like stores upgrade
selector indexes are present
query plans use selector indexes
rollback or restore path documented
```

Backfill structured selectors only from existing structured metadata.

Do not guess selectors for old unstructured records.

Do not silently mutate old evidence.

Update schema version, migration registry, serializer/upcaster registry, and fixtures through existing mechanisms.

## 5. `src/l9_graphite_memory/commands/`

Inspect the existing CLI owner and naming style.

Add commands only through that owner.

Required machine operations:

```text
ingest-governed-candidate
record-reuse
invalidate-source
generated-data-capabilities
```

Use existing search and hydration commands. Do not create replacements.

Each machine command must:

```text
accept JSON from stdin
optionally accept a JSON file when existing conventions permit
emit exactly one JSON object to stdout
emit diagnostics to stderr
never print secrets
preserve typed service status
use stable exit codes
```

Exit-code mapping:

```text
0 success or identical duplicate
2 invalid input
3 authorization denied
4 schema incompatible
5 store or service unavailable
6 conflict or ID collision
7 policy rejection
8 internal invariant failure
```

The command environment example must be updated only if actual command names differ.

Do not add shell wrappers when native CLI commands are the repository convention.

## 6. `src/l9_graphite_memory/mcp/`

Extend the existing MCP server and tool registry.

Do not create a second MCP server.

Add tools equivalent to:

```text
memory.ingest_governed_candidate
memory.record_reuse
memory.invalidate_source
memory.generated_data_capabilities
```

Use the repository’s actual naming convention if different.

Preserve existing:

```text
initialization
tools/list
request validation
principal derivation
authorization
error mapping
receipt mapping
search
hydration
health
```

Update Cursor client verification so readiness proves:

```text
initialize succeeds
tools/list succeeds
health succeeds
candidate-ingress tool exists
reuse tool exists
invalidation tool exists
search tool exists
hydrate tool exists
real invocation reaches the tool plane
```

A healthy HTTP endpoint is not sufficient.

A 404, tool-not-found response, or empty tool inventory must fail readiness.

## 7. `src/l9_graphite_memory/observability/`

Use the existing metrics and health owners.

Add metrics using the current framework:

```text
candidate_ingress_total
candidate_ingress_accepted
candidate_ingress_duplicate
candidate_ingress_quarantined
candidate_ingress_rejected
candidate_schema_incompatible
candidate_ingress_latency

reuse_events_total
reuse_outcomes_total
reuse_write_latency

invalidation_requests_total
invalidation_matches_total
invalidation_failures_total
invalidation_latency

revalidation_pending
selector_lookup_latency
```

Extend health and capability reporting with:

```text
capability_manifest_loaded
service_principal_ready
namespace_mapping_ready
candidate_ingress_ready
reuse_store_ready
invalidation_ready
selector_indexes_ready
search_filter_ready
hydrate_filter_ready
supported schema versions
pending revalidation count
```

Keep projection readiness separate:

```text
projection configured
projection ready
projection required for canonical operation = false
```

Do not introduce another metrics framework.

## 8. Reuse-aware ranking

Locate the existing search or hydration ranking owner.

Add a bounded, explainable reuse signal there only.

Permitted adjustments:

```text
successful finalized reuse → small positive boost
stale → negative penalty
incorrect → stronger negative penalty
caused_confusion → negative penalty
correction_required → negative penalty
```

Required precedence:

```text
authorization
lifecycle validity
temporal validity
scope relevance
current source evidence
then reuse signal
```

Reuse must never:

```text
revive invalidated memory
override authorization
override lifecycle state
override temporal validity
override current repository truth
```

Expose ranking explanation fields where current ranking explanations are produced.

## 9. `docs/`

Create or update the narrowest appropriate documents covering:

```text
Cursor-Governance and Graphiti ownership boundary
governed candidate ingress flow
supported and rejected generated-data classes
candidate schema compatibility
governance promotion versus memory promotion
service-principal authorization
namespace mapping
reuse event semantics
negative reuse and invalidation separation
source invalidation lifecycle
selector indexing
search and hydration exclusion behavior
historical audit behavior
migration process
backup and restore
CLI usage
MCP usage
capability discovery
health interpretation
projection independence
load and concurrency expectations
rollback
activation states
```

Do not duplicate the three deployment runbooks.

Link to:

```text
deployment/generated-data/migration-runbook.md
deployment/generated-data/activation-runbook.md
deployment/generated-data/rollback-runbook.md
```

Document that:

```text
CODE_COMPLETE
LOCAL_CANONICAL_LOOP_PROVEN
COMMAND_LOOP_PROVEN
MCP_TOOL_PLANE_PROVEN
LIVE_CURSOR_GRAPHITI_LOOP_PROVEN
```

are evidence levels, not interchangeable labels.

Do not claim live Cursor integration from fixtures, mocks, local service calls, or outbox delivery.

## 10. `ADRs/`

Inspect the actual ADR directory, numbering, index, metadata format, and assurance tooling.

Add exactly one ADR unless an equivalent accepted ADR already owns this integration.

Suggested title:

```text
Cursor-Governance Governed Memory Candidate Ingress,
Reuse Telemetry, and Source Invalidation
```

The ADR must record:

```text
context
authority boundary
decision to preserve the existing canonical write path
decision to treat governance promotion and memory promotion separately
supported generated-data classes
rejected classes
candidate idempotency
service-principal authorization
namespace mapping
reuse persistence
negative reuse handling
structured source invalidation
non-deletion policy
selector indexing
lifecycle state selected
historical audit access
projection independence
CLI and MCP exposure
migration and rollback
alternatives rejected
consequences
validation evidence
```

Rejected alternatives must include:

```text
parallel generated_data memory subsystem
direct adapter-to-store writes
second MCP server
new search implementation
new hydration implementation
natural-language invalidation matching
automatic invalidation on negative reuse
automatic replacement creation
raw subagent packet duplication
projection as canonical authority
```

Update the ADR index, machine-readable registry, harvest map, and assurance coverage using existing tools.

Do not fabricate ADR numbers or coverage results.

# Required tests and evidence

Run the already-built Wave 2 tests unchanged first.

Then add production-focused tests in the repository’s existing test structure for:

```text
candidate contract validation
supported class mapping
unsupported class rejection
canonical write called exactly once
no adapter-to-store calls
governance promotion does not call memory promotion
candidate idempotency
candidate collision
authorization
namespace narrowing
namespace widening rejection
reuse persistence
reuse duplicate semantics
reuse collision semantics
record body unchanged after reuse
negative reuse creates candidate only
source invalidation matching
source invalidation authorization
source invalidation idempotency
non-matching records unchanged
no deletion
no replacement
evidence preserved
lineage preserved
ordinary search exclusion
ordinary hydration exclusion
historical audit access
selector index query plans
migration fresh-store behavior
migration previous-store behavior
migration mixed-lifecycle behavior
CLI stdin/stdout protocol
CLI exit codes
MCP tools/list
MCP invocation
health versus tool-plane distinction
bounded reuse ranking
projection outage tolerance
concurrent duplicate candidate ingestion
concurrent reuse events
atomic invalidation
```

Cross-repository compatibility tests must inspect the actual Cursor-Governance checkout.

Record both repository SHAs.

# How to handle mismatches in the built output

When an output file contains an assumed command, module, status, or field name that differs from the actual repository:

1. Preserve the semantic requirement.
2. Bind it to the repository’s existing owner.
3. Update the deployment file only when needed for truthful compatibility.
4. Update its tests only when the test encoded a naming assumption rather than a behavioral invariant.
5. Record the deviation in the final report.
6. Never weaken fail-closed behavior.

Examples:

```text
If the CLI command is named differently:
  update cursor-command-env.example and command protocol expectations.

If the repository uses groups rather than namespaces:
  compile namespace-mapping.yaml into the group policy owner.

If invalidation maps to quarantine rather than archive:
  document and test quarantine as the selected lifecycle state.

If MCP tools use another prefix:
  register under the existing prefix and update capability discovery.

If the current receipt does not expose projection_enqueued:
  return it as optional or unavailable rather than inventing true.
```

# Validation sequence

Run the repository’s actual authoritative commands.

At minimum, when present:

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pyright

CURSOR_GOVERNANCE_ROOT=/path/to/Cursor-Governance \
uv run pytest -q tests/deployment/generated_data

uv run pytest -q

python deployment/generated-data/verify_generated_data_tools.py \
  --mode static

CURSOR_GOVERNANCE_ROOT=/path/to/Cursor-Governance \
python deployment/generated-data/verify_cross_repo_contract.py

python tools/assurance/validate_harvest_coverage.py
python tools/assurance/validate_adrs.py
bash scripts/preflight.sh
bash scripts/validate_release.sh
```

Also run, against temporary or explicitly supplied stores:

```text
migration verification
backup/restore verification
selector index verification
bounded load verification
local canonical end-to-end proof
```

Run command-loop and MCP-loop verification only when configured.

Do not claim those states when external configuration is absent.

# Completion criteria

The integration is complete only when:

```text
candidate ingress is publicly callable
candidate ingress reaches MemoryService.write exactly once
canonical admission semantics remain unchanged
reuse events persist
source invalidation uses structured selectors
invalidated records leave ordinary retrieval
historical evidence remains
authorization and namespace rules are enforced
migrations are verified
selector indexes are verified
CLI protocol passes
MCP tool-plane passes when configured
Wave 2 tests pass
full repository tests pass
assurance checks pass
release validation passes
```

# Final report

Return:

```yaml
repository_boundary:
  write_repository:
  read_only_contract_repository:
  graphiti_sha:
  cursor_governance_sha:

preflight:
  canonical_write_path:
  store_owner:
  command_owner:
  mcp_owner:
  migration_owner:
  observability_owner:
  collisions:
  blocking_incompatibilities:

source_changes:
  contracts:
  services:
  stores:
  migrations:
  commands:
  mcp:
  observability:

documentation:
  docs_created:
  docs_modified:
  adr_created_or_extended:
  adr_registry_updates:

output_binding:
  deployment_files_modified:
  deployment_files_unchanged:
  assumptions_rebound:
  test_adjustments:
  behavioral_invariants_preserved:

validation:
  wave2_tests:
  focused_production_tests:
  full_repository_tests:
  cross_repo_contract:
  migration:
  backup_restore:
  selector_indexes:
  load_test:
  local_loop:
  command_loop:
  mcp_loop:
  ruff:
  pyright:
  harvest_coverage:
  adr_validation:
  preflight:
  release_validation:

activation_state:

files_created:
files_modified:
files_intentionally_not_created:

sha256_manifest:

external_gates:
```

Activation-state rules:

```text
CODE_COMPLETE:
  source and focused tests pass

LOCAL_CANONICAL_LOOP_PROVEN:
  local ingestion, search, hydration, reuse, invalidation,
  exclusion and historical audit pass

COMMAND_LOOP_PROVEN:
  the complete loop passes through installed CLI operations

MCP_TOOL_PLANE_PROVEN:
  initialize, inventory and required MCP operations pass

LIVE_CURSOR_GRAPHITI_LOOP_PROVEN:
  an actual Cursor-Governance runtime execution produces,
  retrieves, reuses and invalidates memory through deployed surfaces
```

Do not report a higher state without direct evidence.
