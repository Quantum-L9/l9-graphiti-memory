# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/profile_contract.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-26

"""What the hosted Memory profile must say, beyond what the l9-deploy schema allows.

The l9-deploy v2 schema admits any target. The C1 Memory campaign admits one:
the existing C1 host, the Memory hostname on external ingress, loopback 8200,
signed-agent HTTP over one required external PostgreSQL. ``violations`` names
every departure from that, so a negative test can prove each one is caught.

The schema is a pinned, unmodified copy of Quantum-L9/l9-deploy@b1bdaac
(``tests/fixtures/l9_deploy_v2``); l9-deploy remains its owner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from l9_graphite_memory.version import PACKAGE_VERSION

ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / ".l9" / "deployment.yaml"
SCHEMAS = ROOT / "tests" / "fixtures" / "l9_deploy_v2"
SCHEMA_SOURCE = "Quantum-L9/l9-deploy@b1bdaac50e22ddda526bd99203f498b6b4afd437"
SCHEMA_DIGESTS = {
    "deployment-profile.schema.json": (
        "e69f7146a8035b9e8e000f4cb41726ebd8c9b218f99d66feb947f90662d4d14f"
    ),
    "health-probe.schema.json": (
        "72d94cccb68a23c5bb48e6e5e13c7553a01109334847fde471890ff0e6b20900"
    ),
}

C1_ADDRESS = "46.62.243.82"
L9_MEMORY_VM_ADDRESS = "89.167.34.78"  # a different server; never this profile's target
HOSTNAME = "memory.quantumaipartners.com"
HOST_PORT = 8200
RESERVED_HOST_PORTS = {8100: "Graphiti /graphiti route", 18080: "Cognitive Runtime"}
IMAGE = "ghcr.io/quantum-l9/l9-graphiti-memory"
REQUIRED_ENVIRONMENT = {
    "L9_MEMORY_STORE_BACKEND": "postgres",
    "L9_MEMORY_HTTP_AUTH_REQUIRED": "true",
    "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent",
}
# Credentials reach the container only through the Infisical-rendered runtime.env.
SECRET_MARKERS = ("DSN", "KEY", "GRANT", "TOKEN", "PASSWORD", "SECRET", "ASSERTION")


def schema_validator() -> Draft202012Validator:
    documents = {
        name: json.loads((SCHEMAS / name).read_text(encoding="utf-8")) for name in SCHEMA_DIGESTS
    }
    registry: Registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in documents.values()
    )
    return Draft202012Validator(documents["deployment-profile.schema.json"], registry=registry)


def schema_errors(profile: dict[str, Any]) -> list[str]:
    return sorted(error.message for error in schema_validator().iter_errors(profile))


def violations(profile: dict[str, Any]) -> list[str]:
    """Every way ``profile`` departs from the hosted Memory carrier contract."""

    found: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            found.append(message)

    project = profile.get("project", {})
    require(project.get("id") == "l9-graphiti-memory", "project id")
    require(project.get("repository") == "Quantum-L9/l9-graphiti-memory", "project repository")
    require(profile.get("artifact", {}).get("image") == IMAGE, "artifact image")

    runtime = profile.get("runtime", {})
    require(runtime.get("architecture") == "linux/amd64", "architecture must be linux/amd64")
    require(runtime.get("container_port") == HOST_PORT, "container port must be 8200")
    require(runtime.get("user") == "non_root", "container must run as non-root")
    require(runtime.get("read_only_root_filesystem") is True, "root filesystem must be read-only")
    environment = runtime.get("environment", {})
    for name, value in REQUIRED_ENVIRONMENT.items():
        require(environment.get(name) == value, f"{name} must be {value}")
    leaked = [name for name in environment if any(m in name.upper() for m in SECRET_MARKERS)]
    require(not leaked, f"secret-shaped settings in the profile: {leaked}")
    require(not runtime.get("volumes"), "no host volume may hold a local ledger")
    require(not profile.get("storage", {}).get("persistent_volumes"), "no persistent volume")

    for phase in ("startup", "post_deploy"):
        probe = profile.get("health", {}).get(phase, {})
        require(
            (probe.get("type"), probe.get("path"), probe.get("expected_status"))
            == ("http", "/readyz", 200),
            f"{phase} health must be GET /readyz -> 200",
        )

    postgres = profile.get("services", {}).get("postgres", {})
    require(postgres.get("mode") == "external", "postgres must be an external service")
    require(postgres.get("required") is True, "postgres must be required")
    require(
        postgres.get("probe", {}).get("type") in {"database", "command"},
        "postgres needs a probe that runs on the target",
    )
    backup = profile.get("backup") or {}
    for command in ("command", "verify_command", "restore_test_command"):
        require(bool(backup.get(command)), f"backup {command} is required")
    restore = " ".join(backup.get("restore_test_command", []))
    require("--network none" in restore, "the restore test must be isolated from any network")

    secrets = profile.get("secrets", {})
    require(
        (secrets.get("authority"), secrets.get("runtime_mode")) == ("infisical", "deploy_render"),
        "secrets must be Infisical-rendered at deploy",
    )

    targets = profile.get("targets", {})
    require(set(targets) == {"production"}, "exactly one target: production")
    target = targets.get("production", {})
    server = target.get("server", {})
    require(server.get("address") == C1_ADDRESS, f"target must be C1 {C1_ADDRESS}")
    require(server.get("address") != L9_MEMORY_VM_ADDRESS, "target must not be the L9-Memory VM")
    require(
        target.get("host", {}).get("docker") == "verify", "C1 Docker is verified, never managed"
    )
    require(target.get("host", {}).get("backup_tools") == "postgres", "postgres backup tools")
    ingress = target.get("ingress", {})
    require(ingress.get("mode") == "external", "ingress must be the existing external proxy")
    require(ingress.get("hostnames") == [HOSTNAME], f"hostname must be {HOSTNAME}")
    port = ingress.get("host_port")
    require(port == HOST_PORT, "host port must be 8200")
    require(port not in RESERVED_HOST_PORTS, f"host port {port} belongs to another service")
    require(
        target.get("allowed_source_refs") == [f"refs/tags/v{PACKAGE_VERSION}"],
        f"only the release tag v{PACKAGE_VERSION} may deploy",
    )
    return found
