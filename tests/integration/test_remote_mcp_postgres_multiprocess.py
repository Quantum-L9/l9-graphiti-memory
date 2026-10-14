"""Shared memory across processes: signed agents over HTTP on one PostgreSQL store.

The 3.0.0 claim is that separately authenticated agents, reaching separately
running server processes, share one canonical record store. Every case here
starts real ``l9_graphite_memory.server`` processes on loopback TCP against a
fresh PostgreSQL schema; nothing is shared in memory between them.

Proven here, per process boundary:
- agent A writes through one process, agent B reads and searches the same
  canonical record through another, attributed to A;
- grants are enforced server-side on that shared store (read-only agent,
  foreign namespace, unregistered agent, foreign tenant);
- idempotency replays and key reuse resolve to the original record across
  processes;
- records and idempotency survive every process stopping;
- the configured PostgreSQL store is the one serving; nothing falls back to a
  local SQLite ledger, and an unusable DSN stops the server;
- two processes cold-starting on one empty schema both come up.

Not proven here: TLS, a non-loopback network path, or any deployed host.
Skips visibly without ``L9_MEMORY_TEST_POSTGRES_DSN``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import make_postgres_store, postgres_test_dsn
from tests.integration.remote_mcp_harness import (
    ALLOWED_ORIGIN,
    FOREIGN_NAMESPACE,
    HOME_NAMESPACE,
    OUTSIDER,
    OUTSIDER_KEY,
    READER,
    WRITER,
    credentials,
    free_port,
    mcp_headers,
    server_environment,
    tool,
    tool_payload,
    wait_for,
)

pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")
pytest.importorskip("psycopg2", reason="the shared store requires the [postgres] extra")
httpx2 = pytest.importorskip("httpx2", reason="the HTTP proof needs an HTTP client")

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def schema() -> str:
    """A fresh, empty PostgreSQL schema; no table exists until a server starts."""

    name = f"l9_mp_{uuid.uuid4().hex}"
    make_postgres_store(name).close()
    return name


def _server_env(tmp_path: Path, schema: str, *, tenant: str, dsn: str | None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("L9_MEMORY_", "GRAPHITI_", "ZEP_")) and key != "PYTHONPATH"
    }
    env.update(server_environment())
    env.update(
        {
            "PYTHONPATH": str(SRC),
            "HOME": str(tmp_path / "home"),
            "L9_MEMORY_DATA_DIR": str(tmp_path / "data"),
            "L9_MEMORY_STATE_DIR": str(tmp_path / "state"),
            "L9_MEMORY_PROJECTION_BACKEND": "none",
            "L9_MEMORY_JSON_LOGS": "0",
            "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent",
            "L9_MEMORY_HTTP_ALLOWED_ORIGINS": ALLOWED_ORIGIN,
            "L9_MEMORY_LOCAL_TENANT_ID": tenant,
            "L9_MEMORY_STORE_BACKEND": "postgres",
            "L9_MEMORY_POSTGRES_DSN": (
                dsn if dsn is not None else f"{postgres_test_dsn()} options=-csearch_path={schema}"
            ),
        }
    )
    return env


def _launch(tmp_path: Path, schema: str, *, tenant: str = "l9", dsn: str | None = None):
    port = free_port()
    workdir = tmp_path / f"server-{port}"
    workdir.mkdir()
    log = (workdir / "server.log").open("w")
    process = subprocess.Popen(
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
        cwd=workdir,
        env=_server_env(workdir, schema, tenant=tenant, dsn=dsn),
        stdout=subprocess.DEVNULL,
        stderr=log,
    )
    return process, f"http://127.0.0.1:{port}", workdir, log


def _stop(process: subprocess.Popen[Any], log: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
    log.close()


@contextmanager
def server(tmp_path: Path, schema: str, *, tenant: str = "l9") -> Iterator[tuple[str, Path]]:
    """One server process on the shared schema; yields its URL and workdir."""

    process, url, workdir, log = _launch(tmp_path, schema, tenant=tenant)
    try:
        try:
            wait_for(url)
        except RuntimeError:
            log.flush()
            raise RuntimeError((workdir / "server.log").read_text()) from None
        yield url, workdir
    finally:
        _stop(process, log)


def _call(url: str, agent: str, name: str, arguments: dict[str, Any], **kw: Any) -> Any:
    headers = {**mcp_headers(), **credentials(agent, **kw)}
    return httpx2.post(f"{url}/mcp", content=json.dumps(tool(name, arguments)), headers=headers)


def _payload(url: str, agent: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = _call(url, agent, name, arguments)
    assert response.status_code == 200, response.text
    return tool_payload(response.json())


def _error(url: str, agent: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = _call(url, agent, name, arguments)
    assert response.status_code == 200, response.text
    return dict(response.json()["error"])


def _no_sqlite_ledger(workdir: Path) -> None:
    ledgers = [path for path in workdir.rglob("*") if path.suffix in {".sqlite3", ".sqlite", ".db"}]
    assert ledgers == [], f"a local ledger appeared beside the shared store: {ledgers}"


def test_two_agents_share_one_postgres_store_across_server_processes(
    tmp_path: Path, schema: str
) -> None:
    content = "the shared ledger records a heron on the north weir"
    key = f"mp-{uuid.uuid4().hex}"
    with server(tmp_path, schema) as (url_a, dir_a), server(tmp_path, schema) as (url_b, dir_b):
        # Each process serves the configured shared backend, not a local file.
        for url in (url_a, url_b):
            health = httpx2.get(f"{url}/healthz", timeout=10).json()
            assert health["store"]["name"] == "postgres", health
            assert health["store"]["healthy"] is True, health

        # Agent A writes through process A.
        written = _payload(
            url_a,
            WRITER,
            "memory.write_agent",
            {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": key},
        )
        assert written["status"] == "admitted"
        record_id = written["record_id"]

        # Agent B, a different identity on a different process, reads it.
        got = _payload(url_b, READER, "memory.get", {"record_id": record_id})
        assert got["found"] is True
        assert got["record"]["content"] == content
        assert got["record"]["provenance"]["source_agent_id"] == WRITER
        found = _payload(
            url_b, READER, "memory.search", {"query": "heron", "namespaces": [HOME_NAMESPACE]}
        )
        assert [hit["record"]["record_id"] for hit in found["hits"]] == [record_id]

        # B does not inherit A's rights: its write is refused on the shared store.
        refused = _payload(
            url_b,
            READER,
            "memory.write_agent",
            {"namespace": HOME_NAMESPACE, "content": "the reader tries to write"},
        )
        assert refused["status"] == "rejected"
        assert refused["record_id"] is None
        assert refused["authorization"]["allowed"] is False

        # A namespace outside A's grant is refused for writes and reads.
        foreign = _payload(
            url_b,
            WRITER,
            "memory.write_agent",
            {"namespace": FOREIGN_NAMESPACE, "content": "a fact for an ungranted namespace"},
        )
        assert foreign["status"] == "rejected"
        error = _error(
            url_a, WRITER, "memory.search", {"query": "fact", "namespaces": [FOREIGN_NAMESPACE]}
        )
        assert error["code"] == -32010
        assert error["data"] == {"type": "AuthorizationError"}

        # An agent the server never registered is refused before any tool runs.
        outsider = _call(url_b, OUTSIDER, "memory.health", {}, key=OUTSIDER_KEY)
        assert outsider.status_code == 401

        # The same key replayed through the other process resolves to the original.
        replay = _payload(
            url_b,
            WRITER,
            "memory.write_agent",
            {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": key},
        )
        assert (replay["status"], replay["record_id"]) == ("duplicate", record_id)

        _no_sqlite_ledger(dir_a)
        _no_sqlite_ledger(dir_b)

    # Every process has stopped. A new one on the same store still has the
    # record, and the idempotency key still binds to it.
    with server(tmp_path, schema) as (url_c, dir_c):
        again = _payload(url_c, READER, "memory.get", {"record_id": record_id})
        assert again["record"]["content"] == content
        replay = _payload(
            url_c,
            WRITER,
            "memory.write_agent",
            {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": key},
        )
        assert (replay["status"], replay["record_id"]) == ("duplicate", record_id)
        _no_sqlite_ledger(dir_c)


def test_a_foreign_tenant_process_on_the_same_store_cannot_read_the_record(
    tmp_path: Path, schema: str
) -> None:
    """Tenant is a deployment coordinate: same store, same agents, no crossing."""

    with (
        server(tmp_path, schema) as (url_a, _),
        server(tmp_path, schema, tenant="tenant-b") as (url_b, _),
    ):
        written = _payload(
            url_a,
            WRITER,
            "memory.write_agent",
            {"namespace": HOME_NAMESPACE, "content": "an osprey over the l9 reservoir"},
        )
        assert written["status"] == "admitted"
        error = _error(url_b, READER, "memory.get", {"record_id": written["record_id"]})
        assert error["code"] == -32010
        found = _payload(
            url_b, READER, "memory.search", {"query": "osprey", "namespaces": [HOME_NAMESPACE]}
        )
        assert found["hits"] == []


def test_two_processes_cold_starting_on_one_empty_schema_both_serve(
    tmp_path: Path, schema: str
) -> None:
    first = _launch(tmp_path, schema)
    second = _launch(tmp_path, schema)
    try:
        for _, url, workdir, log in (first, second):
            try:
                wait_for(url)
            except RuntimeError:
                log.flush()
                raise RuntimeError((workdir / "server.log").read_text()) from None
        written = _payload(
            first[1],
            WRITER,
            "memory.write_agent",
            {"namespace": HOME_NAMESPACE, "content": "both cold starts came up"},
        )
        got = _payload(second[1], READER, "memory.get", {"record_id": written["record_id"]})
        assert got["found"] is True
    finally:
        _stop(first[0], first[3])
        _stop(second[0], second[3])


@pytest.mark.parametrize("dsn", ["host=127.0.0.1 port=1 dbname=absent connect_timeout=2", " "])
def test_an_unusable_postgres_dsn_stops_the_server_without_a_local_fallback(
    tmp_path: Path, schema: str, dsn: str
) -> None:
    process, _, workdir, log = _launch(tmp_path, schema, dsn=dsn)
    try:
        assert process.wait(timeout=30) != 0
    finally:
        _stop(process, log)
    _no_sqlite_ledger(workdir)
