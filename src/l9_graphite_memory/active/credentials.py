# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/credentials.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Secret-file and structured credential resolution for Redis backends.

Implements ADR-066. Supports, in strict precedence order:

  1. `url_file`             — a mounted secret file containing a full
                               Redis connection URL.
  2. host/port + password_file — structured connection fields with a
                               mounted password secret file.
  3. `secret_provider_reference` — an opaque reference resolved by a
                               consumer-supplied secret provider
                               callback (e.g. Docker secrets, Vault,
                               a cloud secret manager). This module
                               does not implement any specific provider;
                               it only defines the resolution contract.
  4. `url_env`               — an environment variable containing a
                               full Redis connection URL. Lowest
                               precedence; intended for local
                               development only.

Exactly one credential source may be configured. Configuring more than
one non-null source is a hard configuration error (ambiguous
precedence is never silently resolved).
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MAX_SECRET_FILE_BYTES = 16384


class CredentialResolutionError(ValueError):
    """Raised when a Redis credential cannot be resolved or is invalid."""


class AmbiguousCredentialSourceError(CredentialResolutionError):
    """Raised when more than one credential source is configured."""


@dataclass(frozen=True, slots=True)
class RedisCredentialSettings:
    """Declarative configuration for exactly one credential source.

    Attributes:
        username: Optional Redis ACL username (not a secret by itself).
        password_file: Path to a mounted file containing the password.
        url_file: Path to a mounted file containing a full Redis URL.
        url_env: Name of an environment variable containing a full
            Redis URL. Lowest-precedence, development-oriented source.
        secret_provider_reference: Opaque reference string resolved via
            a caller-supplied `secret_provider` callback.
        host: Redis host, used only with `password_file`.
        port: Redis port, used only with `password_file`.
        database: Redis logical database index, used only with
            `password_file`.
        tls: Whether to require TLS, used only with `password_file`.
    """

    username: str | None = None
    password_file: Path | None = None
    url_file: Path | None = None
    url_env: str | None = None
    secret_provider_reference: str | None = None
    host: str | None = None
    port: int = 6379
    database: int = 0
    tls: bool = True


@dataclass(frozen=True, slots=True)
class ResolvedRedisCredential:
    """Fully resolved, ready-to-use Redis connection parameters.

    `redis_url` is the sole connection string handed to the Redis
    client constructor. It is never logged; callers MUST redact it in
    any diagnostic output (see `redacted_summary()`).
    """

    redis_url: str
    credential_source: str

    def redacted_summary(self) -> dict[str, object]:
        """Return a safe-to-log summary with no credential material."""
        parts = urlsplit(self.redis_url)
        return {
            "credential_source": self.credential_source,
            "scheme": parts.scheme,
            "host": parts.hostname,
            "port": parts.port,
            "username_configured": bool(parts.username),
        }


def _read_secret_file(path: Path, *, field_name: str) -> str:
    if not path.is_absolute():
        raise CredentialResolutionError(
            f"{field_name} must be an absolute path: {path}"
        )
    if path.is_symlink():
        raise CredentialResolutionError(f"{field_name} must not be a symlink: {path}")
    if not path.exists():
        raise CredentialResolutionError(f"{field_name} does not exist: {path}")
    file_stat = path.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise CredentialResolutionError(f"{field_name} must be a regular file: {path}")
    if file_stat.st_size > MAX_SECRET_FILE_BYTES:
        raise CredentialResolutionError(
            f"{field_name} exceeds maximum size of {MAX_SECRET_FILE_BYTES} bytes: {path}"
        )
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise CredentialResolutionError(
            f"{field_name} must not contain NUL bytes: {path}"
        )
    text = raw.decode("utf-8")
    text = text.removesuffix("\n")
    if not text:
        raise CredentialResolutionError(f"{field_name} must not be empty: {path}")
    return text


def _resolve_url_file(settings: RedisCredentialSettings) -> ResolvedRedisCredential:
    assert settings.url_file is not None
    url = _read_secret_file(settings.url_file, field_name="url_file")
    _validate_redis_url(url)
    return ResolvedRedisCredential(redis_url=url, credential_source="url_file")


def _resolve_password_file(settings: RedisCredentialSettings) -> ResolvedRedisCredential:
    assert settings.password_file is not None
    if not settings.host:
        raise CredentialResolutionError(
            "host is required when password_file is configured"
        )
    password = _read_secret_file(settings.password_file, field_name="password_file")
    scheme = "rediss" if settings.tls else "redis"
    userinfo = (
        f"{settings.username}:{password}" if settings.username else f":{password}"
    )
    netloc = f"{userinfo}@{settings.host}:{settings.port}"
    url = urlunsplit((scheme, netloc, f"/{settings.database}", "", ""))
    return ResolvedRedisCredential(redis_url=url, credential_source="password_file")


def _resolve_secret_provider_reference(
    settings: RedisCredentialSettings, secret_provider: Callable[[str], str] | None
) -> ResolvedRedisCredential:
    assert settings.secret_provider_reference is not None
    if secret_provider is None:
        raise CredentialResolutionError(
            "secret_provider_reference is configured but no "
            "secret_provider callback was supplied"
        )
    url = secret_provider(settings.secret_provider_reference)
    if not url:
        raise CredentialResolutionError(
            "secret_provider callback returned an empty value"
        )
    _validate_redis_url(url)
    return ResolvedRedisCredential(
        redis_url=url, credential_source="secret_provider_reference"
    )


def _resolve_url_env(
    settings: RedisCredentialSettings, environ: dict[str, str]
) -> ResolvedRedisCredential:
    assert settings.url_env is not None
    env_url = environ.get(settings.url_env)
    if not env_url:
        raise CredentialResolutionError(
            f"environment variable {settings.url_env!r} is not set or empty"
        )
    _validate_redis_url(env_url)
    return ResolvedRedisCredential(redis_url=env_url, credential_source="url_env")


def _configured_sources(settings: RedisCredentialSettings) -> list[str]:
    return [
        name
        for name, value in (
            ("url_file", settings.url_file),
            ("password_file", settings.password_file),
            ("secret_provider_reference", settings.secret_provider_reference),
            ("url_env", settings.url_env),
        )
        if value
    ]


def resolve_redis_credential(
    settings: RedisCredentialSettings,
    *,
    secret_provider: Callable[[str], str] | None = None,
    environ: dict[str, str] | None = None,
) -> ResolvedRedisCredential:
    """Resolve exactly one configured credential source into a Redis URL.

    Args:
        settings: The declarative credential configuration.
        secret_provider: Required only if `secret_provider_reference` is
            set. Called with the reference string and must return the
            resolved secret value (a full Redis URL or password,
            depending on the provider's contract — this function treats
            the returned value as a full Redis URL).
        environ: Optional environment mapping override, primarily for
            testing. Defaults to `os.environ`.

    Returns:
        A `ResolvedRedisCredential` with a ready-to-use `redis_url`.

    Raises:
        AmbiguousCredentialSourceError: if more than one source is
            configured.
        CredentialResolutionError: if the configured source is missing,
            unreadable, malformed, or if no source is configured.
    """
    resolved_environ = environ if environ is not None else dict(os.environ)
    configured_sources = _configured_sources(settings)

    if len(configured_sources) == 0:
        raise CredentialResolutionError(
            "no Redis credential source configured; exactly one of "
            "url_file, password_file (with host), secret_provider_reference, "
            "or url_env is required"
        )
    if len(configured_sources) > 1:
        raise AmbiguousCredentialSourceError(
            f"multiple Redis credential sources configured: {configured_sources}; "
            "exactly one must be set"
        )

    source = configured_sources[0]
    if source == "url_file":
        return _resolve_url_file(settings)
    if source == "password_file":
        return _resolve_password_file(settings)
    if source == "secret_provider_reference":
        return _resolve_secret_provider_reference(settings, secret_provider)
    assert source == "url_env"
    return _resolve_url_env(settings, resolved_environ)


def _validate_redis_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("redis", "rediss"):
        raise CredentialResolutionError(
            f"Redis URL must use redis:// or rediss:// scheme, got: {parts.scheme!r}"
        )
    if not parts.hostname:
        raise CredentialResolutionError("Redis URL must include a hostname")
