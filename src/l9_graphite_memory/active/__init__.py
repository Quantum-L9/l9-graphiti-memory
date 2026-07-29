# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/__init__.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Active multi-agent memory subsystem (deployment-neutral).

This package provides the deployment-identity, secret-file credential
resolution, and stable external SDK contracts for the Redis-backed
active-memory layer described in ADR-065 through ADR-068.

This package intentionally contains no consumer-specific (e.g. Igorbot,
OpenClaw, Hetzner) identifiers, configuration, or deployment logic. All
contents here are domain-neutral and reusable by any external runtime.
"""

from l9_graphite_memory.active.client import (
    ActiveAgentClient,
    ActiveAgentSession,
)
from l9_graphite_memory.active.credentials import (
    AmbiguousCredentialSourceError,
    CredentialResolutionError,
    RedisCredentialSettings,
    ResolvedRedisCredential,
    resolve_redis_credential,
)
from l9_graphite_memory.active.deployment import (
    ActiveDeployment,
    DeploymentEnvironment,
    DeploymentIdentityError,
    derive_deployment_hash,
    validate_identifier,
)
from l9_graphite_memory.active.errors import (
    ActiveMemoryError,
    ActiveMemoryUnavailableError,
    ContextVersionConflictError,
    LeaseExpiredError,
    SchemaCompatibilityError,
)
from l9_graphite_memory.active.lifecycle import (
    ActiveAgentSessionState,
    LifecycleTransitionError,
    SessionLifecycle,
)
from l9_graphite_memory.active.models import (
    ActiveContext,
    ActiveContextDraft,
    ActiveObservation,
    AgentEvent,
    AgentEventType,
    AgentIdentity,
    AgentLease,
    AgentPresence,
    AgentScope,
    AgentStatus,
    AgentSubscription,
)

__all__ = [
    "ActiveAgentClient",
    "ActiveAgentSession",
    "ActiveAgentSessionState",
    "ActiveContext",
    "ActiveContextDraft",
    "ActiveDeployment",
    "ActiveMemoryError",
    "ActiveMemoryUnavailableError",
    "ActiveObservation",
    "AgentEvent",
    "AgentEventType",
    "AgentIdentity",
    "AgentLease",
    "AgentPresence",
    "AgentScope",
    "AgentStatus",
    "AgentSubscription",
    "AmbiguousCredentialSourceError",
    "ContextVersionConflictError",
    "CredentialResolutionError",
    "DeploymentEnvironment",
    "DeploymentIdentityError",
    "LeaseExpiredError",
    "LifecycleTransitionError",
    "RedisCredentialSettings",
    "ResolvedRedisCredential",
    "SchemaCompatibilityError",
    "SessionLifecycle",
    "derive_deployment_hash",
    "resolve_redis_credential",
    "validate_identifier",
]
