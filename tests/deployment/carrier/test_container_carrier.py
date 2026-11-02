# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/test_container_carrier.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-26

"""The built carrier image, run as the profile runs it, against a disposable PostgreSQL 16.

Each case starts the real image (read-only root, no new privileges, uid 10001)
on a private Docker network with a throwaway ``postgres:16``, publishes it on a
loopback port and probes it over real HTTP, the way l9-deploy and a remote
agent reach it. Credentials go in through an env file, as the deploy-rendered
runtime.env does; the PostgreSQL password is generated per run.

ADR-100 makes the hosted door Auth0 OAuth only: signed-agent HMAC and static
bearer are not hosted doors and not fallbacks. This release has no OAuth mode
(``http_auth_mode`` is ``bearer`` or ``signed-agent``), so the image must not
serve at all. Proven here:
- the image runs as the profile requires and pins no auth mode of its own;
- the complete hosted profile, with a reachable PostgreSQL and a full
  signed-agent registry in runtime.env, refuses to start: ``/readyz`` and
  ``/mcp`` never answer 200, even to a valid signed-agent credential;
- signed-agent and bearer are refused whether the profile or runtime.env names
  them, as are a missing DSN, a SQLite store, disabled auth and stale graph or
  active-memory backends;
- no key, assertion or database password reaches the container log.

These cases superseded the signed-agent proofs (agents sharing records,
credential refusals with 401, readiness following PostgreSQL, records
surviving a replaced container, signed-agent registry refusals, an unreachable
database). They need a serving door, which the published image must not have
before the OAuth resource server exists; issue #108 restores them over OAuth.

Not proven here: TLS, Caddy, the C1 host, Infisical, or the deployed service.
Runs only when ``L9_MEMORY_TEST_CARRIER_IMAGE`` names a locally built image;
the release workflow builds one and fails if anything here is skipped.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.integration.remote_mcp_harness import (
    AGENT_KEYS,
    WRITER,
    credentials,
    free_port,
    mcp_headers,
    rpc,
    server_environment,
)

IMAGE_ENV = "L9_MEMORY_TEST_CARRIER_IMAGE"
IMAGE = os.environ.get(IMAGE_ENV, "").strip()
POSTGRES_IMAGE = (
    "postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97"
)
# What the deployment profile sets; compose gives it precedence over runtime.env.
# No auth mode (ADR-100; the OAuth mode arrives with issue #108).
PROFILE_ENVIRONMENT = {
    "L9_MEMORY_STORE_BACKEND": "postgres",
    "L9_MEMORY_HTTP_AUTH_REQUIRED": "true",
    "L9_MEMORY_PROJECTION_BACKEND": "none",
    "L9_MEMORY_PROJECTION_RUNTIME": "legacy",
    "L9_MEMORY_GRAPH_BACKEND": "none",
    "L9_MEMORY_ACTIVE_BACKEND": "none",
    "L9_MEMORY_JSON_LOGS": "1",
}
# The profile without its backend pins: what a stale runtime.env entry would
# reach if the deployment profile ever stopped overriding it.
UNPINNED_PROFILE = {
    key: value
    for key, value in PROFILE_ENVIRONMENT.items()
    if key not in {"L9_MEMORY_GRAPH_BACKEND", "L9_MEMORY_ACTIVE_BACKEND"}
}

pytestmark = pytest.mark.skipif(
    not IMAGE, reason=f"{IMAGE_ENV} is not set; the carrier proof needs a built image"
)
httpx2 = pytest.importorskip("httpx2", reason="the carrier proof needs an HTTP client")


def _docker(*args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


@dataclass
class Database:
    network: str
    container: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.container} port=5432 user=postgres password={self.password} "
            "dbname=postgres connect_timeout=5"
        )


@pytest.fixture(scope="module")
def database() -> Iterator[Database]:
    if shutil.which("docker") is None:
        pytest.fail(f"{IMAGE_ENV} is set but the docker CLI is unavailable")
    tag = uuid.uuid4().hex[:12]
    network = f"l9-carrier-{tag}"
    container = f"l9-carrier-pg-{tag}"
    password = secrets.token_urlsafe(24)
    _docker("network", "create", network)
    try:
        _docker(
            "run", "-d", "--name", container, "--network", network,
            "-e", f"POSTGRES_PASSWORD={password}", POSTGRES_IMAGE,
        )  # fmt: skip
        _wait_for_postgres(container)
        yield Database(network=network, container=container, password=password)
    finally:
        _docker("rm", "-f", container, check=False)
        _docker("network", "rm", network, check=False)


def _wait_for_postgres(container: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        ready = _docker(
            "exec", container, "pg_isready", "-U", "postgres", "-h", "127.0.0.1", check=False
        )
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("disposable PostgreSQL 16 never became ready")


def _env_file(path: Path, values: dict[str, str]) -> Path:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), "utf-8")
    path.chmod(0o600)
    return path


def _runtime_env(database: Database, **overrides: str | None) -> dict[str, str]:
    """The deploy-rendered runtime.env: credentials only, never in the profile."""

    values: dict[str, str | None] = {
        **server_environment(),
        "L9_MEMORY_POSTGRES_DSN": database.dsn,
        "L9_MEMORY_LOCAL_TENANT_ID": "l9",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


@dataclass
class Carrier:
    container: str
    url: str


def _start(
    tmp_path: Path,
    database: Database,
    *,
    profile: dict[str, str] | None = None,
    **runtime: str | None,
) -> Carrier:
    name = f"l9-carrier-mem-{uuid.uuid4().hex[:12]}"
    port = free_port()
    env_file = _env_file(tmp_path / f"{name}.env", _runtime_env(database, **runtime))
    arguments = [
        "run", "-d", "--name", name, "--network", database.network,
        "--read-only", "--security-opt", "no-new-privileges:true",
        "-p", f"127.0.0.1:{port}:8200", "--env-file", str(env_file),
    ]  # fmt: skip
    for key, value in (PROFILE_ENVIRONMENT if profile is None else profile).items():
        arguments += ["-e", f"{key}={value}"]
    _docker(*arguments, IMAGE)
    return Carrier(container=name, url=f"http://127.0.0.1:{port}")


def _stop(carrier: Carrier) -> str:
    logs = _docker("logs", carrier.container, check=False)
    _docker("rm", "-f", carrier.container, check=False)
    return logs.stdout + logs.stderr


def _readyz(carrier: Carrier) -> httpx2.Response | None:
    try:
        return httpx2.get(f"{carrier.url}/readyz", timeout=10)
    except httpx2.HTTPError:
        return None


def _post(c: Carrier, body: dict[str, Any], headers: dict[str, str]) -> httpx2.Response | None:
    try:
        return httpx2.post(f"{c.url}/mcp", content=json.dumps(body), headers=headers, timeout=10)
    except httpx2.HTTPError:
        return None


def test_the_image_runs_as_the_profile_requires() -> None:
    """The image config, with no auth mode baked in (ADR-100; OAuth is issue #108)."""

    config = json.loads(_docker("image", "inspect", IMAGE).stdout)[0]["Config"]
    assert config["User"] == "10001:10001"
    assert "8200/tcp" in config["ExposedPorts"]
    assert config["Entrypoint"] == ["/usr/local/bin/l9-memory-carrier"]
    revision = config["Labels"]["org.opencontainers.image.revision"]
    assert len(revision) == 40
    assert all(c in "0123456789abcdef" for c in revision)
    environment = dict(item.split("=", 1) for item in config["Env"])
    assert environment["L9_MEMORY_STORE_BACKEND"] == "postgres"
    assert environment["L9_MEMORY_HTTP_AUTH_REQUIRED"] == "true"
    # ADR-100: the image carries no signed-agent or bearer door of its own.
    assert "L9_MEMORY_HTTP_AUTH_MODE" not in environment


NO_HOSTED_DOOR = (
    "L9_MEMORY_HTTP_AUTH_MODE must be the hosted OAuth mode, which this release "
    "does not have (ADR-100, issue #108)"
)
# case -> (profile environment or None for the profile's, runtime.env overrides, refusal)
REFUSED_STARTS: dict[str, tuple[dict[str, str] | None, dict[str, str | None], str]] = {
    # ADR-100: the committed profile with every credential a signed-agent
    # door would need and a reachable PostgreSQL still has no hosted door.
    "the complete hosted profile": (None, {}, NO_HOSTED_DOOR),
    "signed-agent auth in the profile": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent"},
        {},
        "L9_MEMORY_HTTP_AUTH_MODE=signed-agent is not a hosted door (ADR-100)",
    ),
    "signed-agent auth in runtime.env": (
        None,
        {"L9_MEMORY_HTTP_AUTH_MODE": "signed-agent"},
        "L9_MEMORY_HTTP_AUTH_MODE=signed-agent is not a hosted door (ADR-100)",
    ),
    "bearer-only auth in the profile": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE": "bearer"},
        {},
        "L9_MEMORY_HTTP_AUTH_MODE=bearer is not a hosted door (ADR-100)",
    ),
    "bearer tokens in runtime.env": (
        None,
        {
            "L9_MEMORY_HTTP_AUTH_MODE": "bearer",
            "L9_MEMORY_AUTH_TOKENS_JSON": json.dumps({"carrier-static-token": {"user_id": "u"}}),
        },
        "L9_MEMORY_HTTP_AUTH_MODE=bearer is not a hosted door (ADR-100)",
    ),
    "no PostgreSQL DSN": (
        None,
        {"L9_MEMORY_POSTGRES_DSN": None},
        "L9_MEMORY_POSTGRES_DSN is required",
    ),
    "a SQLite store": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_STORE_BACKEND": "sqlite"},
        {},
        "L9_MEMORY_STORE_BACKEND must be postgres",
    ),
    "auth disabled": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_REQUIRED": "false"},
        {},
        "L9_MEMORY_HTTP_AUTH_REQUIRED must be true",
    ),
    "a stale graph backend in runtime.env": (
        UNPINNED_PROFILE,
        {"L9_MEMORY_GRAPH_BACKEND": "neo4j"},
        "L9_MEMORY_GRAPH_BACKEND must be none",
    ),
    "a stale active-memory backend in runtime.env": (
        UNPINNED_PROFILE,
        {"L9_MEMORY_ACTIVE_BACKEND": "redis"},
        "L9_MEMORY_ACTIVE_BACKEND must be none",
    ),
}


@pytest.mark.parametrize("case", REFUSED_STARTS, ids=REFUSED_STARTS.keys())
def test_the_container_refuses_to_serve_without_a_hosted_door_or_store(
    tmp_path, database, case
) -> None:
    """ADR-100: no configuration of this release serves; each names its refusal.

    Supersedes the signed-agent pin of ADR-098 for the hosted carrier.
    """

    profile, runtime, refusal = REFUSED_STARTS[case]
    started = _start(tmp_path, database, profile=profile, **runtime)
    presented = credentials(WRITER)
    initialize = rpc(
        "initialize",
        {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t"}},
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = _docker("inspect", "-f", "{{.State.Running}}", started.container)
            if state.stdout.strip() != "true":
                break
            response = _readyz(started)
            assert response is None or response.status_code != 200, f"{case}: served ready"
            # Not even a valid signed-agent credential reaches MemoryService.
            served = _post(started, initialize, {**mcp_headers(), **presented})
            assert served is None or served.status_code != 200, f"{case}: served /mcp"
            time.sleep(0.5)
        else:
            pytest.fail(f"{case}: the container kept running instead of refusing to start")
        exit_code = _docker("inspect", "-f", "{{.State.ExitCode}}", started.container)
        assert exit_code.stdout.strip() not in {"", "0"}, case
    finally:
        logs = _stop(started)
    assert refusal in logs, logs[-2000:]
    for secret in [
        *AGENT_KEYS.values(),
        database.password,
        presented["Authorization"].split(" ", 1)[1],
        presented["L9-Identity-Assertion-HMAC"],
        "carrier-static-token",
    ]:
        assert secret not in logs, case
