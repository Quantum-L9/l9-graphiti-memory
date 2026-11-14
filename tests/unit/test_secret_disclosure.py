# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_secret_disclosure.py
#   layer: tests
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-11-14

"""U-011: nothing public, logged or printed at startup discloses a secret.

The unauthenticated probes (/healthz, /readyz) publish no record count, no
exception text and no store coordinate; connection errors and DSNs pass
through one redaction path; a startup failure names the variable and the class
of failure, never the value; and settings never print a secret-shaped field.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.adapters.in_memory_store import InMemoryRecordStore
from l9_graphite_memory.adapters.null_projection import NullProjection
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import StoreConnectionError
from l9_graphite_memory.redaction import (
    STORE_UNAVAILABLE,
    dsn_components,
    redact_connection_error,
    redact_dsn,
)
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.services.memory_service import MemoryService

# A host that cannot resolve (RFC 6761 .invalid), so a real driver fails fast
# without a server and without touching the network beyond the resolver.
HOST = "l9-u011-nowhere.invalid"
USER = "memsvc_u011"
DB = "memdb_u011"

# Each case: (DSN, the substrings that must never surface). Passwords carry
# spaces, quotes, ``@`` and ``:``; one DSN is a URI, two are broken.
HOSTILE_DSNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "keyword, quoted password with space quote @ :": (
        (
            f"host={HOST} port=6543 user={USER} password='Pw s@:x \\'q' dbname={DB} "
            "connect_timeout=1"
        ),
        ("Pw s@:x", "s@:x 'q", HOST, USER, DB),
    ),
    "keyword, bare password": (
        f"host={HOST} user={USER} password=Hunter2Bare dbname={DB} connect_timeout=1",
        ("Hunter2Bare", HOST, USER, DB),
    ),
    "uri, password with : and encoded @, query secret": (
        (
            f"postgresql://{USER}:S3cr%40t:Uri@{HOST}:6543/{DB}"
            "?connect_timeout=1&sslpassword=QuerySecret9"
        ),
        ("S3cr%40t:Uri", "S3cr@t:Uri", "QuerySecret9", HOST, USER, DB),
    ),
    "uri, broken (unterminated IPv6 host)": (
        f"postgresql://{USER}:BrokenUriPw@[{HOST}",
        ("BrokenUriPw", HOST, USER),
    ),
    "keyword, broken (missing '=')": (
        f"host={HOST} user={USER} password=BrokenKwPw dbname {DB}",
        ("BrokenKwPw", HOST, USER),
    ),
}


def _assert_clean(text: str, secrets: tuple[str, ...], where: str) -> None:
    for secret in secrets:
        assert secret not in text, f"{secret!r} disclosed in {where}: {text[:600]}"


# -- the redaction helper ----------------------------------------------------


@pytest.mark.parametrize("case", HOSTILE_DSNS, ids=HOSTILE_DSNS.keys())
def test_redact_dsn_removes_every_identifying_component(case: str) -> None:
    dsn, secrets = HOSTILE_DSNS[case]
    _assert_clean(redact_dsn(dsn), secrets, "redact_dsn")


@pytest.mark.parametrize("case", HOSTILE_DSNS, ids=HOSTILE_DSNS.keys())
def test_driver_style_messages_are_scrubbed_with_and_without_the_dsn(case: str) -> None:
    dsn, secrets = HOSTILE_DSNS[case]
    messages = [
        f'invalid dsn: unterminated quoted string in URI: "{dsn}"',
        f'could not translate host name "{HOST}" to address',
        (
            f'connection to server at "{HOST}" (10.0.0.5), port 6543 failed: '
            f'FATAL:  password authentication failed for user "{USER}"'
        ),
    ]
    for message in messages:
        _assert_clean(redact_connection_error(message, dsn), secrets, "redacted message")
    # Without the DSN, the generic layer still strips labelled credentials.
    generic = redact_connection_error(f"failed for {dsn}")
    for marker in ("Hunter2Bare", "QuerySecret9", "S3cr%40t:Uri", "BrokenUriPw", "BrokenKwPw"):
        assert marker not in generic


def test_short_or_unrelated_text_is_left_alone() -> None:
    assert redact_connection_error("store is healthy", "host=db user=x") == "store is healthy"
    assert dsn_components("host=db user=x") == ()


# -- the real driver path -----------------------------------------------------


def _postgres_store(dsn: str) -> Any:
    pytest.importorskip("psycopg2", reason="the postgres adapter needs the [postgres] extra")
    from l9_graphite_memory.adapters.postgres_store import PostgresRecordStore

    return PostgresRecordStore(dsn)


@pytest.mark.parametrize("case", HOSTILE_DSNS, ids=HOSTILE_DSNS.keys())
def test_a_failed_connection_raises_no_secret_and_chains_no_driver_text(case: str) -> None:
    dsn, secrets = HOSTILE_DSNS[case]
    store = _postgres_store(dsn)
    with pytest.raises(StoreConnectionError) as raised:
        store.initialize()
    error = raised.value
    _assert_clean(str(error), secrets, "the raised message")
    assert error.__cause__ is None and error.__suppress_context__ is True
    assert error.driver_error in {"OperationalError", "ProgrammingError"}


@pytest.mark.parametrize("case", HOSTILE_DSNS, ids=HOSTILE_DSNS.keys())
def test_store_health_carries_a_reason_code_and_logs_redacted(
    case: str, caplog: pytest.LogCaptureFixture
) -> None:
    dsn, secrets = HOSTILE_DSNS[case]
    store = _postgres_store(dsn)
    with caplog.at_level(logging.DEBUG):
        health = store.health()
    assert health == {"name": "postgres", "healthy": False, "reason": STORE_UNAVAILABLE}
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "health probe failed" in logged
    _assert_clean(logged, secrets, "the captured log")


# -- the public probe bodies --------------------------------------------------


class _LeakyStore(InMemoryRecordStore):
    """A store whose health dictionary carries everything a public body must not."""

    def __init__(self, *, healthy: bool) -> None:
        super().__init__()
        self._healthy = healthy

    def health(self) -> dict[str, Any]:
        return {
            "name": "postgres",
            "healthy": self._healthy and self.initialized,
            "records": 4242,
            "path": "/var/lib/secret-path",
            "error": f"postgresql://{USER}:LeakPw@{HOST}:6543/{DB}",
            "reason": "Not A Code: password=LeakPw",
        }


def _client(*, healthy: bool) -> Any:
    from fastapi.testclient import TestClient

    from l9_graphite_memory.server import create_http_app

    service = MemoryService(_LeakyStore(healthy=healthy), NullProjection())
    service.initialize()
    runtime = MemoryRuntime(settings=MemorySettings(http_auth_required=False), service=service)
    return TestClient(create_http_app(runtime))


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


FORBIDDEN_KEYS = {"records", "error", "path", "outbox_backlog", "tool_count", "tools"}
LEAKS = ("LeakPw", HOST, USER, DB, "4242", "secret-path", "Not A Code")


@pytest.mark.parametrize("healthy", [True, False], ids=["healthy", "store-down"])
@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_unauthenticated_probes_publish_no_count_text_or_coordinate(
    path: str, healthy: bool
) -> None:
    response = _client(healthy=healthy).get(path)
    assert response.status_code == (200 if healthy else 503)
    body = response.json()
    assert not (_keys(body) & FORBIDDEN_KEYS), _keys(body) & FORBIDDEN_KEYS
    _assert_clean(response.text, LEAKS, f"{path} body")
    # The fields existing consumers read survive (RUNBOOK section C step 6,
    # the carrier proof, the multiprocess and live readiness tests).
    assert body["status"] == ("complete" if healthy else "failed")
    assert body["package_version"]
    assert body["store"] == {"name": "postgres", "healthy": healthy}
    if path == "/readyz":
        families = {family["name"]: family for family in body["readiness"]["families"]}
        assert families["canonical"]["healthy"] is healthy
        assert families["canonical"]["detail"] == {"shared_store": False}
        assert body["readiness"]["ready"] is healthy
        assert set(body["active_memory"]) == {"store", "bus"}


def test_the_authenticated_health_tool_keeps_the_full_report() -> None:
    """The detail is not thrown away: memory.health (behind /mcp auth) has it."""

    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    assert "records" in service.health().store


# -- startup ------------------------------------------------------------------


@pytest.mark.parametrize("case", HOSTILE_DSNS, ids=HOSTILE_DSNS.keys())
def test_a_server_that_cannot_open_its_store_names_the_variable_not_the_value(
    case: str, tmp_path: Path
) -> None:
    pytest.importorskip("psycopg2", reason="the postgres adapter needs the [postgres] extra")
    dsn, secrets = HOSTILE_DSNS[case]
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("L9_MEMORY_")
    }
    environment.update(
        {
            "L9_MEMORY_STORE_BACKEND": "postgres",
            "L9_MEMORY_POSTGRES_DSN": dsn,
            "L9_MEMORY_DATA_DIR": str(tmp_path / "data"),
            "L9_MEMORY_STATE_DIR": str(tmp_path / "state"),
            "L9_MEMORY_JSON_LOGS": "1",
            "L9_MEMORY_LOG_LEVEL": "DEBUG",
            "HOME": str(tmp_path),
        }
    )
    for name in ("INFISICAL_CLIENT_ID", "INFISICAL_CLIENT_SECRET", "INFISICAL_PROJECT_ID"):
        environment.pop(name, None)
    started = subprocess.run(
        [sys.executable, "-m", "l9_graphite_memory.server", "--transport", "http", "--port", "0"],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
        check=False,
    )
    output = started.stdout + started.stderr
    assert started.returncode != 0, output
    assert "L9_MEMORY_POSTGRES_DSN" in started.stderr
    assert "postgres connection failed" in started.stderr
    assert "Traceback" not in started.stderr, started.stderr
    _assert_clean(output, secrets, "server stdout/stderr")


# -- settings -----------------------------------------------------------------

# Name segments that mark a field as carrying a credential or a store
# coordinate. A URL or URI can embed credentials; a host or user names where
# and as whom the service connects; ``extra`` is an unstructured bag.
_SECRET_SEGMENT = re.compile(
    r"(?:^|_)(dsn|tokens?|keys?|password|secret|credentials?|url|uri|host|user|username|"
    r"reference|extra)(?:_|$)"
)
# Matched by name, but not secret: each entry says why.
_NOT_SECRET = {
    "active_key_prefix": "a Redis key namespace, not a key",
    "default_token_budget": "an integer retrieval budget",
    "local_user_id": "the local principal's identifier, not a credential",
}


def test_no_secret_shaped_settings_field_is_repr_visible() -> None:
    visible = [
        name
        for name, field in MemorySettings.model_fields.items()
        if _SECRET_SEGMENT.search(name) and name not in _NOT_SECRET and field.repr
    ]
    assert not visible, f"secret-shaped settings fields printed by repr(): {visible}"
    assert set(_NOT_SECRET) <= set(MemorySettings.model_fields), "stale exemption"


def test_settings_repr_prints_no_configured_secret() -> None:
    settings = MemorySettings(
        postgres_dsn=f"postgresql://{USER}:ReprPw@{HOST}/{DB}",
        graphiti_mcp_url="https://u:UrlPw@graphiti.example/mcp",
        graphiti_mcp_token="ReprToken",
        zep_api_key="ReprZepKey",
        graph_neo4j_password="ReprNeo",
        auth_tokens={"ReprBearer": {"principal_id": "svc", "tenant_id": "t"}},
        extra={"anything": "ReprExtra"},
    )
    printed = repr(settings) + str(settings)
    for secret in ("ReprPw", HOST, "UrlPw", "ReprToken", "ReprZepKey", "ReprNeo", "ReprBearer"):
        assert secret not in printed
    assert "ReprExtra" not in printed
    # Values stay available to the code that needs them.
    assert settings.model_dump()["zep_api_key"] == "ReprZepKey"
    assert json.loads(settings.model_dump_json())["graphiti_mcp_token"] == "ReprToken"


# -- a database that goes away answers 503, not 500 ---------------------------


class _VanishingStore(InMemoryRecordStore):
    """Probe passes, then the backlog read finds the store gone."""

    def outbox_backlog(self) -> int:
        raise StoreConnectionError(
            "postgres connection failed (OperationalError): ***", driver_error="OperationalError"
        )


def test_a_store_lost_after_the_probe_reports_failed_instead_of_raising() -> None:
    service = MemoryService(_VanishingStore(), NullProjection())
    service.initialize()
    report = service.health()
    assert report.status.value == "failed"
    assert report.store == {"name": "memory", "healthy": False, "reason": STORE_UNAVAILABLE}
    assert report.outbox_backlog == 0


class _ClosedConnection:
    closed = 1

    def rollback(self) -> None:  # pragma: no cover - must not be called
        raise AssertionError("rolled back a closed connection")


class _DroppedDuringRollback:
    def __init__(self) -> None:
        self.closed = 0

    def rollback(self) -> None:
        import psycopg2

        self.closed = 2
        raise psycopg2.InterfaceError("connection already closed")


def test_rollback_of_a_connection_the_server_closed_does_not_mask_the_store_error() -> None:
    store = _postgres_store("host=unused")
    store._rollback(_ClosedConnection())
    store._rollback(_DroppedDuringRollback())
