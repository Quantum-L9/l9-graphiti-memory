"""Unit tests for l9_graphite_memory.active.deployment."""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.deployment import (
    ActiveDeployment,
    DeploymentEnvironment,
    DeploymentIdentityError,
    derive_deployment_hash,
    validate_identifier,
)


def test_valid_identifier_passes() -> None:
    assert validate_identifier("assistant-production", field_name="deployment_id") == (
        "assistant-production"
    )


@pytest.mark.parametrize(
    "value",
    ["", "has space", "UPPER", "wild*card", "path/sep", "path\\sep", "a" * 129],
)
def test_invalid_identifier_raises(value: str) -> None:
    with pytest.raises(DeploymentIdentityError):
        validate_identifier(value, field_name="deployment_id")


def test_active_deployment_constructs_with_valid_fields() -> None:
    deployment = ActiveDeployment(
        deployment_id="assistant-production",
        trust_domain="assistant",
        environment=DeploymentEnvironment.PRODUCTION,
    )
    assert deployment.deployment_id == "assistant-production"


def test_active_deployment_rejects_production_placeholder() -> None:
    with pytest.raises(DeploymentIdentityError):
        ActiveDeployment(
            deployment_id="changeme",
            trust_domain="assistant",
            environment=DeploymentEnvironment.PRODUCTION,
        )


def test_active_deployment_allows_placeholder_outside_production() -> None:
    deployment = ActiveDeployment(
        deployment_id="test",
        trust_domain="test",
        environment=DeploymentEnvironment.TEST,
    )
    assert deployment.environment is DeploymentEnvironment.TEST


def test_derive_deployment_hash_is_deterministic() -> None:
    deployment = ActiveDeployment(
        deployment_id="sample-production",
        trust_domain="sample-domain",
        environment=DeploymentEnvironment.PRODUCTION,
    )
    first = derive_deployment_hash(deployment)
    second = derive_deployment_hash(deployment)
    assert first == second
    assert len(first) == 16


def test_derive_deployment_hash_differs_across_deployments() -> None:
    deployment_a = ActiveDeployment(
        deployment_id="alpha-production",
        trust_domain="alpha",
        environment=DeploymentEnvironment.PRODUCTION,
    )
    deployment_b = ActiveDeployment(
        deployment_id="beta-production",
        trust_domain="beta",
        environment=DeploymentEnvironment.PRODUCTION,
    )
    assert derive_deployment_hash(deployment_a) != derive_deployment_hash(deployment_b)
