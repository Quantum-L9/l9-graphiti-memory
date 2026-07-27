<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/CURSOR_INSTANTIATION.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-07-27
/L9_META -->

# Cursor Instantiation

This document describes how the memory control plane is instantiated inside Cursor and how each step is proven. The canonical implementation lives in `src/l9_graphite_memory/client_config/` and is governed by [ADR-064](adr/ADR-064-cursor-client-instantiation-and-proof-boundary.md). Ad hoc edits to `~/.cursor/mcp.json` bypass the control plane and are prohibited by repository law; every mutation must flow through the CLI surface described here.

## Surface

The lifecycle is exposed as a `client` command group on the `l9-memory` CLI. Every subcommand emits a single JSON receipt on stdout and uses the process exit code as the machine-readable verdict: `0` means the operation succeeded or the target is already in the desired state, `1` means an error was raised, and `2` means the operation was blocked or the probe failed and the receipt explains why.

| Command | Effect | Mutates config |
|---|---|---|
| `l9-memory client cursor inspect` | Reports the target path, digest, managed-entry state, unmanaged keys, and blockers | No |
| `l9-memory client cursor install --dry-run` | Computes the receipt an install would produce without touching disk | No |
| `l9-memory client cursor install` | Atomically installs or repairs the managed `l9-graphite-memory` entry | Yes |
| `l9-memory client cursor verify` | Launches the generated command and proves the full MCP handshake | No |
| `l9-memory client cursor status` | Derives drift state from the config and canonical entry | No |
| `l9-memory client cursor uninstall` | Removes only the managed entry, or restores a digest-verified backup | Yes |

All subcommands accept `--path` to target a non-default config file and `--interpreter` to pin the Python executable recorded in the managed entry. `verify` accepts `--timeout` (seconds). `uninstall` accepts `--restore-backup <file>` to restore a previous config after verifying that the backup content matches the digest embedded in its filename.

## Guarantees

The configurator owns exactly one key, `l9-graphite-memory`, inside `mcpServers`. Unrelated servers and unknown top-level keys are preserved byte-for-byte in decoded form. Before any write the target is inspected fail-closed: invalid JSON, a non-object root, a non-object `mcpServers` value, a symlinked target, or a non-regular file blocks the operation with exit code `2` and no partial write. Writes are atomic (temporary sibling file, fsync, `os.replace`), permissioned to `0600`, guarded against concurrent modification by SHA-256 digest re-verification, and preceded by a timestamped, digest-bound backup such as `mcp.json.backup.20260727T163600Z.1288d39e8da6`. Every operation returns a frozen `ClientConfigReceipt` carrying pre/post digests, backup binding, the managed argv, warnings, and the policy version `client-config/v1`.

The managed entry is secret-free by construction. It contains only a `command` (the resolved interpreter) and an `args` array launching `python -m l9_graphite_memory.server --transport stdio`; there is never an `env` block. Credentials are resolved at runtime by the server process from its own environment, per ADR-016.

## Proof of instantiation

`l9-memory client cursor verify` is the only accepted proof that memory is actually on. It spawns the exact argv from the managed entry and drives the real line-delimited JSON-RPC handshake — `initialize`, `notifications/initialized`, `tools/list`, and `tools/call memory.health` — over the same stdio channel Cursor uses. The probe succeeds only when the protocol version and server identity are confirmed, all fifteen canonical tools are present, and `memory.health` reports a non-failed status. The resulting `ProbeReceipt` records each step, the tool count, the health status, redacted stderr evidence, and the exit code of the reaped process. A receipt with `"status": "complete"` is the closing evidence of the instantiation loop.

## Typical sequence

```bash
l9-memory client cursor inspect
l9-memory client cursor install --dry-run
l9-memory client cursor install
l9-memory client cursor verify --timeout 60
l9-memory client cursor status
```

After `install` completes, fully restart Cursor (not just the window) so it re-reads `~/.cursor/mcp.json`, then confirm the `l9-graphite-memory` server and its tools appear under Settings → Tools & MCP. The full activation procedure, including hydration checks, governed writes, guard activation, and write-gate enablement, is defined in the activation playbook that ships with the release pack.

## Recovery

Every mutating operation leaves a digest-bound backup beside the config. To roll back the most recent change, pass the backup to `uninstall`:

```bash
l9-memory client cursor uninstall --restore-backup ~/.cursor/mcp.json.backup.<stamp>.<digest12>
```

Restore verifies that the backup's SHA-256 matches the digest fragment in its filename before writing, and the restore itself is atomic. If the backup has been tampered with, the operation raises a `ConfigurationError` and leaves the current config untouched.
