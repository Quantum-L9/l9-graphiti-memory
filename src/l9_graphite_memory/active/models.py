# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/models.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Core domain contracts for the active-memory subsystem.

These are the deployment-neutral, Redis-independent entities described
in the build plan Phase 1. They carry no dependency on any specific
storage backend and MUST remain importable without the optional
`redis` extra installed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from l9_graphite_memory.active.deployment import (
    DeploymentIdentityError,
    validate_identifier,
)

_SCHEMA_VERSION = 1

_ID_PATTERN = re.compile(r"^[a-z0-9._:-]{1,128}$")

MAX_CONTEXT_BYTES = 65536
MAX_OBSERVATIONS = 100
MAX_OBSERVATION_BYTES = 8192
MAX_METADATA_KEYS = 32
MAX_METADATA_BYTES = 4096


class AgentStatus(str, Enum):
    """Lifecycle/operating status of one agent instance."""

    STARTING = "starting"
    IDLE = "idle"
    ACTIVE = "active"
    BLOCKED = "blocked"
    WAITING = "waiting"
    DEGRADED = "degraded"
    DRAINING = "draining"
    STOPPED = "stopped"


class AgentEventType(str, Enum):
    """Awareness event types published to the awareness bus."""

    AGENT_REGISTERED = "agent.registered"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_STATUS_CHANGED = "agent.status.changed"
    AGENT_CONTEXT_UPDATED = "agent.context.updated"
    AGENT_OBSERVATION_PUBLISHED = "agent.observation.published"
    AGENT_MEMORY_PROMOTED = "agent.memory.promoted"
    AGENT_DRAINING = "agent.draining"
    AGENT_UNREGISTERED = "agent.unregistered"
    AGENT_EXPIRED = "agent.expired"
    ACTIVE_MEMORY_DEGRADED = "active_memory.degraded"
    ACTIVE_MEMORY_RECOVERED = "active_memory.recovered"


def _validate_id_field(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeploymentIdentityError(f"{field_name} must be a non-empty string")
    if not _ID_PATTERN.match(value):
        raise DeploymentIdentityError(
            f"{field_name}={value!r} is invalid; must match {_ID_PATTERN.pattern}"
        )
    return value


def _validate_metadata(metadata: Mapping[str, object]) -> Mapping[str, object]:
    if len(metadata) > MAX_METADATA_KEYS:
        raise DeploymentIdentityError(
            f"metadata has {len(metadata)} keys, exceeding limit of {MAX_METADATA_KEYS}"
        )
    import json

    encoded = json.dumps(metadata, default=str)
    if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
        raise DeploymentIdentityError(
            f"metadata serialized size exceeds {MAX_METADATA_BYTES} bytes"
        )
    return metadata


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """Declared identity of one external agent instance.

    Attributes:
        agent_id: Stable logical identity assigned by the consumer's
            control plane (e.g. "research-agent"). Survives process
            restarts.
        instance_id: Unique identifier for one process incarnation.
            MUST be regenerated on every process/session start.
        role: Declared operating role, subject to authorization by the
            consumer-supplied role registry. Never a substitute for
            authentication.
        capabilities: Descriptive capability tags. Not permission
            grants; authorization decisions are made from authenticated
            principal policy, not from this field.
        principal_id: Authenticated security principal controlling this
            agent instance.
        session_id: Optional execution/session correlation identifier.
        memory_group_ids: Requested Graphiti/active-memory group scopes.
        metadata: Bounded, non-sensitive descriptive data. Must not
            contain secrets, credentials, or unrestricted free text.

    Raises:
        DeploymentIdentityError: if any identifier field is malformed or
            metadata exceeds configured bounds.
    """

    agent_id: str
    instance_id: str
    role: str
    principal_id: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    session_id: str | None = None
    memory_group_ids: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_id_field(self.agent_id, "agent_id")
        _validate_id_field(self.instance_id, "instance_id")
        _validate_id_field(self.role, "role")
        _validate_id_field(self.principal_id, "principal_id")
        if self.session_id is not None:
            _validate_id_field(self.session_id, "session_id")
        for group_id in self.memory_group_ids:
            _validate_id_field(group_id, "memory_group_ids[]")
        for capability in self.capabilities:
            _validate_id_field(capability, "capabilities[]")
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True)
class AgentLease:
    """Server-issued lease proving an agent instance is currently registered.

    Attributes:
        lease_id: Server-generated unique lease identifier.
        agent_id: The agent identity this lease was issued to.
        instance_id: The specific instance this lease was issued to.
        issued_at: UTC timestamp of issuance.
        expires_at: UTC timestamp after which the lease is invalid.
        heartbeat_interval_seconds: Expected renewal cadence.

    Note:
        The raw lease token (bearer credential) is intentionally NOT a
        field on this dataclass. It must be handled as an opaque secret
        by the transport/session layer and never included in `repr()`,
        logs, receipts, or serialized events.
    """

    lease_id: str
    agent_id: str
    instance_id: str
    issued_at: datetime
    expires_at: datetime
    heartbeat_interval_seconds: int

    def __post_init__(self) -> None:
        _validate_id_field(self.lease_id, "lease_id")
        _validate_id_field(self.agent_id, "agent_id")
        _validate_id_field(self.instance_id, "instance_id")
        if self.heartbeat_interval_seconds <= 0:
            raise DeploymentIdentityError("heartbeat_interval_seconds must be positive")
        if self.expires_at <= self.issued_at:
            raise DeploymentIdentityError("expires_at must be after issued_at")

    def is_expired(self, now: datetime) -> bool:
        """Return True if `now` is at or after this lease's expiry."""
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class AgentPresence:
    """Current presence record for one agent instance.

    Attributes:
        identity: The identity this presence record describes.
        status: Current lifecycle status.
        deployment_id: Injected server-side; identifies the owning
            active-memory deployment. Never supplied by the caller.
        started_at: UTC timestamp when this instance registered.
        heartbeat_at: UTC timestamp of the most recent heartbeat.
        expires_at: UTC timestamp after which this presence is stale.
        presence_version: Monotonically increasing version for this
            instance's presence record.
    """

    identity: AgentIdentity
    status: AgentStatus
    deployment_id: str
    started_at: datetime
    heartbeat_at: datetime
    expires_at: datetime
    presence_version: int

    def __post_init__(self) -> None:
        validate_identifier(self.deployment_id, field_name="deployment_id")
        if self.presence_version < 0:
            raise DeploymentIdentityError("presence_version must be non-negative")

    def is_expired(self, now: datetime) -> bool:
        """Return True if `now` is at or after this presence's expiry."""
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class ActiveObservation:
    """One bounded, ephemeral observation published by an agent.

    Attributes:
        observation_id: Unique identifier for this observation.
        kind: Free-form but bounded category tag (e.g. "constraint",
            "finding"). Not validated against a fixed enum because
            observation taxonomies are consumer-defined.
        summary: Concise working information. MUST NOT contain
            unrestricted model reasoning or private chain-of-thought;
            per ADR-031 (reasoning lineage boundary), that data must
            stay outside the active-memory layer entirely.
        confidence: Optional confidence score in [0.0, 1.0].
        relevance: Optional relevance score in [0.0, 1.0].
        source_reference: Optional pointer to originating evidence.
        promotable: Whether this observation is a promotion candidate.
        created_at: UTC creation timestamp.

    Raises:
        DeploymentIdentityError: if `summary` exceeds
            `MAX_OBSERVATION_BYTES` when UTF-8 encoded, or if
            `confidence`/`relevance` are outside [0.0, 1.0].
    """

    observation_id: str
    kind: str
    summary: str
    created_at: datetime
    confidence: float | None = None
    relevance: float | None = None
    source_reference: str | None = None
    promotable: bool = False

    def __post_init__(self) -> None:
        _validate_id_field(self.observation_id, "observation_id")
        if not self.summary:
            raise DeploymentIdentityError("summary must not be empty")
        if len(self.summary.encode("utf-8")) > MAX_OBSERVATION_BYTES:
            raise DeploymentIdentityError(
                f"summary exceeds {MAX_OBSERVATION_BYTES} bytes"
            )
        for name, val in (
            ("confidence", self.confidence),
            ("relevance", self.relevance),
        ):
            if val is not None and not (0.0 <= val <= 1.0):
                raise DeploymentIdentityError(f"{name} must be within [0.0, 1.0]")


@dataclass(frozen=True, slots=True)
class ActiveContextDraft:
    """Caller-supplied draft for a full context replacement.

    This is the input shape accepted by `ActiveStore.put_context()`.
    It intentionally excludes `version`, `deployment_id`, and
    `expires_at`, which are server-assigned.
    """

    objective: str | None
    status: AgentStatus
    working_on: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    observations: tuple[ActiveObservation, ...] = field(default_factory=tuple)
    graph_references: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.observations) > MAX_OBSERVATIONS:
            raise DeploymentIdentityError(
                f"observations count {len(self.observations)} exceeds "
                f"limit of {MAX_OBSERVATIONS}"
            )


@dataclass(frozen=True, slots=True)
class ActiveContext:
    """Committed, versioned active context for one agent instance.

    Attributes:
        agent_id: Owning agent's stable identity.
        instance_id: Owning agent's instance identity.
        role: Role at time of write.
        deployment_id: Injected server-side.
        group_id: Primary group scope this context is visible under.
        draft: The committed content.
        version: Monotonically increasing version, incremented on every
            successful `put_context()` call.
        updated_at: UTC timestamp of this version's commit.
        expires_at: UTC timestamp after which this context is stale and
            MUST NOT be treated as current by any reader.
    """

    agent_id: str
    instance_id: str
    role: str
    deployment_id: str
    group_id: str
    draft: ActiveContextDraft
    version: int
    updated_at: datetime
    expires_at: datetime
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_id_field(self.agent_id, "agent_id")
        _validate_id_field(self.instance_id, "instance_id")
        _validate_id_field(self.role, "role")
        validate_identifier(self.deployment_id, field_name="deployment_id")
        _validate_id_field(self.group_id, "group_id")
        if self.version < 1:
            raise DeploymentIdentityError("version must be >= 1")

    def is_expired(self, now: datetime) -> bool:
        """Return True if `now` is at or after this context's expiry."""
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class AgentScope:
    """Discovery/authorization scope for listing or subscribing to peers.

    Attributes:
        deployment_id: Injected server-side; scopes discovery to one
            deployment's active-memory namespace.
        group_id: Optional group filter.
        role: Optional role filter.
    """

    deployment_id: str
    group_id: str | None = None
    role: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.deployment_id, field_name="deployment_id")
        if self.group_id is not None:
            _validate_id_field(self.group_id, "group_id")
        if self.role is not None:
            _validate_id_field(self.role, "role")


@dataclass(frozen=True, slots=True)
class AgentSubscription:
    """Backend-neutral awareness subscription request."""

    scope: AgentScope


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Awareness-bus event pointer.

    Per ADR-067, this carries only enough information for a subscriber
    to decide whether to re-read current state; it MUST NOT carry
    context content, secrets, lease tokens, or unrestricted metadata.

    Attributes:
        schema_version: Event schema version for compatibility checks.
        event_id: Unique event identifier.
        event_type: One of `AgentEventType`.
        agent_id: Originating agent's stable identity.
        instance_id: Originating agent's instance identity.
        role: Originating agent's role at time of publish.
        deployment_id: Injected server-side.
        group_id: Optional group this event is scoped to.
        state_version: Optional pointer to the context/presence version
            that triggered this event.
        occurred_at: UTC timestamp of publication.
        trace_id: Optional distributed-tracing correlation id.
    """

    event_id: str
    event_type: AgentEventType
    agent_id: str
    instance_id: str
    role: str
    deployment_id: str
    occurred_at: datetime
    schema_version: int = _SCHEMA_VERSION
    group_id: str | None = None
    state_version: int | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        _validate_id_field(self.event_id, "event_id")
        _validate_id_field(self.agent_id, "agent_id")
        _validate_id_field(self.instance_id, "instance_id")
        _validate_id_field(self.role, "role")
        validate_identifier(self.deployment_id, field_name="deployment_id")
        if self.group_id is not None:
            _validate_id_field(self.group_id, "group_id")
