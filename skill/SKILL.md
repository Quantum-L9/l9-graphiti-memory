---
name: l9-graphiti-memory
description: Operate, inspect, integrate, migrate, and validate the L9 contract-governed memory substrate. Use for l9-graphiti-memory repository work, evidence-bound ingestion, memory search or hydration, profile consent, conflict checks, phase locks, lineage, retention, verified deletion, MCP configuration, hook activation, projection health, provider replay, source distillation, procedural candidates, and release validation. Enforce the canonical MemoryService path, server-derived namespace authority, bi-temporal semantics, provider-locator evidence, typed receipts, and no direct store or provider writes.
---

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: skill/SKILL.md
layer: skill
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


# L9 Graphiti Memory

Treat accepted ADRs, `docs/harvest_coverage.yaml`, and executable contracts as authority. Preserve compatibility only where it does not weaken authorization, consent, temporal integrity, admission, idempotency, deletion proof, or evidence.

## Operating sequence

1. Read `AGENTS.md`, `ARCHITECTURE.md`, `RUNBOOK.md`, and `docs/adr/README.md` when a checkout is available.
2. Run:
   ```bash
   l9-memory health
   l9-memory resolve
   ```
3. Retrieve bounded context before governed mutation:
   ```bash
   l9-memory search "<task>" --group-id <namespace>
   l9-memory hydrate "<task>" --group-id <namespace>
   ```
4. For governed repository work, check conflicts and obtain a task-bound lock:
   ```bash
   l9-memory conflicts --group-id <namespace>
   l9-memory phase-lock "<task>" --group-id <namespace>
   l9-memory verify-phase-lock "<task>" --group-id <namespace>
   ```
5. Write only through CLI, MCP, SDK, `MemoryService`, or an approved adapter.
6. Run the applicable validation gates before claiming completion.

## Safe write pattern

Use explicit provenance and evidence. Prefer dry-run for bulk or sensitive ingestion.

```bash
l9-memory write "Always run contract tests before merge" \
  --kind decision \
  --group-id <namespace> \
  --source operator \
  --dry-run
```

Identity and preference memory requires current purpose-bound consent. Never infer consent from behavior.

## Source ingestion

```bash
l9-memory distill <source-file> --group-id <namespace> --dry-run
l9-memory import <legacy-jsonl> --group-id <namespace> --dry-run
l9-memory bootstrap --root <repository> --group-id <namespace> --dry-run
```

Require source digests, exact ranges, candidate status, and idempotency evidence. Empty provider output is not a successful extraction unless a typed receipt proves a valid empty result.

## Retrieval rules

- Request only authorized namespaces.
- Distinguish no hits from canonical or projection failure.
- Use valid-time and recorded-time filters for historical questions.
- Treat graph and semantic systems as rebuildable projections.
- Accept only strategies recorded as actually executed.
- Use bounded hydration instead of dumping complete histories.

## Curation and privacy

- Use supersession rather than destructive mutation.
- Treat duplicate, rejected, quarantined, partial, failed, archived, and deleted states separately.
- Procedural synthesis creates candidates only.
- Verify lineage before promotion.
- Verified deletion requires administrator authority, a reason, and a verification reference.
- Do not mark projected deletion complete until the stored provider locator has been erased and confirmed.

## Integration rules

- Keep CLI, MCP, hooks, SDK, and importers thin.
- Add stores and projections through ports and conformance tests.
- Require projection writes to return a stable locator.
- Add enrichment through durable outbox consumers.
- Keep credentials out of generated desktop configuration and source control.
- Support current Graphiti provider tools while retaining explicit compatibility mappings for older deployments.

## Failure policy

Fail closed for authentication, authorization, consent, canonical persistence, phase locks, deletion proof, and audit receipts. Allow typed partial results only for optional projections or enrichment. Never convert an exception into an empty successful result. Never use a direct database or provider write as a recovery path.

## Validation

```bash
pytest -q
python tools/assurance/validate_harvest_coverage.py
python tools/assurance/validate_adrs.py
python tools/assurance/check_memory_write_bypass.py
python tools/assurance/check_config_drift.py
python tools/assurance/check_secrets.py
python tools/assurance/audit_package_wiring.py
bash scripts/preflight.sh
bash scripts/validate_release.sh
```

Do not claim live Zep, Graphiti, Infisical, hosted CI, production migration, rollback, or credential rotation without executed evidence. Record unavailable environments as external blockers.
