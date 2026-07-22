# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/config/loader.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Load settings from one optional YAML file and environment overrides."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from l9_graphite_memory.errors import ConfigurationError

from .models import MemorySettings, TokenPrincipalConfig

_ENV_TO_FIELD = {
    "L9_MEMORY_DATA_DIR": "data_dir",
    "L9_MEMORY_STATE_DIR": "state_dir",
    "L9_MEMORY_DATABASE_PATH": "database_path",
    "L9_MEMORY_REGISTRY_PATH": "registry_path",
    "L9_MEMORY_WORKSPACE_NAMESPACE": "workspace_namespace",
    "L9_MEMORY_ENABLED": "memory_enabled",
    "L9_MEMORY_WRITE_GATES": "write_gates_enabled",
    "L9_MEMORY_GATE_TTL_MINUTES": "gate_ttl_minutes",
    "L9_MEMORY_PROJECTION_BACKEND": "projection_backend",
    "GRAPHITI_MCP_URL": "graphiti_mcp_url",
    "GRAPHITI_MCP_TOKEN": "graphiti_mcp_token",
    "ZEP_API_KEY": "zep_api_key",
    "ZEP_API_URL": "zep_api_url",
    "L9_MEMORY_PROJECTION_REQUIRED": "projection_required",
    "L9_MEMORY_HTTP_AUTH_REQUIRED": "http_auth_required",
    "L9_MEMORY_LOCAL_PRINCIPAL_ID": "local_principal_id",
    "L9_MEMORY_LOCAL_TENANT_ID": "local_tenant_id",
    "L9_MEMORY_LOCAL_ORGANIZATION_ID": "local_organization_id",
    "L9_MEMORY_LOCAL_WORKSPACE_ID": "local_workspace_id",
    "L9_MEMORY_LOCAL_USER_ID": "local_user_id",
    "L9_MEMORY_LOCAL_AGENT_ID": "local_agent_id",
    "L9_MEMORY_LOCAL_READ_NAMESPACES": "local_read_namespaces",
    "L9_MEMORY_LOCAL_WRITE_NAMESPACES": "local_write_namespaces",
    "L9_MEMORY_LOCAL_PROMOTE_NAMESPACES": "local_promote_namespaces",
    "L9_MEMORY_LOCAL_IS_ADMIN": "local_is_admin",
    "L9_MEMORY_OUTBOX_BATCH_SIZE": "outbox_batch_size",
    "L9_MEMORY_OUTBOX_MAX_ATTEMPTS": "outbox_max_attempts",
    "L9_MEMORY_OUTBOX_BASE_DELAY_SECONDS": "outbox_base_delay_seconds",
    "L9_MEMORY_DEFAULT_SEARCH_LIMIT": "default_search_limit",
    "L9_MEMORY_DEFAULT_TOKEN_BUDGET": "default_token_budget",
    "L9_MEMORY_LOG_LEVEL": "log_level",
    "L9_MEMORY_JSON_LOGS": "json_logs",
}

_BOOL_FIELDS = {
    "memory_enabled",
    "write_gates_enabled",
    "projection_required",
    "http_auth_required",
    "json_logs",
    "local_is_admin",
}
_LIST_FIELDS = {
    "local_read_namespaces",
    "local_write_namespaces",
    "local_promote_namespaces",
}


_INT_FIELDS = {
    "gate_ttl_minutes",
    "outbox_batch_size",
    "outbox_max_attempts",
    "outbox_base_delay_seconds",
    "default_search_limit",
    "default_token_budget",
}


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"invalid boolean value: {value!r}")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigurationError(f"configuration file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigurationError("configuration root must be a mapping")
    return dict(raw)


def _load_auth_tokens() -> dict[str, TokenPrincipalConfig]:
    raw_json = os.environ.get("L9_MEMORY_AUTH_TOKENS_JSON", "").strip()
    path_value = os.environ.get("L9_MEMORY_AUTH_TOKENS_FILE", "").strip()
    if raw_json and path_value:
        raise ConfigurationError(
            "set only one of L9_MEMORY_AUTH_TOKENS_JSON or L9_MEMORY_AUTH_TOKENS_FILE"
        )
    if path_value:
        path = Path(path_value).expanduser()
        if not path.is_file():
            raise ConfigurationError(f"auth token file not found: {path}")
        raw_json = path.read_text(encoding="utf-8")
    if not raw_json:
        return {}
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"invalid token configuration JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ConfigurationError(
            "auth token configuration must be a token-to-principal mapping"
        )
    return {
        str(token): TokenPrincipalConfig.model_validate(claims)
        for token, claims in decoded.items()
    }


def load_settings(config_path: str | Path | None = None) -> MemorySettings:
    """Resolve canonical settings: defaults -> YAML -> environment."""

    selected = config_path or os.environ.get("L9_MEMORY_CONFIG")
    data: dict[str, Any] = {}
    source = "defaults"
    if selected:
        path = Path(selected).expanduser()
        data.update(_load_yaml(path))
        source = str(path)

    for env_name, field_name in _ENV_TO_FIELD.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        if field_name in _BOOL_FIELDS:
            value: Any = _parse_bool(raw)
        elif field_name in _LIST_FIELDS:
            value = tuple(item.strip() for item in raw.split(",") if item.strip())
        elif field_name in _INT_FIELDS:
            try:
                value = int(raw)
            except ValueError as exc:
                raise ConfigurationError(f"{env_name} must be an integer") from exc
        else:
            value = raw
        data[field_name] = value

    auth_tokens = _load_auth_tokens()
    if auth_tokens:
        data["auth_tokens"] = auth_tokens
    data["config_source"] = source

    try:
        settings = MemorySettings.model_validate(data)
    except Exception as exc:
        raise ConfigurationError(f"invalid memory settings: {exc}") from exc

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    settings.resolved_database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
