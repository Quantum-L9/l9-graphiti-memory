# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/trust_boundary.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-16

"""Model-process trust-boundary proof for the agent-facing memory contract."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
_MODEL_SURFACE_FILES = (
    "mcp_tools.py",
    "client_config/cursor.py",
    "client_config/mcp_probe.py",
    "client_config/contracts.py",
)
_KEYCHAIN_MARKERS = (
    "keychain",
    "keyring",
    "security find-generic-password",
    "graphiti_env_loader",
    "GRAPHITI_MCP_TOKEN",
)


def model_process_trust_boundary() -> dict[str, bool]:
    """Return the Release B model-process secret side-door proof.

    The model talks to MemoryService through MCP. It must not hold a Graphiti
    bearer and must not be able to read the Keychain graphiti-mcp-token.
    """
    haystack = ""
    for relative in _MODEL_SURFACE_FILES:
        haystack += (_PACKAGE_ROOT / relative).read_text(encoding="utf-8")
    lowered = haystack.lower()
    return {
        "model_has_graphiti_bearer": "GRAPHITI_MCP_TOKEN" in haystack,
        "model_can_read_keychain_graphiti_token": any(
            marker.lower() in lowered for marker in _KEYCHAIN_MARKERS
        ),
    }
