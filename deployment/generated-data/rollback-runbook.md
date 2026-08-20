<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: deployment/generated-data/rollback-runbook.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


# Generated-Data Integration Rollback Runbook

## Objective

Disable the new generated-data integration without disabling established memory
search, hydration, canonical records, audit evidence, or unrelated MCP tools.

## Immediate containment

1. Disable governed candidate ingress.
2. Disable reuse-event recording.
3. Disable source invalidation dispatch.
4. Revoke only the generated-data service principal permissions.
5. Preserve existing canonical records and receipts.
6. Keep normal memory search and hydration available when safe.
7. Set external projection to the documented safe mode when it is implicated.

## Do not

* delete admitted records;
* delete reuse or invalidation events;
* delete receipts;
* remove historical evidence;
* create replacement records automatically;
* rerun original subagents;
* remove unrelated MCP server registrations;
* widen another principal to compensate.

## Store rollback

1. Stop writers.
2. Preserve the current store as incident evidence.
3. Verify the rollback backup hash and integrity.
4. Restore the verified canonical backup.
5. Start with external projection disabled.
6. Run existing `resolve`, `health`, search, and hydration checks.
7. Verify previous lifecycle states remain correct.
8. Replay post-backup operations from durable receipts using original
   idempotency keys.

## Configuration rollback

Remove or disable:

* generated-data command environment variables;
* generated-data principal grants;
* generated-data MCP tool registrations;
* generated-data write activation flags.

Retain:

* deployment runbooks;
* capability manifest;
* incident evidence;
* migration evidence;
* read-only compatibility verification.

## Verification

A successful rollback proves:

* canonical store integrity;
* normal search and hydration;
* no generated-data ingress;
* no reuse writes;
* no invalidation writes;
* existing records remain accessible according to their lifecycle;
* audit evidence remains present;
* projection outage does not block canonical operation.
