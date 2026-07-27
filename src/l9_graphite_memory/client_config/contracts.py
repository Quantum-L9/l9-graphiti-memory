# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/client_config/contracts.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Evidence-bearing contracts for client instantiation operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts.temporal import utc_now
from l9_graphite_memory.version import CLIENT_CONFIG_POLICY_VERSION

_SHA256 = r"^[a-f0-9]{64}$"


class ClientConfigAction(str, Enum):
    INSPECT = "inspect"
    INSTALL = "install"
    VERIFY = "verify"
    STATUS = "status"
    UNINSTALL = "uninstall"


class ClientConfigStatus(str, Enum):
    COMPLETE = "complete"
    UNCHANGED = "unchanged"
    DRY_RUN = "dry_run"
    BLOCKED = "blocked"
    FAILED = "failed"


class ManagedServerEntry(BaseModel):
    """The exact managed MCP server entry the configurator owns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    command: str
    args: tuple[str, ...]

    def as_config(self) -> dict[str, object]:
        return {"command": self.command, "args": list(self.args)}


class CursorConfigInspection(BaseModel):
    """Read-only report of the target config file state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inspection_id: UUID = Field(default_factory=uuid4)
    path: str
    exists: bool
    is_regular_file: bool = False
    is_symlink: bool = False
    parent_is_symlink: bool = False
    parseable: bool = False
    root_is_object: bool = False
    servers_is_object: bool = False
    managed_entry_present: bool = False
    managed_entry_current: bool = False
    managed_entry_has_env: bool = False
    unmanaged_server_keys: tuple[str, ...] = ()
    unknown_top_level_keys: tuple[str, ...] = ()
    config_sha256: str | None = Field(default=None, pattern=_SHA256)
    blockers: tuple[str, ...] = ()
    policy_version: str = CLIENT_CONFIG_POLICY_VERSION
    inspected_at: datetime = Field(default_factory=utc_now)


class ClientConfigReceipt(BaseModel):
    """Durable receipt for every install, uninstall, or status operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    action: ClientConfigAction
    status: ClientConfigStatus
    path: str
    changed: bool = False
    managed_entry_present: bool = False
    command_argv: tuple[str, ...] = ()
    pre_sha256: str | None = Field(default=None, pattern=_SHA256)
    post_sha256: str | None = Field(default=None, pattern=_SHA256)
    backup_path: str | None = None
    backup_sha256: str | None = Field(default=None, pattern=_SHA256)
    preserved_server_keys: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    policy_version: str = CLIENT_CONFIG_POLICY_VERSION
    created_at: datetime = Field(default_factory=utc_now)


class ProbeStep(BaseModel):
    """One observed request/response exchange during a live probe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    ok: bool
    detail: str = ""


class ProbeReceipt(BaseModel):
    """Proof-of-instantiation evidence from the generated server command."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    status: ClientConfigStatus
    command_argv: tuple[str, ...]
    protocol_version: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    tool_count: int = Field(default=0, ge=0)
    required_tools_present: bool = False
    missing_tools: tuple[str, ...] = ()
    health_status: str | None = None
    steps: tuple[ProbeStep, ...] = ()
    stderr_excerpt: str = ""
    timed_out: bool = False
    exit_code: int | None = None
    reasons: tuple[str, ...] = ()
    policy_version: str = CLIENT_CONFIG_POLICY_VERSION
    created_at: datetime = Field(default_factory=utc_now)
