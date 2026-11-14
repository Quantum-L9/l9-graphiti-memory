"""The OAuth door over a real socket (ADR-100, ADR-102).

A real server on a loopback port, an HTTP client over TCP, and an issuer that
lives in this process. These tests prove the wire behaviour of
``http_auth_mode=oauth``. They are not the live PKCE receipt.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")
pytest.importorskip("jwt", reason="OAuth validation requires the [server] extra")
httpx2 = pytest.importorskip("httpx2", reason="the HTTP proof needs an HTTP client")

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz import oauth
from l9_graphite_memory.authz.oauth import (
    OAUTH_ACTORS_ENV,
    OAUTH_GRANTS_ENV,
    PROTECTED_RESOURCE_METADATA_PATH,
    PROTECTED_RESOURCE_METADATA_URL,
)
from l9_graphite_memory.config import MemorySettings, TokenPrincipalConfig
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.mcp_tools import MCPToolApplication
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.server import (
    MCP_CANONICAL_ENDPOINT_PATH,
    MCP_ENDPOINT_PATHS,
    create_http_app,
)
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import MEMORY_RESOURCE_IDENTIFIER
from tests.integration.remote_mcp_harness import (
    ALLOWED_ORIGIN,
    FORBIDDEN_ORIGIN,
    HOME_NAMESPACE,
    WRITER,
    credentials,
    mcp_headers,
    rpc,
    serve,
    server_environment,
    tool,
    tool_payload,
)
from tests.oauth_fakes import (
    CLIENT_ID,
    ISSUER,
    OTHER_ISSUER,
    OTHER_RESOURCE,
    SUBJECT,
    FakeIssuer,
    hmac_token,
    public_pem,
    rsa_key,
    unsigned_token,
)

READER = "user|reader-0002"
STRANGER = "user|no-grant-0003"
SERVICE_TOKEN = "service-token-for-tests"
GRANTS = {
    SUBJECT: {"read_namespaces": [HOME_NAMESPACE], "write_namespaces": [HOME_NAMESPACE]},
    READER: {"read_namespaces": [HOME_NAMESPACE]},
}


def _settings(**overrides: Any) -> MemorySettings:
    values: dict[str, Any] = {
        "http_auth_required": True,
        "http_auth_mode": "oauth",
        "http_oauth_issuer": ISSUER,
        "http_allowed_origins": (ALLOWED_ORIGIN,),
        "local_tenant_id": "l9",
        "local_organization_id": "quantum-l9",
        "local_workspace_id": "l9-workspace",
        # A static bearer token is configured on purpose: OAuth mode must not
        # fall through to it.
        "auth_tokens": {
            SERVICE_TOKEN: TokenPrincipalConfig(
                principal_id="service",
                tenant_id="l9",
                read_namespaces=("*",),
                write_namespaces=("*",),
                is_admin=True,
            )
        },
    }
    values.update(overrides)
    return MemorySettings(**values)


def _service() -> MemoryService:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    return service


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> FakeIssuer:
    """The issuer, wired in as the server's only route to issuer documents."""

    fake = FakeIssuer()
    monkeypatch.setattr(oauth, "https_get", fake.fetch)
    monkeypatch.setenv(OAUTH_GRANTS_ENV, json.dumps(GRANTS))
    # The signed-agent registry and both stdio doors are present too, so a
    # fall-through to any of them would be visible.
    for name, value in server_environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "local-human-door-secret")
    return fake


@pytest.fixture
def service() -> MemoryService:
    return _service()


@pytest.fixture
def client(issuer: FakeIssuer, service: MemoryService) -> Iterator[Any]:
    runtime = MemoryRuntime(settings=_settings(), service=service)
    try:
        with (
            serve(create_http_app(runtime)) as url,
            httpx2.Client(base_url=url, timeout=10) as http,
        ):
            yield http
    finally:
        runtime.close()


def _post(
    client: Any,
    message: Any,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    path: str = "/mcp",
) -> Any:
    sent = mcp_headers()
    if token is not None:
        sent["Authorization"] = f"Bearer {token}"
    sent.update(headers or {})
    return client.post(path, content=json.dumps(message), headers=sent)


def _assert_unauthorized(response: Any, *, presented: str | None) -> dict[str, Any]:
    """A 401 with the Bearer challenge, no request id, and no echoed credential."""

    assert response.status_code == 401, response.text
    body = response.json()
    assert body["jsonrpc"] == "2.0" and "id" not in body
    assert body["error"]["code"] == -32001
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith('Bearer realm="l9-graphite-memory"')
    assert f'resource_metadata="{PROTECTED_RESOURCE_METADATA_URL}"' in challenge
    assert ('error="invalid_token"' in challenge) == (presented is not None)
    if presented:
        assert presented not in response.text + json.dumps(dict(response.headers))
    return dict(body)


# --- admitted ----------------------------------------------------------------


def test_a_valid_token_initializes_lists_tools_and_reads(client, issuer, service) -> None:
    token = issuer.access_token()
    initialized = _post(client, rpc("initialize", {"protocolVersion": "2025-11-25"}), token=token)
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["result"]["protocolVersion"] == "2025-11-25"

    listed = _post(client, rpc("tools/list"), token=token)
    assert listed.status_code == 200
    assert any(entry["name"] == "memory.search" for entry in listed.json()["result"]["tools"])

    # Seeded through MemoryService, because an OAuth write is refused below.
    seeded = MCPToolApplication(service).call(
        MemoryPrincipal(
            principal_id="seed",
            tenant_id="l9",
            organization_id="quantum-l9",
            workspace_id="l9-workspace",
            agent_id="seed",
            write_namespaces=(HOME_NAMESPACE,),
        ),
        "memory.write_agent",
        {
            "namespace": HOME_NAMESPACE,
            "content": "The OAuth door admits an audience-bound token.",
        },
    )
    assert seeded.record_id
    found = _post(
        client,
        tool("memory.search", {"namespaces": [HOME_NAMESPACE], "query": "audience-bound token"}),
        token=issuer.access_token(sub=READER),
    )
    assert found.status_code == 200, found.text
    assert str(seeded.record_id) in json.dumps(tool_payload(found.json()))


def test_each_request_is_validated_on_its_own_token(client, issuer) -> None:
    assert _post(client, rpc("tools/list"), token=issuer.access_token()).status_code == 200
    _assert_unauthorized(_post(client, rpc("tools/list")), presented=None)


def test_a_notification_needs_a_token_and_gets_202(client, issuer) -> None:
    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    _assert_unauthorized(_post(client, message), presented=None)
    accepted = _post(client, message, token=issuer.access_token())
    assert accepted.status_code == 202 and accepted.content == b""


# --- refused -----------------------------------------------------------------


def test_a_request_without_a_token_is_challenged(client) -> None:
    _assert_unauthorized(_post(client, rpc("tools/list")), presented=None)


def _refused_tokens(issuer: FakeIssuer) -> dict[str, str]:
    now = int(time.time())
    return {
        "wrong issuer": issuer.access_token(iss=OTHER_ISSUER),
        "wrong audience": issuer.access_token(aud=OTHER_RESOURCE),
        "trailing-slash audience": issuer.access_token(aud=MEMORY_RESOURCE_IDENTIFIER + "/"),
        "expired": issuer.access_token(iat=now - 7200, exp=now - 3600),
        "not yet valid": issuer.access_token(nbf=now + 3600, exp=now + 7200),
        "alg none": unsigned_token(issuer.claims()),
        "hs256 with the public key": hmac_token(issuer.claims(), public_pem(issuer.key)),
        "missing kid": issuer.access_token(headers={"kid": None}),
        "unknown kid": issuer.access_token(headers={"kid": "not-published"}),
        "foreign signature": issuer.access_token(key=rsa_key(1)),
        "malformed": "not.a.jwt",
        "opaque": "opaque-access-token-0123456789",
    }


@pytest.mark.parametrize(
    "case",
    [
        "wrong issuer",
        "wrong audience",
        "trailing-slash audience",
        "expired",
        "not yet valid",
        "alg none",
        "hs256 with the public key",
        "missing kid",
        "unknown kid",
        "foreign signature",
        "malformed",
        "opaque",
    ],
)
def test_an_invalid_token_is_refused_with_401(client, issuer, case: str) -> None:
    token = _refused_tokens(issuer)[case]
    _assert_unauthorized(_post(client, rpc("tools/list"), token=token), presented=token)


def test_unreachable_issuer_keys_refuse_with_401_and_no_fallback(client, issuer) -> None:
    issuer.unreachable = True
    token = issuer.access_token()
    body = _assert_unauthorized(_post(client, rpc("tools/list"), token=token), presented=token)
    assert "unavailable" in body["error"]["message"]
    # With keys unobtainable, no other configured credential opens the door.
    _assert_unauthorized(
        _post(client, rpc("tools/list"), token=SERVICE_TOKEN), presented=SERVICE_TOKEN
    )


def test_the_other_doors_are_closed_in_oauth_mode(client) -> None:
    _assert_unauthorized(
        _post(client, rpc("tools/list"), token=SERVICE_TOKEN), presented=SERVICE_TOKEN
    )
    agent = credentials(WRITER)
    refused = client.post(
        "/mcp", content=json.dumps(rpc("tools/list")), headers={**mcp_headers(), **agent}
    )
    _assert_unauthorized(refused, presented=agent["Authorization"].removeprefix("Bearer "))


def test_a_token_in_the_url_is_refused_and_not_echoed(client, issuer) -> None:
    token = issuer.access_token()
    refused = client.post(
        f"/mcp?access_token={token}", content=json.dumps(rpc("tools/list")), headers=mcp_headers()
    )
    assert refused.status_code == 400
    assert token not in refused.text


def test_a_forbidden_origin_is_refused_before_the_token_is_read(client, issuer) -> None:
    refused = _post(
        client,
        rpc("tools/list"),
        token=issuer.access_token(),
        headers={"Origin": FORBIDDEN_ORIGIN},
    )
    assert refused.status_code == 403
    assert issuer.fetches == []


# --- identity and authorization ----------------------------------------------


def test_an_oauth_write_is_refused_because_a_subject_is_not_an_actor(client, issuer) -> None:
    response = _post(
        client,
        tool("memory.write_agent", {"namespace": HOME_NAMESPACE, "content": "hello"}),
        token=issuer.access_token(),
    )
    assert response.status_code == 200, response.text
    error = response.json()["error"]
    assert error["code"] == -32010 and error["data"]["type"] == "AuthorizationError"
    assert "not an actor" in error["message"]


def test_a_subject_without_a_grant_is_authenticated_and_reads_nothing(client, issuer) -> None:
    token = issuer.access_token(sub=STRANGER)
    assert _post(client, rpc("tools/list"), token=token).status_code == 200
    denied = _post(
        client, tool("memory.search", {"namespaces": [HOME_NAMESPACE], "query": "x"}), token=token
    )
    assert denied.status_code == 200
    assert denied.json()["error"]["data"]["type"] == "AuthorizationError"


def test_a_namespace_outside_the_grant_is_denied(client, issuer) -> None:
    denied = _post(
        client,
        tool("memory.search", {"namespaces": ["repo-b"], "query": "x"}),
        token=issuer.access_token(),
    )
    assert denied.json()["error"]["data"]["type"] == "AuthorizationError"


def test_a_tool_argument_cannot_name_the_client_or_the_actor(client, issuer) -> None:
    for argument in ("client_id", "actor"):
        refused = _post(
            client,
            tool("memory.health", {argument: "public-client-for-tests"}),
            token=issuer.access_token(),
        )
        assert refused.json()["error"]["data"]["type"] == "AuthorizationError"


# --- one canonical resource --------------------------------------------------


def test_the_canonical_endpoint_is_the_path_of_the_resource_identifier() -> None:
    assert MCP_CANONICAL_ENDPOINT_PATH == "/mcp"
    assert MEMORY_RESOURCE_IDENTIFIER.endswith(MCP_CANONICAL_ENDPOINT_PATH)
    assert not MEMORY_RESOURCE_IDENTIFIER.endswith("/")


@pytest.mark.parametrize("method", ["PUT", "PATCH", "OPTIONS", "HEAD"])
def test_no_verb_answers_405_on_the_trailing_slash_spelling(client, issuer, method: str) -> None:
    # A 405 would say the path exists and another verb works. It does not.
    response = client.request(method, "/mcp/", follow_redirects=False)
    assert response.status_code == 404, response.text
    assert "Allow" not in response.headers
    assert "Location" not in response.headers
    assert issuer.fetches == []


@pytest.mark.parametrize("method", ["POST", "GET", "DELETE"])
def test_the_trailing_slash_spelling_is_not_an_endpoint_in_oauth_mode(
    client, issuer, method: str
) -> None:
    response = client.request(
        method,
        "/mcp/",
        content=json.dumps(rpc("tools/list")),
        headers={**mcp_headers(), "Authorization": f"Bearer {issuer.access_token()}"},
        follow_redirects=False,
    )
    assert response.status_code == 404, response.text
    body = response.json()
    assert "id" not in body and body["error"]["code"] == -32600
    assert MEMORY_RESOURCE_IDENTIFIER in body["error"]["message"]
    assert "Location" not in response.headers
    assert issuer.fetches == [], "the refused spelling validates nothing"


def test_get_and_delete_on_the_endpoint_are_still_405(client) -> None:
    for method in ("GET", "DELETE"):
        response = client.request(method, "/mcp")
        assert response.status_code == 405 and response.headers["Allow"] == "POST"


# --- protected resource metadata and probes ----------------------------------


def test_protected_resource_metadata_is_served_without_a_token(client) -> None:
    response = client.get(PROTECTED_RESOURCE_METADATA_PATH)
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json() == {
        "resource": MEMORY_RESOURCE_IDENTIFIER,
        "authorization_servers": [ISSUER],
        "bearer_methods_supported": ["header"],
        "resource_name": "L9 Graphite Memory",
    }
    # The host root is not claimed for the Memory resource.
    assert client.get("/.well-known/oauth-protected-resource").status_code == 404


def test_health_and_readiness_stay_unauthenticated(client, issuer) -> None:
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["readiness"]["ready"] is True
    assert issuer.fetches == []


# --- startup -----------------------------------------------------------------


def _create(settings: MemorySettings) -> Any:
    runtime = MemoryRuntime(settings=settings, service=_service())
    try:
        return create_http_app(runtime)
    finally:
        runtime.close()


@pytest.mark.parametrize("value", [None, "", "  "])
def test_oauth_mode_refuses_to_start_without_an_issuer(issuer, value) -> None:
    with pytest.raises(ConfigurationError, match="requires L9_MEMORY_HTTP_OAUTH_ISSUER"):
        _create(_settings(http_oauth_issuer=value))


def test_oauth_mode_refuses_to_start_with_an_issuer_that_is_not_https(issuer) -> None:
    with pytest.raises(ConfigurationError, match="must be an https URL"):
        _create(_settings(http_oauth_issuer="http://issuer.example.test/"))


def test_oauth_mode_refuses_to_start_without_a_grant_map(issuer, monkeypatch) -> None:
    monkeypatch.delenv(OAUTH_GRANTS_ENV)
    with pytest.raises(ConfigurationError, match=f"requires {OAUTH_GRANTS_ENV}"):
        _create(_settings())


def test_oauth_mode_refuses_an_administrator_grant_at_startup(issuer, monkeypatch) -> None:
    monkeypatch.setenv(OAUTH_GRANTS_ENV, json.dumps({SUBJECT: {"is_admin": True}}))
    with pytest.raises(ConfigurationError, match="grants is_admin"):
        _create(_settings())


def test_oauth_mode_requires_authentication(issuer) -> None:
    with pytest.raises(ConfigurationError, match="requires http_auth_required=true"):
        _create(_settings(http_auth_required=False))


def test_startup_reads_nothing_from_the_issuer(issuer) -> None:
    _create(_settings())
    assert issuer.fetches == []


# --- the other modes are unchanged -------------------------------------------


def test_bearer_mode_keeps_both_paths_its_challenge_and_no_metadata(issuer) -> None:
    runtime = MemoryRuntime(settings=_settings(http_auth_mode="bearer"), service=_service())
    try:
        with serve(create_http_app(runtime)) as url, httpx2.Client(base_url=url) as http:
            assert MCP_ENDPOINT_PATHS == ("/mcp", "/mcp/")
            for path in MCP_ENDPOINT_PATHS:
                ok = _post(http, tool("memory.health", {}), token=SERVICE_TOKEN, path=path)
                assert ok.status_code == 200, ok.text
            missing = _post(http, rpc("tools/list"))
            assert missing.status_code == 401
            assert missing.headers["WWW-Authenticate"] == 'Bearer realm="l9-graphite-memory"'
            # An access token the OAuth door would admit is not a bearer credential.
            refused = _post(http, rpc("tools/list"), token=issuer.access_token())
            assert refused.status_code == 401
            assert refused.headers["WWW-Authenticate"] == (
                'Bearer realm="l9-graphite-memory", error="invalid_token"'
            )
            assert http.get(PROTECTED_RESOURCE_METADATA_PATH).status_code == 404
            assert issuer.fetches == []
    finally:
        runtime.close()


def test_signed_agent_mode_keeps_both_paths_and_refuses_an_access_token(issuer) -> None:
    runtime = MemoryRuntime(settings=_settings(http_auth_mode="signed-agent"), service=_service())
    try:
        with serve(create_http_app(runtime)) as url, httpx2.Client(base_url=url) as http:
            for path in MCP_ENDPOINT_PATHS:
                ok = http.post(
                    path,
                    content=json.dumps(rpc("tools/list")),
                    headers={**mcp_headers(), **credentials(WRITER)},
                )
                assert ok.status_code == 200, ok.text
            refused = _post(http, rpc("tools/list"), token=issuer.access_token())
            assert refused.status_code == 401
            assert "resource_metadata" not in refused.headers["WWW-Authenticate"]
            assert http.get(PROTECTED_RESOURCE_METADATA_PATH).status_code == 404
            assert issuer.fetches == []
    finally:
        runtime.close()


# --- the actor path (ADR-103) ------------------------------------------------

ACTORS = {
    SUBJECT: {
        CLIENT_ID: {
            "actor_ref": "l9.actor-registry/global@1#claude-code",
            "surface_ref": "l9.surface-registry/global@1#claude-code-cli",
        }
    }
}


@pytest.fixture
def bound_client(
    issuer: FakeIssuer, service: MemoryService, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Any]:
    """A server whose operator bound SUBJECT through CLIENT_ID to an actor."""

    monkeypatch.setenv(OAUTH_ACTORS_ENV, json.dumps(ACTORS))
    runtime = MemoryRuntime(settings=_settings(), service=service)
    try:
        with (
            serve(create_http_app(runtime)) as url,
            httpx2.Client(base_url=url, timeout=10) as http,
        ):
            yield http
    finally:
        runtime.close()


def test_a_bound_subject_and_client_write_is_admitted_over_the_wire(
    bound_client, issuer, service
) -> None:
    response = _post(
        bound_client,
        tool("memory.write_agent", {"namespace": HOME_NAMESPACE, "content": "bound write"}),
        token=issuer.access_token(),
    )
    assert response.status_code == 200, response.text
    receipt = tool_payload(response.json())
    assert receipt["status"] == "admitted", receipt
    record = service.store.get_record(UUID(receipt["record_id"]))
    assert record is not None and record.provenance.source_agent_id == "claude-code"


def test_an_unbound_pair_is_still_refused_over_the_wire(bound_client, issuer) -> None:
    response = _post(
        bound_client,
        tool("memory.write_agent", {"namespace": HOME_NAMESPACE, "content": "x"}),
        token=issuer.access_token(azp="another-public-client"),
    )
    error = response.json()["error"]
    assert error["data"]["type"] == "AuthorizationError" and "not an actor" in error["message"]


@pytest.mark.parametrize(
    "claims",
    [{"gty": "client-credentials"}, {"sub": f"{CLIENT_ID}@clients"}, {"sub": CLIENT_ID}],
    ids=["gty", "clients-subject", "subject-is-client"],
)
def test_a_client_credentials_token_is_refused_with_401(
    bound_client, issuer, claims: dict[str, Any]
) -> None:
    token = issuer.access_token(**claims)
    response = _post(bound_client, rpc("tools/list"), token=token)
    _assert_unauthorized(response, presented=token)
