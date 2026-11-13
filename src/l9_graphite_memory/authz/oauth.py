"""OAuth 2.1 resource server for the Streamable HTTP transport (ADR-100, ADR-102).

The server is a resource server only. It issues nothing, proxies nothing and
stores no client secret: it validates an access token an external
authorization server issued for the Memory resource
(:data:`~l9_graphite_memory.version.MEMORY_RESOURCE_IDENTIFIER`) and derives a
principal from it.

Every request is validated on its own evidence:

``Authorization: Bearer <access token>``
    A JWT signed with an asymmetric algorithm by a key the configured issuer
    publishes. ``iss`` must equal the configured issuer exactly, ``aud`` must
    contain the Memory resource, ``exp`` and ``nbf`` are enforced, and the
    header must name the signing key (``kid``).

The verification keys come only from the configured issuer. A key carried in
the token (``jwk``), a key location named by it (``jku``, ``x5u``) and a
symmetric key are never used. When the issuer's keys cannot be obtained the
request is refused: there is no second door behind this one.

An OAuth subject is not an actor and not a surface (ADR-100). The principal
built here carries the verified subject, the namespaces a server-side grant
gives that subject, the client id the token names, and an agent identity only
when the operator bound that exact (subject, client id) pair to an actor in
``L9_MEMORY_OAUTH_ACTORS_JSON`` (ADR-103). A token issued without an end user
(the client-credentials grant) is refused: it has no subject a person stands
behind. ``MemoryService`` remains the only authorization decision.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from l9_graphite_memory.authz.signed_assertion import decode_json_object
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.contracts.identity import (
    ACTOR_REGISTRY_PREFIX,
    OAUTH_AUTH_METHOD,
    SURFACE_REGISTRY_PREFIX,
)
from l9_graphite_memory.errors import AuthenticationError, ConfigurationError
from l9_graphite_memory.observability import get_logger
from l9_graphite_memory.version import MEMORY_RESOURCE_IDENTIFIER, PACKAGE_VERSION

if TYPE_CHECKING:
    from l9_graphite_memory.config import MemorySettings

log = get_logger("l9.memory.oauth")

OAUTH_ISSUER_ENV = "L9_MEMORY_HTTP_OAUTH_ISSUER"
OAUTH_GRANTS_ENV = "L9_MEMORY_OAUTH_GRANTS_JSON"
OAUTH_ACTORS_ENV = "L9_MEMORY_OAUTH_ACTORS_JSON"

# Asymmetric signatures only. "none" and every HMAC algorithm are absent, so a
# token cannot be verified with material a client can know: an HS256 token
# signed with the issuer's public key is refused before any key is used.
ALLOWED_SIGNING_ALGORITHMS: tuple[str, ...] = ("RS256", "PS256", "ES256")
_ALGORITHM_KEY_TYPES = {"RS256": "RSA", "PS256": "RSA", "ES256": "EC"}
# JWK members that only a private or symmetric key carries. A key set that
# publishes one is not a set of verification keys.
_PRIVATE_JWK_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})

# Tolerated clock difference between the issuer and this server for exp, nbf
# and iat.
CLOCK_SKEW_SECONDS = 30
# An access token is a few hundred bytes to a few KiB. Anything this large is
# refused before it is parsed.
MAX_ACCESS_TOKEN_BYTES = 16_384
MAX_KEY_ID_LENGTH = 256
MAX_SUBJECT_LENGTH = 200

# Issuer metadata and key retrieval. Every bound is a ceiling on what one
# request to this server can make it do.
ISSUER_FETCH_TIMEOUT_SECONDS = 5.0
MAX_ISSUER_DOCUMENT_BYTES = 262_144
# Keys are trusted for this long after they were read. Past it they are read
# again, and if that fails the cached keys are dropped: a key the issuer has
# withdrawn stops verifying within one lifetime.
JWKS_CACHE_TTL_SECONDS = 600
# A token naming a key the cache does not hold triggers at most one re-read
# per interval, so a stream of invented key ids cannot turn into a stream of
# requests to the issuer.
JWKS_REFRESH_COOLDOWN_SECONDS = 60
# After a failed read the issuer is left alone for this long.
JWKS_FAILURE_BACKOFF_SECONDS = 5

_resource = urlsplit(MEMORY_RESOURCE_IDENTIFIER)
# RFC 9728 section 3.1: the well-known segment is inserted between the host
# and the resource's path. The host root is not claimed, because the Memory
# resource is one path on a host that also routes other resources.
PROTECTED_RESOURCE_METADATA_PATH = f"/.well-known/oauth-protected-resource{_resource.path}"
PROTECTED_RESOURCE_METADATA_URL = (
    f"{_resource.scheme}://{_resource.netloc}{PROTECTED_RESOURCE_METADATA_PATH}"
)

_UNKNOWN_SIGNING_KEY = "access token signing key is not published by the configured issuer"
_KEYS_UNAVAILABLE = "issuer signing keys are unavailable; the access token cannot be validated"
_MALFORMED = "access token is not a well-formed JWT"
_USERLESS = (
    "access token was issued without an end user (client credentials); "
    "a hosted Memory principal must be a user"
)
# Grant-type values that mean "no end user". Auth0 names the grant in ``gty``
# (``client-credentials``); the RFC spelling is ``client_credentials``.
_USERLESS_GRANT_TYPES = frozenset({"client-credentials", "client_credentials"})
# Auth0 appends this to the client id when the subject of a client-credentials
# token is the application itself. It is the platform's convention, not a
# tenant's naming.
_CLIENT_SUBJECT_SUFFIX = "@clients"
# Auth0's subject profile for a token whose subject is a person.
_USER_SUBJECT_PROFILE = "user"
MAX_COORDINATE_LENGTH = 300

Fetch = Callable[[str], bytes]
Clock = Callable[[], float]


class IssuerUnavailableError(Exception):
    """An issuer document could not be read, or is not what it must be."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: issuer documents are read from the URL configured."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Follow nothing; urllib then reports the 3xx response as an error."""


_OPENER = urllib.request.build_opener(_NoRedirect)


def https_get(
    url: str,
    *,
    timeout: float = ISSUER_FETCH_TIMEOUT_SECONDS,
    max_bytes: int = MAX_ISSUER_DOCUMENT_BYTES,
) -> bytes:
    """Read one issuer document over https, bounded in time and size.

    Redirects are refused, so a document is never read from a location the
    issuer's own metadata did not name.
    """

    if urlsplit(url).scheme != "https":
        raise IssuerUnavailableError("issuer documents are read over https only")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"l9-graphite-memory/{PACKAGE_VERSION}",
        },
        method="GET",
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
    except (OSError, http.client.HTTPException) as exc:  # URLError is an OSError
        raise IssuerUnavailableError(type(exc).__name__) from exc
    if not isinstance(body, bytes) or len(body) > max_bytes:
        raise IssuerUnavailableError("issuer document is too large")
    return body


def validated_issuer(value: str | None) -> str:
    """The configured issuer, or a startup refusal that says what is wrong.

    The value is returned as configured. It is compared with ``iss`` character
    for character, so it is never normalised here.
    """

    issuer = (value or "").strip()
    if not issuer:
        raise ConfigurationError(
            f"http_auth_mode={OAUTH_AUTH_METHOD} requires {OAUTH_ISSUER_ENV}: the "
            "authorization server's issuer URL, exactly as it appears in the "
            "access token's iss claim"
        )
    try:
        parts = urlsplit(issuer)
        host = parts.hostname
        credentials = parts.username or parts.password
    except ValueError as exc:
        raise ConfigurationError(f"{OAUTH_ISSUER_ENV} is not a valid URL") from exc
    if parts.scheme != "https" or not host:
        raise ConfigurationError(
            f"{OAUTH_ISSUER_ENV} must be an https URL; http_auth_mode={OAUTH_AUTH_METHOD} "
            "does not trust an issuer it cannot authenticate"
        )
    if credentials or parts.query or parts.fragment:
        raise ConfigurationError(
            f"{OAUTH_ISSUER_ENV} must not carry user information, a query or a fragment"
        )
    return issuer


def protected_resource_metadata(issuer: str) -> dict[str, Any]:
    """The RFC 9728 document for the Memory resource."""

    return {
        "resource": MEMORY_RESOURCE_IDENTIFIER,
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
        "resource_name": "L9 Graphite Memory",
    }


def _load_jwt() -> Any:
    """PyJWT with asymmetric support, or a startup refusal naming the extra."""

    try:
        import jwt
        from jwt.algorithms import has_crypto
    except ImportError as exc:
        raise ConfigurationError(
            f"http_auth_mode={OAUTH_AUTH_METHOD} requires PyJWT and cryptography; "
            "install l9-graphite-memory[server]"
        ) from exc
    if not has_crypto:
        raise ConfigurationError(
            f"http_auth_mode={OAUTH_AUTH_METHOD} requires cryptography for asymmetric "
            "signatures; install l9-graphite-memory[server]"
        )
    return jwt


def _fingerprint(value: str) -> str:
    """A short digest that names a subject in a log or an error without printing it."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class _KeySnapshot:
    keys: Mapping[str, Any]
    loaded_at: float


class IssuerKeys:
    """The configured issuer's verification keys, cached and refreshed in bounds.

    The key set location is read from the issuer's own metadata document,
    which must name the configured issuer. Nothing is read at construction:
    the first token that needs a key triggers the first read.
    """

    def __init__(self, issuer: str, *, jwt: Any, fetch: Fetch, clock: Clock) -> None:
        self._issuer = issuer
        self._jwt = jwt
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._jwks_uri: str | None = None
        self._snapshot: _KeySnapshot | None = None
        self._failed_at: float | None = None

    def key(self, key_id: str) -> Any:
        """The verification key for ``key_id``, or an authentication refusal."""

        snapshot = self._snapshot
        if snapshot is not None and self._clock() - snapshot.loaded_at < JWKS_CACHE_TTL_SECONDS:
            found = snapshot.keys.get(key_id)
            if found is not None:
                return found
        with self._lock:
            return self._key_locked(key_id)

    def _key_locked(self, key_id: str) -> Any:
        now = self._clock()
        snapshot = self._snapshot
        fresh = snapshot is not None and now - snapshot.loaded_at < JWKS_CACHE_TTL_SECONDS
        if snapshot is not None and fresh:
            found = snapshot.keys.get(key_id)
            if found is not None:
                return found
            if now - snapshot.loaded_at < JWKS_REFRESH_COOLDOWN_SECONDS:
                raise AuthenticationError(_UNKNOWN_SIGNING_KEY)
        if not fresh:
            # Expired keys verify nothing, whatever happens to the re-read.
            self._snapshot = None
        if self._failed_at is not None and now - self._failed_at < JWKS_FAILURE_BACKOFF_SECONDS:
            raise AuthenticationError(_KEYS_UNAVAILABLE)
        try:
            keys = self._read_keys()
        except IssuerUnavailableError as exc:
            self._failed_at = now
            log.warning("issuer signing keys could not be read", extra={"reason": str(exc)})
            raise AuthenticationError(_KEYS_UNAVAILABLE) from exc
        self._failed_at = None
        self._snapshot = _KeySnapshot(keys=keys, loaded_at=self._clock())
        found = keys.get(key_id)
        if found is None:
            raise AuthenticationError(_UNKNOWN_SIGNING_KEY)
        return found

    def _document(self, url: str) -> dict[str, Any]:
        try:
            raw = self._fetch(url)
        except OSError as exc:
            raise IssuerUnavailableError(type(exc).__name__) from exc
        try:
            document = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            raise IssuerUnavailableError("issuer document is not JSON") from exc
        if not isinstance(document, dict):
            raise IssuerUnavailableError("issuer document is not a JSON object")
        return document

    def _key_set_location(self) -> str:
        if self._jwks_uri is not None:
            return self._jwks_uri
        metadata = self._document(self._issuer.rstrip("/") + "/.well-known/openid-configuration")
        if metadata.get("issuer") != self._issuer:
            raise IssuerUnavailableError("issuer metadata names a different issuer")
        location = metadata.get("jwks_uri")
        if not isinstance(location, str) or urlsplit(location).scheme != "https":
            raise IssuerUnavailableError("issuer metadata names no https jwks_uri")
        self._jwks_uri = location
        return location

    def _read_keys(self) -> dict[str, Any]:
        entries = self._document(self._key_set_location()).get("keys")
        if not isinstance(entries, list):
            raise IssuerUnavailableError("issuer key set has no keys array")
        usable: dict[str, Any] = {}
        ambiguous: set[str] = set()
        for entry in entries:
            key_id, key = self._verification_key(entry)
            if key_id is None or key_id in ambiguous:
                continue
            if key_id in usable:
                # Two keys under one id: neither can be chosen, so neither is used.
                ambiguous.add(key_id)
                del usable[key_id]
                continue
            usable[key_id] = key
        if not usable:
            raise IssuerUnavailableError("issuer key set publishes no usable signing key")
        return usable

    def _verification_key(self, entry: Any) -> tuple[str | None, Any]:
        """One usable public signing key, or ``(None, None)`` for anything else."""

        if not isinstance(entry, dict):
            return None, None
        key_id = entry.get("kid")
        if not isinstance(key_id, str) or not key_id or len(key_id) > MAX_KEY_ID_LENGTH:
            return None, None
        if entry.get("use", "sig") != "sig" or _PRIVATE_JWK_MEMBERS & entry.keys():
            return None, None
        try:
            key = self._jwt.PyJWK(entry)
        except self._jwt.PyJWTError:
            return None, None
        algorithm = key.algorithm_name
        if _ALGORITHM_KEY_TYPES.get(algorithm) != entry.get("kty"):
            return None, None
        return key_id, key


@dataclass(frozen=True)
class VerifiedAccessToken:
    """What a validated access token established. It is not an actor."""

    subject: str
    client_id: str | None
    algorithm: str
    key_id: str
    claims: Mapping[str, Any]


class AccessTokenValidator:
    """Validate an access token issued by one issuer for the Memory resource."""

    def __init__(
        self,
        issuer: str,
        *,
        fetch: Fetch | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.issuer = validated_issuer(issuer)
        self.audience = MEMORY_RESOURCE_IDENTIFIER
        self._jwt = _load_jwt()
        self._keys = IssuerKeys(
            self.issuer,
            jwt=self._jwt,
            fetch=fetch or https_get,
            clock=clock or time.monotonic,
        )

    def verify(self, token: str) -> VerifiedAccessToken:
        """Return the validated token, or raise ``AuthenticationError``.

        Order: shape, algorithm allow-list, key id, the issuer's key, then the
        signature and the claims. Nothing in a refusal repeats the token.
        """

        jwt = self._jwt
        if not token or len(token) > MAX_ACCESS_TOKEN_BYTES or not token.isascii():
            raise AuthenticationError(_MALFORMED)
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError(_MALFORMED) from exc
        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or algorithm not in ALLOWED_SIGNING_ALGORITHMS:
            raise AuthenticationError("access token signing algorithm is not allowed")
        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id or len(key_id) > MAX_KEY_ID_LENGTH:
            raise AuthenticationError("access token does not name its signing key (kid)")
        key = self._keys.key(key_id)
        claims = self._decode(token, key)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > MAX_SUBJECT_LENGTH:
            raise AuthenticationError("access token subject is not usable")
        client_id = claims.get("azp", claims.get("client_id"))
        client_id = client_id if isinstance(client_id, str) and client_id else None
        if _is_userless(claims, subject=subject, client_id=client_id):
            log.warning(
                "user-less access token refused",
                extra={"subject_fingerprint": _fingerprint(subject)},
            )
            raise AuthenticationError(_USERLESS)
        return VerifiedAccessToken(
            subject=subject,
            client_id=client_id,
            algorithm=algorithm,
            key_id=key_id,
            claims=claims,
        )

    def _decode(self, token: str, key: Any) -> dict[str, Any]:
        jwt = self._jwt
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(ALLOWED_SIGNING_ALGORITHMS),
                audience=self.audience,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "enforce_minimum_key_length": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("access token has expired") from exc
        except jwt.ImmatureSignatureError as exc:
            raise AuthenticationError("access token is not yet valid") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthenticationError(
                "access token was not issued by the configured issuer"
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthenticationError(
                "access token audience does not include the Memory resource"
            ) from exc
        except jwt.MissingRequiredClaimError as exc:
            raise AuthenticationError(f"access token is missing the {exc.claim} claim") from exc
        except jwt.InvalidAlgorithmError as exc:
            raise AuthenticationError("access token signing algorithm is not allowed") from exc
        except jwt.InvalidSignatureError as exc:
            raise AuthenticationError("access token signature is not valid") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"access token is not valid: {type(exc).__name__}") from exc
        return dict(claims)


def _is_userless(claims: Mapping[str, Any], *, subject: str, client_id: str | None) -> bool:
    """Whether a validated token stands for no end user.

    Any one signal is enough, so a token that drops one of them is still
    caught by another:

    - a grant-type claim (``gty``, or ``grant_type``) naming client
      credentials, as a string or in a list;
    - a subject ending in ``@clients``, Auth0's subject for an application;
    - a subject equal to a client id the token names (``azp`` or
      ``client_id``): RFC 9068 section 2.2 makes the client the subject when
      no resource owner is involved, and Auth0 does the same for an API with
      agent subject claims;
    - a subject profile (``sub_profile``) other than ``user``, such as Auth0's
      ``ai_agent`` for an agent authenticated as itself.

    A token with none of them is a user token as far as this server can tell.
    """

    for name in ("gty", "grant_type"):
        value = claims.get(name)
        values = value if isinstance(value, list) else [value]
        if any(isinstance(item, str) and item in _USERLESS_GRANT_TYPES for item in values):
            return True
    if subject.endswith(_CLIENT_SUBJECT_SUFFIX):
        return True
    named_clients = {client_id, claims.get("azp"), claims.get("client_id")}
    if subject in {value for value in named_clients if isinstance(value, str) and value}:
        return True
    profile = claims.get("sub_profile")
    return profile is not None and profile != _USER_SUBJECT_PROFILE


class OAuthSubjectGrant(BaseModel):
    """Namespaces one OAuth subject may use, from ``L9_MEMORY_OAUTH_GRANTS_JSON``.

    The grant is server-side configuration keyed by the verified ``sub``. It is
    not an identity: it names no principal, no user and no agent, so it cannot
    turn a subject into an actor. ``is_admin`` exists only so that an
    administrator grant is refused by name at startup.
    """

    model_config = ConfigDict(extra="forbid")

    roles: tuple[str, ...] = ()
    read_namespaces: tuple[str, ...] = ()
    write_namespaces: tuple[str, ...] = ()
    promote_namespaces: tuple[str, ...] = ()
    is_admin: bool = False


def subject_grants_from_config(raw: Mapping[str, Any]) -> dict[str, OAuthSubjectGrant]:
    """Validate the decoded grant map, or refuse to start.

    Every entry is checked now, so a malformed grant stops the server instead
    of surfacing on one subject's request. Subjects are named by fingerprint.
    """

    grants: dict[str, OAuthSubjectGrant] = {}
    for subject, value in raw.items():
        if not isinstance(subject, str) or not subject or len(subject) > MAX_SUBJECT_LENGTH:
            raise ConfigurationError(f"{OAUTH_GRANTS_ENV} keys must be non-empty token subjects")
        name = f"subject fingerprint={_fingerprint(subject)}"
        if not isinstance(value, dict):
            raise ConfigurationError(f"{OAUTH_GRANTS_ENV} grant for {name} must be a JSON object")
        try:
            grant = OAuthSubjectGrant.model_validate(value)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
                for error in exc.errors()
            )
            raise ConfigurationError(
                f"malformed OAuth grant for {name} in {OAUTH_GRANTS_ENV}: {details}"
            ) from exc
        if grant.is_admin:
            raise ConfigurationError(
                f"{OAUTH_GRANTS_ENV} grants is_admin to {name}; administrator authority "
                "is not reachable over HTTP (ADR-098, ADR-100)"
            )
        grants[subject] = grant
    return grants


class OAuthActorBinding(BaseModel):
    """One operator-declared actor for one verified (subject, client id) pair.

    Read from ``L9_MEMORY_OAUTH_ACTORS_JSON`` as
    ``{"<subject>": {"<client id>": {"actor_ref": ..., "surface_ref": ...}}}``.
    The token proves the subject and the client; the operator, in server-side
    configuration, states which actor that person runs through that client.
    The client id selects among the subject's bindings and resolves nothing
    on its own (ADR-100, ADR-103).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_ref: str
    surface_ref: str | None = None

    @field_validator("actor_ref")
    @classmethod
    def _actor_coordinate(cls, value: str) -> str:
        return _coordinate(value, ACTOR_REGISTRY_PREFIX, "actor_ref")

    @field_validator("surface_ref")
    @classmethod
    def _surface_coordinate(cls, value: str | None) -> str | None:
        return None if value is None else _coordinate(value, SURFACE_REGISTRY_PREFIX, "surface_ref")

    @property
    def actor_id(self) -> str:
        """The actor fragment, the same spelling a signed agent's ``agent_id`` has."""

        return self.actor_ref.removeprefix(ACTOR_REGISTRY_PREFIX)

    def digest(self, subject: str, client_id: str) -> str:
        """A digest binding this declaration to the pair it was declared for."""

        material = json.dumps(
            [subject, client_id, self.actor_ref, self.surface_ref],
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(material).hexdigest()


def _coordinate(value: str, prefix: str, field: str) -> str:
    fragment = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or not fragment
        or len(value) > MAX_COORDINATE_LENGTH
        or not fragment.isascii()
        or any(character.isspace() or character in "#/" for character in fragment)
    ):
        raise ValueError(f"{field} must be a {prefix}<id> coordinate")
    return value


ActorBindings = dict[str, dict[str, OAuthActorBinding]]


def actor_bindings_from_config(raw: Mapping[str, Any]) -> ActorBindings:
    """Validate the decoded actor map, or refuse to start.

    A binding whose actor fragment is the client id it is keyed under is
    refused: that would make a client id an actor by another name.
    """

    bindings: ActorBindings = {}
    for subject, clients in raw.items():
        if not isinstance(subject, str) or not subject or len(subject) > MAX_SUBJECT_LENGTH:
            raise ConfigurationError(f"{OAUTH_ACTORS_ENV} keys must be non-empty token subjects")
        name = f"subject fingerprint={_fingerprint(subject)}"
        if subject.endswith(_CLIENT_SUBJECT_SUFFIX):
            raise ConfigurationError(
                f"{OAUTH_ACTORS_ENV} binds {name}, an application subject; "
                "a hosted Memory principal must be a user"
            )
        if not isinstance(clients, dict) or not clients:
            raise ConfigurationError(
                f"{OAUTH_ACTORS_ENV} entry for {name} must map client ids to bindings"
            )
        resolved: dict[str, OAuthActorBinding] = {}
        for client_id, value in clients.items():
            if not isinstance(client_id, str) or not client_id or len(client_id) > 200:
                raise ConfigurationError(
                    f"{OAUTH_ACTORS_ENV} entry for {name} has an unusable client id"
                )
            client = f"client fingerprint={_fingerprint(client_id)}"
            if not isinstance(value, dict):
                raise ConfigurationError(
                    f"{OAUTH_ACTORS_ENV} binding for {name}, {client} must be a JSON object"
                )
            try:
                binding = OAuthActorBinding.model_validate(value)
            except ValidationError as exc:
                details = "; ".join(
                    f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
                    for error in exc.errors()
                )
                raise ConfigurationError(
                    f"malformed OAuth actor binding for {name}, {client} in "
                    f"{OAUTH_ACTORS_ENV}: {details}"
                ) from exc
            if binding.actor_id == client_id or binding.actor_id == subject:
                raise ConfigurationError(
                    f"{OAUTH_ACTORS_ENV} binding for {name}, {client} names the client "
                    "or the subject as the actor; an OAuth client is not an actor"
                )
            resolved[client_id] = binding
        bindings[subject] = resolved
    return bindings


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Authorization must use Bearer scheme")
    return token


class OAuthResourceServer:
    """Authenticate one request's access token and resolve its server-side grant."""

    def __init__(
        self,
        settings: MemorySettings,
        *,
        grants: Mapping[str, Any],
        actors: Mapping[str, Any] | None = None,
        fetch: Fetch | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._settings = settings
        self._validator = AccessTokenValidator(
            validated_issuer(settings.http_oauth_issuer), fetch=fetch, clock=clock
        )
        self._grants = subject_grants_from_config(grants)
        self._actors = actor_bindings_from_config(actors or {})

    @classmethod
    def from_environment(
        cls, settings: MemorySettings, *, fetch: Fetch | None = None
    ) -> OAuthResourceServer:
        """Build the resource server; a missing issuer or grant map stops startup."""

        # The issuer is checked first so its absence is the first thing said.
        validated_issuer(settings.http_oauth_issuer)
        raw = os.environ.get(OAUTH_GRANTS_ENV, "").strip()
        if not raw:
            raise ConfigurationError(
                f"http_auth_mode={OAUTH_AUTH_METHOD} requires {OAUTH_GRANTS_ENV}: a JSON "
                "object mapping a token subject to its namespaces ({} grants nobody)"
            )
        try:
            grants = decode_json_object(raw, OAUTH_GRANTS_ENV)
        except AuthenticationError as exc:
            raise ConfigurationError(str(exc)) from exc
        # The actor map is optional: absent, no (subject, client) pair has an
        # actor, so every consequential write is refused and reads still work.
        raw_actors = os.environ.get(OAUTH_ACTORS_ENV, "").strip()
        actors: Mapping[str, Any] = {}
        if raw_actors:
            try:
                actors = decode_json_object(raw_actors, OAUTH_ACTORS_ENV)
            except AuthenticationError as exc:
                raise ConfigurationError(str(exc)) from exc
        return cls(settings, grants=grants, actors=actors, fetch=fetch)

    @property
    def issuer(self) -> str:
        return self._validator.issuer

    @property
    def metadata(self) -> dict[str, Any]:
        return protected_resource_metadata(self._validator.issuer)

    def authenticate(self, authorization: str | None) -> MemoryPrincipal:
        """Return the principal for a valid access token, or raise.

        The subject is the principal and the client id rides alongside it as
        ``oauth_client_id``. ``agent_id`` is set only from an operator binding
        for this exact (subject, client id) pair, with the server-built
        evidence reference for that binding; otherwise it stays unset, because
        a validated token proves which subject the issuer authenticated, not
        which actor is calling. ``user_id`` stays unset. A subject without a
        grant is authenticated and holds no namespace.
        """

        verified = self._validator.verify(_bearer(authorization))
        grant = self._grants.get(verified.subject) or OAuthSubjectGrant()
        binding = (
            self._actors.get(verified.subject, {}).get(verified.client_id)
            if verified.client_id
            else None
        )
        actor_fields: dict[str, Any] = {}
        if binding is not None and verified.client_id is not None:
            actor_fields = {
                "agent_id": binding.actor_id,
                "surface_ref": binding.surface_ref,
                "actor_evidence_refs": (
                    (
                        f"oauth-actor-binding:{OAUTH_ACTORS_ENV}:"
                        f"{binding.digest(verified.subject, verified.client_id)}"
                    ),
                ),
            }
        return MemoryPrincipal(
            principal_id=verified.subject,
            tenant_id=self._settings.local_tenant_id,
            organization_id=self._settings.local_organization_id,
            workspace_id=self._settings.local_workspace_id,
            roles=grant.roles,
            read_namespaces=grant.read_namespaces,
            write_namespaces=grant.write_namespaces,
            promote_namespaces=grant.promote_namespaces,
            auth_method=OAUTH_AUTH_METHOD,
            oauth_client_id=verified.client_id,
            **actor_fields,
        )


__all__ = [
    "ALLOWED_SIGNING_ALGORITHMS",
    "OAUTH_ACTORS_ENV",
    "OAUTH_GRANTS_ENV",
    "OAUTH_ISSUER_ENV",
    "PROTECTED_RESOURCE_METADATA_PATH",
    "PROTECTED_RESOURCE_METADATA_URL",
    "AccessTokenValidator",
    "IssuerUnavailableError",
    "OAuthActorBinding",
    "OAuthResourceServer",
    "OAuthSubjectGrant",
    "VerifiedAccessToken",
    "actor_bindings_from_config",
    "https_get",
    "protected_resource_metadata",
    "validated_issuer",
]
