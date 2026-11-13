"""OAuth resource-server validation (ADR-102).

Each case builds a token the way an attacker or a misconfigured issuer would
and checks that it is refused, and that only a token the configured issuer
signed for the Memory resource is admitted. Keys are generated in this
process; nothing here is evidence about a real tenant.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

pytest.importorskip("jwt", reason="OAuth validation requires the [server] extra")
pytest.importorskip("cryptography", reason="OAuth validation requires the [server] extra")

from l9_graphite_memory.authz import oauth
from l9_graphite_memory.authz.oauth import (
    ALLOWED_SIGNING_ALGORITHMS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_FAILURE_BACKOFF_SECONDS,
    JWKS_REFRESH_COOLDOWN_SECONDS,
    OAUTH_GRANTS_ENV,
    PROTECTED_RESOURCE_METADATA_PATH,
    PROTECTED_RESOURCE_METADATA_URL,
    AccessTokenValidator,
    OAuthResourceServer,
    protected_resource_metadata,
    validated_issuer,
)
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts.identity import OAUTH_AUTH_METHOD
from l9_graphite_memory.errors import AuthenticationError, ConfigurationError
from l9_graphite_memory.version import MEMORY_RESOURCE_IDENTIFIER
from tests.oauth_fakes import (
    CLIENT_ID,
    ISSUER,
    KEY_ID,
    OTHER_ISSUER,
    OTHER_RESOURCE,
    SUBJECT,
    FakeIssuer,
    ec_key,
    hmac_token,
    public_jwk,
    public_pem,
    rsa_key,
    unsigned_token,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def validator(issuer: FakeIssuer, clock: Clock) -> AccessTokenValidator:
    return AccessTokenValidator(ISSUER, fetch=issuer.fetch, clock=clock)


def _refused(validator: AccessTokenValidator, token: str, match: str) -> None:
    with pytest.raises(AuthenticationError, match=match) as raised:
        validator.verify(token)
    assert token not in str(raised.value), "a refusal must not repeat the token"


# --- admitted ----------------------------------------------------------------


def test_a_token_from_the_configured_issuer_for_the_memory_resource_is_admitted(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    verified = validator.verify(issuer.access_token())
    assert verified.subject == SUBJECT
    assert verified.client_id == CLIENT_ID
    assert verified.algorithm == "RS256"
    assert verified.key_id == KEY_ID
    assert verified.claims["aud"] == MEMORY_RESOURCE_IDENTIFIER


def test_an_audience_list_that_contains_the_memory_resource_is_admitted(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    token = issuer.access_token(aud=[MEMORY_RESOURCE_IDENTIFIER, f"{ISSUER}userinfo"])
    assert validator.verify(token).subject == SUBJECT


def test_an_elliptic_curve_issuer_key_is_admitted(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    issuer.key, issuer.algorithm = ec_key(0), "ES256"
    assert validator.verify(issuer.access_token()).algorithm == "ES256"


# --- refused: claims ---------------------------------------------------------


def test_a_token_from_another_issuer_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    _refused(validator, issuer.access_token(iss=OTHER_ISSUER), "configured issuer")


@pytest.mark.parametrize("claimed", [ISSUER.rstrip("/"), ISSUER.upper(), ISSUER + "/"])
def test_the_issuer_is_compared_exactly(
    issuer: FakeIssuer, validator: AccessTokenValidator, claimed: str
) -> None:
    _refused(validator, issuer.access_token(iss=claimed), "configured issuer")


@pytest.mark.parametrize(
    "audience",
    [
        OTHER_RESOURCE,
        [OTHER_RESOURCE, f"{ISSUER}userinfo"],
        MEMORY_RESOURCE_IDENTIFIER + "/",
        MEMORY_RESOURCE_IDENTIFIER.rsplit("/", 1)[0],
        CLIENT_ID,
    ],
)
def test_a_token_for_another_audience_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator, audience: Any
) -> None:
    _refused(validator, issuer.access_token(aud=audience), "audience")


def test_an_expired_token_is_refused(issuer: FakeIssuer, validator: AccessTokenValidator) -> None:
    now = int(time.time())
    _refused(validator, issuer.access_token(iat=now - 7200, exp=now - 3600), "expired")


def test_a_token_that_is_not_yet_valid_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    now = int(time.time())
    _refused(validator, issuer.access_token(nbf=now + 3600, exp=now + 7200), "not yet valid")


def test_a_token_issued_in_the_future_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    now = int(time.time())
    _refused(validator, issuer.access_token(iat=now + 3600, exp=now + 7200), "not yet valid")


@pytest.mark.parametrize("claim", ["exp", "iss", "aud", "sub"])
def test_a_token_missing_a_required_claim_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator, claim: str
) -> None:
    _refused(validator, issuer.access_token(**{claim: None}), f"missing the {claim} claim")


@pytest.mark.parametrize("subject", ["", "s" * 201])
def test_an_unusable_subject_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator, subject: str
) -> None:
    _refused(validator, issuer.access_token(sub=subject), "subject")


# --- refused: algorithm and key ----------------------------------------------


def test_an_unsigned_token_is_refused(issuer: FakeIssuer, validator: AccessTokenValidator) -> None:
    _refused(validator, unsigned_token(issuer.claims()), "algorithm is not allowed")
    assert issuer.fetches == [], "an unsigned token must not reach the issuer"


def test_hs256_with_the_public_key_as_the_secret_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    forged = hmac_token(issuer.claims(), public_pem(issuer.key))
    _refused(validator, forged, "algorithm is not allowed")
    assert issuer.fetches == []


def test_no_symmetric_or_unsigned_algorithm_is_on_the_allow_list() -> None:
    assert ALLOWED_SIGNING_ALGORITHMS
    for algorithm in ALLOWED_SIGNING_ALGORITHMS:
        assert not algorithm.startswith("HS")
        assert algorithm.lower() != "none"


def test_a_token_without_a_key_id_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    _refused(validator, issuer.access_token(headers={"kid": None}), "does not name")
    assert issuer.fetches == []


def test_a_token_naming_an_unknown_key_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    _refused(validator, issuer.access_token(headers={"kid": "not-published"}), "not published")


def test_a_token_signed_by_another_key_under_a_published_key_id_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    _refused(validator, issuer.access_token(key=rsa_key(1)), "signature is not valid")


def test_a_key_carried_in_the_token_is_never_used(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    attacker = rsa_key(1)
    carried = {"jwk": public_jwk(attacker, "attacker-key"), "jku": "https://attacker.example.test"}
    _refused(
        validator,
        issuer.access_token(key=attacker, headers={**carried, "kid": "attacker-key"}),
        "not published",
    )
    _refused(validator, issuer.access_token(key=attacker, headers=carried), "signature")
    assert all(url.startswith(issuer.base) for url in issuer.fetches)


def test_a_symmetric_key_in_the_key_set_is_never_a_verification_key(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    secret = b"a-shared-secret-of-thirty-two-bytes!"
    issuer.publish_own_key = False
    issuer.extra_keys = [
        {"kty": "oct", "kid": KEY_ID, "k": "YS1zaGFyZWQtc2VjcmV0", "alg": "HS256", "use": "sig"}
    ]
    _refused(validator, hmac_token(issuer.claims(), secret), "algorithm is not allowed")
    _refused(validator, issuer.access_token(), "unavailable")


def test_a_key_set_entry_with_private_material_is_not_used(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    from jwt.algorithms import RSAAlgorithm

    private = json.loads(RSAAlgorithm.to_jwk(issuer.key))
    private.update({"kid": KEY_ID, "use": "sig", "alg": "RS256"})
    issuer.publish_own_key = False
    issuer.extra_keys = [private]
    _refused(validator, issuer.access_token(), "unavailable")


def test_two_keys_under_one_key_id_are_both_unusable(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    issuer.extra_keys = [public_jwk(rsa_key(1), KEY_ID)]
    _refused(validator, issuer.access_token(), "unavailable")


# The warning is the signing side of this fixture; the refusal is what is tested.
@pytest.mark.filterwarnings("ignore:The RSA key is 1024 bits long")
def test_an_undersized_rsa_key_is_refused(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    issuer.key = rsa_key(2, 1024)
    _refused(validator, issuer.access_token(), "InvalidKeyError")


@pytest.mark.parametrize(
    "token",
    ["", "not-a-jwt", "a.b", "a.b.c", "....", "é.é.é", "x" * 20_000, "e30.e30.e30"],
)
def test_a_malformed_token_is_refused(validator: AccessTokenValidator, token: str) -> None:
    with pytest.raises(AuthenticationError):
        validator.verify(token)


# --- issuer keys: retrieval, caching, failure --------------------------------


def test_unreachable_issuer_keys_refuse_the_token(
    issuer: FakeIssuer, validator: AccessTokenValidator
) -> None:
    issuer.unreachable = True
    _refused(validator, issuer.access_token(), "unavailable")


def test_issuer_metadata_naming_another_issuer_is_not_trusted(clock: Clock) -> None:
    issuer = FakeIssuer()
    metadata = {**issuer.metadata(), "issuer": OTHER_ISSUER}

    def fetch(url: str) -> bytes:
        return json.dumps(metadata).encode() if url == issuer.metadata_url else issuer.fetch(url)

    validator = AccessTokenValidator(ISSUER, fetch=fetch, clock=clock)
    _refused(validator, issuer.access_token(), "unavailable")
    assert issuer.key_set_reads() == 0


@pytest.mark.parametrize("location", ["http://issuer.example.test/jwks.json", None, 7])
def test_a_key_set_location_that_is_not_https_is_not_read(clock: Clock, location: Any) -> None:
    issuer = FakeIssuer()
    metadata = {**issuer.metadata(), "jwks_uri": location}
    read: list[str] = []

    def fetch(url: str) -> bytes:
        read.append(url)
        return json.dumps(metadata).encode()

    validator = AccessTokenValidator(ISSUER, fetch=fetch, clock=clock)
    _refused(validator, issuer.access_token(), "unavailable")
    assert read == [issuer.metadata_url]


@pytest.mark.parametrize("document", [b"not json", b"[]", b'{"keys": {}}', b'{"keys": []}'])
def test_a_malformed_key_set_refuses_the_token(clock: Clock, document: bytes) -> None:
    issuer = FakeIssuer()

    def fetch(url: str) -> bytes:
        return document if url == issuer.jwks_url else issuer.fetch(url)

    validator = AccessTokenValidator(ISSUER, fetch=fetch, clock=clock)
    _refused(validator, issuer.access_token(), "unavailable")


def test_keys_are_read_once_and_cached(issuer: FakeIssuer, validator: AccessTokenValidator) -> None:
    for _ in range(5):
        validator.verify(issuer.access_token())
    assert issuer.fetches == [issuer.metadata_url, issuer.jwks_url]


def test_unknown_key_ids_cause_at_most_one_reread_per_cooldown(
    issuer: FakeIssuer, validator: AccessTokenValidator, clock: Clock
) -> None:
    validator.verify(issuer.access_token())
    for index in range(20):
        _refused(validator, issuer.access_token(headers={"kid": f"k{index}"}), "not published")
    assert issuer.key_set_reads() == 1
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    for index in range(20):
        _refused(validator, issuer.access_token(headers={"kid": f"n{index}"}), "not published")
    assert issuer.key_set_reads() == 2


def test_a_rotated_key_is_found_after_the_cooldown(
    issuer: FakeIssuer, validator: AccessTokenValidator, clock: Clock
) -> None:
    validator.verify(issuer.access_token())
    issuer.key, issuer.key_id = rsa_key(1), "issuer-key-2"
    _refused(validator, issuer.access_token(), "not published")
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    assert validator.verify(issuer.access_token()).key_id == "issuer-key-2"
    # The withdrawn key no longer verifies anything.
    _refused(validator, issuer.access_token(key=rsa_key(0), headers={"kid": KEY_ID}), "published")


def test_expired_keys_are_dropped_when_they_cannot_be_reread(
    issuer: FakeIssuer, validator: AccessTokenValidator, clock: Clock
) -> None:
    token = issuer.access_token()
    validator.verify(token)
    issuer.unreachable = True
    clock.now += JWKS_CACHE_TTL_SECONDS - 1
    validator.verify(token)
    clock.now += 2
    _refused(validator, token, "unavailable")
    issuer.unreachable = False
    # Inside the backoff the issuer is not asked again.
    reads = len(issuer.fetches)
    _refused(validator, token, "unavailable")
    assert len(issuer.fetches) == reads
    clock.now += JWKS_FAILURE_BACKOFF_SECONDS + 1
    assert validator.verify(token).subject == SUBJECT


def test_a_failed_reread_keeps_keys_that_are_still_in_date(
    issuer: FakeIssuer, validator: AccessTokenValidator, clock: Clock
) -> None:
    token = issuer.access_token()
    validator.verify(token)
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    issuer.unreachable = True
    _refused(validator, issuer.access_token(headers={"kid": "unknown"}), "unavailable")
    assert validator.verify(token).subject == SUBJECT


def test_the_default_fetch_reads_https_only_and_follows_no_redirect() -> None:
    with pytest.raises(oauth.IssuerUnavailableError, match="https only"):
        oauth.https_get("http://issuer.example.test/.well-known/jwks.json")
    request = oauth.urllib.request.Request("https://issuer.example.test/")
    assert oauth._NoRedirect().redirect_request(request, None, 302, "Found", {}, "http://x") is None


# --- configuration -----------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_unset_issuer_is_a_startup_refusal(value: str | None) -> None:
    with pytest.raises(ConfigurationError, match="requires L9_MEMORY_HTTP_OAUTH_ISSUER"):
        validated_issuer(value)


@pytest.mark.parametrize(
    "value",
    [
        "http://issuer.example.test/",
        "issuer.example.test",
        "ftp://issuer.example.test/",
        "https://",
    ],
)
def test_an_issuer_that_is_not_https_is_a_startup_refusal(value: str) -> None:
    with pytest.raises(ConfigurationError, match="must be an https URL"):
        validated_issuer(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://user:pw@issuer.example.test/",
        "https://issuer.example.test/?tenant=a",
        "https://issuer.example.test/#frag",
    ],
)
def test_an_issuer_with_extra_url_parts_is_a_startup_refusal(value: str) -> None:
    with pytest.raises(ConfigurationError, match="must not carry"):
        validated_issuer(value)


def test_the_issuer_is_kept_exactly_as_configured() -> None:
    assert validated_issuer(ISSUER) == ISSUER
    assert validated_issuer(ISSUER.rstrip("/")) == ISSUER.rstrip("/")


def test_the_mode_and_issuer_load_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("L9_MEMORY_HTTP_AUTH_MODE", OAUTH_AUTH_METHOD)
    monkeypatch.setenv("L9_MEMORY_HTTP_OAUTH_ISSUER", ISSUER)
    settings = load_settings()
    assert settings.http_auth_mode == "oauth" == OAUTH_AUTH_METHOD
    assert settings.http_oauth_issuer == ISSUER


def test_the_issuer_has_no_default() -> None:
    settings = MemorySettings()
    assert settings.http_oauth_issuer is None
    assert settings.http_auth_mode == "bearer"


# --- principal and grants ----------------------------------------------------


def _settings() -> MemorySettings:
    return MemorySettings(
        http_auth_mode="oauth",
        http_oauth_issuer=ISSUER,
        local_tenant_id="l9",
        local_organization_id="quantum-l9",
        local_workspace_id="l9-workspace",
    )


def _server(issuer: FakeIssuer, grants: dict[str, Any]) -> OAuthResourceServer:
    return OAuthResourceServer(_settings(), grants=grants, fetch=issuer.fetch)


def test_the_principal_is_the_subject_and_names_no_actor(issuer: FakeIssuer) -> None:
    grants = {SUBJECT: {"read_namespaces": ["repo-a"], "write_namespaces": ["repo-a"]}}
    principal = _server(issuer, grants).authenticate(f"Bearer {issuer.access_token()}")
    assert principal.auth_method == OAUTH_AUTH_METHOD
    assert principal.principal_id == SUBJECT
    assert principal.agent_id is None and principal.user_id is None
    assert principal.read_namespaces == ("repo-a",)
    assert principal.write_namespaces == ("repo-a",)
    assert not principal.is_admin and not principal.is_global_admin
    assert (principal.tenant_id, principal.organization_id) == ("l9", "quantum-l9")
    assert CLIENT_ID not in principal.model_dump_json()


def test_claims_in_the_token_never_widen_the_grant(issuer: FakeIssuer) -> None:
    token = issuer.access_token(
        scope="admin memory:write",
        permissions=["admin"],
        roles=["admin"],
        is_admin=True,
        read_namespaces=["*"],
        tenant_id="other-tenant",
        agent_id="claude-code",
    )
    principal = _server(issuer, {SUBJECT: {"read_namespaces": ["repo-a"]}}).authenticate(
        f"Bearer {token}"
    )
    assert principal.read_namespaces == ("repo-a",)
    assert principal.write_namespaces == () and principal.roles == ()
    assert principal.tenant_id == "l9" and principal.agent_id is None
    assert not principal.is_admin


def test_a_subject_without_a_grant_holds_no_namespace(issuer: FakeIssuer) -> None:
    principal = _server(issuer, {}).authenticate(f"Bearer {issuer.access_token()}")
    assert principal.principal_id == SUBJECT
    assert principal.read_namespaces == principal.write_namespaces == ()
    assert principal.promote_namespaces == principal.maintain_namespaces == ()


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer   "])
def test_a_request_without_a_bearer_token_is_refused(issuer: FakeIssuer, header: Any) -> None:
    with pytest.raises(AuthenticationError):
        _server(issuer, {}).authenticate(header)
    assert issuer.fetches == []


def test_an_administrator_grant_is_a_startup_refusal(issuer: FakeIssuer) -> None:
    with pytest.raises(ConfigurationError, match="grants is_admin") as raised:
        _server(issuer, {SUBJECT: {"read_namespaces": ["*"], "is_admin": True}})
    assert SUBJECT not in str(raised.value)


@pytest.mark.parametrize(
    "grant",
    [
        "repo-a",
        ["repo-a"],
        {"read_namespaces": "repo-a"},
        {"maintain_namespaces": ["repo-a"]},
        {"principal_id": "someone-else"},
        {"agent_id": "claude-code"},
        {"is_global_admin": True},
    ],
)
def test_a_malformed_grant_is_a_startup_refusal(issuer: FakeIssuer, grant: Any) -> None:
    with pytest.raises(ConfigurationError, match=OAUTH_GRANTS_ENV):
        _server(issuer, {SUBJECT: grant})


def test_the_grant_map_is_required_and_may_grant_nobody(
    issuer: FakeIssuer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(OAUTH_GRANTS_ENV, raising=False)
    with pytest.raises(ConfigurationError, match=f"requires {OAUTH_GRANTS_ENV}"):
        OAuthResourceServer.from_environment(_settings(), fetch=issuer.fetch)
    monkeypatch.setenv(OAUTH_GRANTS_ENV, "[]")
    with pytest.raises(ConfigurationError, match="must be a JSON object"):
        OAuthResourceServer.from_environment(_settings(), fetch=issuer.fetch)
    monkeypatch.setenv(OAUTH_GRANTS_ENV, "{}")
    server = OAuthResourceServer.from_environment(_settings(), fetch=issuer.fetch)
    assert server.issuer == ISSUER
    assert issuer.fetches == [], "startup reads nothing from the issuer"


def test_a_missing_issuer_is_reported_before_a_missing_grant_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OAUTH_GRANTS_ENV, raising=False)
    with pytest.raises(ConfigurationError, match="L9_MEMORY_HTTP_OAUTH_ISSUER"):
        OAuthResourceServer.from_environment(MemorySettings(http_auth_mode="oauth"))


# --- protected resource metadata ---------------------------------------------


def test_the_metadata_names_the_one_resource_and_the_configured_issuer() -> None:
    document = protected_resource_metadata(ISSUER)
    assert document["resource"] == MEMORY_RESOURCE_IDENTIFIER
    assert document["authorization_servers"] == [ISSUER]
    assert document["bearer_methods_supported"] == ["header"]


def test_the_metadata_location_is_derived_from_the_resource_path() -> None:
    assert PROTECTED_RESOURCE_METADATA_PATH == "/.well-known/oauth-protected-resource/mcp"
    host = MEMORY_RESOURCE_IDENTIFIER.removesuffix("/mcp")
    assert PROTECTED_RESOURCE_METADATA_URL == host + PROTECTED_RESOURCE_METADATA_PATH
