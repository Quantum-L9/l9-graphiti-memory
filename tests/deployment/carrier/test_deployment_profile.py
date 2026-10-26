# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/test_deployment_profile.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-26

"""The committed .l9/deployment.yaml is a valid v2 profile for exactly the C1 Memory target.

Every positive is paired with the malformed or mis-targeted profiles that must
not pass: a schema-valid profile aimed at the wrong host, port, ingress or store
is as much a failure as an invalid one.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.deployment.carrier.profile_contract import (
    C1_ADDRESS,
    HOST_PORT,
    HOSTNAME,
    L9_MEMORY_VM_ADDRESS,
    PROFILE,
    SCHEMA_DIGESTS,
    SCHEMAS,
    schema_errors,
    violations,
)

Mutation = Callable[[dict[str, Any]], None]


def _profile() -> dict[str, Any]:
    document = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _target(profile: dict[str, Any]) -> dict[str, Any]:
    target: dict[str, Any] = profile["targets"]["production"]
    return target


def _mutated(mutate: Mutation) -> dict[str, Any]:
    profile = copy.deepcopy(_profile())
    mutate(profile)
    return profile


def test_the_schema_fixture_is_the_pinned_l9_deploy_schema() -> None:
    for name, digest in SCHEMA_DIGESTS.items():
        assert hashlib.sha256((SCHEMAS / name).read_bytes()).hexdigest() == digest, name


def test_the_committed_profile_is_a_valid_v2_profile() -> None:
    assert schema_errors(_profile()) == []


def test_the_committed_profile_targets_only_the_c1_memory_endpoint() -> None:
    profile = _profile()
    assert violations(profile) == []
    target = _target(profile)
    assert target["server"]["address"] == C1_ADDRESS
    assert target["ingress"] == {
        "mode": "external",
        "hostnames": [HOSTNAME],
        "host_port": HOST_PORT,
    }


def test_the_host_key_is_a_well_formed_public_key_line_not_a_placeholder() -> None:
    # Its value is an evidence lead that must be re-verified against the host
    # before release; here it must at least be a real ed25519 key encoding.
    import base64

    kind, blob = _target(_profile())["server"]["host_key"].split(" ")
    assert kind == "ssh-ed25519"
    raw = base64.b64decode(blob, validate=True)
    assert raw[4:15] == b"ssh-ed25519"
    assert len(raw) == 51


SCHEMA_INVALID: dict[str, Mutation] = {
    "privileged host port": lambda p: _target(p)["ingress"].update(host_port=80),
    "unpublished ingress with a host port": lambda p: _target(p)["ingress"].update(
        mode="none", hostnames=[]
    ),
    "stateful profile without a backup contract": lambda p: p.pop("backup"),
    "stateful profile without services": lambda p: p.pop("services"),
    "malformed host key": lambda p: _target(p)["server"].update(host_key="not-a-key"),
    "unknown top-level field": lambda p: p.update(fallback={"store": "sqlite"}),
    "wrong schema id": lambda p: p.update(schema="l9.deployment-profile/v1"),
    "no allowed source ref": lambda p: _target(p).update(allowed_source_refs=[]),
    "external service without required flag": lambda p: p["services"]["postgres"].pop("required"),
}


@pytest.mark.parametrize("mutate", SCHEMA_INVALID.values(), ids=SCHEMA_INVALID.keys())
def test_a_malformed_profile_is_refused_by_the_schema(mutate: Mutation) -> None:
    assert schema_errors(_mutated(mutate)) != []


MISTARGETED: dict[str, Mutation] = {
    "the Graphiti route port": lambda p: _target(p)["ingress"].update(host_port=8100),
    "the Cognitive Runtime port": lambda p: _target(p)["ingress"].update(host_port=18080),
    "the separate L9-Memory VM": lambda p: _target(p)["server"].update(
        address=L9_MEMORY_VM_ADDRESS
    ),
    "a managed Caddy site": lambda p: _target(p)["ingress"].update(mode="caddy"),
    "another hostname": lambda p: _target(p)["ingress"].update(hostnames=["mcp.example.com"]),
    "a managed Docker runtime on C1": lambda p: _target(p)["host"].update(docker="managed"),
    "a branch instead of the release tag": lambda p: _target(p).update(
        allowed_source_refs=["refs/heads/main"]
    ),
    "a SQLite store": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_STORE_BACKEND="sqlite"
    ),
    "bearer-only auth": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_HTTP_AUTH_MODE="bearer"
    ),
    "auth disabled": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_HTTP_AUTH_REQUIRED="false"
    ),
    "a DSN in the committed profile": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_POSTGRES_DSN="host=db user=memory"
    ),
    "an optional PostgreSQL": lambda p: p["services"]["postgres"].update(required=False),
    "no PostgreSQL service": lambda p: p["services"].pop("postgres"),
    "a writable root filesystem": lambda p: p["runtime"].update(read_only_root_filesystem=False),
    "a persistent local volume": lambda p: p["storage"].update(
        persistent_volumes=[{"name": "ledger", "mount_path": "/data", "backup_policy": "none"}]
    ),
    "a networked restore test": lambda p: p["backup"].update(
        restore_test_command=["sh", "-c", "psql $LIVE_DSN < dump.sql"]
    ),
    "a liveness-only health probe": lambda p: p["health"]["startup"].update(path="/healthz"),
    "an unpinned graph backend": lambda p: p["runtime"]["environment"].pop(
        "L9_MEMORY_GRAPH_BACKEND"
    ),
    "an unpinned active-memory backend": lambda p: p["runtime"]["environment"].pop(
        "L9_MEMORY_ACTIVE_BACKEND"
    ),
}


@pytest.mark.parametrize("mutate", MISTARGETED.values(), ids=MISTARGETED.keys())
def test_a_mistargeted_profile_is_caught(mutate: Mutation) -> None:
    assert violations(_mutated(mutate)) != []


def test_the_release_tag_ref_moves_with_the_package_version(monkeypatch) -> None:
    from tests.deployment.carrier import profile_contract

    monkeypatch.setattr(profile_contract, "PACKAGE_VERSION", "3.0.1")
    assert "only the release tag v3.0.1 may deploy" in violations(_profile())
