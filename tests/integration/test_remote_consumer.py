"""The Memory-owned remote consumer against a real signed-agent server (ADR-082, amendment 2026-10-16).

A real uvicorn server on loopback TCP, in ``signed-agent`` mode, serves one
``MemoryService``. The consumer side is the shipped ``l9-memory`` CLI with
``L9_MEMORY_REMOTE_URL`` set, and :class:`RemoteMemoryClient` directly. Every
case reads the receipt and the exit code a consumer reads, never the server's
internals.

Proven here:
- every ADR-082 lifecycle operation and both agent write doors reach the
  hosted service and return the local receipt shapes and exit codes;
- identity is the verified agent's, per request: cross-agent visibility,
  server-side refusals, and the human door unreachable;
- credential expiry is refused locally, a tampered or over-ceiling
  credential is refused by the server, and a refreshing provider recovers;
- distillation and every other non-lifecycle command are refused before any
  request is sent, and an unreachable server is a typed failure: nothing
  falls back to a local store.
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

from l9_graphite_memory import cli
from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz.signed_assertion import mint_assertion
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    CloseRequest,
    HydrationRequest,
    MemorySearchRequest,
    PhaseLockRequest,
)
from l9_graphite_memory.remote_client import (
    AGENT_ASSERTION_ENV,
    IDENTITY_ASSERTION_HMAC_ENV,
    IDENTITY_ASSERTION_JSON_ENV,
    REMOTE_URL_ENV,
    AgentCredentials,
    RemoteFailureKind,
    RemoteMemoryClient,
    RemoteMemoryError,
)
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.server import create_http_app
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import (
    CONTROL_PLANE_CONTRACT_VERSION,
    REMOTE_MCP_CONTRACT_VERSION,
)
from tests.integration.remote_mcp_harness import (
    AGENT_KEYS,
    ALLOWED_ORIGIN,
    FOREIGN_NAMESPACE,
    HOME_NAMESPACE,
    OUTSIDER,
    OUTSIDER_KEY,
    READER,
    WRITER,
    free_port,
    identity_body,
    seal,
    serve,
    server_environment,
)

pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "control_plane"


def agent_credentials(
    agent_id: str, *, key: str | None = None, ttl_seconds: int = 900
) -> AgentCredentials:
    """What a consumer holds: a minted assertion and sealed evidence, no key."""

    signing_key = key if key is not None else AGENT_KEYS[agent_id]
    sealed, mac = seal(identity_body(agent_id), signing_key)
    return AgentCredentials(
        agent_assertion=mint_assertion(agent_id, signing_key, ttl_seconds=ttl_seconds),
        identity_assertion=sealed,
        identity_assertion_hmac=mac,
    )


def agent_env(agent_id: str, **kwargs: Any) -> dict[str, str]:
    credentials = agent_credentials(agent_id, **kwargs)
    return {
        AGENT_ASSERTION_ENV: credentials.agent_assertion,
        IDENTITY_ASSERTION_JSON_ENV: json.dumps(dict(credentials.identity_assertion)),
        IDENTITY_ASSERTION_HMAC_ENV: credentials.identity_assertion_hmac,
    }


@pytest.fixture
def client_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Local directories a fallback would write into, watched by every test."""

    home = tmp_path / "client"
    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(home / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(home / "state"))
    monkeypatch.delenv("L9_MEMORY_DATABASE_PATH", raising=False)
    monkeypatch.delenv("L9_MEMORY_STORE_BACKEND", raising=False)
    monkeypatch.delenv("L9_MEMORY_NAMESPACE", raising=False)
    monkeypatch.delenv(REMOTE_URL_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    return home


def no_local_ledger(home: Path) -> None:
    ledgers = [p for p in home.rglob("*") if p.suffix in {".sqlite3", ".sqlite", ".db"}]
    assert ledgers == [], f"the remote consumer opened a local store: {ledgers}"


@pytest.fixture
def server_url(monkeypatch: pytest.MonkeyPatch, client_home: Path) -> Iterator[str]:
    for name, value in server_environment().items():
        monkeypatch.setenv(name, value)
    # Held by this process, and still never a remote principal (ADR-098).
    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "local-human-door-secret")
    for name in ("L9_MEMORY_AGENTS_DOOR_SECRET", AGENT_ASSERTION_ENV):
        monkeypatch.delenv(name, raising=False)
    settings = MemorySettings(
        http_auth_required=True,
        http_auth_mode="signed-agent",
        http_allowed_origins=(ALLOWED_ORIGIN,),
        local_tenant_id="l9",
        local_organization_id="quantum-l9",
        local_workspace_id="l9-workspace",
    )
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    runtime = MemoryRuntime(settings=settings, service=service)
    try:
        with serve(create_http_app(runtime)) as url:
            yield url
    finally:
        runtime.close()


def run_cli(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    agent: str | None,
    argv: list[str],
    *,
    stdin: str | None = None,
    **credential_kwargs: Any,
) -> tuple[int, Any, Any]:
    """Run ``l9-memory`` as a consumer would; return (exit, stdout JSON, stderr JSON)."""

    monkeypatch.setenv(REMOTE_URL_ENV, url)
    for name in (AGENT_ASSERTION_ENV, IDENTITY_ASSERTION_JSON_ENV, IDENTITY_ASSERTION_HMAC_ENV):
        monkeypatch.delenv(name, raising=False)
    if agent is not None:
        for name, value in agent_env(agent, **credential_kwargs).items():
            monkeypatch.setenv(name, value)
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", _Stdin(stdin))
    code = cli.main(argv)
    captured = capsys.readouterr()
    out = json.loads(captured.out) if captured.out.strip() else None
    err = json.loads(captured.err) if captured.err.strip() else None
    return code, out, err


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def closed_port_url() -> str:
    return f"http://127.0.0.1:{free_port()}"


# ---------------------------------------------------------------------------
# Lifecycle parity over HTTP
# ---------------------------------------------------------------------------


def test_capabilities_bind_the_server_contract(capsys, monkeypatch, server_url) -> None:
    code, receipt, _ = run_cli(capsys, monkeypatch, server_url, WRITER, ["capabilities"])
    assert code == 0
    assert receipt["contract_version"] == CONTROL_PLANE_CONTRACT_VERSION
    assert receipt["remote_mcp_contract_version"] == REMOTE_MCP_CONTRACT_VERSION
    mcp = next(t for t in receipt["transports"] if t["transport"] == "mcp")
    assert mcp["operations"]["close"] == "memory.close"


def test_every_lifecycle_command_reaches_the_hosted_service(
    capsys, monkeypatch, server_url, client_home
) -> None:
    def run(argv: list[str], agent: str = WRITER, **kw: Any) -> tuple[int, Any, Any]:
        return run_cli(capsys, monkeypatch, server_url, agent, argv, **kw)

    code, health, _ = run(["health"])
    assert code == (0 if health["status"] == "complete" else 1)
    assert health["contract_version"] == CONTROL_PLANE_CONTRACT_VERSION

    # ingest (the CLI's write) — provenance is the verified agent's.
    code, written, _ = run(
        ["write", "the remote ledger records a kingfisher", "--group-id", HOME_NAMESPACE]
        + ["--kind", "observation", "--tag", "remote-proof", "--idempotency-key", "rk-1"]
    )
    assert code == 0, written
    assert written["status"] == "admitted"
    record_id = written["record_id"]

    code, dry, _ = run(
        ["write", "a dry run commits nothing", "--group-id", HOME_NAMESPACE, "--dry-run"]
    )
    assert code == 0
    assert dry["status"] == "admitted"

    code, found, _ = run(["search", "kingfisher", "--group-id", HOME_NAMESPACE])
    assert code == 0
    assert [hit["record"]["record_id"] for hit in found["hits"]] == [record_id]
    assert found["hits"][0]["record"]["provenance"]["source_agent_id"] == WRITER

    code, hydrated, _ = run(
        ["hydrate", "what does the ledger record", "--group-id", HOME_NAMESPACE]
    )
    assert code == 0
    assert any(record_id in section["record_ids"] for section in hydrated["sections"])

    code, record, _ = run(["get", record_id, "--group-id", HOME_NAMESPACE])
    assert code == 0
    assert record["content"] == "the remote ledger records a kingfisher"
    code, missing, _ = run(["get", str(uuid.uuid4()), "--group-id", HOME_NAMESPACE])
    assert code == 2
    assert missing["found"] is False
    # The dry run passed admission and committed nothing.
    code, uncommitted, _ = run(["get", dry["record_id"], "--group-id", HOME_NAMESPACE])
    assert code == 2
    assert uncommitted["found"] is False

    code, conflicts, _ = run(["conflicts", "--group-id", HOME_NAMESPACE])
    assert code == 0
    assert conflicts["conflicts"] == []

    signature = "remote-proof-signature-0001"
    code, lock, _ = run(
        ["phase-lock", "remote proof", "--group-id", HOME_NAMESPACE, "--task-signature", signature]
    )
    assert code == 0
    assert lock["granted"] is True
    assert Path(lock["state_file"]).is_relative_to(client_home / "state")
    code, verified, _ = run(["verify-phase-lock", signature, "--group-id", HOME_NAMESPACE])
    assert code == 0
    assert verified["valid"] is True

    candidate = (FIXTURE / "continuation_candidate.json").read_text(encoding="utf-8")
    code, admitted, _ = run(["ingest-governed-candidate"], stdin=candidate)
    assert code == 0, admitted
    assert admitted["storage_committed"] is True
    code, replayed_candidate, _ = run(["ingest-governed-candidate"], stdin=candidate)
    assert code == 0
    assert replayed_candidate["record_id"] == admitted["record_id"]

    close_args = ["close", "--summary", "remote session closed", "--group-id", HOME_NAMESPACE]
    close_args += ["--session-id", "remote-42", "--idempotency-key", "close-remote-42"]
    code, closed, _ = run(close_args)
    assert code == 0
    assert closed["status"] == "complete"
    assert closed["record_id"]
    code, replay, _ = run(close_args)
    assert code == 0
    assert replay["replayed"] is True
    assert replay["record_id"] == closed["record_id"]
    assert replay["replay_payload_matched"] is True
    code, dry_close, _ = run(
        ["close", "--summary", "dry", "--group-id", HOME_NAMESPACE, "--dry-run"]
    )
    assert code == 3
    assert dry_close["status"] == "partial"

    no_local_ledger(client_home)


def test_agent_write_doors_and_typed_receipts(server_url) -> None:
    client = RemoteMemoryClient(server_url, agent_credentials(WRITER))
    capabilities = client.connect()
    assert client.protocol_version in capabilities.http_mcp_protocol_versions

    agent = client.write_agent(
        {
            "namespace": HOME_NAMESPACE,
            "content": "agent lane remote write",
            "memory_class": "insight",
        }
    )
    assert agent.status.value == "admitted"

    signature = "governed-remote-signature"
    lock = client.phase_lock(PhaseLockRequest(namespace=HOME_NAMESPACE, task_signature=signature))
    assert lock.granted
    governed = client.write_governed(
        {
            "namespace": HOME_NAMESPACE,
            "content": "governed remote write",
            "task_signature": signature,
        }
    )
    assert governed.status.value == "admitted"
    assert client.verify_phase_lock(HOME_NAMESPACE, signature).valid is False  # namespace moved

    hits = client.search(MemorySearchRequest(query="remote write", namespaces=(HOME_NAMESPACE,)))
    assert {hit.record.record_id for hit in hits.hits} == {agent.record_id, governed.record_id}
    record = client.get(agent.record_id)  # type: ignore[arg-type]
    assert record is not None
    assert record.provenance.source_agent_id == WRITER
    bundle = client.hydrate(HydrationRequest(task="remote write", namespaces=(HOME_NAMESPACE,)))
    assert bundle.sections
    closed = client.close(CloseRequest(namespace=HOME_NAMESPACE, summary="typed close"))
    assert closed.status.value == "complete"
    assert closed.record_id is not None


# ---------------------------------------------------------------------------
# Identity, authorization and cross-agent visibility
# ---------------------------------------------------------------------------


def test_another_agent_sees_the_record_but_keeps_its_own_grant(
    capsys, monkeypatch, server_url
) -> None:
    code, written, _ = run_cli(
        capsys,
        monkeypatch,
        server_url,
        WRITER,
        ["write", "a heron on the south weir", "--group-id", HOME_NAMESPACE],
    )
    assert code == 0

    code, record, _ = run_cli(
        capsys, monkeypatch, server_url, READER, ["get", written["record_id"]]
    )
    assert code == 0
    assert record["provenance"]["source_agent_id"] == WRITER

    # The reader's own write is a rejected receipt, as on stdio: exit 2.
    code, refused, _ = run_cli(
        capsys,
        monkeypatch,
        server_url,
        READER,
        ["write", "the reader writes", "--group-id", HOME_NAMESPACE],
    )
    assert code == 2
    assert refused["status"] == "rejected"
    assert refused["record_id"] is None

    # An ungranted read is an AuthorizationError, the type a local run raises.
    code, out, err = run_cli(
        capsys,
        monkeypatch,
        server_url,
        WRITER,
        ["search", "heron", "--group-id", FOREIGN_NAMESPACE],
    )
    assert code == 1
    assert out is None
    assert err["error"] == "AuthorizationError"
    assert err["remote"]["failure_kind"] == "authorization"


def test_unregistered_and_tampered_credentials_are_refused_by_the_server(
    capsys, monkeypatch, server_url
) -> None:
    code, _, err = run_cli(capsys, monkeypatch, server_url, OUTSIDER, ["health"], key=OUTSIDER_KEY)
    assert code == 1
    assert err["error"] == "AuthenticationError"
    assert err["remote"] == {
        "failure_kind": "authentication",
        "http_status": 401,
        "rpc_code": None,
        "remote_type": None,
    }
    secret = AGENT_KEYS[WRITER]
    assert secret not in json.dumps(err)

    code, _, err = run_cli(
        capsys, monkeypatch, server_url, WRITER, ["health"], key="not-the-writer-key-000000000000"
    )
    assert code == 1
    assert err["remote"]["http_status"] == 401


def test_a_credential_beyond_the_lifetime_ceiling_is_refused(server_url) -> None:
    client = RemoteMemoryClient(server_url, agent_credentials(WRITER, ttl_seconds=86_400))
    with pytest.raises(RemoteMemoryError) as caught:
        client.health()
    assert caught.value.kind is RemoteFailureKind.AUTHENTICATION
    assert "ceiling" in str(caught.value)


def test_expired_credential_is_refused_before_any_request(capsys, monkeypatch, client_home) -> None:
    # The URL is a closed port: had a request been sent, the failure would be
    # "unreachable". The expiry refusal is decided locally first.
    code, _, err = run_cli(
        capsys, monkeypatch, closed_port_url(), WRITER, ["health"], ttl_seconds=2
    )
    assert code == 1
    assert err["error"] == "AuthenticationError"
    assert err["remote"]["failure_kind"] == "credential_expired"
    no_local_ledger(client_home)


def test_credential_provider_is_consulted_per_request_and_recovers_from_401(server_url) -> None:
    issued: list[AgentCredentials] = []

    def provider() -> AgentCredentials:
        # The first credential was signed with a key the server never held;
        # every later call mints a fresh, short-lived one.
        key = "stale-key-that-the-server-never-held-0" if not issued else None
        issued.append(agent_credentials(WRITER, key=key, ttl_seconds=60))
        return issued[-1]

    client = RemoteMemoryClient(server_url, provider)
    assert client.health().contract_version == CONTROL_PLANE_CONTRACT_VERSION
    # initialize (refused, then retried with a re-minted credential), the
    # initialized notification, capabilities and health: one mint each.
    assert len(issued) == 5
    assert len({credential.agent_assertion for credential in issued}) == 5


def test_missing_identity_is_a_configuration_failure(capsys, monkeypatch, server_url) -> None:
    code, _, err = run_cli(capsys, monkeypatch, server_url, None, ["health"])
    assert code == 1
    assert err["error"] == "ConfigurationError"
    assert AGENT_ASSERTION_ENV in err["message"]


# ---------------------------------------------------------------------------
# No fallback, blocked operations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["distill", "notes.md", "--group-id", HOME_NAMESPACE],
        ["bootstrap", "--group-id", HOME_NAMESPACE],
        ["stats"],
        ["import", "notes.md"],
        ["promote", str(uuid.uuid4()), "semantic", "operator review"],
        ["client", "cursor", "status"],
    ],
)
def test_non_lifecycle_commands_are_refused_without_a_request(
    capsys, monkeypatch, client_home, argv
) -> None:
    (Path.cwd() / "notes.md").write_text("a local excerpt", encoding="utf-8")
    code, out, err = run_cli(capsys, monkeypatch, closed_port_url(), WRITER, argv)
    assert code == 1
    assert out is None
    assert err["error"] == "RemoteOperationUnsupported"
    assert err["remote"]["failure_kind"] == "unsupported_remotely"
    if argv[0] == "distill":
        assert "administrator" in err["message"]
    no_local_ledger(client_home)


def test_an_unreachable_server_is_a_typed_failure_not_a_local_answer(
    capsys, monkeypatch, client_home
) -> None:
    for argv in (
        ["health"],
        ["search", "anything", "--group-id", HOME_NAMESPACE],
        ["close", "--summary", "s", "--group-id", HOME_NAMESPACE],
    ):
        code, out, err = run_cli(capsys, monkeypatch, closed_port_url(), WRITER, argv)
        assert code == 1
        assert out is None
        assert err["error"] == "ConnectionError"
        assert err["remote"]["failure_kind"] == "unreachable"
    no_local_ledger(client_home)


def test_plain_http_to_a_remote_host_is_refused(capsys, monkeypatch, client_home) -> None:
    code, _, err = run_cli(capsys, monkeypatch, "http://memory.example.invalid", WRITER, ["health"])
    assert code == 1
    assert err["error"] == "ConfigurationError"
    assert "https" in err["message"]


def test_search_token_budget_is_refused_not_dropped(capsys, monkeypatch, server_url) -> None:
    code, _, err = run_cli(
        capsys,
        monkeypatch,
        server_url,
        WRITER,
        ["search", "x", "--group-id", HOME_NAMESPACE, "--token-budget", "256"],
    )
    assert code == 1
    assert err["remote"]["failure_kind"] == "invalid_request"


class _Redirector(http.server.BaseHTTPRequestHandler):
    hits: ClassVar[list[str]] = []

    def do_POST(self) -> None:
        type(self).hits.append(self.path)
        self.send_response(307)
        self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/elsewhere")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        return None


def test_a_redirect_is_refused_and_credentials_go_nowhere_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_Redirector, "hits", [])
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Redirector)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}"
        client = RemoteMemoryClient(url, agent_credentials(WRITER))
        with pytest.raises(RemoteMemoryError) as caught:
            client.health()
        assert caught.value.kind is RemoteFailureKind.PROTOCOL
        assert caught.value.http_status == 307
        assert _Redirector.hits == ["/mcp"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_a_server_that_stalls_is_a_timeout() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        client = RemoteMemoryClient(url, agent_credentials(WRITER), timeout_seconds=0.5)
        started = time.monotonic()
        with pytest.raises(RemoteMemoryError) as caught:
            client.health()
        assert caught.value.kind is RemoteFailureKind.TIMEOUT
        assert caught.value.error_type == "TimeoutError"
        assert time.monotonic() - started < 10
    finally:
        listener.close()


def test_credentials_are_read_after_secrets_are_loaded(capsys, monkeypatch, client_home) -> None:
    """Credentials delivered by the secret loader (e.g. Infisical) must be seen."""

    loaded = agent_env(WRITER)

    def load_secrets_sync() -> None:
        for name, value in loaded.items():
            monkeypatch.setenv(name, value)

    monkeypatch.setattr(cli, "load_secrets_sync", load_secrets_sync)
    # No credentials in the environment until the loader runs; the server is
    # a closed port, so reading them in time turns "configuration" into
    # "unreachable".
    code, _, err = run_cli(capsys, monkeypatch, closed_port_url(), None, ["health"])
    assert code == 1
    assert err["remote"]["failure_kind"] == "unreachable", err
