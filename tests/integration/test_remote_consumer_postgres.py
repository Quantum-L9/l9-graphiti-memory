"""The remote consumer across processes on one PostgreSQL store (ADR-082, amendment 2026-10-16).

Every actor is its own operating-system process: two (or three) signed-agent
server processes on one fresh PostgreSQL schema, and each consumer call a
separate ``python -m l9_graphite_memory`` process with ``L9_MEMORY_REMOTE_URL``
set, exactly as a hook would invoke ``l9-memory``. Nothing is shared in memory.

Proven here:
- a governed candidate admitted by one agent through one server is hydrated
  by another agent through another server;
- a close replayed through a different server process collapses onto the
  first close record (idempotency is canonical, not per process);
- a phase lock granted through one process verifies through another;
- grants hold across processes (read-only agent, foreign namespace);
- records survive every server process stopping;
- the consumer never opens a local ledger, and a stopped server is a typed
  failure rather than a local answer.

Runs from the source tree and from the installed wheel alone. Skips visibly
without ``L9_MEMORY_TEST_POSTGRES_DSN``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.authz.signed_assertion import mint_assertion
from tests.integration import test_remote_mcp_postgres_multiprocess as _shared
from tests.integration.remote_mcp_harness import (
    AGENT_KEYS,
    FOREIGN_NAMESPACE,
    HOME_NAMESPACE,
    READER,
    WRITER,
    identity_body,
    seal,
)

# The shared-store fixtures and server launcher of the ADR-098 PostgreSQL
# proof, reused so both proofs start servers identically.
import_root = _shared.import_root
schema = _shared.schema
server = _shared.server

pytest.importorskip("psycopg2", reason="the shared store requires the [postgres] extra")

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "control_plane"


def _agent_env(agent_id: str) -> dict[str, str]:
    key = AGENT_KEYS[agent_id]
    sealed, mac = seal(identity_body(agent_id), key)
    return {
        "L9_MEMORY_AGENT_ASSERTION": mint_assertion(agent_id, key, ttl_seconds=900),
        "L9_MEMORY_IDENTITY_ASSERTION_JSON": json.dumps(sealed),
        "L9_MEMORY_IDENTITY_ASSERTION_HMAC": mac,
    }


class Consumer:
    """``l9-memory`` invoked as a fresh process per call, as a hook does."""

    def __init__(self, tmp_path: Path, root: Path) -> None:
        self.home = tmp_path / "consumer"
        self.home.mkdir()
        self.root = root

    def __call__(
        self, url: str, agent: str, argv: list[str], *, stdin: str | None = None
    ) -> tuple[int, Any, Any]:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("L9_MEMORY_", "GRAPHITI_", "ZEP_")) and key != "PYTHONPATH"
        }
        env.update(_agent_env(agent))
        env.update(
            {
                "PYTHONPATH": str(self.root),
                "HOME": str(self.home / "home"),
                "L9_MEMORY_DATA_DIR": str(self.home / "data"),
                "L9_MEMORY_STATE_DIR": str(self.home / "state"),
                "L9_MEMORY_JSON_LOGS": "0",
                "L9_MEMORY_REMOTE_URL": url,
            }
        )
        completed = subprocess.run(
            [sys.executable, "-m", "l9_graphite_memory", *argv],
            cwd=self.home,
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        out = json.loads(completed.stdout) if completed.stdout.strip() else None
        err = json.loads(completed.stderr) if completed.stderr.strip() else None
        return completed.returncode, out, err

    def assert_no_local_ledger(self) -> None:
        ledgers = [p for p in self.home.rglob("*") if p.suffix in {".sqlite3", ".sqlite", ".db"}]
        assert ledgers == [], f"the remote consumer opened a local store: {ledgers}"


def test_lifecycle_spans_server_processes_on_one_postgres_store(
    tmp_path: Path, schema: str, import_root: Path
) -> None:
    consumer = Consumer(tmp_path, import_root)
    candidate = (FIXTURE / "continuation_candidate.json").read_text(encoding="utf-8")
    close_key = f"close-{uuid.uuid4().hex}"
    signature = f"mp-{uuid.uuid4().hex[:24]}"
    with (
        server(tmp_path, schema, root=import_root) as (url_a, dir_a),
        server(tmp_path, schema, root=import_root) as (url_b, dir_b),
    ):
        code, health, _ = consumer(url_a, WRITER, ["health"])
        assert code == 0, health
        assert health["store"]["name"] == "postgres"

        # Governed candidate admission through A, hydration by another agent through B.
        code, admitted, err = consumer(
            url_a, WRITER, ["ingest-governed-candidate"], stdin=candidate
        )
        assert code == 0, err
        assert admitted["storage_committed"] is True
        code, bundle, err = consumer(
            url_b,
            READER,
            ["hydrate", "realign memory control plane", "--group-id", HOME_NAMESPACE],
        )
        assert code == 0, err
        hydrated = {rid for section in bundle["sections"] for rid in section["record_ids"]}
        assert admitted["record_id"] in hydrated

        # Close through A, replay through B: one close record.
        close = ["close", "--summary", "multi-process session", "--group-id", HOME_NAMESPACE]
        close += ["--session-id", "mp-1", "--idempotency-key", close_key]
        code, first, err = consumer(url_a, WRITER, close)
        assert code == 0, err
        code, replay, err = consumer(url_b, WRITER, close)
        assert code == 0, err
        assert replay["replayed"] is True
        assert replay["record_id"] == first["record_id"]
        assert replay["replay_payload_matched"] is True

        # A phase lock granted through A verifies through B.
        code, lock, err = consumer(
            url_a,
            WRITER,
            ["phase-lock", "mp", "--group-id", HOME_NAMESPACE, "--task-signature", signature],
        )
        assert code == 0 and lock["granted"] is True, err
        code, verified, err = consumer(
            url_b, WRITER, ["verify-phase-lock", signature, "--group-id", HOME_NAMESPACE]
        )
        assert code == 0 and verified["valid"] is True, err

        # Grants are the server's, whichever process answers.
        code, refused, _ = consumer(
            url_b, READER, ["write", "the reader writes", "--group-id", HOME_NAMESPACE]
        )
        assert code == 2 and refused["status"] == "rejected"
        code, _, err = consumer(url_a, WRITER, ["search", "x", "--group-id", FOREIGN_NAMESPACE])
        assert code == 1 and err["error"] == "AuthorizationError"

        for workdir in (dir_a, dir_b):
            ledgers = [p for p in workdir.rglob("*") if p.suffix in {".sqlite3", ".sqlite", ".db"}]
            assert ledgers == []
    consumer.assert_no_local_ledger()


def test_records_outlive_server_processes_and_a_stopped_server_is_not_answered_locally(
    tmp_path: Path, schema: str, import_root: Path
) -> None:
    consumer = Consumer(tmp_path, import_root)
    content = f"durable remote record {uuid.uuid4().hex}"
    with server(tmp_path, schema, root=import_root) as (url_a, _):
        code, written, err = consumer(
            url_a, WRITER, ["write", content, "--group-id", HOME_NAMESPACE, "--kind", "decision"]
        )
        assert code == 0, err
    stopped_url = url_a

    with server(tmp_path, schema, root=import_root) as (url_c, _):
        code, record, err = consumer(url_c, READER, ["get", written["record_id"]])
        assert code == 0, err
        assert record["content"] == content
        assert record["provenance"]["source_agent_id"] == WRITER

    for argv in (["health"], ["get", written["record_id"]]):
        code, out, err = consumer(stopped_url, READER, argv)
        assert code == 1 and out is None
        assert err["error"] == "ConnectionError"
        assert err["remote"]["failure_kind"] == "unreachable"
    consumer.assert_no_local_ledger()
