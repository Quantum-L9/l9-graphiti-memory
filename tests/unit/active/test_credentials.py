# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/active/test_credentials.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Unit tests for l9_graphite_memory.active.credentials."""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.active.credentials import (
    AmbiguousCredentialSourceError,
    CredentialResolutionError,
    RedisCredentialSettings,
    resolve_redis_credential,
)


def test_no_source_configured_raises(tmp_path: Path) -> None:
    settings = RedisCredentialSettings()
    with pytest.raises(CredentialResolutionError):
        resolve_redis_credential(settings)


def test_multiple_sources_configured_raises(tmp_path: Path) -> None:
    url_file = tmp_path / "url"
    url_file.write_text("redis://localhost:6379/0\n")
    settings = RedisCredentialSettings(url_file=url_file, url_env="SOME_VAR")
    with pytest.raises(AmbiguousCredentialSourceError):
        resolve_redis_credential(settings, environ={"SOME_VAR": "redis://x/0"})


def test_url_file_resolves(tmp_path: Path) -> None:
    url_file = tmp_path / "url"
    url_file.write_text("redis://active-redis:6379/0\n")
    settings = RedisCredentialSettings(url_file=url_file)
    resolved = resolve_redis_credential(settings)
    assert resolved.redis_url == "redis://active-redis:6379/0"
    assert resolved.credential_source == "url_file"


def test_password_file_resolves_with_host(tmp_path: Path) -> None:
    password_file = tmp_path / "password"
    password_file.write_text("s3cret-value\n")
    settings = RedisCredentialSettings(
        username="active-memory",
        password_file=password_file,
        host="active-redis",
        port=6379,
        database=0,
        tls=False,
    )
    resolved = resolve_redis_credential(settings)
    assert resolved.redis_url == "redis://active-memory:s3cret-value@active-redis:6379/0"
    assert resolved.credential_source == "password_file"


def test_password_file_without_host_raises(tmp_path: Path) -> None:
    password_file = tmp_path / "password"
    password_file.write_text("s3cret\n")
    settings = RedisCredentialSettings(password_file=password_file)
    with pytest.raises(CredentialResolutionError):
        resolve_redis_credential(settings)


def test_url_env_resolves(tmp_path: Path) -> None:
    settings = RedisCredentialSettings(url_env="ACTIVE_MEMORY_REDIS_URL")
    resolved = resolve_redis_credential(
        settings, environ={"ACTIVE_MEMORY_REDIS_URL": "redis://localhost:6379/0"}
    )
    assert resolved.credential_source == "url_env"


def test_url_env_missing_raises(tmp_path: Path) -> None:
    settings = RedisCredentialSettings(url_env="MISSING_VAR")
    with pytest.raises(CredentialResolutionError):
        resolve_redis_credential(settings, environ={})


def test_secret_provider_reference_resolves(tmp_path: Path) -> None:
    settings = RedisCredentialSettings(secret_provider_reference="vault://secret/redis")

    def provider(reference: str) -> str:
        assert reference == "vault://secret/redis"
        return "redis://provider-resolved:6379/0"

    resolved = resolve_redis_credential(settings, secret_provider=provider)
    assert resolved.redis_url == "redis://provider-resolved:6379/0"


def test_secret_provider_reference_without_callback_raises(tmp_path: Path) -> None:
    settings = RedisCredentialSettings(secret_provider_reference="vault://secret/redis")
    with pytest.raises(CredentialResolutionError):
        resolve_redis_credential(settings)


def test_symlink_secret_file_rejected(tmp_path: Path) -> None:
    real_file = tmp_path / "real_password"
    real_file.write_text("s3cret\n")
    symlink = tmp_path / "password_link"
    symlink.symlink_to(real_file)
    settings = RedisCredentialSettings(password_file=symlink, host="active-redis")
    with pytest.raises(CredentialResolutionError):
        resolve_redis_credential(settings)


def test_oversized_secret_file_rejected(tmp_path: Path) -> None:
    oversized_file = tmp_path / "url"
    oversized_file.write_text("redis://" + ("a" * 20000) + ":6379/0")
    settings = RedisCredentialSettings(url_file=oversized_file)
    with pytest.raises(CredentialResolutionError):
        resolve_redis_credential(settings)


def test_redacted_summary_contains_no_secret(tmp_path: Path) -> None:
    password_file = tmp_path / "password"
    password_file.write_text("s3cret-value\n")
    settings = RedisCredentialSettings(
        username="active-memory",
        password_file=password_file,
        host="active-redis",
    )
    resolved = resolve_redis_credential(settings)
    summary = resolved.redacted_summary()
    assert "s3cret-value" not in str(summary)
    assert summary["host"] == "active-redis"
    assert summary["username_configured"] is True
