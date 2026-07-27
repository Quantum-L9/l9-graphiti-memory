# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/client_config/__init__.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Canonical client instantiation control plane for editor MCP configs.

This package owns the full lifecycle for wiring the memory control plane
into MCP clients (Cursor first). Every mutation is atomic, evidence-bearing,
fail-closed, and scoped to the single managed server entry. No module in
this package may talk to record stores or projection providers directly;
proof of instantiation is obtained only through the generated server
command over the MCP stdio protocol.
"""

from __future__ import annotations

from .contracts import (
    ClientConfigAction,
    ClientConfigReceipt,
    ClientConfigStatus,
    CursorConfigInspection,
    ManagedServerEntry,
    ProbeReceipt,
    ProbeStep,
)
from .cursor import (
    MANAGED_SERVER_KEY,
    CursorClientConfigurator,
    default_cursor_config_path,
    managed_server_entry,
)
from .mcp_probe import REQUIRED_TOOL_NAMES, probe_generated_server

__all__ = [
    "MANAGED_SERVER_KEY",
    "REQUIRED_TOOL_NAMES",
    "ClientConfigAction",
    "ClientConfigReceipt",
    "ClientConfigStatus",
    "CursorClientConfigurator",
    "CursorConfigInspection",
    "ManagedServerEntry",
    "ProbeReceipt",
    "ProbeStep",
    "default_cursor_config_path",
    "managed_server_entry",
    "probe_generated_server",
]
