# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/version.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Package version and contract versions."""

PACKAGE_VERSION = "3.0.0"
# 2.2.0 adds the optional structured source_locator to Provenance and
# EvidenceRef (ADR-078). Records persisted at 2.1.0 upcast losslessly: the new
# field is absent there and stays None.
MEMORY_SCHEMA_VERSION = "2.2.0"
# The MCP revision the stdio transport answers with. Installed stdio clients are
# probed against it (client_config.mcp_probe), so it is deliberately not the
# HTTP revision: each transport negotiates from its own supported set.
MCP_PROTOCOL_VERSION = "2024-11-05"
# Streamable HTTP revisions the HTTP transport negotiates, newest first
# (ADR-098). 2025-03-26 is absent because that revision requires receiving
# JSON-RPC batches, which this server does not accept; a request that carries
# no MCP-Protocol-Version header is therefore refused rather than assumed.
HTTP_MCP_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-11-25", "2025-06-18")
# RFC 8707 resource indicator and Auth0 API audience for the hosted Memory
# service (ADR-100). The path is part of the identifier: the host alone is
# not the audience, and the Graphiti route on this host is a different
# resource. Issuer domain and client ids are not part of this value.
MEMORY_RESOURCE_IDENTIFIER = "https://memory.quantumaipartners.com/mcp"
ADMISSION_POLICY_VERSION = "memory-admission/v2"
RANKING_POLICY_VERSION = "memory-ranking/v2"
AUTHORIZATION_POLICY_VERSION = "memory-authz/v1"
RETENTION_POLICY_VERSION = "memory-retention/v2"
PHASE_LOCK_POLICY_VERSION = "memory-phase-lock/v2"

CONSTELLATION_BRIDGE_VERSION = "l9-memory-gate/v1"
CLIENT_CONFIG_POLICY_VERSION = "client-config/v1"
# The consumer-facing control-plane contract: which lifecycle operations the CLI
# and MCP transports expose, their receipt shapes, and their exit semantics.
# A consumer (Cursor-Governance) binds to this signal rather than inferring
# compatibility from tool presence (ADR-082). Bump when a lifecycle operation
# or its receipt changes incompatibly.
CONTROL_PLANE_CONTRACT_VERSION = "memory-control-plane/v1"
# The remote MCP transport and authentication contract (ADR-098): Streamable
# HTTP revisions, the signed-agent credential carriers, and their refusal
# semantics. Bump when a carrier, status code, or negotiation rule changes.
REMOTE_MCP_CONTRACT_VERSION = "memory-remote-mcp/v1"
