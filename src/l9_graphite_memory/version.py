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

PACKAGE_VERSION = "2.2.0"
# 2.2.0 adds the optional structured source_locator to Provenance and
# EvidenceRef (ADR-078). Records persisted at 2.1.0 upcast losslessly: the new
# field is absent there and stays None.
MEMORY_SCHEMA_VERSION = "2.2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
ADMISSION_POLICY_VERSION = "memory-admission/v2"
RANKING_POLICY_VERSION = "memory-ranking/v2"
AUTHORIZATION_POLICY_VERSION = "memory-authz/v1"
RETENTION_POLICY_VERSION = "memory-retention/v2"
PHASE_LOCK_POLICY_VERSION = "memory-phase-lock/v2"

CONSTELLATION_BRIDGE_VERSION = "l9-memory-gate/v1"
CLIENT_CONFIG_POLICY_VERSION = "client-config/v1"
