#!/usr/bin/env python3
"""Guard the active-memory subsystem's public API surface.

Fails (exit 1) if:
  - any symbol in `_REQUIRED_PUBLIC_SYMBOLS` is missing from
    `l9_graphite_memory.active.__all__`
  - any symbol in `_FORBIDDEN_PUBLIC_SYMBOLS` (Redis-internal adapter
    classes) is exported from `l9_graphite_memory.active.__all__`

This is the CI gate referenced by ADR-071 and the build-plan Phase 6
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
        print(
            f"ERROR: failed to import l9_graphite_memory.active: {exc}", file=sys.stderr
        )
        return 1

    exported = set(getattr(active_pkg, "__all__", []))

    missing = _REQUIRED_PUBLIC_SYMBOLS - exported
    leaked = _FORBIDDEN_PUBLIC_SYMBOLS & exported

    ok = True
    if missing:
        print(
            f"ERROR: missing required public symbols: {sorted(missing)}",
            file=sys.stderr,
        )
        ok = False
    if leaked:
        print(
            f"ERROR: forbidden internal symbols are publicly exported: {sorted(leaked)}",
            file=sys.stderr,
        )
        ok = False

    if not ok:
        return 1

    print(f"OK: public API surface check passed ({len(exported)} exported symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
