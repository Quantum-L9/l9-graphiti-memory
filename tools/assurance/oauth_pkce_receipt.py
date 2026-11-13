#!/usr/bin/env python3
"""Produce the live PKCE receipt for the Memory OAuth resource (ADR-100, ADR-102).

An operator runs this once against the real authorization server. It is not
run in CI and no test runs it against a live system.

What it does:

1. Asks the Memory endpoint for ``initialize`` with no credential and requires
   a ``401`` whose challenge names the protected-resource metadata. An
   endpoint that admits an unauthenticated request proves nothing below.
2. Runs authorization code with PKCE (S256) over a loopback redirect, as a
   public client, naming the Memory resource with the RFC 8707 ``resource``
   parameter on both the authorization and the token request.
3. Validates the returned access token with the package's own validator
   (signature against the issuer's published keys, exact issuer, audience,
   expiry) and presents it to the Memory endpoint, which must admit it.
4. Presents the same token with an altered signature, which must be refused.
5. Repeats the authorization naming a resource that is not the Memory
   resource. Either the authorization server refuses it, or it issues a token
   the validator and the Memory endpoint both refuse. A Memory-audience token
   for a mismatched resource fails the receipt.

The receipt holds claim metadata and digests. It never holds a token, a code,
a verifier, the client id or the issuer name. Every check is evaluated or
recorded as not evaluated; the receipt passes only when every check passed.

Authorization-server settings this tool assumes are listed in ADR-102.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import http.server
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from l9_graphite_memory.authz.oauth import (
    AccessTokenValidator,
    https_get,
    validated_issuer,
)
from l9_graphite_memory.errors import AuthenticationError, ConfigurationError
from l9_graphite_memory.version import (
    HTTP_MCP_PROTOCOL_VERSIONS,
    MEMORY_RESOURCE_IDENTIFIER,
    PACKAGE_VERSION,
)

RECEIPT_SCHEMA = "l9.memory.oauth-pkce-receipt/v1"
DEFAULT_REDIRECT_PORT = 8765
CALLBACK_PATH = "/callback"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MISMATCHED_RESOURCE = f"{MEMORY_RESOURCE_IDENTIFIER}/pkce-receipt-mismatched-resource"
HTTP_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 1_048_576
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
NOT_EVALUATED = "not_evaluated"


class ReceiptError(Exception):
    """The run cannot continue. The message never contains a credential."""


def sha256(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(data).hexdigest()


def memory_endpoint(base_url: str) -> str:
    """The MCP endpoint for a Memory base URL: https, or http on loopback only."""

    try:
        parts = urlsplit(base_url.strip())
        host = parts.hostname
        credentials = parts.username or parts.password
    except ValueError as exc:
        raise ReceiptError("the Memory URL is not a valid URL") from exc
    if parts.scheme not in {"https", "http"} or not host:
        raise ReceiptError("the Memory URL must be an https URL")
    if parts.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise ReceiptError("an http Memory URL is accepted for a loopback host only")
    if credentials or parts.query or parts.fragment:
        raise ReceiptError("the Memory URL must not carry user information, a query or a fragment")
    path = parts.path.rstrip("/")
    if not path.endswith("/mcp"):
        path += "/mcp"
    return f"{parts.scheme}://{parts.netloc}{path}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Follow nothing: a credential is sent only to the URL that was named."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any]:
        try:
            decoded = json.loads(self.body)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}


class Http:
    """The three requests the run makes. Tests replace the issuer side."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirect)

    def get(self, url: str) -> bytes:
        """One issuer document, https only, bounded, no redirect."""

        return https_get(url, timeout=HTTP_TIMEOUT_SECONDS)

    def post_form(self, url: str, form: dict[str, str]) -> HttpResponse:
        """The token request of a public client: no client secret is sent."""

        if urlsplit(url).scheme != "https":
            raise ReceiptError("the token endpoint must be https")
        return self._send(
            url,
            urlencode(form).encode("ascii"),
            {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )

    def post_mcp(self, url: str, message: dict[str, Any], token: str | None) -> HttpResponse:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self._send(url, json.dumps(message).encode("utf-8"), headers)

    def _send(self, url: str, body: bytes, headers: dict[str, str]) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return HttpResponse(
                    response.status, dict(response.headers), response.read(MAX_RESPONSE_BYTES)
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, dict(exc.headers), exc.read(MAX_RESPONSE_BYTES))
        except (OSError, http.client.HTTPException) as exc:
            raise ReceiptError(
                f"{urlsplit(url).netloc} is unreachable: {type(exc).__name__}"
            ) from exc


class LoopbackCallback:
    """Receive one authorization response on ``http://127.0.0.1:<port>/callback``."""

    def __init__(self, port: int) -> None:
        self.result: dict[str, str] | None = None
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                if parts.path != CALLBACK_PATH:
                    self.send_error(404)
                    return
                query = parse_qs(parts.query)
                outer.result = {name: values[0] for name, values in query.items()}
                page = b"<p>The authorization response was received. Close this window.</p>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, format: str, *args: Any) -> None:
                """Stay silent: the request line carries the authorization code."""

        try:
            self._server = http.server.HTTPServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            raise ReceiptError(f"cannot listen on 127.0.0.1:{port}: {type(exc).__name__}") from exc
        self._server.timeout = 0.25
        self.redirect_uri = f"http://127.0.0.1:{self._server.server_address[1]}{CALLBACK_PATH}"

    def wait(self, timeout: float) -> dict[str, str] | None:
        deadline = time.monotonic() + timeout
        while self.result is None and time.monotonic() < deadline:
            self._server.handle_request()
        return self.result

    def close(self) -> None:
        self._server.server_close()


@dataclass(frozen=True)
class ReceiptRequest:
    issuer: str
    client_id: str
    memory_url: str
    redirect_port: int = DEFAULT_REDIRECT_PORT
    scope: str | None = None
    mismatched_resource: str = DEFAULT_MISMATCHED_RESOURCE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class _Authorization:
    """How one authorization attempt ended. ``token`` never leaves this process."""

    outcome: str
    token: str | None = None
    detail: dict[str, Any] | None = None


def _server_metadata(issuer: str, transport: Http) -> dict[str, str]:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        document = json.loads(transport.get(url))
    except Exception as exc:  # any failure to read it ends the run the same way
        raise ReceiptError(
            f"authorization server metadata is unavailable: {type(exc).__name__}"
        ) from exc
    if not isinstance(document, dict) or document.get("issuer") != issuer:
        raise ReceiptError("authorization server metadata does not name the issuer given")
    endpoints: dict[str, str] = {}
    for name in ("authorization_endpoint", "token_endpoint"):
        value = document.get(name)
        if not isinstance(value, str) or urlsplit(value).scheme != "https":
            raise ReceiptError(f"authorization server metadata has no https {name}")
        endpoints[name] = value
    methods = document.get("code_challenge_methods_supported")
    if isinstance(methods, list) and "S256" not in methods:
        raise ReceiptError("the authorization server does not advertise PKCE S256")
    return endpoints


def _authorize(
    request: ReceiptRequest,
    endpoints: dict[str, str],
    resource: str,
    *,
    transport: Http,
    open_browser: Callable[[str], Any],
) -> _Authorization:
    """One authorization-code grant with PKCE for ``resource``."""

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    callback = LoopbackCallback(request.redirect_port)
    try:
        query = {
            "response_type": "code",
            "client_id": request.client_id,
            "redirect_uri": callback.redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": resource,
        }
        if request.scope:
            query["scope"] = request.scope
        url = f"{endpoints['authorization_endpoint']}?{urlencode(query)}"
        sys.stdout.write(f"\nOpen this URL to authorize the request for {resource}:\n{url}\n")
        sys.stdout.flush()
        open_browser(url)
        answer = callback.wait(request.timeout_seconds)
        redirect_uri = callback.redirect_uri
    finally:
        callback.close()
    if answer is None:
        return _Authorization("no_authorization_response")
    if answer.get("state") != state:
        return _Authorization("state_mismatch")
    if "error" in answer or "code" not in answer:
        return _Authorization(
            "refused_at_authorization",
            detail={
                "error": answer.get("error", "")[:64],
                "error_description_sha256": sha256(answer.get("error_description", "")),
            },
        )
    form = {
        "grant_type": "authorization_code",
        "client_id": request.client_id,
        "code": answer["code"],
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "resource": resource,
    }
    response = transport.post_form(endpoints["token_endpoint"], form)
    body = response.json()
    token = body.get("access_token")
    if response.status != 200 or not isinstance(token, str) or not token:
        error = body.get("error")
        return _Authorization(
            "refused_at_token",
            detail={
                "http_status": response.status,
                "error": error[:64] if isinstance(error, str) else None,
            },
        )
    token_type = body.get("token_type")
    return _Authorization(
        "token_issued",
        token=token,
        detail={
            "token_type": token_type[:32] if isinstance(token_type, str) else None,
            "expires_in": body.get("expires_in")
            if isinstance(body.get("expires_in"), int)
            else None,
            "refresh_token_returned": "refresh_token" in body,
            "id_token_returned": "id_token" in body,
        },
    )


def _initialize(endpoint: str, transport: Http, token: str | None) -> HttpResponse:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": HTTP_MCP_PROTOCOL_VERSIONS[0],
            "capabilities": {},
            "clientInfo": {"name": "l9-oauth-pkce-receipt", "version": PACKAGE_VERSION},
        },
    }
    return transport.post_mcp(endpoint, message, token)


def _challenge(response: HttpResponse) -> str:
    for name, value in response.headers.items():
        if name.lower() == "www-authenticate":
            return value
    return ""


def _altered(token: str) -> str:
    """The same token with one signature character changed."""

    head, _, signature = token.rpartition(".")
    if not head or not signature:
        return token + "x"
    replacement = "A" if signature[0] != "A" else "B"
    return f"{head}.{replacement}{signature[1:]}"


def _claim_metadata(verified: Any, request: ReceiptRequest) -> dict[str, Any]:
    """What the receipt may say about a validated token: metadata and digests."""

    claims = verified.claims
    audience = claims.get("aud")
    audiences = [audience] if isinstance(audience, str) else list(audience or [])
    expires, issued = claims.get("exp"), claims.get("iat")
    scope = claims.get("scope")
    return {
        "algorithm": verified.algorithm,
        "key_id_sha256": sha256(verified.key_id),
        "claim_names": sorted(claims),
        "issuer_matches": claims.get("iss") == request.issuer,
        "audience_contains_resource": MEMORY_RESOURCE_IDENTIFIER in audiences,
        "audience_count": len(audiences),
        "audience_sha256": sorted(sha256(str(item)) for item in audiences),
        "subject_sha256": sha256(verified.subject),
        "client_id_claim_matches": verified.client_id == request.client_id,
        "expires_at": expires if isinstance(expires, int) else None,
        "issued_at": issued if isinstance(issued, int) else None,
        "lifetime_seconds": expires - issued
        if isinstance(expires, int) and isinstance(issued, int)
        else None,
        "not_before_present": "nbf" in claims,
        "scope": sorted(scope.split()) if isinstance(scope, str) else None,
    }


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"passed": False, "outcome": NOT_EVALUATED, "reason": reason}


def run_receipt(
    request: ReceiptRequest,
    *,
    transport: Http | None = None,
    open_browser: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Run every check and return the receipt. Nothing is written here."""

    try:
        issuer = validated_issuer(request.issuer)
    except ConfigurationError as exc:
        raise ReceiptError("the issuer must be an https URL without a query or fragment") from exc
    if not request.client_id.strip():
        raise ReceiptError("a public client id is required")
    if request.mismatched_resource == MEMORY_RESOURCE_IDENTIFIER:
        raise ReceiptError("the mismatched resource must differ from the Memory resource")
    transport = transport or Http()
    open_browser = open_browser or webbrowser.open
    endpoint = memory_endpoint(request.memory_url)
    endpoints = _server_metadata(issuer, transport)
    validator = AccessTokenValidator(issuer, fetch=transport.get)
    secrets_seen: list[str] = []
    skipped = "the matching-resource authorization returned no token"
    checks: dict[str, dict[str, Any]] = {
        "unauthenticated_request_refused": _not_evaluated("not reached"),
        "matching_resource_token_issued": _not_evaluated("not reached"),
        "token_is_audience_bound": _not_evaluated(skipped),
        "memory_admits_token": _not_evaluated(skipped),
        "memory_refuses_altered_token": _not_evaluated(skipped),
        "mismatched_resource_refused": _not_evaluated("not reached"),
    }
    server_info: dict[str, Any] = {}

    # 1. An endpoint that admits no credential proves nothing about a token.
    bare = _initialize(endpoint, transport, None)
    challenge = _challenge(bare)
    checks["unauthenticated_request_refused"] = {
        "passed": bare.status == 401
        and challenge.lower().startswith("bearer")
        and "resource_metadata=" in challenge,
        "http_status": bare.status,
        "bearer_challenge": challenge.lower().startswith("bearer"),
        "challenge_names_resource_metadata": "resource_metadata=" in challenge,
    }

    # 2-4. The Memory resource.
    matching = _authorize(
        request,
        endpoints,
        MEMORY_RESOURCE_IDENTIFIER,
        transport=transport,
        open_browser=open_browser,
    )
    checks["matching_resource_token_issued"] = {
        "passed": matching.token is not None,
        "outcome": matching.outcome,
        **(matching.detail or {}),
    }
    if matching.token is not None:
        token = matching.token
        secrets_seen.append(token)
        try:
            verified = validator.verify(token)
        except AuthenticationError as exc:
            checks["token_is_audience_bound"] = {"passed": False, "refusal": str(exc)}
        else:
            metadata = _claim_metadata(verified, request)
            checks["token_is_audience_bound"] = {
                "passed": metadata["audience_contains_resource"] and metadata["issuer_matches"],
                "access_token_sha256": sha256(token),
                **metadata,
            }
        admitted = _initialize(endpoint, transport, token)
        result = admitted.json().get("result")
        info = result.get("serverInfo") if isinstance(result, dict) else None
        if isinstance(info, dict):
            server_info = {
                "name": str(info.get("name", ""))[:64],
                "version": str(info.get("version", ""))[:32],
            }
        checks["memory_admits_token"] = {
            "passed": admitted.status == 200 and isinstance(result, dict),
            "http_status": admitted.status,
        }
        altered = _initialize(endpoint, transport, _altered(token))
        checks["memory_refuses_altered_token"] = {
            "passed": altered.status == 401,
            "http_status": altered.status,
        }

    # 5. A resource that is not the Memory resource.
    mismatched = _authorize(
        request,
        endpoints,
        request.mismatched_resource,
        transport=transport,
        open_browser=open_browser,
    )
    checks["mismatched_resource_refused"] = _mismatch_check(
        mismatched, validator=validator, endpoint=endpoint, transport=transport
    )
    if mismatched.token is not None:
        secrets_seen.append(mismatched.token)

    failures = sorted(name for name, check in checks.items() if not check["passed"])
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "status": "passed" if not failures else "failed",
        "failed_checks": failures,
        "subject": {
            "resource": MEMORY_RESOURCE_IDENTIFIER,
            "resource_parameter": "resource",
            "mismatched_resource": request.mismatched_resource,
            "issuer_sha256": sha256(issuer),
            "client_id_sha256": sha256(request.client_id),
            "memory_endpoint": endpoint,
            "memory_server": server_info,
            "scope_requested": request.scope,
            "validator_package_version": PACKAGE_VERSION,
            "tool_sha256": sha256(Path(__file__).read_bytes()),
        },
        "checks": checks,
        "limits": (
            "Attests the observations above for this issuer, client and endpoint at "
            "this time. It grants no authority and admits no release."
        ),
    }
    rendered = json.dumps(receipt, sort_keys=True)
    for secret in (*secrets_seen, request.client_id, issuer):
        if secret in rendered:
            raise ReceiptError("refusing to write a receipt that contains a credential or a name")
    receipt["receipt_sha256"] = sha256(rendered)
    return receipt


def _mismatch_check(
    attempt: _Authorization,
    *,
    validator: AccessTokenValidator,
    endpoint: str,
    transport: Http,
) -> dict[str, Any]:
    """Refused by the authorization server, or by the resource server, or failed."""

    if attempt.outcome in {"refused_at_authorization", "refused_at_token"}:
        return {
            "passed": True,
            "outcome": "authorization_server_refused",
            "stage": attempt.outcome,
            **(attempt.detail or {}),
        }
    if attempt.token is None:
        # No answer is not a refusal: the check was not completed.
        return _not_evaluated(attempt.outcome)
    try:
        validator.verify(attempt.token)
    except AuthenticationError as exc:
        local_refusal = str(exc)
    else:
        return {
            "passed": False,
            "outcome": "memory_audience_token_issued_for_mismatched_resource",
        }
    presented = _initialize(endpoint, transport, attempt.token)
    return {
        "passed": presented.status == 401,
        "outcome": "resource_server_refused"
        if presented.status == 401
        else "resource_server_admitted_mismatched_token",
        "validator_refusal": local_refusal,
        "http_status": presented.status,
    }


def write_receipt(receipt: dict[str, Any], path: Path) -> None:
    """Create the receipt file; an existing file is never replaced."""

    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produce the live PKCE receipt for the Memory OAuth resource."
    )
    parser.add_argument("--issuer", required=True, help="issuer URL, exactly as in the iss claim")
    parser.add_argument("--client-id", required=True, help="public (no secret) client id")
    parser.add_argument("--memory-url", required=True, help="Memory base URL serving /mcp")
    parser.add_argument("--output", required=True, type=Path, help="receipt file to create")
    parser.add_argument("--redirect-port", type=int, default=DEFAULT_REDIRECT_PORT)
    parser.add_argument("--scope", default=None, help="optional scope to request")
    parser.add_argument("--mismatched-resource", default=DEFAULT_MISMATCHED_RESOURCE)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--no-browser", action="store_true", help="print the URLs instead of opening them"
    )
    args = parser.parse_args(argv)
    if args.output.exists():
        sys.stderr.write(f"FAIL: {args.output} already exists; a receipt is never replaced\n")
        return 2
    request = ReceiptRequest(
        issuer=args.issuer,
        client_id=args.client_id,
        memory_url=args.memory_url,
        redirect_port=args.redirect_port,
        scope=args.scope,
        mismatched_resource=args.mismatched_resource,
        timeout_seconds=args.timeout,
    )
    try:
        receipt = run_receipt(request, open_browser=(lambda url: None) if args.no_browser else None)
        write_receipt(receipt, args.output)
    except (ReceiptError, ConfigurationError, OSError) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    if receipt["status"] != "passed":
        sys.stdout.write(
            f"FAIL: {', '.join(receipt['failed_checks'])}; receipt written to {args.output}\n"
        )
        return 1
    sys.stdout.write(f"PASS: PKCE receipt written to {args.output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
