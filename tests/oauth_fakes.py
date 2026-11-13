"""A local authorization server for the OAuth resource-server tests (ADR-102).

Everything here runs in the test process. Keys are generated when the tests
run and exist nowhere else, the issuer is a reserved ``.test`` name that never
resolves, and no request leaves the machine: the resource server reads the
issuer's documents through :meth:`FakeIssuer.fetch`.

A token this issuer signs proves the validation code. It is not the live PKCE
receipt ADR-100 requires, and no test here claims it is.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from l9_graphite_memory.version import MEMORY_RESOURCE_IDENTIFIER

ISSUER = "https://issuer.example.test/"
OTHER_ISSUER = "https://other-issuer.example.test/"
CLIENT_ID = "public-client-for-tests"
SUBJECT = "user|reader-0001"
OTHER_RESOURCE = "https://other-api.example.test/v1"
KEY_ID = "issuer-key-1"


@functools.cache
def rsa_key(index: int = 0, bits: int = 2048) -> rsa.RSAPrivateKey:
    """One RSA key per index for the whole run; generation is the slow part."""

    del index
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


@functools.cache
def ec_key(index: int = 0) -> ec.EllipticCurvePrivateKey:
    del index
    return ec.generate_private_key(ec.SECP256R1())


def public_jwk(key: Any, key_id: str, *, algorithm: str = "RS256") -> dict[str, Any]:
    """The public JWK an issuer would publish for ``key``."""

    encoder = ECAlgorithm if isinstance(key, ec.EllipticCurvePrivateKey) else RSAAlgorithm
    document = json.loads(encoder.to_jwk(key.public_key()))
    document.update({"kid": key_id, "use": "sig", "alg": algorithm})
    return dict(document)


def public_pem(key: Any) -> bytes:
    return bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _segment(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def unsigned_token(claims: dict[str, Any], *, key_id: str = KEY_ID) -> str:
    """An ``alg: none`` token: a header, a payload and an empty signature."""

    return f"{_segment({'alg': 'none', 'typ': 'JWT', 'kid': key_id})}.{_segment(claims)}."


def hmac_token(claims: dict[str, Any], secret: bytes, *, key_id: str = KEY_ID) -> str:
    """An HS256 token signed with ``secret``.

    Built by hand because the JWT library refuses to sign with an asymmetric
    key as an HMAC secret, which is exactly the forgery this is used to test.
    """

    signing_input = f"{_segment({'alg': 'HS256', 'typ': 'JWT', 'kid': key_id})}.{_segment(claims)}"
    signature = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')}"


class FakeIssuer:
    """An authorization server that lives in the test process.

    It publishes metadata and a key set, signs access tokens, and runs the
    authorization-code grant with PKCE the way a resource-indicator-aware
    server does: a token is issued for the resource the request named, and a
    resource it does not know is refused.
    """

    def __init__(self, issuer: str = ISSUER, *, key_id: str = KEY_ID) -> None:
        self.issuer = issuer
        self.base = issuer.rstrip("/")
        self.key_id = key_id
        self.key: Any = rsa_key(0)
        self.algorithm = "RS256"
        self.fetches: list[str] = []
        self.unreachable = False
        self.extra_keys: list[dict[str, Any]] = []
        self.publish_own_key = True
        # Resources this server issues tokens for. A request naming anything
        # else is refused unless `ignores_resource` models a server that
        # falls back to a default audience.
        self.resources = {MEMORY_RESOURCE_IDENTIFIER}
        self.ignores_resource = False
        self.subject = SUBJECT
        self.authorizations: list[dict[str, str]] = []
        self.token_requests: list[dict[str, str]] = []
        self._codes: dict[str, dict[str, str]] = {}

    # --- documents ----------------------------------------------------------

    @property
    def metadata_url(self) -> str:
        return f"{self.base}/.well-known/openid-configuration"

    @property
    def jwks_url(self) -> str:
        return f"{self.base}/.well-known/jwks.json"

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.base}/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{self.base}/oauth/token"

    def metadata(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "jwks_uri": self.jwks_url,
            "code_challenge_methods_supported": ["S256"],
        }

    def jwks(self) -> dict[str, Any]:
        keys = list(self.extra_keys)
        if self.publish_own_key:
            keys.insert(0, public_jwk(self.key, self.key_id, algorithm=self.algorithm))
        return {"keys": keys}

    def fetch(self, url: str) -> bytes:
        """The resource server's only way to reach this issuer."""

        self.fetches.append(url)
        if self.unreachable:
            raise OSError("issuer is unreachable")
        if url == self.metadata_url:
            return json.dumps(self.metadata()).encode("utf-8")
        if url == self.jwks_url:
            return json.dumps(self.jwks()).encode("utf-8")
        raise OSError(f"no such issuer document: {url}")

    def key_set_reads(self) -> int:
        return self.fetches.count(self.jwks_url)

    # --- tokens -------------------------------------------------------------

    def claims(self, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "sub": self.subject,
            "aud": MEMORY_RESOURCE_IDENTIFIER,
            "azp": CLIENT_ID,
            "iat": now,
            "exp": now + 600,
        }
        claims.update(overrides)
        return {name: value for name, value in claims.items() if value is not None}

    def access_token(
        self,
        *,
        key: Any | None = None,
        algorithm: str | None = None,
        headers: dict[str, Any] | None = None,
        **claims: Any,
    ) -> str:
        """A signed access token. ``None`` for a claim leaves that claim out."""

        sent_headers: dict[str, Any] = {"kid": self.key_id}
        sent_headers.update(headers or {})
        sent_headers = {name: value for name, value in sent_headers.items() if value is not None}
        return str(
            jwt.encode(
                self.claims(**claims),
                key if key is not None else self.key,
                algorithm=algorithm or self.algorithm,
                headers=sent_headers,
            )
        )

    # --- authorization code with PKCE ---------------------------------------

    def authorize(self, url: str) -> str:
        """Answer an authorization request with the redirect a browser follows."""

        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == self.authorization_endpoint
        query = {name: values[0] for name, values in parse_qs(parts.query).items()}
        self.authorizations.append(query)
        redirect_uri = query["redirect_uri"]
        answer: dict[str, str] = {"state": query.get("state", "")}
        resource = query.get("resource", "")
        if query.get("response_type") != "code" or query.get("code_challenge_method") != "S256":
            answer.update(error="invalid_request", error_description="PKCE S256 is required")
        elif not self.ignores_resource and resource not in self.resources:
            answer.update(error="access_denied", error_description="Service not found")
        else:
            code = secrets.token_urlsafe(24)
            self._codes[code] = query
            answer["code"] = code
        return f"{redirect_uri}?{urlencode(answer)}"

    def token(self, form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        """The token endpoint: one-time code, bound redirect, PKCE verifier."""

        self.token_requests.append(dict(form))
        granted = self._codes.pop(form.get("code", ""), None)
        if form.get("grant_type") != "authorization_code" or granted is None:
            return 400, {"error": "invalid_grant"}
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(form.get("code_verifier", "").encode("ascii")).digest()
            )
            .decode("ascii")
            .rstrip("=")
        )
        if (
            challenge != granted["code_challenge"]
            or form.get("redirect_uri") != granted["redirect_uri"]
            or form.get("client_id") != granted["client_id"]
        ):
            return 400, {"error": "invalid_grant"}
        if form.get("resource", "") != granted.get("resource", ""):
            return 400, {"error": "invalid_target"}
        audience = MEMORY_RESOURCE_IDENTIFIER if self.ignores_resource else granted["resource"]
        return 200, {
            "access_token": self.access_token(aud=audience, azp=granted["client_id"]),
            "token_type": "Bearer",
            "expires_in": 600,
        }
