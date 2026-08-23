# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/config/models.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Typed configuration. Defaults live here and nowhere else."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TokenPrincipalConfig(BaseModel):
    """Principal claims associated with one server-side bearer token."""

    model_config = ConfigDict(extra="forbid")

    principal_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)
    organization_id: str = "default"
    workspace_id: str = "default"
    user_id: str | None = None
    agent_id: str | None = None
    roles: tuple[str, ...] = ()
    read_namespaces: tuple[str, ...] = ()
    write_namespaces: tuple[str, ...] = ()
    promote_namespaces: tuple[str, ...] = ()
    maintain_namespaces: tuple[str, ...] = ()
    is_admin: bool = False
    is_global_admin: bool = False


class MemorySettings(BaseModel):
    """Resolved process settings with explicit security and degradation behavior."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    data_dir: Path = Field(default_factory=lambda: Path("~/.local/share/l9-memory").expanduser())
    state_dir: Path = Field(default_factory=lambda: Path("~/.local/state/l9-memory").expanduser())
    # "sqlite" is a local/single-process ledger and is not a distributed
    # authority. Shared multi-agent deployments must select "postgres" so every
    # agent and worker reads and writes one canonical store (ADR-072).
    store_backend: Literal["sqlite", "postgres"] = "sqlite"
    database_path: Path | None = None
    postgres_dsn: str | None = None
    postgres_statement_timeout_ms: int = Field(default=30_000, ge=1_000, le=600_000)
    # Selecting a different backend points at a different canonical store.
    # Startup refuses when the configured store is empty while a prior ledger
    # still holds records, unless the operator says that is intended (ADR-077).
    acknowledge_backend_transition: bool = False
    registry_path: Path | None = None
    workspace_namespace: str = "l9-workspace"

    memory_enabled: bool = True
    write_gates_enabled: bool = False
    gate_ttl_minutes: int = Field(default=30, ge=1, le=1_440)

    projection_backend: Literal["none", "http", "zep"] = "none"
    graphiti_mcp_url: str | None = None
    graphiti_mcp_token: str | None = None
    zep_api_key: str | None = None
    zep_api_url: str | None = None
    projection_required: bool = False

    http_auth_required: bool = True
    auth_tokens: dict[str, TokenPrincipalConfig] = Field(default_factory=dict)
    local_principal_id: str = "local-operator"
    local_tenant_id: str = "local"
    local_organization_id: str = "local"
    local_workspace_id: str = "local"
    local_user_id: str | None = None
    local_agent_id: str | None = "l9-memory-cli"
    local_read_namespaces: tuple[str, ...] = ()
    local_write_namespaces: tuple[str, ...] = ()
    local_promote_namespaces: tuple[str, ...] = ()
    local_maintain_namespaces: tuple[str, ...] = ()
    local_is_admin: bool = False
    local_is_global_admin: bool = False

    outbox_batch_size: int = Field(default=50, ge=1, le=1_000)
    outbox_max_attempts: int = Field(default=8, ge=1, le=100)
    outbox_base_delay_seconds: int = Field(default=5, ge=1, le=3_600)
    # How long a claimed outbox event stays owned before another worker may
    # recover it. Must exceed the slowest expected projection call.
    outbox_lease_seconds: int = Field(default=300, ge=5, le=86_400)

    default_search_limit: int = Field(default=20, ge=1, le=200)
    default_token_budget: int = Field(default=1_200, ge=128, le=64_000)
    log_level: str = "INFO"
    json_logs: bool = True

    config_source: str = "defaults"
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data_dir", "state_dir", "database_path", "registry_path", mode="before")
    @classmethod
    def expand_path(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser()
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"unsupported log level: {value}")
        return normalized

    @model_validator(mode="after")
    def validate_store_backend(self) -> MemorySettings:
        if self.store_backend == "postgres" and not (self.postgres_dsn or "").strip():
            raise ValueError(
                "store_backend 'postgres' requires postgres_dsn (set L9_MEMORY_POSTGRES_DSN)"
            )
        return self

    @property
    def resolved_database_path(self) -> Path:
        return (self.database_path or self.data_dir / "memory.sqlite3").expanduser()

    @property
    def is_shared_store(self) -> bool:
        """True when canonical state is shared rather than process-local."""

        return self.store_backend == "postgres"
