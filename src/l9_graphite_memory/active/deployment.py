# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/deployment.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deployment identity contracts for the active-memory subsystem.

Implements ADR-065. A deployment identity binds one configured
active-memory runtime (one backend, one set of Redis credentials) to a
stable logical identifier and authorization/provenance boundary
(`trust_domain`). Deployment identity is immutable for the lifetime of a
running process and is injected server-side; it MUST NOT be accepted
from request payloads.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9._:-]{1,128}$")
_HASH_ALGORITHM_VERSION = "v1"


class DeploymentIdentityError(ValueError):
    """Raised when a deployment identifier or environment is invalid."""


class DeploymentEnvironment(str, Enum):
    """Deployment stage used for isolation, diagnostics, and policy.

    This enumeration is domain-agnostic. Consumer applications map their
    own environment names (e.g. a self-hosted VPS production stage) onto
    one of these values; this package does not encode any consumer's
    infrastructure naming.
    """

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def validate_identifier(value: str, *, field_name: str) -> str:
    """Validate a deployment_id, trust_domain, or similar identifier.

    Rules (per ADR-065):
      - length 1-128 characters
      - lowercase ascii letters, digits, '.', '_', '-', ':' only
      - no whitespace, wildcards, path separators, or control characters

    Raises:
        DeploymentIdentityError: if the value violates the above rules.
    """
    if not isinstance(value, str) or not value:
        raise DeploymentIdentityError(f"{field_name} must be a non-empty string")
    if not _IDENTIFIER_PATTERN.match(value):
        raise DeploymentIdentityError(
            f"{field_name}={value!r} is invalid; must match "
            f"{_IDENTIFIER_PATTERN.pattern} (1-128 chars, lowercase "
            "alnum plus '.', '_', '-', ':')"
        )
    if any(ch.isspace() for ch in value):
        raise DeploymentIdentityError(f"{field_name} must not contain whitespace")
    if "*" in value or "?" in value or "[" in value or "]" in value:
        raise DeploymentIdentityError(
            f"{field_name} must not contain Redis glob wildcard characters"
        )
    if "/" in value or "\\" in value:
        raise DeploymentIdentityError(f"{field_name} must not contain path separators")
    return value


_PRODUCTION_PLACEHOLDER_VALUES = frozenset(
    {
        "example",
        "example-production",
        "changeme",
        "change-me",
        "placeholder",
        "test",
        "unset",
        "unknown",
        "",
    }
)


@dataclass(frozen=True, slots=True)
class ActiveDeployment:
    """Immutable identity for one configured active-memory runtime.

    Attributes:
        deployment_id: Stable logical identifier for this runtime instance
            of the active-memory subsystem (e.g. one Redis backend, one
            set of credentials). Must be unique across independently
            operated active-memory backends that a fleet of external
            consumers might use.
        trust_domain: Authorization and provenance boundary containing
            this deployment. Used to scope cross-deployment isolation
            checks and to tag promoted Graphiti records with their
            originating trust boundary.
        environment: Deployment stage (development/test/staging/
            production). Used for policy decisions such as rejecting
            placeholder identifiers in production.

    Raises:
        DeploymentIdentityError: via `validate()` if any field is invalid,
            or if a production environment uses a recognized placeholder
            value for deployment_id or trust_domain.
    """

    deployment_id: str
    trust_domain: str
    environment: DeploymentEnvironment

    def __post_init__(self) -> None:
        validate_identifier(self.deployment_id, field_name="deployment_id")
        validate_identifier(self.trust_domain, field_name="trust_domain")
        if not isinstance(self.environment, DeploymentEnvironment):
            raise DeploymentIdentityError(
                f"environment must be a DeploymentEnvironment, got {type(self.environment)!r}"
            )
        if self.environment is DeploymentEnvironment.PRODUCTION:
            lowered_id = self.deployment_id.lower()
            lowered_domain = self.trust_domain.lower()
            if (
                lowered_id in _PRODUCTION_PLACEHOLDER_VALUES
                or lowered_domain in _PRODUCTION_PLACEHOLDER_VALUES
            ):
                raise DeploymentIdentityError(
                    "production environment must not use placeholder "
                    f"deployment_id/trust_domain values: "
                    f"deployment_id={self.deployment_id!r}, "
                    f"trust_domain={self.trust_domain!r}"
                )

    def canonical_string(self) -> str:
        """Canonical representation used as input to hash derivation."""
        return f"{_HASH_ALGORITHM_VERSION}|{self.trust_domain}|{self.deployment_id}"


def derive_deployment_hash(deployment: ActiveDeployment) -> str:
    """Derive the deterministic, versioned key/channel hash for a deployment.

    Uses SHA-256 over a canonical `{version}|{trust_domain}|{deployment_id}`
    string and returns the first 16 hex characters (64 bits) as the
    namespace component embedded in Redis keys and Pub/Sub channels.

    This function is deterministic and MUST remain stable for a given
    deployment identity within algorithm version "v1". Changing the
    algorithm requires bumping `_HASH_ALGORITHM_VERSION` and treating it
    as a breaking key-space migration (see ADR-065, ADR-068).
    """
    digest = hashlib.sha256(deployment.canonical_string().encode("utf-8")).hexdigest()
    return digest[:16]
