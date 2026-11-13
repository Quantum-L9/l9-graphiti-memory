# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/test_deployment_profile.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-11-13

"""The committed .l9/deployment.yaml is a valid v2 profile for exactly the C1 Memory target.

Every positive is paired with the malformed or mis-targeted profiles that must
not pass: a schema-valid profile aimed at the wrong host, port, ingress or store
is as much a failure as an invalid one.
"""

from __future__ import annotations

import copy
import hashlib
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.deployment.carrier.profile_contract import (
    BACKUP_COMMANDS,
    C1_ADDRESS,
    DSN_SETTING,
    HOST_PORT,
    HOSTNAME,
    L9_MEMORY_VM_ADDRESS,
    OAUTH_ISSUER,
    POSTGRES_IMAGE,
    PROFILE,
    SCHEMA_DIGESTS,
    SCHEMAS,
    rendered,
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


def test_the_committed_profile_pins_the_oauth_door_and_no_retired_one() -> None:
    """Issue #108: the hosted door is OAuth (ADR-102), pinned where runtime.env cannot reach."""

    environment = _profile()["runtime"]["environment"]
    assert environment["L9_MEMORY_HTTP_AUTH_MODE"] == "oauth"
    assert environment["L9_MEMORY_HTTP_OAUTH_ISSUER"] == OAUTH_ISSUER
    assert OAUTH_ISSUER.startswith("https://") and OAUTH_ISSUER.endswith("/")
    pins = [
        line
        for line in PROFILE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#") and ("signed-agent" in line or "bearer" in line)
    ]
    assert pins == []


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
    "signed-agent auth": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_HTTP_AUTH_MODE="signed-agent"
    ),
    "no pinned auth mode": lambda p: p["runtime"]["environment"].pop("L9_MEMORY_HTTP_AUTH_MODE"),
    "no pinned issuer": lambda p: p["runtime"]["environment"].pop("L9_MEMORY_HTTP_OAUTH_ISSUER"),
    "another issuer": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_HTTP_OAUTH_ISSUER="https://other-tenant.us.auth0.com/"
    ),
    "the issuer without its trailing slash": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_HTTP_OAUTH_ISSUER=OAUTH_ISSUER.rstrip("/")
    ),
    "subject grants in the committed profile": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_OAUTH_GRANTS_JSON="{}"
    ),
    "actor bindings in the committed profile": lambda p: p["runtime"]["environment"].update(
        L9_MEMORY_OAUTH_ACTORS_JSON="{}"
    ),
    "the root deploy user": lambda p: _target(p)["server"]["ssh"].update(user="root"),
    "a secret-store slug that resolves no project": lambda p: p["secrets"].update(
        project_slug="l9-graphiti-memory"
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


# The data plane: PostgreSQL 16 in a container on l9-runtime with no host port.
# Each entry is a way the probe, dump, verification or restore test could stop
# matching that placement, paired with the violation that must name it.


def _edit(command: str, old: str, new: str) -> Mutation:
    """Replace ``old`` in the script of ``backup.<command>``; ``old`` must be there."""

    def mutate(profile: dict[str, Any]) -> None:
        arguments: list[str] = profile["backup"][command]
        assert old in arguments[-1], f"{old!r} is not in backup.{command}"
        arguments[-1] = arguments[-1].replace(old, new)

    return mutate


def _replace(command: str, arguments: list[str]) -> Mutation:
    return lambda p: p["backup"].update({command: arguments})


# backup.command as committed before the database moved onto l9-runtime.
HOST_TOOL_BACKUP = [
    "sh",
    "-c",
    (
        'DATABASE_URL="$(docker exec l9-graphiti-memory-app-1 printenv L9_MEMORY_POSTGRES_DSN)"'
        " && export DATABASE_URL"
        " && exec /usr/local/sbin/l9-postgres-backup {project} {environment} {request_id}"
    ),
]
OTHER_DIGEST = "postgres:16@sha256:" + "0" * 64

OFF_THE_DATA_PLANE: dict[str, tuple[Mutation, str]] = {
    "the host backup tool, as the profile had it": (
        _replace("command", HOST_TOOL_BACKUP),
        "the dump must not use the host's unpinned pg_dump tool",
    ),
    "a pg_dump from the host's own client": (
        _edit("command", "docker run --rm --network l9-runtime", "pg_dump >/dev/null; docker run"),
        "pg_dump must run once, inside the pinned PostgreSQL 16 image",
    ),
    "a dump that never runs pg_dump in the image": (
        _edit("command", "pg_dump --format=plain", "cat /dev/null"),
        "pg_dump must run once, inside the pinned PostgreSQL 16 image",
    ),
    "an unpinned dump image": (
        _edit("command", POSTGRES_IMAGE, "postgres:16"),
        "backup command runs a PostgreSQL image other than the pinned one: ['postgres:16']",
    ),
    "a dump image that is not the restore test's": (
        _edit("command", POSTGRES_IMAGE, OTHER_DIGEST),
        f"backup command runs a PostgreSQL image other than the pinned one: ['{OTHER_DIGEST}']",
    ),
    "an unpinned restore image": (
        _edit("restore_test_command", POSTGRES_IMAGE, "postgres:latest"),
        "the restore test must use the pinned PostgreSQL 16 image",
    ),
    "a dump off the runtime network": (
        _edit("command", "--network l9-runtime", "--network bridge"),
        "the dump must run on the l9-runtime network, where the database resolves",
    ),
    "a dump on the host network": (
        _edit("command", "--network l9-runtime", "--network host"),
        "backup command publishes a port or joins the host network",
    ),
    "a published database port": (
        _edit("command", "docker run --rm", "docker run --rm -p 5432:5432"),
        "backup command publishes a port or joins the host network",
    ),
    "a published port on the restore container": (
        _edit("restore_test_command", "--network none", "--network none --publish 5433:5432"),
        "backup restore_test_command publishes a port or joins the host network",
    ),
    "a DSN literal in the dump": (
        _edit("command", "-e PGHOST", "-e PGHOST -e DSN postgresql://memory@db/memory"),
        "backup command carries a DSN or password literal",
    ),
    "a password literal in the dump": (
        _edit("command", "pg_dump --format=plain", "pg_dump 'host=db password=x' --format=plain"),
        "backup command carries a DSN or password literal",
    ),
    "a credential given a value on the command line": (
        _edit("command", "-e PGPASSWORD", '-e PGPASSWORD="$PGPASSWORD"'),
        "backup command puts a credential on a command line",
    ),
    "the DSN as a pg_dump argument": (
        _edit(
            "command", "pg_dump --format=plain", 'pg_dump --dbname="$DATABASE_URL" --format=plain'
        ),
        "backup command puts a credential on a command line",
    ),
    "a traced shell that prints the credentials": (
        _edit("command", "set -eu", "set -eux"),
        "backup command may print the environment that holds the DSN",
    ),
    "a DSN that does not come from the release container": (
        _edit("command", "docker exec l9-graphiti-memory-app-1 python", "python3"),
        "the dump must read the DSN from the running release container",
    ),
    "a dump whose failure is masked by gzip": (
        _edit("command", "bash -o pipefail -c", "bash -c"),
        "a failed pg_dump must fail the backup command",
    ),
    "a dump outside the canonical backup directory": (
        _edit("command", "dir=/srv/l9/backups/", "dir=/var/tmp/"),
        "the dump must land at /srv/l9/backups/{project}/{environment}/{request_id}.sql.gz",
    ),
    "a dump with no checksum beside it": (
        _edit("command", 'sha256sum "$out" > "$out.sha256"', "true"),
        "the dump needs its .sha256 beside it for l9-backup-verify",
    ),
    "a literal brace that str.format_map rejects": (
        _edit("command", 'test -n "$PGHOST"', 'test -n "${PGHOST}"'),
        "backup command is not valid under str.format_map: KeyError('PGHOST')",
    ),
    "verification that skips l9-backup-verify": (
        _replace("verify_command", ["sh", "-c", "ls /srv/l9/backups/{project}/{environment}"]),
        "verification must use /usr/local/sbin/l9-backup-verify",
    ),
    "a restore test on the runtime network": (
        _edit("restore_test_command", "--network none", "--network l9-runtime"),
        "the restore test must be isolated from any network",
    ),
    "a restore test that queries the release container": (
        _edit(
            "restore_test_command",
            'docker exec "$c" psql -U',
            "docker exec l9-graphiti-memory-app-1 psql -U",
        ),
        "the restore test must not reach the live database",
    ),
    "a restore test of an unverified dump": (
        _edit("restore_test_command", '/usr/local/sbin/l9-backup-verify "$f";', ""),
        "the restore test must verify the dump first",
    ),
    "a restore test that proves no table": (
        _edit("restore_test_command", "memory_records", "pg_class"),
        "the restore test must prove the canonical memory_records table",
    ),
    "a probe from the host": (
        lambda p: p["services"]["postgres"]["probe"].update(
            command=["pg_isready", "-h", "127.0.0.1", "-p", "5432"]
        ),
        "the postgres probe must run inside the release container",
    ),
    "a probe that prints the DSN": (
        lambda p: p["services"]["postgres"]["probe"].update(
            command=["docker", "exec", "l9-graphiti-memory-app-1", "printenv", DSN_SETTING]
        ),
        "postgres probe may print the environment that holds the DSN",
    ),
    "no backup tools on the host": (
        lambda p: _target(p)["host"].update(backup_tools="none"),
        "host.backup_tools must stay postgres: it installs /usr/local/sbin/l9-backup-verify",
    ),
}


@pytest.mark.parametrize(
    ("mutate", "violation"), OFF_THE_DATA_PLANE.values(), ids=OFF_THE_DATA_PLANE.keys()
)
def test_a_profile_off_the_data_plane_is_caught_by_name(mutate: Mutation, violation: str) -> None:
    profile = _mutated(mutate)
    # Still a schema-valid profile: only the carrier contract can refuse it.
    assert schema_errors(profile) == []
    assert violation in violations(profile)


@pytest.mark.parametrize("command", BACKUP_COMMANDS)
def test_each_backup_command_renders_to_a_script_the_shell_parses(command: str) -> None:
    # What l9-deploy runs after str.format_map: sh -c <script>. Parsed, not run.
    shell, flag, script = rendered(_profile()["backup"][command])
    assert (shell, flag) == ("sh", "-c")
    assert "{" not in script and "}" not in script
    parsed = subprocess.run(["sh", "-n", "-c", script], capture_output=True, text=True, check=False)
    assert parsed.returncode == 0, parsed.stderr


def _dsn_splitter() -> str:
    """The Python the dump runs inside the release container, cut from the profile."""

    script = rendered(_profile()["backup"]["command"])[-1]
    start = script.index("python -c '") + len("python -c '")
    return script[start : script.index("')\"", start)]


def _split(dsn: str | None) -> subprocess.CompletedProcess[str]:
    environment = {k: v for k, v in os.environ.items() if k != DSN_SETTING}
    if dsn is not None:
        environment[DSN_SETTING] = dsn
    return subprocess.run(
        [sys.executable, "-c", _dsn_splitter()],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


AWKWARD_PASSWORD = "p w'\"$(id)`x`;&"

DSN_FORMS = {
    "url": (
        "postgresql://l9_memory:s3cr3t-value@l9-graphiti-memory-postgres:5432/l9_memory",
        "s3cr3t-value",
        "",
    ),
    "keyword": (
        (
            "host=l9-graphiti-memory-postgres port=5432 user=l9_memory dbname=l9_memory"
            " password='p w\\'\"$(id)`x`;&' sslmode=disable"
        ),
        AWKWARD_PASSWORD,
        "disable",
    ),
}


@pytest.mark.parametrize(("dsn", "password", "sslmode"), DSN_FORMS.values(), ids=DSN_FORMS.keys())
def test_the_dump_splits_the_dsn_into_libpq_variables_the_shell_can_eval(
    dsn: str, password: str, sslmode: str
) -> None:
    split = _split(dsn)
    assert split.returncode == 0, split.stderr
    # The profile evals this output; a value must survive the shell unchanged
    # and must not be run by it.
    show = 'eval "$1"; printf "%s\\n" "$PGHOST" "$PGPORT" "$PGUSER" "$PGPASSWORD" "$PGDATABASE"'
    show += ' "${PGSSLMODE-}"'
    shown = subprocess.run(
        ["sh", "-c", show, "sh", split.stdout], capture_output=True, text=True, check=False
    )
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout.split("\n")[:-1] == [
        "l9-graphiti-memory-postgres",
        "5432",
        "l9_memory",
        password,
        "l9_memory",
        sslmode,
    ]


@pytest.mark.parametrize(
    "dsn",
    ["hunter2-secret no-equals-sign", None],
    ids=["a DSN that does not parse", "no DSN"],
)
def test_a_dsn_the_dump_cannot_split_fails_without_printing_it(dsn: str | None) -> None:
    split = _split(dsn)
    assert split.returncode != 0
    assert split.stdout == ""
    assert split.stderr.strip() == f"{DSN_SETTING} is missing or does not parse"


def test_the_release_tag_ref_moves_with_the_package_version(monkeypatch) -> None:
    from tests.deployment.carrier import profile_contract

    monkeypatch.setattr(profile_contract, "PACKAGE_VERSION", "3.0.1")
    assert "only the release tag v3.0.1 may deploy" in violations(_profile())
