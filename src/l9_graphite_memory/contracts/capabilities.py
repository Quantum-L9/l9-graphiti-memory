# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/capabilities.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-09-05

"""Control-plane capability receipt consumed by memory clients (ADR-082).

A consumer such as Cursor-Governance must not infer compatibility from the
presence of a tool or a subcommand. This receipt names the package, the
schema, the control-plane contract, and every lifecycle operation each
transport exposes, so a runtime binding can be proven exact before the first
lifecycle call is made.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts.generated_data import SUPPORTED_CLASSES, VISIBILITY_TEMPLATES
from l9_graphite_memory.version import (
    CONTROL_PLANE_CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    MEMORY_SCHEMA_VERSION,
    PACKAGE_VERSION,
)

#: Lifecycle operations every transport must expose. The CLI subcommand and the
#: MCP tool for one operation converge on the same MemoryService method.
LIFECYCLE_OPERATIONS: tuple[str, ...] = (
    "health",
    "capabilities",
    "hydrate",
    "search",
    "get",
    "ingest",
    "ingest_governed_candidate",
    "close",
    "conflicts",
    "phase_lock",
    "verify_phase_lock",
)

#: Operation name -> CLI subcommand. ``resolve`` is CLI-only: an MCP principal
#: already carries its authorized namespaces, so there is nothing to resolve.
CLI_OPERATION_COMMANDS: dict[str, str] = {
    "resolve": "resolve",
    "health": "health",
    "capabilities": "capabilities",
    "hydrate": "hydrate",
    "search": "search",
    "get": "get",
    "ingest": "write",
    "ingest_governed_candidate": "ingest-governed-candidate",
    "close": "close",
    "conflicts": "conflicts",
    "phase_lock": "phase-lock",
    "verify_phase_lock": "verify-phase-lock",
}

#: Operation name -> canonical MCP tool.
MCP_OPERATION_TOOLS: dict[str, str] = {
    "health": "memory.health",
    "capabilities": "memory.capabilities",
    "hydrate": "memory.hydrate",
    "search": "memory.search",
    "get": "memory.get",
    "ingest": "memory.ingest",
    "ingest_governed_candidate": "memory.ingest_governed_candidate",
    "close": "memory.close",
    "conflicts": "memory.conflicts",
    "phase_lock": "memory.phase_lock",
    "verify_phase_lock": "memory.verify_phase_lock",
}

#: Exit codes of the integration-facing CLI commands. Zero is reserved for a
#: committed canonical outcome; a dry run is deliberately non-zero because no
#: canonical state was committed (INV-06: provider success is not write success).
CLI_EXIT_CODES: dict[str, int] = {
    "committed": 0,
    "error": 1,
    "failed_or_rejected": 2,
    "dry_run_not_committed": 3,
    "candidate_rejected": 7,
}


class TransportSurface(BaseModel):
    """One transport (CLI or MCP) and the operation names it exposes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transport: str = Field(min_length=1)
    operations: dict[str, str] = Field(default_factory=dict)


class ControlPlaneCapabilities(BaseModel):
    """Machine-readable capability receipt for the memory control plane."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package: str = "l9-graphite-memory"
    package_version: str = PACKAGE_VERSION
    schema_version: str = MEMORY_SCHEMA_VERSION
    contract_version: str = CONTROL_PLANE_CONTRACT_VERSION
    mcp_protocol_version: str = MCP_PROTOCOL_VERSION
    lifecycle_operations: tuple[str, ...] = LIFECYCLE_OPERATIONS
    transports: tuple[TransportSurface, ...] = ()
    exit_codes: dict[str, int] = Field(default_factory=lambda: dict(CLI_EXIT_CODES))
    generated_data_classes: tuple[str, ...] = ()
    candidate_visibilities: tuple[str, ...] = ()

    def missing_operations(self) -> dict[str, tuple[str, ...]]:
        """Operations a transport declares but does not expose, by transport."""

        missing: dict[str, tuple[str, ...]] = {}
        for surface in self.transports:
            absent = tuple(
                operation
                for operation in self.lifecycle_operations
                if operation not in surface.operations
            )
            if absent:
                missing[surface.transport] = absent
        return missing


def build_capabilities(
    *,
    cli_commands: Iterable[str],
    mcp_tools: Iterable[str],
) -> ControlPlaneCapabilities:
    """Assemble the receipt from the live CLI and MCP inventories.

    Only operations whose command or tool is actually registered are
    reported, so the receipt cannot claim a surface the transport lacks.
    """

    commands = set(cli_commands)
    tools = set(mcp_tools)
    return ControlPlaneCapabilities(
        transports=(
            TransportSurface(
                transport="cli",
                operations={
                    operation: command
                    for operation, command in CLI_OPERATION_COMMANDS.items()
                    if command in commands
                },
            ),
            TransportSurface(
                transport="mcp",
                operations={
                    operation: tool
                    for operation, tool in MCP_OPERATION_TOOLS.items()
                    if tool in tools
                },
            ),
        ),
        generated_data_classes=tuple(sorted(SUPPORTED_CLASSES)),
        candidate_visibilities=tuple(sorted(VISIBILITY_TEMPLATES)),
    )


__all__ = [
    "CLI_EXIT_CODES",
    "CLI_OPERATION_COMMANDS",
    "LIFECYCLE_OPERATIONS",
    "MCP_OPERATION_TOOLS",
    "ControlPlaneCapabilities",
    "TransportSurface",
    "build_capabilities",
]
