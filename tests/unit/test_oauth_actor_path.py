"""The OAuth actor path (ADR-103, issue #108 section 3).

A validated access token proves a subject and a client. It proves no actor:
the actor comes only from an operator binding for that exact (subject, client
id) pair. These tests drive the resource server and the MCP tool layer
together, with an issuer that lives in this process. Nothing here exercises a
live tenant.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("jwt", reason="OAuth validation requires the [server] extra")
pytest.importorskip("cryptography", reason="OAuth validation requires the [server] extra")

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz.oauth import (
    OAUTH_ACTORS_ENV,
    OAUTH_GRANTS_ENV,
    OAuthResourceServer,
    actor_bindings_from_config,
)
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import EvidenceKind, MemoryPrincipal, WriteStatus
from l9_graphite_memory.contracts.identity import OAUTH_AUTH_METHOD
from l9_graphite_memory.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
)
from l9_graphite_memory.mcp_tools import (
    OAUTH_SUBJECT_CONSENT_EVIDENCE,
    MCPToolApplication,
    oauth_hosted_coordinates,
)
from l9_graphite_memory.services import MemoryService
from tests.oauth_fakes import CLIENT_ID, ISSUER, SUBJECT, FakeIssuer

NAMESPACE = "repo-a"
ACTOR_REF = "l9.actor-registry/global@1#claude-code"
SURFACE_REF = "l9.surface-registry/global@1#claude-code-cli"
OTHER_CLIENT = "another-public-client"
GRANTS = {SUBJECT: {"read_namespaces": [NAMESPACE], "write_namespaces": [NAMESPACE]}}
ACTORS = {SUBJECT: {CLIENT_ID: {"actor_ref": ACTOR_REF, "surface_ref": SURFACE_REF}}}


def _settings() -> MemorySettings:
    return MemorySettings(
        http_auth_mode="oauth",
        http_oauth_issuer=ISSUER,
        local_tenant_id="l9",
        local_organization_id="quantum-l9",
        local_workspace_id="l9-workspace",
    )


def _server(issuer: FakeIssuer, actors: dict[str, Any] | None = ACTORS) -> OAuthResourceServer:
    return OAuthResourceServer(_settings(), grants=GRANTS, actors=actors, fetch=issuer.fetch)


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


@pytest.fixture
def service() -> MemoryService:
    memory = MemoryService(InMemoryRecordStore(), NullProjection())
    memory.initialize()
    return memory


def _principal(issuer: FakeIssuer, actors: dict[str, Any] | None = ACTORS, **claims: Any) -> Any:
    return _server(issuer, actors).authenticate(f"Bearer {issuer.access_token(**claims)}")


def _write(service: MemoryService, principal: MemoryPrincipal, **extra: Any) -> Any:
    arguments = {"namespace": NAMESPACE, "content": "the deploy finished", **extra}
    return MCPToolApplication(service).call(principal, "memory.write_agent", arguments)


# --- actor evidence ----------------------------------------------------------


def test_a_bound_subject_and_client_write_is_admitted_and_attributed(issuer, service) -> None:
    principal = _principal(issuer)
    assert principal.agent_id == "claude-code"
    assert principal.oauth_client_id == CLIENT_ID
    assert principal.principal_id == SUBJECT
    assert principal.surface_ref == SURFACE_REF
    assert len(principal.actor_evidence_refs) == 1
    assert principal.actor_evidence_refs[0].startswith(f"oauth-actor-binding:{OAUTH_ACTORS_ENV}:")
    coordinates = oauth_hosted_coordinates(principal)
    assert coordinates.actor_ref == ACTOR_REF
    assert coordinates.surface_ref == SURFACE_REF

    receipt = _write(service, principal)
    assert receipt.status is WriteStatus.ADMITTED
    record = service.store.get_record(receipt.record_id)
    assert record is not None
    assert record.provenance.source_agent_id == "claude-code"


def test_an_authenticated_subject_without_an_actor_binding_cannot_write(issuer, service) -> None:
    principal = _principal(issuer, actors=None)
    assert principal.agent_id is None and principal.actor_evidence_refs == ()
    assert principal.oauth_client_id == CLIENT_ID
    with pytest.raises(AuthorizationError, match="not an actor"):
        _write(service, principal)


def test_the_binding_is_for_the_pair_not_for_the_subject_or_the_client(issuer, service) -> None:
    # Same subject, another client: the binding does not apply.
    other_client = _principal(issuer, azp=OTHER_CLIENT)
    assert other_client.agent_id is None
    with pytest.raises(AuthorizationError):
        _write(service, other_client)
    # Same client, another subject: the binding does not apply either.
    other_subject = _principal(issuer, sub="user|someone-else")
    assert other_subject.agent_id is None
    with pytest.raises(AuthorizationError):
        _write(service, other_subject)


def test_the_client_id_is_read_from_client_id_when_azp_is_absent(issuer) -> None:
    principal = _principal(issuer, azp=None, client_id=CLIENT_ID)
    assert principal.oauth_client_id == CLIENT_ID
    assert principal.agent_id == "claude-code"


def test_actor_claims_in_the_token_are_ignored(issuer, service) -> None:
    principal = _principal(
        issuer,
        actors=None,
        agent_id="claude-code",
        act={"sub": "claude-code"},
        actor_ref=ACTOR_REF,
    )
    assert principal.agent_id is None
    with pytest.raises(AuthorizationError):
        _write(service, principal)


def test_caller_supplied_actor_arguments_are_refused(issuer, service) -> None:
    principal = _principal(issuer, actors=None)
    for argument, value in (
        ("actor", ACTOR_REF),
        ("actor_identity", ACTOR_REF),
        ("client_id", CLIENT_ID),
        ("surface", SURFACE_REF),
    ):
        with pytest.raises(AuthorizationError, match="server-derived"):
            _write(service, principal, **{argument: value})


def test_a_principal_holding_evidence_that_names_the_client_is_not_an_actor() -> None:
    forged = MemoryPrincipal(
        principal_id=SUBJECT,
        tenant_id="l9",
        agent_id=CLIENT_ID,
        oauth_client_id=CLIENT_ID,
        actor_evidence_refs=("oauth-actor-binding:x",),
        auth_method=OAUTH_AUTH_METHOD,
        write_namespaces=(NAMESPACE,),
    )
    assert oauth_hosted_coordinates(forged).actor_ref is None


def test_reads_need_no_actor(issuer, service) -> None:
    principal = _principal(issuer, actors=None)
    found = MCPToolApplication(service).call(
        principal, "memory.search", {"namespaces": [NAMESPACE], "query": "deploy"}
    )
    assert found is not None


# --- actor map configuration -------------------------------------------------


@pytest.mark.parametrize(
    "actors",
    [
        {SUBJECT: {CLIENT_ID: {"actor_ref": "claude-code"}}},
        {SUBJECT: {CLIENT_ID: {"actor_ref": "l9.actor-registry/global@1#"}}},
        {SUBJECT: {CLIENT_ID: {"actor_ref": ACTOR_REF, "surface_ref": "cli"}}},
        {SUBJECT: {CLIENT_ID: {"actor_ref": ACTOR_REF, "is_admin": True}}},
        {SUBJECT: {CLIENT_ID: {"actor_ref": f"l9.actor-registry/global@1#{CLIENT_ID}"}}},
        {SUBJECT: {CLIENT_ID: "claude-code"}},
        {SUBJECT: {}},
        # The fragment becomes MemoryPrincipal.agent_id (200 max): a longer one
        # must stop startup, not fail every request it is bound to.
        {SUBJECT: {CLIENT_ID: {"actor_ref": "l9.actor-registry/global@1#" + "a" * 201}}},
        # An OAuth client is not a surface either, under any prefix.
        {
            SUBJECT: {
                CLIENT_ID: {
                    "actor_ref": ACTOR_REF,
                    "surface_ref": f"l9.surface-registry/global@1#{CLIENT_ID}",
                }
            }
        },
        {f"{CLIENT_ID}@clients": {CLIENT_ID: {"actor_ref": ACTOR_REF}}},
    ],
)
def test_a_malformed_actor_binding_is_a_startup_refusal(actors: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError):
        actor_bindings_from_config(actors)


def test_an_actor_id_at_the_principal_limit_is_accepted() -> None:
    actors = {SUBJECT: {CLIENT_ID: {"actor_ref": "l9.actor-registry/global@1#" + "a" * 200}}}
    assert actor_bindings_from_config(actors)[SUBJECT][CLIENT_ID].actor_id == "a" * 200


def test_the_actor_map_loads_from_the_environment_and_is_optional(
    issuer: FakeIssuer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(OAUTH_GRANTS_ENV, json.dumps(GRANTS))
    monkeypatch.delenv(OAUTH_ACTORS_ENV, raising=False)
    unbound = OAuthResourceServer.from_environment(_settings(), fetch=issuer.fetch)
    assert unbound.authenticate(f"Bearer {issuer.access_token()}").agent_id is None

    monkeypatch.setenv(OAUTH_ACTORS_ENV, json.dumps(ACTORS))
    bound = OAuthResourceServer.from_environment(_settings(), fetch=issuer.fetch)
    assert bound.authenticate(f"Bearer {issuer.access_token()}").agent_id == "claude-code"

    monkeypatch.setenv(OAUTH_ACTORS_ENV, "[not json")
    with pytest.raises(ConfigurationError):
        OAuthResourceServer.from_environment(_settings(), fetch=issuer.fetch)


# --- tokens without an end user ----------------------------------------------


@pytest.mark.parametrize(
    "claims",
    [
        {"gty": "client-credentials"},
        {"gty": ["client-credentials"]},
        {"grant_type": "client_credentials"},
        {"sub": f"{CLIENT_ID}@clients"},
        {"sub": "agt_72jbvv7LfRKYp59gtRLtkn", "sub_profile": "ai_agent"},
        {"sub": CLIENT_ID},
        {"sub": "m2m-client", "azp": None, "client_id": "m2m-client"},
    ],
    ids=[
        "auth0-gty",
        "gty-list",
        "rfc-grant-type",
        "auth0-clients-subject",
        "auth0-agent-subject",
        "subject-is-azp",
        "subject-is-client_id",
    ],
)
def test_a_token_without_an_end_user_is_refused(issuer: FakeIssuer, claims: dict) -> None:
    # Every check passes but the user-less one: issuer, audience and signature
    # are valid, and the subject is granted.
    server = _server(issuer)
    with pytest.raises(AuthenticationError, match="without an end user"):
        server.authenticate(f"Bearer {issuer.access_token(**claims)}")


def test_a_user_subject_profile_is_admitted(issuer: FakeIssuer) -> None:
    principal = _principal(issuer, sub_profile="user")
    assert principal.agent_id == "claude-code"


# --- server-verified explicit evidence ---------------------------------------


def _preference(subject: str, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "memory_class": "preference",
        "subject": subject,
        "predicate": "prefers",
        "object": "dark mode",
        "valid_from": "2026-11-01T00:00:00+00:00",
        "consent": {
            "subject_id": subject,
            "purpose": "personalization",
            "evidence_description": "set in the client settings",
            "granted_at": "2026-10-01T00:00:00+00:00",
        },
    }
    arguments.update(overrides)
    return arguments


def test_consent_from_the_verified_subject_is_explicit_evidence(issuer, service) -> None:
    principal = _principal(issuer)
    receipt = _write(service, principal, **_preference(SUBJECT))
    assert receipt.status is WriteStatus.ADMITTED, receipt.admission.reasons
    record = service.store.get_record(receipt.record_id)
    assert record is not None
    explicit = [item for item in record.evidence if item.kind is EvidenceKind.EXPLICIT]
    assert [item.description for item in explicit] == [OAUTH_SUBJECT_CONSENT_EVIDENCE]
    assert explicit[0].source_id == principal.audit_subject


def test_consent_for_another_subject_with_a_caller_claim_is_quarantined(issuer, service) -> None:
    principal = _principal(issuer)
    arguments = _preference(
        "user|someone-else",
        evidence=[{"kind": "explicit", "description": "they said so"}],
    )
    receipt = _write(service, principal, **arguments)
    assert receipt.status is WriteStatus.QUARANTINED
    record = service.store.get_record(receipt.record_id)
    assert record is not None
    assert all(item.kind is not EvidenceKind.EXPLICIT for item in record.evidence)


def test_a_caller_claim_of_explicit_evidence_alone_is_quarantined(issuer, service) -> None:
    principal = _principal(issuer)
    arguments = _preference(
        SUBJECT,
        consent=None,
        evidence=[{"kind": "explicit", "description": "trust me"}],
    )
    del arguments["consent"]
    receipt = _write(service, principal, **arguments)
    # Without consent the preference is rejected outright; with a claim and a
    # foreign-subject consent it is quarantined (above). Neither admits.
    assert receipt.status is not WriteStatus.ADMITTED


def test_consent_matching_the_subject_on_a_non_oauth_door_adds_nothing(service) -> None:
    principal = MemoryPrincipal(
        principal_id=SUBJECT,
        tenant_id="l9",
        agent_id="claude-code",
        write_namespaces=(NAMESPACE,),
        read_namespaces=(NAMESPACE,),
        auth_method="signed-agent",
    )
    receipt = _write(
        service,
        principal,
        **_preference(SUBJECT, evidence=[{"kind": "explicit", "description": "trust me"}]),
    )
    assert receipt.status is WriteStatus.QUARANTINED
