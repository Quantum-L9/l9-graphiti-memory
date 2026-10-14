# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_installed_wheel_lifecycle.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-06

"""The consumer lifecycle against the *built and installed* wheel (stage M2).

Cursor-Governance binds an installed artifact, never this checkout, so the
proof that matters is the one that runs from a wheel installed into an empty
target directory with nothing else on ``PYTHONPATH``: capabilities, health,
governed continuation admission, tag-selected retrieval, and an idempotent
close, each through the console entry point the consumer actually invokes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "control_plane" / "continuation_candidate.json"


@pytest.fixture(scope="module")
def installed_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel once and install it into an isolated target directory."""

    pytest.importorskip("build")
    root = tmp_path_factory.mktemp("wheel")
    dist = root / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist), str(REPO_ROOT)],
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


def _env(site: Path, data: Path) -> dict[str, str]:
    """Only the installed wheel is importable; the checkout is not on the path."""

    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONPATH",
            "L9_MEMORY_CONFIG",
            "GRAPHITI_GROUP_ID",
            "CURSOR_CONVERSATION_ID",
            "L9_SESSION_ID",
        }
    }
    # pydantic and pyyaml come from the running interpreter's site; the wheel
    # itself is the only l9_graphite_memory on the path.
    env["PYTHONPATH"] = str(site)
    env.update(
        {
            "HOME": str(data / "home"),
            "L9_MEMORY_DATA_DIR": str(data / "data"),
            "L9_MEMORY_STATE_DIR": str(data / "state"),
            "L9_MEMORY_NAMESPACE": "repo-a",
            "L9_MEMORY_PROJECTION_BACKEND": "none",
            "L9_MEMORY_JSON_LOGS": "0",
        }
    )
    return env


def _run(env: dict[str, str], cwd: Path, *argv: str, stdin: str | None = None):
    result = subprocess.run(
        [sys.executable, "-m", "l9_graphite_memory.cli", *argv],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
        input=stdin,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else None
    return result.returncode, payload, result.stderr


def test_installed_wheel_is_the_module_that_runs(installed_site: Path, tmp_path: Path) -> None:
    env = _env(installed_site, tmp_path)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import l9_graphite_memory, sys; print(l9_graphite_memory.__file__)",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env=env,
    )
    assert probe.stdout.strip().startswith(str(installed_site))


def test_installed_wheel_runs_the_consumer_lifecycle(installed_site: Path, tmp_path: Path) -> None:
    env = _env(installed_site, tmp_path)
    cwd = tmp_path / "workspace"
    cwd.mkdir()

    code, capabilities, _ = _run(env, cwd, "capabilities")
    assert code == 0
    assert capabilities["contract_version"] == "memory-control-plane/v1"
    cli_ops = next(
        item["operations"] for item in capabilities["transports"] if item["transport"] == "cli"
    )
    assert {"close", "hydrate", "ingest_governed_candidate", "capabilities"} <= set(cli_ops)

    code, health, _ = _run(env, cwd, "health")
    assert code == 0 and health["status"] == "complete"
    assert health["projection"]["name"] == "none"
    assert health["package_version"] == capabilities["package_version"]

    candidate = FIXTURE.read_text(encoding="utf-8")
    code, admitted, stderr = _run(env, cwd, "ingest-governed-candidate", stdin=candidate)
    assert code == 0, stderr
    assert admitted["status"] == "admitted" and admitted["record_id"]
    code, replayed, _ = _run(env, cwd, "ingest-governed-candidate", stdin=candidate)
    assert code == 0 and replayed["status"] == "duplicate"
    assert replayed["record_id"] == admitted["record_id"]

    code, hydrated, _ = _run(
        env, cwd, "hydrate", "resume", "--group-id", "repo-a", "--tag", "session_continuation"
    )
    assert code == 0
    record_ids = {rid for section in hydrated["sections"] for rid in section["record_ids"]}
    assert record_ids == {admitted["record_id"]}

    code, found, _ = _run(
        env, cwd, "search", "anything", "--group-id", "repo-a", "--tag", "session_continuation"
    )
    assert code == 0 and len(found["hits"]) == 1
    payload = found["hits"][0]["record"]["metadata"]["structured_payload"]
    assert payload["schema"] == "cursor.continuation/v2"

    close_args = ("close", "--summary", "installed wheel close", "--group-id", "repo-a")
    code, dry, _ = _run(env, cwd, *close_args, "--dry-run")
    assert code == 3 and dry["status"] == "partial"
    code, first, _ = _run(env, cwd, *close_args, "--idempotency-key", "wheel-close-1")
    assert code == 0 and first["status"] == "complete" and first["replayed"] is False
    code, second, _ = _run(env, cwd, *close_args, "--idempotency-key", "wheel-close-1")
    assert code == 0 and second["replayed"] is True
    assert second["record_id"] == first["record_id"]


def test_installed_wheel_cursor_client_lifecycle_proves_installed_entry(
    installed_site: Path, tmp_path: Path
) -> None:
    env = _env(installed_site, tmp_path)
    cwd = tmp_path / "workspace"
    cwd.mkdir()
    config = tmp_path / "home" / ".cursor" / "mcp.json"

    code, installed, _ = _run(env, cwd, "client", "cursor", "install", "--path", str(config))
    assert code == 0 and installed["status"] == "complete"
    written = json.loads(config.read_text(encoding="utf-8"))
    entry = written["mcpServers"]["l9-graphite-memory"]
    assert "env" not in entry and entry["args"][-2:] == ["--transport", "stdio"]

    code, verified, stderr = _run(
        env, cwd, "client", "cursor", "verify", "--path", str(config), "--timeout", "90"
    )
    assert code == 0, stderr
    assert verified["status"] == "complete"
    assert verified["argv_source"] == "installed"
    assert verified["config_path"] == str(config)
    assert list(verified["command_argv"]) == [entry["command"], *entry["args"]]
    assert verified["health_status"] in {"complete", "partial"}


def test_installed_wheel_serves_remote_mcp_to_signed_agents(
    installed_site: Path, tmp_path: Path
) -> None:
    """ADR-098 against the artifact: the console server entry point, real TCP, signed agents.

    The server process imports only the installed wheel; the credentials are
    minted client-side exactly as a remote agent mints them.
    """

    pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
    pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")
    httpx2 = pytest.importorskip("httpx2", reason="the HTTP proof needs an HTTP client")
    from l9_graphite_memory.mcp_tools import tool_definitions
    from l9_graphite_memory.version import HTTP_MCP_PROTOCOL_VERSIONS, PACKAGE_VERSION
    from tests.integration.remote_mcp_harness import (
        ALLOWED_ORIGIN,
        FORBIDDEN_ORIGIN,
        FOREIGN_NAMESPACE,
        HOME_NAMESPACE,
        READER,
        WRITER,
        credentials,
        free_port,
        mcp_headers,
        rpc,
        server_environment,
        tool,
        tool_payload,
        wait_for,
    )

    env = _env(installed_site, tmp_path)
    env.update(server_environment())
    env.update(
        {
            "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent",
            "L9_MEMORY_HTTP_ALLOWED_ORIGINS": ALLOWED_ORIGIN,
            "L9_MEMORY_LOCAL_TENANT_ID": "l9",
            "L9_MEMORY_HUMAN_DOOR_SECRET": "local-human-door-secret",
        }
    )
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    log = tmp_path / "server.log"
    with log.open("w") as stderr:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "l9_graphite_memory.server",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
    try:
        wait_for(url)

        def post(message, *, agent=WRITER, headers=None, protocol="2025-11-25"):
            sent = mcp_headers(protocol=protocol)
            if agent is not None:
                sent.update(credentials(agent))
            sent.update(headers or {})
            return httpx2.post(f"{url}/mcp", content=json.dumps(message), headers=sent, timeout=10)

        initialize = post(rpc("initialize", {"protocolVersion": "2025-11-25"}), protocol=None)
        assert initialize.status_code == 200, initialize.text
        assert initialize.json()["result"]["protocolVersion"] == "2025-11-25"
        assert initialize.json()["result"]["serverInfo"]["version"] == PACKAGE_VERSION
        notified = post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert (notified.status_code, notified.content) == (202, b"")
        assert post(rpc("tools/list")).json()["result"]["tools"] == tool_definitions()

        capabilities = tool_payload(post(tool("memory.capabilities", {})).json())
        assert capabilities["package_version"] == PACKAGE_VERSION
        assert capabilities["http_mcp_protocol_versions"] == list(HTTP_MCP_PROTOCOL_VERSIONS)

        written = tool_payload(
            post(
                tool(
                    "memory.write_agent",
                    {"namespace": HOME_NAMESPACE, "content": "heron wades in the mill pond"},
                )
            ).json()
        )
        assert written["status"] == "admitted", written
        found = tool_payload(
            post(
                tool("memory.search", {"query": "heron", "namespaces": [HOME_NAMESPACE]}),
                agent=READER,
            ).json()
        )
        assert written["record_id"] in {hit["record"]["record_id"] for hit in found["hits"]}

        denied = tool_payload(
            post(
                tool("memory.write_agent", {"namespace": FOREIGN_NAMESPACE, "content": "no grant"})
            ).json()
        )
        assert (denied["status"], denied["record_id"]) == ("rejected", None)

        assert post(rpc("tools/list"), agent=None).status_code == 401
        tampered = credentials(WRITER)
        tampered["L9-Identity-Assertion-HMAC"] = "0" * 64
        assert post(rpc("tools/list"), agent=None, headers=tampered).status_code == 401
        assert post(rpc("tools/list"), headers={"Origin": FORBIDDEN_ORIGIN}).status_code == 403
        assert post(rpc("tools/list"), protocol="2024-11-05").status_code == 400
        assert post(rpc("tools/list"), protocol=None).status_code == 400
        assert httpx2.get(f"{url}/mcp", timeout=10).status_code == 405
        assert server.poll() is None, log.read_text()[-2000:]
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=15)


def test_installed_wheel_refuses_an_administrator_agent_grant_before_serving(
    installed_site: Path, tmp_path: Path
) -> None:
    """ADR-098 against the artifact: an administrator agent grant never reaches a socket.

    The console server entry point exits with the refusal before it binds the
    port, so no request is ever served under an administrator agent principal.
    """

    pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
    pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")
    import socket

    from tests.integration.remote_mcp_harness import (
        AGENT_GRANTS,
        READER,
        free_port,
        server_environment,
    )

    env = _env(installed_site, tmp_path)
    env.update(server_environment())
    grants = {**AGENT_GRANTS, READER: {**AGENT_GRANTS[READER], "is_admin": True}}
    env.update(
        {
            "L9_MEMORY_AGENT_GRANTS_JSON": json.dumps(grants),
            "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent",
            "L9_MEMORY_LOCAL_TENANT_ID": "l9",
        }
    )
    port = free_port()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "l9_graphite_memory.server",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode != 0, completed.stderr[-2000:]
    assert f"is_admin to agent_id='{READER}'" in completed.stderr, completed.stderr[-2000:]
    assert "administrator authority is not reachable over HTTP" in completed.stderr
    assert "Uvicorn running" not in completed.stderr
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
