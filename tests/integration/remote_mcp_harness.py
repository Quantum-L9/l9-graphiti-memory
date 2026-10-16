# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/remote_mcp_harness.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.7.0
#   updated: 2026-07-22

"""Shared harness for the remote (Streamable HTTP) MCP proof (ADR-098).

Everything here is client-side: it mints credentials the way a remote agent
must, and it drives a real server over a real TCP socket. Nothing in it is
trusted by the server; the server verifies each request on its own evidence.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from l9_graphite_memory.authz.signed_assertion import (
    identity_assertion_hmac,
    local_assertion_digest,
    mint_assertion,
)
from l9_graphite_memory.contracts.identity import (
    AGENT_BINDINGS_REF,
    GLOBAL_IDENTITY_AUTHORITY_REVISION,
    IDENTITY_BINDING_REF,
    IDENTITY_PROJECTION_REF,
    IDENTITY_RESOLVER_REF,
    MEMORY_PRODUCT_REF,
)

PROTOCOL_VERSION = "2025-11-25"
ACCEPT = "application/json, text/event-stream"
ALLOWED_ORIGIN = "https://console.l9.example"
FORBIDDEN_ORIGIN = "https://attacker.example"

# Two agents with server-registered keys. The keys are test fixtures that
# exist only in this process; production keys never appear in a repository.
WRITER = "claude-code"
READER = "cursor"
CO_WRITER = "codex"  # a second agent with the same write grant as WRITER
OUTSIDER = "manus"  # holds a key the server never registered
AGENT_KEYS = {
    WRITER: "writer-signing-key-0123456789abcdef",
    READER: "reader-signing-key-0123456789abcdef",
    CO_WRITER: "cowriter-signing-key-0123456789abcd",
}
OUTSIDER_KEY = "outsider-signing-key-0123456789abcd"
HOME_NAMESPACE = "repo-a"
FOREIGN_NAMESPACE = "repo-b"
AGENT_GRANTS = {
    WRITER: {
        "roles": ["implementer", "memory-client"],
        "read_namespaces": [HOME_NAMESPACE],
        "write_namespaces": [HOME_NAMESPACE],
        "promote_namespaces": [],
        "is_admin": False,
    },
    READER: {
        "roles": ["reviewer", "memory-client"],
        "read_namespaces": [HOME_NAMESPACE],
        "write_namespaces": [],
        "promote_namespaces": [],
        "is_admin": False,
    },
    CO_WRITER: {
        "roles": ["implementer", "memory-client"],
        "read_namespaces": [HOME_NAMESPACE],
        "write_namespaces": [HOME_NAMESPACE],
        "promote_namespaces": [],
        "is_admin": False,
    },
}


def identity_body(agent_id: str, *, actor: str | None = None) -> dict[str, Any]:
    """An unsealed ``l9.identity-assertion/v1`` for ``agent_id``.

    ``actor`` overrides the actor coordinate so a test can build evidence that
    names a different actor than the one presenting it.
    """

    actor_id = actor or agent_id
    actor_ref = f"l9.actor-registry/global@1#{actor_id}"
    return {
        "schema": "l9.identity-assertion/v1",
        "subject_ref": actor_ref,
        "product_ref": MEMORY_PRODUCT_REF,
        "resolved_dimensions": {
            "actor_identity": actor_ref,
            "constellation_identity": "unknown",
            "release_identity": "unknown",
            "runtime_identity": "unknown",
            "surface_identity": "l9.surface-registry/global@1#claude-code-cli",
        },
        "bindings": [IDENTITY_BINDING_REF, f"{AGENT_BINDINGS_REF}#{actor_id}"],
        "evidence_refs": [
            IDENTITY_PROJECTION_REF,
            IDENTITY_BINDING_REF,
            f"{AGENT_BINDINGS_REF}#{actor_id}",
        ],
        "resolver_ref": IDENTITY_RESOLVER_REF,
        "governing_coordinates": {
            "actor_registry_digest": (
                "sha256:34fbe4abc246e21c28401941025317be52c109c88335577616a2648cc93c6f6f"
            ),
            "agent_bindings_ref": AGENT_BINDINGS_REF,
            "global_identity_authority_revision": GLOBAL_IDENTITY_AUTHORITY_REVISION,
            "identity_binding_ref": IDENTITY_BINDING_REF,
            "identity_projection_digest": (
                "sha256:9d7491d507b7204caeaa9892019ab39a5e459cf507c59fa192fa238e3a953c5c"
            ),
            "identity_projection_ref": IDENTITY_PROJECTION_REF,
            "surface_registry_digest": (
                "sha256:d7200409ff02141a274ff8c9221d31429f6a6fae27539e6d9c8d20f1a6eba988"
            ),
        },
        "result": "resolved",
        "provenance": {
            "runtime_evidence_digest": (
                "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        },
    }


def seal(body: dict[str, Any], key: str) -> tuple[dict[str, Any], str]:
    sealed = dict(body)
    sealed["assertion_digest"] = local_assertion_digest(body)
    return sealed, identity_assertion_hmac(sealed["assertion_digest"], key)


def encode(sealed: dict[str, Any]) -> str:
    """The ``L9-Identity-Assertion`` header value, encoded independently of the server."""

    raw = json.dumps(sealed, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def credentials(
    agent_id: str,
    *,
    key: str | None = None,
    ttl_seconds: int = 900,
    body: dict[str, Any] | None = None,
    identity_key: str | None = None,
) -> dict[str, str]:
    """The three credential headers a remote agent presents on every request."""

    signing_key = key if key is not None else AGENT_KEYS[agent_id]
    sealed, mac = seal(
        body if body is not None else identity_body(agent_id),
        identity_key if identity_key is not None else signing_key,
    )
    return {
        "Authorization": f"Bearer {mint_assertion(agent_id, signing_key, ttl_seconds=ttl_seconds)}",
        "L9-Identity-Assertion": encode(sealed),
        "L9-Identity-Assertion-HMAC": mac,
    }


def mcp_headers(*, protocol: str | None = PROTOCOL_VERSION) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": ACCEPT}
    if protocol is not None:
        headers["MCP-Protocol-Version"] = protocol
    return headers


def rpc(method: str, params: dict[str, Any] | None = None, *, request_id: int = 1) -> dict:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def tool(name: str, arguments: dict[str, Any], *, request_id: int = 1) -> dict:
    return rpc("tools/call", {"name": name, "arguments": arguments}, request_id=request_id)


def tool_payload(response_body: dict[str, Any]) -> dict[str, Any]:
    assert "result" in response_body, response_body
    return dict(json.loads(response_body["result"]["content"][0]["text"]))


def server_environment() -> dict[str, str]:
    """The server-side registry: keys and grants, never sent by a client."""

    return {
        "L9_MEMORY_AGENT_SIGNING_KEYS_JSON": json.dumps(AGENT_KEYS),
        "L9_MEMORY_AGENT_GRANTS_JSON": json.dumps(AGENT_GRANTS),
    }


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextlib.contextmanager
def serve(app: Any) -> Iterator[str]:
    """Run ``app`` under uvicorn on a real loopback socket; yield its base URL."""

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=free_port(), log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="remote-mcp-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{config.port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def wait_for(url: str, *, timeout: float = 30.0) -> None:
    """Block until a server in another process answers ``/healthz``."""

    import httpx2

    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx2.get(f"{url}/healthz", timeout=2).status_code in {200, 503}:
                return
        except httpx2.HTTPError as exc:
            last = exc
        time.sleep(0.1)
    raise RuntimeError(f"server at {url} never answered: {last!r}")


def build_installed_site(root: Path, repo_root: Path) -> Path:
    """Build the wheel once into ``root`` and install it, alone, into ``root/site``.

    Consumers bind an installed artifact, never a checkout, so proofs that
    matter run with only this directory on ``PYTHONPATH``. Dependencies come
    from the running interpreter; ``l9_graphite_memory`` comes only from here.
    """

    dist = root / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist), str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SOURCE_DATE_EPOCH": "1784592000"},
    )
    assert build.returncode == 0, build.stderr[-2000:]
    wheels = sorted(dist.glob("l9_graphite_memory-*.whl"))
    assert len(wheels) == 1, wheels
    site = root / "site"
    site.mkdir()
    if shutil.which("uv"):
        install = [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(site),
            "--reinstall",
            "--no-deps",
            str(wheels[0]),
        ]
    else:
        install = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(site),
            "--force-reinstall",
            "--no-deps",
            str(wheels[0]),
        ]
    result = subprocess.run(install, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    return site
