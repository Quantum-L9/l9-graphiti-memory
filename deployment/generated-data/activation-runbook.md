<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: deployment/generated-data/activation-runbook.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


# Generated-Data Integration Activation Runbook

## Boundary

Cursor-Governance is the control plane. It validates packets, harvests units,
classifies them, selects routes, makes governance promotion decisions, compiles
future context, records consumption, and emits repository-change events.

`l9-graphiti-memory` is the memory data plane. It admits governed memory
candidates through the existing canonical memory service, stores reuse events,
applies source invalidation through existing lifecycle machinery, and provides
search and hydration.

## Required public operations

The deployed memory runtime must expose:

* governed candidate ingestion;
* search;
* hydration;
* reuse recording;
* source invalidation;
* health;
* generated-data capabilities.

All machine commands consume JSON from stdin and emit one JSON object to stdout.
Diagnostics go to stderr.

## Service principal

Create or bind the existing authorization system to:

```yaml
principal: cursor-governance-generated-data
type: service
```

Grant only the permissions declared in `principal-policy.yaml`.

Do not authorize deployed subagents as direct canonical writers. Preserve their
identity as provenance.

## Namespace mapping

Load `namespace-mapping.yaml` through the existing namespace owner.

Prove:

* repository-local candidates map to their repository namespace;
* campaign-local candidates map to their campaign namespace;
* visibility may be narrowed;
* visibility may not be widened;
* cross-repository retrieval is not implicit;
* reuse inherits the referenced record namespace;
* invalidation requires authority over every affected namespace.

## Command environment

Copy command forms from `cursor-command-env.example` into the deployment
environment. Do not copy secrets into repository files.

## Static verification

```bash
python deployment/generated-data/verify_generated_data_tools.py \
  --mode static
```

## Local canonical verification

```bash
python deployment/generated-data/verify_generated_data_tools.py \
  --mode local
```

Local verification proves canonical store access. It does not prove the MCP tool
plane.

## Cross-repository compatibility

```bash
CURSOR_GOVERNANCE_ROOT=/path/to/Cursor-Governance \
python deployment/generated-data/verify_cross_repo_contract.py
```

## Live command proof

Configure all command variables, then run:

```bash
python deployment/generated-data/verify_generated_data_tools.py \
  --mode live

python deployment/generated-data/live_end_to_end_proof.py \
  --mode commands
```

A healthy HTTP endpoint is not sufficient. Tool-plane readiness requires real
operation invocation. A 404, tool-not-found response, or health-only success is
a failed activation.

## MCP verification

Use the repository's existing Cursor client lifecycle:

```bash
l9-memory client cursor install
l9-memory client cursor verify
l9-memory client cursor status
```

Verification must prove initialize, tools/list, health, candidate ingress,
reuse, invalidation, search, and hydration.

## Invalidation lifecycle

Use the lifecycle state selected by the generated-data source integration.
Invalidation must:

* preserve evidence and lineage;
* exclude the record from ordinary search and hydration;
* retain authorized historical visibility;
* avoid deletion;
* avoid automatic replacement creation;
* create or expose a revalidation requirement.

## Soak

Before enabling unrestricted generated-data writes:

* tool-plane checks remain green for the chosen soak period;
* no unexplained candidate rejection spike;
* no duplicate canonical writes;
* no selector lookup regression;
* no false invalidation;
* no authorization widening;
* backup/restore proof passes;
* bounded load proof passes.

## Activation states

* `CODE_COMPLETE`: source and tests pass.
* `LOCAL_CANONICAL_LOOP_PROVEN`: local canonical loop passes.
* `COMMAND_LOOP_PROVEN`: deployed command surfaces pass.
* `MCP_TOOL_PLANE_PROVEN`: MCP initialize, inventory, and operations pass.
* `LIVE_CURSOR_GRAPHITI_LOOP_PROVEN`: a real Cursor-Governance execution
  produces, retrieves, reuses, and invalidates memory through deployed surfaces.
