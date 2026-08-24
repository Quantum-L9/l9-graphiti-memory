# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_http_mcp_transport_wire.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-28

"""Wire-level regression tests for HttpMcpTransport's real HTTP request cycle.

test_http_transport_dialect.py mocks list_tools()/call_tool() directly and
never exercises _rpc()/_headers()/_post()/_parse_body() against a real
request/response. These tests fill that gap: they patch
urllib.request.urlopen to return scripted HTTPResponse-like objects so the
actual Accept header, session handshake, and SSE-vs-JSON body parsing are
verified end to end.
"""

from __future__ import annotations

import io
import json
import sys
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.transport import HttpMcpTransport

if sys.version_info >= (3, 11):
    from typing import Self
else:  # Python 3.10 has no typing.Self; use the backport.
    from typing_extensions import Self


class _FakeResponse:
    def __init__(self, headers: Message, body: bytes) -> None:
        self.headers = headers
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _headers(content_type: str, session_id: str | None = None) -> Message:
    msg = Message()
    msg["content-type"] = content_type
    if session_id:
        msg["mcp-session-id"] = session_id
    return msg


def _sse_body(payload: dict) -> bytes:
    return f"event: message\ndata: {json.dumps(payload)}\n\n".encode()


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_headers_always_accept_both_json_and_event_stream() -> None:
    transport = HttpMcpTransport(url="https://graphiti.example")
    accept = transport._headers()["Accept"]
    assert "application/json" in accept
    assert "text/event-stream" in accept


def test_initialize_then_tools_list_reuses_session_id() -> None:
    transport = HttpMcpTransport(url="https://graphiti.example")
    calls: list[dict] = []

    responses = [
        _FakeResponse(
            _headers("application/json", session_id="abc123"),
            _json_body({"jsonrpc": "2.0", "id": "l9-memory-init", "result": {}}),
        ),
        _FakeResponse(
            _headers("application/json", session_id="abc123"),
            _json_body({"jsonrpc": "2.0", "result": {}}),
        ),
        _FakeResponse(
            _headers("text/event-stream", session_id="abc123"),
            _sse_body(
                {
                    "jsonrpc": "2.0",
                    "id": "l9-memory",
                    "result": {"tools": [{"name": "add_memory"}]},
                }
            ),
        ),
    ]

    def fake_urlopen(request, timeout=None, context=None):
        calls.append(
            {
                "method": json.loads(request.data)["method"],
                "headers": dict(request.headers),
            }
        )
        return responses.pop(0)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        tools = transport.list_tools()

    assert tools == ["add_memory"]
    assert [c["method"] for c in calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    # The initialize call cannot carry a session id yet; every call after it must.
    assert "Mcp-session-id" not in calls[0]["headers"]
    assert calls[2]["headers"].get("Mcp-session-id") == "abc123"


def test_session_expiry_triggers_single_reinit_and_retry() -> None:
    transport = HttpMcpTransport(url="https://graphiti.example")
    transport._session_id = "stale-session"
    call_methods: list[str] = []

    def make_error() -> HTTPError:
        body = json.dumps({"error": {"message": "Bad Request: Missing session ID"}}).encode("utf-8")
        return HTTPError("https://graphiti.example/mcp", 400, "Bad Request", None, io.BytesIO(body))

    responses = [
        make_error(),
        _FakeResponse(_headers("application/json", session_id="fresh-session"), _json_body({})),
        _FakeResponse(_headers("application/json", session_id="fresh-session"), _json_body({})),
        _FakeResponse(
            _headers("text/event-stream", session_id="fresh-session"),
            _sse_body({"jsonrpc": "2.0", "result": {"tools": []}}),
        ),
    ]

    def fake_urlopen(request, timeout=None, context=None):
        call_methods.append(json.loads(request.data)["method"])
        item = responses.pop(0)
        if isinstance(item, HTTPError):
            raise item
        return item

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        tools = transport.list_tools()

    assert tools == []
    # First tools/list fails with a stale session, triggers exactly one
    # re-initialize (initialize + notifications/initialized), then one retry.
    assert call_methods == [
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    assert transport._session_id == "fresh-session"


def test_parse_body_rejects_unknown_content_type() -> None:
    with pytest.raises(ProjectionError, match="unsupported Content-Type"):
        HttpMcpTransport._parse_body("text/plain", b"not json")


def test_parse_body_handles_plain_json_response() -> None:
    decoded = HttpMcpTransport._parse_body(
        "application/json", _json_body({"jsonrpc": "2.0", "result": {"ok": True}})
    )
    assert decoded["result"] == {"ok": True}


def test_parse_body_handles_sse_framed_response() -> None:
    decoded = HttpMcpTransport._parse_body(
        "text/event-stream; charset=utf-8",
        _sse_body({"jsonrpc": "2.0", "result": {"ok": True}}),
    )
    assert decoded["result"] == {"ok": True}
