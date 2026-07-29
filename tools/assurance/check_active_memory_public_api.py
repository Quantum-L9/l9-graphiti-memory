#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_active_memory_public_api.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Guard the active-memory subsystem's public API surface.

Fails (exit 1) if:
  - any symbol in `_REQUIRED_PUBLIC_SYMBOLS` is missing from
    `l9_graphite_memory.active.__all__`
  - any symbol in `_FORBIDDEN_PUBLIC_SYMBOLS` (Redis-internal adapter
    classes) is exported from `l9_graphite_memory.active.__all__`

This is the CI gate referenced by ADR-067 and the build-plan Phase 6
exit criteria: "external process can use active memory without
importing Redis internals."
"""

from __future__ import annotations

import sys

_REQUIRED_PUBLIC_SYMBOLS = frozenset(
    {
        "ActiveDeployment",
        "DeploymentEnvironment",
        "ActiveAgentClient",
        "ActiveAgentSession",
        "ActiveContext",
        "ActiveContextDraft",
        "AgentEvent",
        "AgentIdentity",
        "AgentScope",
        "ActiveMemoryError",
        "ActiveMemoryUnavailableError",
        "ContextVersionConflictError",
        "LeaseExpiredError",
    }
)

_FORBIDDEN_PUBLIC_SYMBOLS = frozenset(
    {
        "RedisActiveStore",
        "RedisAwarenessBus",
        "RedisConnectionPool",
        "RedisKeyBuilder",
        "RedisLeaseScript",
    }
)


def main() -> int:
    try:
        import l9_graphite_memory.active as active_pkg
    except ImportError as exc:
        sys.stderr.write(
            f"ERROR: failed to import l9_graphite_memory.active: {exc}\n"
        )
        return 1

    exported = set(getattr(active_pkg, "__all__", []))

    missing = _REQUIRED_PUBLIC_SYMBOLS - exported
    leaked = _FORBIDDEN_PUBLIC_SYMBOLS & exported

    ok = True
    if missing:
        sys.stderr.write(
            f"ERROR: missing required public symbols: {sorted(missing)}\n"
        )
        ok = False
    if leaked:
        sys.stderr.write(
            f"ERROR: forbidden internal symbols are publicly exported: {sorted(leaked)}\n"
        )
        ok = False

    if not ok:
        return 1

    sys.stdout.write(
        f"OK: public API surface check passed ({len(exported)} exported symbols)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
