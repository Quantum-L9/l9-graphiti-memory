# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/secrets.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Infisical Universal Auth adapter with environment-only fallback."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

log = logging.getLogger("l9.memory.secrets")


@dataclass(frozen=True)
class LoadSecretsResult:
    loaded: bool
    injected: int
    source: Literal["infisical", "environment"]


@dataclass(frozen=True)
class RefreshSecretsResult(LoadSecretsResult):
    refreshed_at: str


def env_flag(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def load_secrets_sync(
    *,
    required: bool | None = None,
    overwrite: bool = False,
    logger: logging.Logger | None = None,
) -> LoadSecretsResult:
    """Hydrate ``os.environ`` from Infisical when all three bootstrap values exist."""

    active_log = logger or log
    client_id = os.environ.get("INFISICAL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET", "").strip()
    project_id = os.environ.get("INFISICAL_PROJECT_ID", "").strip()
    is_required = (
        env_flag(os.environ.get("INFISICAL_REQUIRED")) if required is None else required
    )
    configured = [bool(client_id), bool(client_secret), bool(project_id)]
    if not all(configured):
        if any(configured):
            message = "Infisical is partially configured; client id, client secret, and project id are all required"
            if is_required:
                raise RuntimeError(message)
            active_log.warning(message)
        elif is_required:
            raise RuntimeError("Infisical is required but not configured")
        return LoadSecretsResult(loaded=False, injected=0, source="environment")

    try:
        from infisical_client import (
            AuthenticationOptions,
            ClientSettings,
            InfisicalClient,
            ListSecretsOptions,
            UniversalAuthMethod,
        )
    except ImportError as exc:
        if is_required:
            raise RuntimeError(
                "infisical-python is required; install l9-graphite-memory[infisical]"
            ) from exc
        active_log.warning(
            "infisical-python is unavailable; using existing environment"
        )
        return LoadSecretsResult(loaded=False, injected=0, source="environment")

    try:
        settings_kwargs: dict[str, Any] = {
            "auth": AuthenticationOptions(
                universal_auth=UniversalAuthMethod(
                    client_id=client_id, client_secret=client_secret
                )
            )
        }
        site_url = os.environ.get("INFISICAL_SITE_URL", "").strip()
        if site_url:
            settings_kwargs["site_url"] = site_url
        client = InfisicalClient(settings=ClientSettings(**settings_kwargs))
        secrets = client.listSecrets(
            options=ListSecretsOptions(
                environment=os.environ.get("INFISICAL_ENV", "prod"),
                project_id=project_id,
                path=os.environ.get("INFISICAL_SECRET_PATH", "/"),
                recursive=env_flag(os.environ.get("INFISICAL_RECURSIVE")),
                expand_secret_references=True,
                include_imports=True,
                attach_to_process_env=False,
            )
        )
        injected = 0
        for secret in secrets:
            value = secret.to_dict()
            key = value.get("secretKey") or value.get("secret_key")
            secret_value = value.get("secretValue") or value.get("secret_value")
            if (
                key
                and secret_value is not None
                and (overwrite or key not in os.environ)
            ):
                os.environ[str(key)] = str(secret_value)
                injected += 1
        active_log.info("loaded %d secrets from Infisical", injected)
        return LoadSecretsResult(loaded=True, injected=injected, source="infisical")
    except Exception as exc:
        if is_required:
            raise RuntimeError(f"Infisical secret load failed: {exc}") from exc
        active_log.warning(
            "Infisical secret load failed; using existing environment: %s", exc
        )
        return LoadSecretsResult(loaded=False, injected=0, source="environment")


async def load_secrets(**kwargs: Any) -> LoadSecretsResult:
    return load_secrets_sync(**kwargs)


async def refresh_secrets(
    *,
    logger: logging.Logger | None = None,
    on_refresh: Callable[[RefreshSecretsResult], None] | None = None,
) -> RefreshSecretsResult:
    base = load_secrets_sync(overwrite=True, logger=logger)
    result = RefreshSecretsResult(
        loaded=base.loaded,
        injected=base.injected,
        source=base.source,
        refreshed_at=datetime.now(timezone.utc).isoformat(),
    )
    if on_refresh:
        on_refresh(result)
    return result


def install_sighup_reload(
    *,
    logger: logging.Logger | None = None,
    on_refresh: Callable[[RefreshSecretsResult], None] | None = None,
) -> Callable[[], None]:
    active_log = logger or log
    if sys.platform == "win32" or not hasattr(signal, "SIGHUP"):
        active_log.info("SIGHUP reload is unavailable on this platform")
        return lambda: None

    def handler(_signum: int, _frame: object) -> None:
        try:
            base = load_secrets_sync(overwrite=True, logger=active_log)
            result = RefreshSecretsResult(
                loaded=base.loaded,
                injected=base.injected,
                source=base.source,
                refreshed_at=datetime.now(timezone.utc).isoformat(),
            )
            if on_refresh:
                on_refresh(result)
        except Exception:  # noqa: BLE001
            active_log.exception("secret refresh failed after SIGHUP")

    previous = signal.signal(signal.SIGHUP, handler)

    def uninstall() -> None:
        signal.signal(signal.SIGHUP, previous)

    return uninstall


def start_refresh_interval(
    interval_seconds: int = 900,
    *,
    logger: logging.Logger | None = None,
    on_refresh: Callable[[RefreshSecretsResult], None] | None = None,
) -> asyncio.Task[None]:
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be positive")

    async def loop() -> None:
        while True:
            await refresh_secrets(logger=logger, on_refresh=on_refresh)
            await asyncio.sleep(interval_seconds)

    return asyncio.create_task(loop())
