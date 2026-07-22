<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: QUICKSTART.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Quick Start

## Standalone canonical memory

```bash
python -m pip install .
export L9_MEMORY_PROJECTION_BACKEND=none
l9-memory resolve
l9-memory health
l9-memory write 'Test memory' \
  --kind observation \
  --group-id l9-graphiti-memory \
  --source quickstart
l9-memory search 'Test' --group-id l9-graphiti-memory
l9-memory hydrate 'What should I remember?' --group-id l9-graphiti-memory
```

## Governed workflow

```bash
l9-memory conflicts --group-id l9-graphiti-memory
l9-memory phase-lock 'upgrade memory integration' --group-id l9-graphiti-memory
l9-memory verify-phase-lock 'upgrade memory integration' --group-id l9-graphiti-memory
```

## Source distillation

```bash
l9-memory distill README.md --group-id l9-graphiti-memory --dry-run
l9-memory import legacy-episodes.jsonl --group-id l9-graphiti-memory --dry-run
```

## MCP

```bash
l9-memory-server --transport stdio
```

See `RUNBOOK.md` for consent-governed profile writes, deletion, provider projection, recovery, backups, and release validation.
