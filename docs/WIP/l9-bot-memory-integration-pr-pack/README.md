<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/README.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# L9 Bot Trio Canonical Memory PR Stack

Push-ready, dependency-ordered PR overlays for four repositories. The PRs are stacked by release dependency across repositories, not by shared Git ancestry.

## Stack

1. `l9-graphiti-memory`: publish the governed TypeScript MCP client `2.0.0`.
2. `LLM-Router`: add the async atomic budget-store port and consume the memory client.
3. `Website-Bot`: activate Router, governed hydration, and publish canonical bot interop.
4. `SEO-Bot`: consume the completed package stack and promote only corroborated measured outcomes.

## Use

```bash
scripts/validate-pack.sh
scripts/preflight-stack.sh /path/to/workspace
scripts/prepare-stack.sh /path/to/workspace
# Run native repository CI and release gates.
PUSH_STACK=1 scripts/push-stack.sh /path/to/workspace
```

`push-stack.sh` creates draft PRs and refuses to run without explicit authorization. It never force-pushes.

## Authority

- `AUTHORITY.md`: normative architecture and boundaries.
- `PACK_CONTRACT.yaml`: machine-readable invariants.
- `PR_STACK.yaml`: exact PR order, bases, branches, dependencies, and publication gates.
- `RUNBOOK.md`: operator workflow.
- `VALIDATION.md`: pack-local proof and external gates.
