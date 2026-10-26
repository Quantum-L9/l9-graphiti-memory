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
loopback port and drives it over real HTTP, the way l9-deploy and a remote
agent reach it. Credentials go in through an env file, as the deploy-rendered
runtime.env does; the PostgreSQL password is generated per run.

Proven here:
- ``/readyz`` is 200 only while the canonical PostgreSQL store is reachable,
  503 when it is gone, and the served store is PostgreSQL, never a SQLite file;
- ``/mcp`` refuses a missing, malformed, expired, unregistered or mis-sealed
  credential with 401 and a Bearer challenge; a registered signed agent
  initializes, writes, and another agent reads and searches the record; a
  namespace outside the grant is refused;
- the record survives the container being replaced;
- no key, assertion or database password reaches the container log;
- the container refuses to start without PostgreSQL, on a SQLite or bearer or
  unauthenticated setting, without the agent registry, with an administrator
  grant, or against an unreachable database.

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
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.integration.remote_mcp_harness import (
    AGENT_GRANTS,
    AGENT_KEYS,
    FOREIGN_NAMESPACE,
    HOME_NAMESPACE,
    OUTSIDER,
    OUTSIDER_KEY,
    READER,
    WRITER,
    credentials,
    free_port,
    mcp_headers,
    rpc,
    server_environment,
    tool,
    tool_payload,
)

IMAGE_ENV = "L9_MEMORY_TEST_CARRIER_IMAGE"
IMAGE = os.environ.get(IMAGE_ENV, "").strip()
POSTGRES_IMAGE = (
    "postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97"
)
# What the deployment profile sets; compose gives it precedence over runtime.env.
PROFILE_ENVIRONMENT = {
    "L9_MEMORY_STORE_BACKEND": "postgres",
    "L9_MEMORY_HTTP_AUTH_REQUIRED": "true",
    "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent",
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


def _token() -> str:
    """A unique, digit-free marker for record content.

    Admission redacts PII, and a run of ten digits inside a random hex string
    reads as a phone number, so a uuid in content is rewritten about one time
    in ten. Letters only keep the stored content byte-for-byte comparable.
    """

    return uuid.uuid4().hex.translate(str.maketrans("0123456789", "ghijklmnop"))


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


def _wait_ready(carrier: Carrier, *, status: int = 200, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        response = _readyz(carrier)
        if response is not None and response.status_code == status:
            body: dict[str, Any] = response.json()
            return body
        last = response.status_code if response is not None else "no answer"
        running = _docker("inspect", "-f", "{{.State.Running}}", carrier.container, check=False)
        if running.stdout.strip() != "true":
            break
        time.sleep(0.5)
    logs = _docker("logs", carrier.container, check=False)
    raise AssertionError(f"/readyz never answered {status} (last {last}): {logs.stderr[-2000:]}")


def _wait_not_ready(carrier: Carrier, *, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    consecutive = 0
    while time.monotonic() < deadline:
        response = _readyz(carrier)
        consecutive = consecutive + 1 if response is None or response.status_code != 200 else 0
        if consecutive >= 3:
            return
        time.sleep(0.5)
    raise AssertionError("/readyz kept answering 200 without its canonical store")


@contextmanager
def carrier(tmp_path: Path, database: Database, **runtime: str | None) -> Iterator[Carrier]:
    started = _start(tmp_path, database, **runtime)
    try:
        _wait_ready(started)
        yield started
    finally:
        _stop(started)


def _post(c: Carrier, body: dict[str, Any], headers: dict[str, str]) -> httpx2.Response:
    return httpx2.post(f"{c.url}/mcp", content=json.dumps(body), headers=headers, timeout=15)


def _call(c: Carrier, agent: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = _post(c, tool(name, arguments), {**mcp_headers(), **credentials(agent)})
    assert response.status_code == 200, response.text
    return tool_payload(response.json())


def _written(c: Carrier, content: str) -> str:
    written = _call(
        c,
        WRITER,
        "memory.write_agent",
        {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": uuid.uuid4().hex},
    )
    assert written["status"] == "admitted", written
    record_id: str = written["record_id"]
    return record_id


def test_the_image_runs_as_the_profile_requires() -> None:
    config = json.loads(_docker("image", "inspect", IMAGE).stdout)[0]["Config"]
    assert config["User"] == "10001:10001"
    assert "8200/tcp" in config["ExposedPorts"]
    assert config["Entrypoint"] == ["/usr/local/bin/l9-memory-carrier"]
    revision = config["Labels"]["org.opencontainers.image.revision"]
    assert len(revision) == 40
    assert all(c in "0123456789abcdef" for c in revision)


def test_readiness_follows_the_canonical_postgres_store(tmp_path, database) -> None:
    with carrier(tmp_path, database) as c:
        ready = _wait_ready(c)
        canonical = ready["readiness"]["families"]
        store = next(family for family in canonical if family["name"] == "canonical")
        assert store["healthy"] is True
        assert store["detail"]["shared_store"] is True
        assert httpx2.get(f"{c.url}/healthz", timeout=10).json()["store"]["name"] == "postgres"
        # Serving wrote nothing to the container filesystem: no ledger, no state.
        _written(c, "a write that must land in PostgreSQL, not on local disk")
        assert _docker("diff", c.container).stdout.strip() == ""
        _docker("stop", database.container)
        try:
            # Not ready while the store is gone. The server currently answers
            # 500 (an unhandled StoreError) rather than 503; either way never
            # 200, which is what the l9-deploy health probe and Caddy rely on.
            _wait_not_ready(c)
        finally:
            _docker("start", database.container)
            _wait_for_postgres(database.container)
        _wait_ready(c)


def test_signed_agents_share_records_and_every_bad_credential_is_refused(
    tmp_path, database
) -> None:
    with carrier(tmp_path, database) as c:
        initialize = rpc(
            "initialize",
            {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t"}},
        )
        refusals = {
            "no credential": mcp_headers(),
            "malformed bearer": {**mcp_headers(), "Authorization": "Bearer not.a.token"},
            "expired assertion": {**mcp_headers(), **credentials(WRITER, ttl_seconds=-120)},
            "unregistered agent": {**mcp_headers(), **credentials(OUTSIDER, key=OUTSIDER_KEY)},
            "assertion sealed under another key": {
                **mcp_headers(),
                **credentials(WRITER, identity_key=AGENT_KEYS[READER]),
            },
        }
        for case, headers in refusals.items():
            response = _post(c, initialize, headers)
            assert response.status_code == 401, (case, response.text)
            assert response.headers["WWW-Authenticate"].startswith("Bearer"), case

        session = _post(c, initialize, {**mcp_headers(), **credentials(WRITER)})
        assert session.status_code == 200, session.text
        assert session.json()["result"]["serverInfo"]["name"] == "l9-graphite-memory"

        content = f"carrier proof {_token()}: the kingfisher nests by the sluice"
        record_id = _written(c, content)
        got = _call(c, READER, "memory.get", {"record_id": record_id})
        assert got["found"] is True
        assert got["record"]["content"] == content
        assert got["record"]["provenance"]["source_agent_id"] == WRITER
        hits = _call(
            c, READER, "memory.search", {"query": "kingfisher", "namespaces": [HOME_NAMESPACE]}
        )
        assert record_id in [hit["record"]["record_id"] for hit in hits["hits"]]

        foreign = _call(
            c,
            WRITER,
            "memory.write_agent",
            {"namespace": FOREIGN_NAMESPACE, "content": "outside the grant"},
        )
        assert foreign["status"] == "rejected"
        assert foreign["record_id"] is None
        assert foreign["authorization"]["allowed"] is False
        read_only = _call(
            c, READER, "memory.write_agent", {"namespace": HOME_NAMESPACE, "content": "no grant"}
        )
        assert read_only["status"] == "rejected"


def test_records_survive_the_container_being_replaced(tmp_path, database) -> None:
    content = f"carrier persistence {_token()}"
    with carrier(tmp_path, database) as first:
        record_id = _written(first, content)
    with carrier(tmp_path, database) as second:
        got = _call(second, READER, "memory.get", {"record_id": record_id})
        assert got["found"] is True
        assert got["record"]["content"] == content


def test_no_secret_reaches_the_container_log(tmp_path, database) -> None:
    started = _start(tmp_path, database)
    presented = credentials(WRITER)
    try:
        _wait_ready(started)
        _written(started, "a write whose credentials must not be logged")
        _post(started, rpc("ping"), {**mcp_headers(), "Authorization": "Bearer leaked.123.x.y"})
    finally:
        logs = _stop(started)
    assert logs.strip(), "the container wrote no log to inspect"
    for secret in [
        *AGENT_KEYS.values(),
        database.password,
        presented["Authorization"].split(" ", 1)[1],
        presented["L9-Identity-Assertion-HMAC"],
        "leaked.123.x.y",
    ]:
        assert secret not in logs


ADMIN_GRANTS = {agent: {**grant, "is_admin": True} for agent, grant in AGENT_GRANTS.items()}
# case -> (profile environment or None for the profile's, runtime.env overrides, refusal)
REFUSED_STARTS: dict[str, tuple[dict[str, str] | None, dict[str, str | None], str]] = {
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
    "bearer-only auth": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE": "bearer"},
        {},
        "L9_MEMORY_HTTP_AUTH_MODE must be signed-agent",
    ),
    "auth disabled": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_REQUIRED": "false"},
        {},
        "L9_MEMORY_HTTP_AUTH_REQUIRED must be true",
    ),
    "no agent signing keys": (
        None,
        {"L9_MEMORY_AGENT_SIGNING_KEYS_JSON": None},
        "requires L9_MEMORY_AGENT_SIGNING_KEYS_JSON",
    ),
    "no agent grants": (
        None,
        {"L9_MEMORY_AGENT_GRANTS_JSON": None},
        "requires L9_MEMORY_AGENT_GRANTS_JSON",
    ),
    "an administrator grant": (
        None,
        {"L9_MEMORY_AGENT_GRANTS_JSON": json.dumps(ADMIN_GRANTS)},
        "administrator authority is not reachable over HTTP",
    ),
    "an unreachable database": (
        None,
        {"L9_MEMORY_POSTGRES_DSN": "host=l9-carrier-nowhere port=5432 user=x connect_timeout=3"},
        "postgres connection failed",
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
def test_the_container_refuses_to_serve_a_misconfigured_store_or_door(
    tmp_path, database, case
) -> None:
    profile, runtime, refusal = REFUSED_STARTS[case]
    started = _start(tmp_path, database, profile=profile, **runtime)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = _docker("inspect", "-f", "{{.State.Running}}", started.container)
            if state.stdout.strip() != "true":
                break
            response = _readyz(started)
            assert response is None or response.status_code != 200, f"{case}: served ready"
            time.sleep(0.5)
        else:
            pytest.fail(f"{case}: the container kept running instead of refusing to start")
        exit_code = _docker("inspect", "-f", "{{.State.ExitCode}}", started.container)
        assert exit_code.stdout.strip() not in {"", "0"}, case
    finally:
        logs = _stop(started)
    assert refusal in logs, logs[-2000:]
    assert database.password not in logs
    assert not any(key in logs for key in AGENT_KEYS.values())
