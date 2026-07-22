# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graphiti_gate_lib.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deprecated import shim for the local memory receipt guard.

This module is retained for hook compatibility only. It is not the L9
constellation Gate and owns no routing or workflow state.
"""

from .memory_guard import (
    GuardDecision,
    GuardEvidence,
    evidence_dir,
    evidence_path,
    guard_enabled,
    hydration_fresh,
    load_evidence,
    main,
    memory_ok,
    phase_lock_ok,
    pre_tool_use,
    shell_guard,
    shell_is_read_only,
    subagent_guard,
)

shell_gate = shell_guard
subagent_gate = subagent_guard
gates_enabled = guard_enabled
state_dir = evidence_dir
state_path = evidence_path
load_state = load_evidence
prefetch_fresh = hydration_fresh

__all__ = [
    "GuardDecision",
    "GuardEvidence",
    "evidence_dir",
    "evidence_path",
    "gates_enabled",
    "guard_enabled",
    "hydration_fresh",
    "load_evidence",
    "load_state",
    "main",
    "memory_ok",
    "phase_lock_ok",
    "prefetch_fresh",
    "pre_tool_use",
    "shell_gate",
    "shell_guard",
    "shell_is_read_only",
    "state_dir",
    "state_path",
    "subagent_gate",
    "subagent_guard",
]

if __name__ == "__main__":
    raise SystemExit(main())
