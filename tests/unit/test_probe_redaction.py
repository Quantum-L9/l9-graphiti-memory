# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_probe_redaction.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Probe receipts are durable evidence and must not carry credentials (F-16)."""

from __future__ import annotations

from l9_graphite_memory.client_config.mcp_probe import redact_stderr


def test_named_secret_values_are_redacted() -> None:
    text = "auth failed for token hunter2secret at 10:00"
    assert "hunter2secret" not in redact_stderr(text, {"GRAPHITI_MCP_TOKEN": "hunter2secret"})


def test_url_userinfo_is_redacted_even_when_the_variable_name_is_innocent() -> None:
    text = "ConnectionError: rediss://cache-user:S3cretPw@redis.internal:6380/0 refused"
    redacted = redact_stderr(
        text, {"REDIS_URL": "rediss://cache-user:S3cretPw@redis.internal:6380/0"}
    )
    assert "S3cretPw" not in redacted
    assert "cache-user" not in redacted
    assert "rediss://[REDACTED]@redis.internal:6380/0" in redacted


def test_urls_without_userinfo_are_left_intact() -> None:
    text = "connecting to https://graphiti.example/mcp"
    assert redact_stderr(text, {}) == text
