# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/profile_contract.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-11-13

"""What the hosted Memory profile must say, beyond what the l9-deploy schema allows.

The l9-deploy v2 schema admits any target. The C1 Memory campaign admits one:
the existing C1 host, the Memory hostname on external ingress, loopback 8200,
authenticated HTTP over one required external PostgreSQL. ``violations`` names
every departure from that, so a negative test can prove each one is caught.

ADR-100: the hosted door is Auth0 OAuth only; signed-agent HMAC and static
bearer are not hosted doors and not fallbacks. This release has no OAuth mode,
so the profile names no ``L9_MEMORY_HTTP_AUTH_MODE`` and the carrier refuses to
start; issue #108 pins the OAuth mode once it exists.

The database is a dedicated PostgreSQL 16 container on C1's ``l9-runtime``
Docker network with no published host port (operator decision 2026-11-13), so
its name resolves only on that network. ``_data_plane_violations`` pins what
follows from that: the probe and the dump run where the name resolves, the DSN
is read only from the running release container and never reaches the profile
or a command line, the dump comes from one pinned PostgreSQL 16 image rather
than the host's unpinned client, it lands where ``l9-backup-verify`` expects
it, and the restore test never touches the live database.

The schema is a pinned, unmodified copy of Quantum-L9/l9-deploy@b1bdaac
(``tests/fixtures/l9_deploy_v2``); l9-deploy remains its owner.
"""

from __future__ import annotations

import json
import re
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
    # Compose lets these override runtime.env, so a stale secret-store entry
    # cannot turn on a backend the profile does not declare.
    "L9_MEMORY_PROJECTION_BACKEND": "none",
    "L9_MEMORY_PROJECTION_RUNTIME": "legacy",
    "L9_MEMORY_GRAPH_BACKEND": "none",
    "L9_MEMORY_ACTIVE_BACKEND": "none",
}
# ADR-100: neither is a hosted door. Until issue #108 adds the OAuth mode the
# profile names no auth mode at all.
RETIRED_HOSTED_AUTH_MODES = ("signed-agent", "bearer")
# Credentials reach the container only through the Infisical-rendered runtime.env.
SECRET_MARKERS = ("DSN", "KEY", "GRANT", "TOKEN", "PASSWORD", "SECRET", "ASSERTION")

# The data plane: one database container on the runtime network, no host port.
RELEASE_CONTAINER = "l9-graphiti-memory-app-1"  # l9-deploy names it <project.id>-app-1
RUNTIME_NETWORK = "l9-runtime"
DSN_SETTING = "L9_MEMORY_POSTGRES_DSN"
# The one PostgreSQL image any profile command may run: the dump and the restore
# test share it, so a dump is always restored by the major version that wrote it.
POSTGRES_IMAGE = (
    "postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97"
)
BACKUP_DIRECTORY = "/srv/l9/backups/{project}/{environment}"
BACKUP_FILE = "{request_id}.sql.gz"
BACKUP_VERIFY_TOOL = "/usr/local/sbin/l9-backup-verify"
HOST_BACKUP_TOOL = "l9-postgres-backup"  # runs the host's unpinned pg_dump
# What l9-deploy substitutes into every command argument with str.format_map.
COMMAND_FIELDS = {
    "project": "l9-graphiti-memory",
    "environment": "production",
    "request_id": "request-0001",
}
BACKUP_COMMANDS = ("command", "verify_command", "restore_test_command")

_POSTGRES_IMAGE_REFERENCE = re.compile(r"(?<![\w./-])postgres:[^\s'\"]+")
_DSN_LITERAL = re.compile(r"postgres(?:ql)?://|\bpassword\s*=", re.IGNORECASE)
# -p/-P as a docker run or create flag (mkdir -p is not one), or --publish anywhere.
_PUBLISHED_PORT = re.compile(
    r"docker\s+(?:run|create)\b[^;|&]*?\s(?:-p|-P)(?:[\s=]|$)|--publish(?:-all)?\b"
)
_HOST_NETWORK = re.compile(r"--net(?:work)?[\s=]+host\b")
# A value given to a credential on a command line is visible to ps; forwarding
# the variable by name (docker run -e NAME) is not.
_CREDENTIAL_ON_COMMAND_LINE = re.compile(
    r"(?:-e|--env)[\s=]+(?:PG[A-Z]+|DATABASE_URL|POSTGRES_PASSWORD|L9_MEMORY_\w+)=|--dbname"
)
_PRINTS_THE_ENVIRONMENT = re.compile(
    r"\bprintenv\b|\bset\s+-\w*x|\bsh\s+-\w*x|(?:^|[\s;|&])env(?:[\s;|&]|$)"
)


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


def rendered(command: list[str]) -> list[str]:
    """``command`` as l9-deploy runs it: every argument through ``str.format_map``."""

    return [argument.format_map(COMMAND_FIELDS) for argument in command]


def _data_plane_violations(profile: dict[str, Any]) -> list[str]:
    """Departures from: PostgreSQL 16 in a container on l9-runtime, no host port."""

    found: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            found.append(message)

    def text(command: Any) -> str:
        return " ".join(command) if isinstance(command, list) else ""

    probe_command = profile.get("services", {}).get("postgres", {}).get("probe", {}).get("command")
    backup = profile.get("backup") or {}
    commands: dict[str, Any] = {"postgres probe": probe_command}
    commands.update({f"backup {name}": backup.get(name) for name in BACKUP_COMMANDS})

    for name, command in commands.items():
        script = text(command)
        require(bool(script), f"{name} is required")
        try:
            rendered(command or [])
        except (KeyError, IndexError, ValueError) as error:
            found.append(f"{name} is not valid under str.format_map: {error!r}")
        require(not _DSN_LITERAL.search(script), f"{name} carries a DSN or password literal")
        require(
            not _CREDENTIAL_ON_COMMAND_LINE.search(script),
            f"{name} puts a credential on a command line",
        )
        require(
            not _PRINTS_THE_ENVIRONMENT.search(script),
            f"{name} may print the environment that holds the DSN",
        )
        require(
            not _PUBLISHED_PORT.search(script) and not _HOST_NETWORK.search(script),
            f"{name} publishes a port or joins the host network",
        )
        unpinned = [
            image for image in _POSTGRES_IMAGE_REFERENCE.findall(script) if image != POSTGRES_IMAGE
        ]
        require(
            not unpinned, f"{name} runs a PostgreSQL image other than the pinned one: {unpinned}"
        )

    # The probe: inside the release container, which is on the network and holds the DSN.
    require(
        isinstance(probe_command, list)
        and probe_command[:3] == ["docker", "exec", RELEASE_CONTAINER],
        "the postgres probe must run inside the release container",
    )
    probe = text(probe_command)
    require(DSN_SETTING in probe, "the postgres probe must read the DSN from the environment")
    require("print" not in probe, "the postgres probe must print nothing")

    # The dump: a pinned PostgreSQL 16 pg_dump on the runtime network.
    dump = text(backup.get("command"))
    require(HOST_BACKUP_TOOL not in dump, "the dump must not use the host's unpinned pg_dump tool")
    require(
        f"docker exec {RELEASE_CONTAINER} " in dump and DSN_SETTING in dump,
        "the dump must read the DSN from the running release container",
    )
    require(
        dump.count("pg_dump") == 1 and 0 <= dump.find(POSTGRES_IMAGE) < dump.find("pg_dump"),
        "pg_dump must run once, inside the pinned PostgreSQL 16 image",
    )
    require(
        f"--network {RUNTIME_NETWORK}" in dump,
        f"the dump must run on the {RUNTIME_NETWORK} network, where the database resolves",
    )
    require("pipefail" in dump, "a failed pg_dump must fail the backup command")
    require(
        BACKUP_DIRECTORY in dump and BACKUP_FILE in dump,
        f"the dump must land at {BACKUP_DIRECTORY}/{BACKUP_FILE}",
    )
    require(
        "sha256sum" in dump and ".sha256" in dump,
        "the dump needs its .sha256 beside it for l9-backup-verify",
    )

    verify = text(backup.get("verify_command"))
    require(BACKUP_VERIFY_TOOL in verify, f"verification must use {BACKUP_VERIFY_TOOL}")
    require(BACKUP_DIRECTORY in verify, "verification must read the canonical backup directory")

    # The restore test: a throwaway, network-less container, never the live database.
    restore = text(backup.get("restore_test_command"))
    require("--network none" in restore, "the restore test must be isolated from any network")
    require(
        RUNTIME_NETWORK not in restore
        and RELEASE_CONTAINER not in restore
        and DSN_SETTING not in restore,
        "the restore test must not reach the live database",
    )
    require(POSTGRES_IMAGE in restore, "the restore test must use the pinned PostgreSQL 16 image")
    require(BACKUP_VERIFY_TOOL in restore, "the restore test must verify the dump first")
    require(
        BACKUP_DIRECTORY in restore, "the restore test must read the canonical backup directory"
    )
    require(
        "memory_records" in restore,
        "the restore test must prove the canonical memory_records table",
    )
    return found


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
    mode = environment.get("L9_MEMORY_HTTP_AUTH_MODE")
    require(
        mode not in RETIRED_HOSTED_AUTH_MODES,
        f"L9_MEMORY_HTTP_AUTH_MODE={mode} is not a hosted door (ADR-100)",
    )
    require(
        "L9_MEMORY_HTTP_AUTH_MODE" not in environment,
        "L9_MEMORY_HTTP_AUTH_MODE stays unset until the OAuth mode exists (issue #108)",
    )
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
    found.extend(_data_plane_violations(profile))

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
    require(
        target.get("host", {}).get("backup_tools") == "postgres",
        f"host.backup_tools must stay postgres: it installs {BACKUP_VERIFY_TOOL}",
    )
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
