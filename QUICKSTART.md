<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: QUICKSTART.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-10-13
/L9_META -->

# Quick Start

## Standalone canonical memory

```bash
uv sync --frozen --no-install-project --no-build --extra dev --extra server
source .venv/bin/activate
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

Published package (no checkout): `pip install l9-graphite-memory`.

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

This is the local stdio MCP mode of the 2.6.0 release: the server runs on the
same machine as the agent and is launched by it. It is supported and is what
the Cursor lifecycle below installs.

The target agent transport is a centrally hosted, authenticated HTTPS MCP
service (ADR-038 amendment, 2026-10-13). It is **not implemented** in this
release, so there is no remote-client quickstart yet. Do not point agents at
`l9-memory-server --transport http` as a substitute: that surface is not
qualified for remote agents (see `RUNBOOK.md`, "Remote HTTP MCP").

## Cursor instantiation

```bash
l9-memory client cursor install --dry-run
l9-memory client cursor install
l9-memory client cursor verify
l9-memory client cursor status
```

`install` atomically writes the managed local stdio `l9-graphite-memory` entry into `~/.cursor/mcp.json`, preserving unrelated servers and never persisting secrets. `verify` launches that stdio command and proves the full MCP handshake, tool inventory, and `memory.health` for the local entry; it is not evidence about any remote HTTP service. Restart Cursor after installing, then see `docs/CURSOR_INSTANTIATION.md` for the full lifecycle and recovery.

See `RUNBOOK.md` for consent-governed profile writes, deletion, provider projection, recovery, backups, and release validation.
