"""The operator PKCE receipt tool, against an issuer in this process (ADR-102).

The tool runs for real: a loopback redirect listener, a real Memory server on
a loopback port in OAuth mode, and the package's own token validator. Only the
authorization server is a fake, and nothing leaves the machine. A receipt
produced here is a test artifact, not the live receipt ADR-100 requires.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")
pytest.importorskip("jwt", reason="OAuth validation requires the [server] extra")

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz import oauth
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.server import create_http_app
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import MEMORY_RESOURCE_IDENTIFIER
from tests.integration.remote_mcp_harness import serve
from tests.oauth_fakes import CLIENT_ID, ISSUER, OTHER_RESOURCE, SUBJECT, FakeIssuer

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "assurance" / "oauth_pkce_receipt.py"


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("oauth_pkce_receipt", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through it
    spec.loader.exec_module(module)
    return module


tool = _load_tool()
CHECKS = {
    "unauthenticated_request_refused",
    "matching_resource_token_issued",
    "token_is_audience_bound",
    "memory_admits_token",
    "memory_refuses_altered_token",
    "mismatched_resource_refused",
}


class Transport(tool.Http):  # type: ignore[misc]
    """Issuer requests go to the in-process issuer; Memory requests go over TCP."""

    def __init__(self, issuer: FakeIssuer) -> None:
        super().__init__()
        self.issuer = issuer
        self.tokens: list[str] = []

    def get(self, url: str) -> bytes:
        return self.issuer.fetch(url)

    def post_form(self, url: str, form: dict[str, str]) -> Any:
        assert url == self.issuer.token_endpoint
        status, body = self.issuer.token(form)
        if "access_token" in body:
            self.tokens.append(body["access_token"])
        return tool.HttpResponse(status, {}, json.dumps(body).encode("utf-8"))


def _browser(issuer: FakeIssuer) -> Callable[[str], None]:
    """A browser: ask the issuer, then follow its redirect to the loopback listener."""

    def follow(location: str) -> None:
        with urllib.request.urlopen(location, timeout=10) as response:
            response.read()

    def open_url(url: str) -> None:
        threading.Thread(target=follow, args=(issuer.authorize(url),), daemon=True).start()

    return open_url


def _memory(settings: MemorySettings) -> Iterator[str]:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    runtime = MemoryRuntime(settings=settings, service=service)
    try:
        with serve(create_http_app(runtime)) as url:
            yield url
    finally:
        runtime.close()


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> FakeIssuer:
    fake = FakeIssuer()
    monkeypatch.setattr(oauth, "https_get", fake.fetch)
    monkeypatch.setenv(oauth.OAUTH_GRANTS_ENV, "{}")
    return fake


@pytest.fixture
def memory_url(issuer: FakeIssuer) -> Iterator[str]:
    yield from _memory(MemorySettings(http_auth_mode="oauth", http_oauth_issuer=ISSUER))


def _run(issuer: FakeIssuer, memory_url: str, **overrides: Any) -> tuple[dict[str, Any], Transport]:
    transport = Transport(issuer)
    browser = overrides.pop("open_browser", None) or _browser(issuer)
    request = tool.ReceiptRequest(
        issuer=ISSUER,
        client_id=CLIENT_ID,
        memory_url=memory_url,
        redirect_port=0,
        timeout_seconds=overrides.pop("timeout_seconds", 20),
        **overrides,
    )
    return tool.run_receipt(request, transport=transport, open_browser=browser), transport


def _assert_holds_no_secret(receipt: dict[str, Any], transport: Transport) -> None:
    rendered = json.dumps(receipt)
    assert transport.tokens, "the run obtained at least one token"
    for token in transport.tokens:
        assert token not in rendered
        for segment in token.split("."):
            assert segment not in rendered
    for name in (CLIENT_ID, ISSUER, ISSUER.rstrip("/"), SUBJECT):
        assert name not in rendered
    for request in transport.issuer.token_requests:
        assert request["code"] not in rendered and request["code_verifier"] not in rendered


def test_a_bound_token_and_a_refused_mismatch_produce_a_passing_receipt(
    issuer: FakeIssuer, memory_url: str
) -> None:
    receipt, transport = _run(issuer, memory_url)

    assert receipt["schema"] == "l9.memory.oauth-pkce-receipt/v1"
    assert receipt["status"] == "passed" and receipt["failed_checks"] == []
    assert set(receipt["checks"]) == CHECKS
    assert all(check["passed"] for check in receipt["checks"].values())

    bound = receipt["checks"]["token_is_audience_bound"]
    assert bound["audience_contains_resource"] and bound["issuer_matches"]
    assert bound["algorithm"] == "RS256" and bound["client_id_claim_matches"]
    assert bound["access_token_sha256"] == tool.sha256(transport.tokens[0])
    assert bound["subject_sha256"] == tool.sha256(SUBJECT)
    assert receipt["checks"]["unauthenticated_request_refused"]["http_status"] == 401
    assert receipt["checks"]["memory_admits_token"]["http_status"] == 200
    assert receipt["checks"]["memory_refuses_altered_token"]["http_status"] == 401
    mismatch = receipt["checks"]["mismatched_resource_refused"]
    assert mismatch["outcome"] == "authorization_server_refused"
    assert mismatch["stage"] == "refused_at_authorization" and mismatch["error"] == "access_denied"

    subject = receipt["subject"]
    assert subject["resource"] == MEMORY_RESOURCE_IDENTIFIER
    assert subject["memory_endpoint"] == f"{memory_url}/mcp"
    assert subject["issuer_sha256"] == tool.sha256(ISSUER)
    assert subject["client_id_sha256"] == tool.sha256(CLIENT_ID)
    assert subject["memory_server"]["name"] == "l9-graphite-memory"
    assert subject["tool_sha256"] == tool.sha256(TOOL_PATH.read_bytes())
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == tool.sha256(json.dumps(body, sort_keys=True))
    _assert_holds_no_secret(receipt, transport)


def test_the_requests_are_public_client_pkce_naming_the_resource(
    issuer: FakeIssuer, memory_url: str
) -> None:
    _run(issuer, memory_url, scope="memory:read")
    matching, mismatched = issuer.authorizations
    assert matching["resource"] == MEMORY_RESOURCE_IDENTIFIER
    assert mismatched["resource"] == tool.DEFAULT_MISMATCHED_RESOURCE != MEMORY_RESOURCE_IDENTIFIER
    for sent in issuer.authorizations:
        assert sent["response_type"] == "code" and sent["code_challenge_method"] == "S256"
        assert sent["client_id"] == CLIENT_ID and sent["scope"] == "memory:read"
        assert sent["redirect_uri"].startswith("http://127.0.0.1:")
        assert sent["redirect_uri"].endswith("/callback")
        assert len(sent["code_challenge"]) == 43 and "audience" not in sent
    assert matching["state"] != mismatched["state"]
    assert matching["code_challenge"] != mismatched["code_challenge"]
    (exchange,) = issuer.token_requests
    assert exchange["resource"] == MEMORY_RESOURCE_IDENTIFIER
    assert exchange["grant_type"] == "authorization_code"
    assert 43 <= len(exchange["code_verifier"]) <= 128
    assert "client_secret" not in exchange


def test_a_token_for_another_resource_is_refused_by_the_resource_server(
    issuer: FakeIssuer, memory_url: str
) -> None:
    issuer.resources.add(OTHER_RESOURCE)
    receipt, transport = _run(issuer, memory_url, mismatched_resource=OTHER_RESOURCE)
    mismatch = receipt["checks"]["mismatched_resource_refused"]
    assert receipt["status"] == "passed"
    assert mismatch["outcome"] == "resource_server_refused" and mismatch["http_status"] == 401
    assert "audience" in mismatch["validator_refusal"]
    assert len(transport.tokens) == 2
    _assert_holds_no_secret(receipt, transport)


def test_a_server_that_ignores_the_resource_fails_the_receipt(
    issuer: FakeIssuer, memory_url: str
) -> None:
    # A default audience makes the matching leg pass and proves no binding.
    issuer.ignores_resource = True
    receipt, transport = _run(issuer, memory_url)
    assert receipt["status"] == "failed"
    assert receipt["failed_checks"] == ["mismatched_resource_refused"]
    mismatch = receipt["checks"]["mismatched_resource_refused"]
    assert mismatch["outcome"] == "memory_audience_token_issued_for_mismatched_resource"
    _assert_holds_no_secret(receipt, transport)


def test_a_token_not_bound_to_the_memory_resource_fails_the_receipt(
    issuer: FakeIssuer, memory_url: str
) -> None:
    # A server that does not read `resource` and issues its own audience.
    issue = issuer.access_token
    issuer.access_token = lambda **claims: issue(**{**claims, "aud": OTHER_RESOURCE})  # type: ignore[method-assign]
    receipt, transport = _run(issuer, memory_url)
    assert receipt["status"] == "failed"
    assert {"token_is_audience_bound", "memory_admits_token"} <= set(receipt["failed_checks"])
    assert "audience" in receipt["checks"]["token_is_audience_bound"]["refusal"]
    assert receipt["checks"]["memory_admits_token"]["http_status"] == 401
    _assert_holds_no_secret(receipt, transport)


def test_an_endpoint_that_admits_everything_fails_the_receipt(issuer: FakeIssuer) -> None:
    open_settings = MemorySettings(http_auth_required=False, http_auth_mode="bearer")
    for memory_url in _memory(open_settings):
        receipt, _ = _run(issuer, memory_url)
    assert receipt["status"] == "failed"
    assert {"unauthenticated_request_refused", "memory_refuses_altered_token"} <= set(
        receipt["failed_checks"]
    )
    assert receipt["checks"]["unauthenticated_request_refused"]["http_status"] == 200


def test_an_unanswered_authorization_is_not_evaluated_and_never_passes(
    issuer: FakeIssuer, memory_url: str
) -> None:
    receipt, _ = _run(issuer, memory_url, timeout_seconds=0.3, open_browser=lambda url: None)
    assert receipt["status"] == "failed"
    assert receipt["checks"]["unauthenticated_request_refused"]["passed"]
    assert receipt["checks"]["matching_resource_token_issued"]["outcome"] == (
        "no_authorization_response"
    )
    for name in ("token_is_audience_bound", "memory_admits_token", "memory_refuses_altered_token"):
        assert receipt["checks"][name]["outcome"] == "not_evaluated"
    mismatch = receipt["checks"]["mismatched_resource_refused"]
    assert mismatch == {
        "passed": False,
        "outcome": "not_evaluated",
        "reason": "no_authorization_response",
    }


def test_an_answer_with_another_state_is_not_accepted(issuer: FakeIssuer, memory_url: str) -> None:
    def forged(url: str) -> None:
        location = issuer.authorize(url).replace("state=", "state=forged")
        threading.Thread(
            target=lambda: urllib.request.urlopen(location, timeout=10).read(), daemon=True
        ).start()

    receipt, _ = _run(issuer, memory_url, open_browser=forged)
    assert receipt["status"] == "failed"
    assert receipt["checks"]["matching_resource_token_issued"]["outcome"] == "state_mismatch"
    assert issuer.token_requests == [], "no code is redeemed for an unsolicited answer"


@pytest.mark.parametrize(
    ("base", "endpoint"),
    [
        ("https://memory.example.test", "https://memory.example.test/mcp"),
        ("https://memory.example.test/", "https://memory.example.test/mcp"),
        ("https://memory.example.test/mcp", "https://memory.example.test/mcp"),
        ("https://memory.example.test/mcp/", "https://memory.example.test/mcp"),
        ("http://127.0.0.1:8200", "http://127.0.0.1:8200/mcp"),
        ("http://localhost:8200", "http://localhost:8200/mcp"),
    ],
)
def test_the_memory_endpoint_is_the_canonical_path(base: str, endpoint: str) -> None:
    assert tool.memory_endpoint(base) == endpoint


@pytest.mark.parametrize(
    "base",
    [
        "http://memory.example.test",
        "memory.example.test",
        "https://user:pw@memory.example.test",
        "https://memory.example.test/?token=x",
        "ftp://memory.example.test",
    ],
)
def test_an_unsafe_memory_url_is_refused(base: str) -> None:
    with pytest.raises(tool.ReceiptError):
        tool.memory_endpoint(base)


@pytest.mark.parametrize(
    "arguments",
    [
        {"issuer": "http://issuer.example.test/"},
        {"issuer": "https://issuer.example.test/?x=1"},
        {"client_id": "  "},
        {"mismatched_resource": MEMORY_RESOURCE_IDENTIFIER},
        {"memory_url": "http://memory.example.test"},
    ],
)
def test_bad_arguments_stop_the_run_before_any_request(arguments: dict[str, str]) -> None:
    issuer = FakeIssuer()
    values = {"issuer": ISSUER, "client_id": CLIENT_ID, "memory_url": "http://127.0.0.1:9"}
    values.update(arguments)
    with pytest.raises(tool.ReceiptError):
        tool.run_receipt(
            tool.ReceiptRequest(**values),
            transport=Transport(issuer),
            open_browser=lambda url: None,
        )
    assert issuer.fetches == [] and issuer.authorizations == []


def test_metadata_naming_another_issuer_stops_the_run() -> None:
    issuer = FakeIssuer()
    issuer.issuer = "https://other-issuer.example.test/"
    with pytest.raises(tool.ReceiptError, match="does not name the issuer"):
        tool.run_receipt(
            tool.ReceiptRequest(
                issuer=ISSUER, client_id=CLIENT_ID, memory_url="http://127.0.0.1:9"
            ),
            transport=Transport(issuer),
            open_browser=lambda url: None,
        )


def test_a_receipt_file_is_created_once_and_never_replaced(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    tool.write_receipt({"schema": tool.RECEIPT_SCHEMA, "status": "failed"}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"
    with pytest.raises(FileExistsError):
        tool.write_receipt({"status": "passed"}, path)
    arguments = ["--issuer", ISSUER, "--client-id", CLIENT_ID, "--memory-url", "http://127.0.0.1:9"]
    assert tool.main([*arguments, "--output", str(path)]) == 2
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"


def test_the_command_refuses_an_issuer_that_is_not_https(tmp_path: Path, capsys: Any) -> None:
    path = tmp_path / "receipt.json"
    code = tool.main(
        [
            "--issuer",
            "http://issuer.example.test/",
            "--client-id",
            CLIENT_ID,
            "--memory-url",
            "http://127.0.0.1:9",
            "--output",
            str(path),
            "--no-browser",
        ]
    )
    assert code == 2 and not path.exists()
    assert "https" in capsys.readouterr().err
