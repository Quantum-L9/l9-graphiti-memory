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

import os
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
# The model-facing surface: the modules the model process itself loads. This is
# the trust boundary's definition, not a sample of it — server-side modules such
# as config/loader.py legitimately consume the bearer and are deliberately out of
# scope. _assert_surface_intact() below fails loudly if one of these is renamed,
# so the scan cannot silently pass over a surface that moved.
_MODEL_SURFACE_FILES = (
    "mcp_tools.py",
    "client_config/cursor.py",
    "client_config/mcp_probe.py",
    "client_config/contracts.py",
)
# Environment variables that would put a live Graphiti bearer in this process.
# config/loader.py maps GRAPHITI_MCP_TOKEN onto the server-side credential, so a
# model process that has it set holds the bearer regardless of what any source
# file says.
_BEARER_ENV_VARS = ("GRAPHITI_MCP_TOKEN",)
_KEYCHAIN_MARKERS = (
    "keychain",
    "keyring",
    "security find-generic-password",
    "graphiti_env_loader",
    "GRAPHITI_MCP_TOKEN",
)


def _assert_surface_intact() -> None:
    missing = [
        relative for relative in _MODEL_SURFACE_FILES if not (_PACKAGE_ROOT / relative).is_file()
    ]
    if missing:
        msg = (
            "model-surface files are missing, so the trust-boundary proof cannot "
            f"be evaluated: {', '.join(missing)}"
        )
        raise FileNotFoundError(msg)


def model_process_trust_boundary() -> dict[str, bool]:
    """Return the Release B model-process secret side-door proof.

    The model talks to MemoryService through MCP. It must not hold a Graphiti
    bearer and must not be able to read the Keychain graphiti-mcp-token.

    The bearer answer is taken from the effective process environment first: a
    live ``GRAPHITI_MCP_TOKEN`` means this process holds the credential, whether
    or not any scanned source file mentions it. The source scan then covers the
    static path, where the model surface reaches for the token itself.
    """
    _assert_surface_intact()
    haystack = ""
    for relative in _MODEL_SURFACE_FILES:
        haystack += (_PACKAGE_ROOT / relative).read_text(encoding="utf-8")
    lowered = haystack.lower()
    live_bearer = any(os.environ.get(name) for name in _BEARER_ENV_VARS)
    return {
        "model_has_graphiti_bearer": live_bearer or "GRAPHITI_MCP_TOKEN" in haystack,
        "model_can_read_keychain_graphiti_token": any(
            marker.lower() in lowered for marker in _KEYCHAIN_MARKERS
        ),
    }
