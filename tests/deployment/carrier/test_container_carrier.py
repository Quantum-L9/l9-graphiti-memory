# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/deployment/carrier/test_container_carrier.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-11-13

"""The built carrier image, run as the profile runs it, against a disposable PostgreSQL 16.

Each case starts the real image (read-only root, no new privileges, uid 10001)
on a private Docker network with a throwaway ``postgres:16``, publishes it on a
loopback port and drives it over real HTTP, the way l9-deploy and a remote
agent reach it. The profile environment is the committed
``.l9/deployment.yaml`` with one substitution, the issuer; operator data and
credentials go in through an env file, as the deploy-rendered runtime.env does.
The PostgreSQL password is generated per run.

The door is the package's OAuth resource server (ADR-100, ADR-102) with
operator-bound actors (ADR-103). Its issuer is a local authorization server in
its own container on the same network (``issuer.example.test``, TLS under a
certificate authority generated per run). The carrier reaches it through the
real issuer read (``https_get``: https only, no redirect, system trust store);
the only test-specific setting is ``SSL_CERT_FILE``, which makes the run's
authority the trust store. Tokens are signed in this process with a key that
exists nowhere else. None of this is the live PKCE receipt.

Proven here (issue #108 section 2):
- ``/readyz`` is 200 only while the canonical PostgreSQL store is reachable,
  the served store is PostgreSQL, and serving writes nothing to the container;
- ``/mcp`` refuses with 401 and a Bearer challenge naming the protected
  resource metadata: no credential, a malformed token, a wrong issuer, a wrong
  audience, a wrong resource, an expired token, a foreign signature, a
  client-credentials (user-less) token, a valid signed-agent credential and a
  static bearer token. Stale signed-agent and bearer settings in runtime.env do
  not open their doors: the profile's pinned mode wins;
- a valid audience-bound token initializes; a subject bound to an actor writes,
  and another subject reads and searches the record; a namespace outside the
  grant is refused, and a subject with no actor cannot write;
- the trailing-slash resource path is not an endpoint, and the protected
  resource metadata names the configured issuer;
- the record survives the container being replaced;
- no token, key, grant or database password reaches the container log;
- the container refuses to start on every mode but oauth (unset, signed-agent,
  bearer, another value), without the issuer or with a non-https one, without
  the grant map, with an administrator grant, with an actor bound to its own
  client id, without PostgreSQL, on SQLite, with auth disabled, against an
  unreachable database, and with stale graph or active-memory backends.

Not proven here: TLS in front of the service, Caddy, the C1 host, Infisical,
Auth0, or the deployed service.
Runs only when ``L9_MEMORY_TEST_CARRIER_IMAGE`` names a locally built image;
the release workflow builds one and fails if anything here is skipped.
"""

from __future__ import annotations

import datetime
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.deployment.carrier.profile_contract import OAUTH_ISSUER, PROFILE
from tests.integration.remote_mcp_harness import (
    AGENT_KEYS,
    FOREIGN_NAMESPACE,
    HOME_NAMESPACE,
    WRITER,
    credentials,
    free_port,
    mcp_headers,
    rpc,
    server_environment,
    tool,
    tool_payload,
)

IMAGE_ENV = "L9_MEMORY_TEST_CARRIER_IMAGE"
IMAGE = os.environ.get(IMAGE_ENV, "").strip()
POSTGRES_IMAGE = (
    "postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97"
)

pytestmark = pytest.mark.skipif(
    not IMAGE, reason=f"{IMAGE_ENV} is not set; the carrier proof needs a built image"
)
httpx2 = pytest.importorskip("httpx2", reason="the carrier proof needs an HTTP client")
pytest.importorskip("jwt", reason="signing test tokens requires the [server] extra")

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from l9_graphite_memory.version import MEMORY_RESOURCE_IDENTIFIER
from tests.oauth_fakes import (
    CLIENT_ID,
    OTHER_RESOURCE,
    FakeIssuer,
    rsa_key,
)

ISSUER_HOST = "issuer.example.test"
ISSUER_PORT = 8443
TEST_ISSUER = f"https://{ISSUER_HOST}:{ISSUER_PORT}/"
OTHER_TEST_ISSUER = f"https://other-{ISSUER_HOST}:{ISSUER_PORT}/"
ISSUER_MOUNT = "/run/l9-test-issuer"
TEST_TRUST_STORE = f"{ISSUER_MOUNT}/ca.pem"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"

WRITER_SUBJECT = "user|carrier-writer-0001"
READER_SUBJECT = "user|carrier-reader-0002"
GRANTS = {
    WRITER_SUBJECT: {"read_namespaces": [HOME_NAMESPACE], "write_namespaces": [HOME_NAMESPACE]},
    READER_SUBJECT: {"read_namespaces": [HOME_NAMESPACE]},
}
WRITER_ACTOR = "claude-code"
ACTORS = {
    WRITER_SUBJECT: {
        CLIENT_ID: {
            "actor_ref": f"l9.actor-registry/global@1#{WRITER_ACTOR}",
            "surface_ref": "l9.surface-registry/global@1#claude-code-cli",
        }
    }
}
STATIC_BEARER = "carrier-static-token-for-tests"


def _committed_profile_environment() -> dict[str, str]:
    """``runtime.environment`` of the committed profile, as Compose passes it."""

    document = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in document["runtime"]["environment"].items()}


COMMITTED_ENVIRONMENT = _committed_profile_environment()
# The committed profile with the one substitution a test cannot avoid: the
# issuer is the local authorization server instead of the Auth0 tenant.
assert COMMITTED_ENVIRONMENT["L9_MEMORY_HTTP_OAUTH_ISSUER"] == OAUTH_ISSUER
PROFILE_ENVIRONMENT = {**COMMITTED_ENVIRONMENT, "L9_MEMORY_HTTP_OAUTH_ISSUER": TEST_ISSUER}
# The profile without its backend pins: what a stale runtime.env entry would
# reach if the deployment profile ever stopped overriding it.
UNPINNED_PROFILE = {
    key: value
    for key, value in PROFILE_ENVIRONMENT.items()
    if key not in {"L9_MEMORY_GRAPH_BACKEND", "L9_MEMORY_ACTIVE_BACKEND"}
}


def _without(environment: dict[str, str], *names: str) -> dict[str, str]:
    return {key: value for key, value in environment.items() if key not in names}


def _token() -> str:
    """A unique, digit-free marker for record content.

    Admission redacts PII, and a run of ten digits inside a random hex string
    reads as a phone number, so a uuid in content is rewritten about one time
    in ten. Letters only keep the stored content byte-for-byte comparable.
    """

    return uuid.uuid4().hex.translate(str.maketrans("0123456789", "ghijklmnop"))


def _docker(*args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


# --- the network, the database and the issuer --------------------------------


@dataclass
class Database:
    network: str
    container: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.container} port=5432 user=postgres password={self.password} "
            "dbname=postgres connect_timeout=5"
        )


@pytest.fixture(scope="module")
def database() -> Iterator[Database]:
    if shutil.which("docker") is None:
        pytest.fail(f"{IMAGE_ENV} is set but the docker CLI is unavailable")
    tag = uuid.uuid4().hex[:12]
    network = f"l9-carrier-{tag}"
    container = f"l9-carrier-pg-{tag}"
    password = secrets.token_urlsafe(24)
    _docker("network", "create", network)
    try:
        _docker(
            "run", "-d", "--name", container, "--network", network,
            "-e", f"POSTGRES_PASSWORD={password}", POSTGRES_IMAGE,
        )  # fmt: skip
        _wait_for_postgres(container)
        yield Database(network=network, container=container, password=password)
    finally:
        _docker("rm", "-f", container, check=False)
        _docker("network", "rm", network, check=False)


def _wait_for_postgres(container: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        ready = _docker(
            "exec", container, "pg_isready", "-U", "postgres", "-h", "127.0.0.1", check=False
        )
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("disposable PostgreSQL 16 never became ready")


def _pem(certificate: x509.Certificate) -> bytes:
    return certificate.public_bytes(serialization.Encoding.PEM)


def _key_usage(**granted: bool) -> x509.KeyUsage:
    """A key usage extension with exactly the ``granted`` bits set."""

    bits = (
        "digital_signature", "content_commitment", "key_encipherment", "data_encipherment",
        "key_agreement", "key_cert_sign", "crl_sign", "encipher_only", "decipher_only",
    )  # fmt: skip
    return x509.KeyUsage(**{bit: granted.get(bit, False) for bit in bits})


def _certificate_authority(directory: Path) -> None:
    """A per-run authority and a server certificate for ``ISSUER_HOST``.

    Both carry the extensions Python's strict X.509 verification requires.
    The private keys are throwaway test material that exist only in this run.
    """

    now = datetime.datetime.now(datetime.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "l9 carrier test authority")])
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_key_usage(key_cert_sign=True, crl_sign=True), critical=True)
        .add_extension(ca_ski, critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ISSUER_HOST)]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(ISSUER_HOST)]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(_key_usage(digital_signature=True, key_agreement=True), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    (directory / "ca.pem").write_bytes(_pem(ca))
    (directory / "issuer.pem").write_bytes(_pem(server))
    (directory / "issuer.key").write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


# The authorization server's container: two documents over TLS, nothing else.
ISSUER_SERVER = """\
import http.server, pathlib, ssl, sys
root = pathlib.Path(sys.argv[1])
documents = {
    "/.well-known/openid-configuration": root / "metadata.json",
    "/.well-known/jwks.json": root / "jwks.json",
}
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = documents.get(self.path)
        if path is None:
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
server = http.server.ThreadingHTTPServer(("0.0.0.0", int(sys.argv[2])), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(root / "issuer.pem", root / "issuer.key")
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
"""


@dataclass
class Issuer:
    fake: FakeIssuer
    directory: Path
    container: str


@pytest.fixture(scope="module")
def issuer(database: Database, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Issuer]:
    """The local authorization server, reachable from the carrier as ``ISSUER_HOST``."""

    directory = tmp_path_factory.mktemp("issuer")
    fake = FakeIssuer(TEST_ISSUER)
    _certificate_authority(directory)
    (directory / "metadata.json").write_text(json.dumps(fake.metadata()), "utf-8")
    (directory / "jwks.json").write_text(json.dumps(fake.jwks()), "utf-8")
    (directory / "serve.py").write_text(ISSUER_SERVER, "utf-8")
    # The containers run as uid 10001 and read the mount; nothing here is a
    # credential of anything but this run.
    directory.chmod(0o755)
    for entry in directory.iterdir():
        entry.chmod(0o644)
    container = f"l9-carrier-issuer-{uuid.uuid4().hex[:12]}"
    _docker(
        "run", "-d", "--name", container, "--network", database.network,
        "--network-alias", ISSUER_HOST, "--read-only",
        "--security-opt", "no-new-privileges:true",
        "-v", f"{directory}:{ISSUER_MOUNT}:ro", "--entrypoint", "python",
        IMAGE, f"{ISSUER_MOUNT}/serve.py", ISSUER_MOUNT, str(ISSUER_PORT),
    )  # fmt: skip
    try:
        _wait_for_issuer(container, fake.jwks_url)
        yield Issuer(fake=fake, directory=directory, container=container)
    finally:
        _docker("rm", "-f", container, check=False)


def _wait_for_issuer(container: str, url: str) -> None:
    probe = f"import urllib.request; urllib.request.urlopen({url!r}, timeout=3).read()"
    deadline = time.monotonic() + 60
    last = ""
    while time.monotonic() < deadline:
        answered = _docker(
            "exec", "-e", f"SSL_CERT_FILE={TEST_TRUST_STORE}", container, "python", "-c", probe,
            check=False,
        )  # fmt: skip
        if answered.returncode == 0:
            return
        last = answered.stderr[-500:]
        time.sleep(0.5)
    raise RuntimeError(f"the local authorization server never answered over TLS: {last}")


# --- the carrier --------------------------------------------------------------


def _env_file(path: Path, values: dict[str, str]) -> Path:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), "utf-8")
    path.chmod(0o600)
    return path


def _runtime_env(database: Database, **overrides: str | None) -> dict[str, str]:
    """The deploy-rendered runtime.env: operator data and credentials, never the profile.

    It also carries a stale entry for every retired door (a signed-agent
    registry, a static bearer map and a signed-agent mode), so a fall-through
    to any of them would be visible.
    """

    values: dict[str, str | None] = {
        **server_environment(),
        "L9_MEMORY_AUTH_TOKENS_JSON": json.dumps(
            {STATIC_BEARER: {"principal_id": "static", "tenant_id": "l9"}}
        ),
        "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent",
        "L9_MEMORY_POSTGRES_DSN": database.dsn,
        "L9_MEMORY_LOCAL_TENANT_ID": "l9",
        "L9_MEMORY_LOCAL_ORGANIZATION_ID": "quantum-l9",
        "L9_MEMORY_LOCAL_WORKSPACE_ID": "l9-workspace",
        "L9_MEMORY_OAUTH_GRANTS_JSON": json.dumps(GRANTS),
        "L9_MEMORY_OAUTH_ACTORS_JSON": json.dumps(ACTORS),
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


@dataclass
class Carrier:
    container: str
    url: str


def _start(
    tmp_path: Path,
    database: Database,
    issuer: Issuer,
    *,
    profile: dict[str, str] | None = None,
    **runtime: str | None,
) -> Carrier:
    name = f"l9-carrier-mem-{uuid.uuid4().hex[:12]}"
    port = free_port()
    env_file = _env_file(tmp_path / f"{name}.env", _runtime_env(database, **runtime))
    arguments = [
        "run", "-d", "--name", name, "--network", database.network,
        "--read-only", "--security-opt", "no-new-privileges:true",
        "-p", f"127.0.0.1:{port}:8200", "--env-file", str(env_file),
        # The run's authority is the trust store; the issuer read is otherwise
        # exactly the production one.
        "-v", f"{issuer.directory}:{ISSUER_MOUNT}:ro",
        "-e", f"SSL_CERT_FILE={TEST_TRUST_STORE}",
    ]  # fmt: skip
    # Compose gives the profile precedence over runtime.env; so does -e here.
    for key, value in (PROFILE_ENVIRONMENT if profile is None else profile).items():
        arguments += ["-e", f"{key}={value}"]
    _docker(*arguments, IMAGE)
    return Carrier(container=name, url=f"http://127.0.0.1:{port}")


def _stop(carrier: Carrier) -> str:
    logs = _docker("logs", carrier.container, check=False)
    _docker("rm", "-f", carrier.container, check=False)
    return logs.stdout + logs.stderr


def _readyz(carrier: Carrier) -> Any:
    try:
        return httpx2.get(f"{carrier.url}/readyz", timeout=10)
    except httpx2.HTTPError:
        return None


def _wait_ready(carrier: Carrier, *, status: int = 200, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        response = _readyz(carrier)
        if response is not None and response.status_code == status:
            body: dict[str, Any] = response.json()
            return body
        last = response.status_code if response is not None else "no answer"
        running = _docker("inspect", "-f", "{{.State.Running}}", carrier.container, check=False)
        if running.stdout.strip() != "true":
            break
        time.sleep(0.5)
    logs = _docker("logs", carrier.container, check=False)
    raise AssertionError(f"/readyz never answered {status} (last {last}): {logs.stderr[-2000:]}")


def _wait_not_ready(carrier: Carrier, *, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    consecutive = 0
    while time.monotonic() < deadline:
        response = _readyz(carrier)
        consecutive = consecutive + 1 if response is None or response.status_code != 200 else 0
        if consecutive >= 3:
            return
        time.sleep(0.5)
    raise AssertionError("/readyz kept answering 200 without its canonical store")


@contextmanager
def carrier(
    tmp_path: Path, database: Database, issuer: Issuer, **runtime: str | None
) -> Iterator[Carrier]:
    started = _start(tmp_path, database, issuer, **runtime)
    try:
        _wait_ready(started)
        yield started
    finally:
        _stop(started)


def _bearer(token: str) -> dict[str, str]:
    return {**mcp_headers(), "Authorization": f"Bearer {token}"}


def _post(c: Carrier, body: dict[str, Any], headers: dict[str, str], path: str = "/mcp") -> Any:
    return httpx2.post(f"{c.url}{path}", content=json.dumps(body), headers=headers, timeout=15)


def _call(c: Carrier, token: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = _post(c, tool(name, arguments), _bearer(token))
    assert response.status_code == 200, response.text
    return tool_payload(response.json())


def _written(c: Carrier, issuer: Issuer, content: str) -> str:
    written = _call(
        c,
        issuer.fake.access_token(sub=WRITER_SUBJECT),
        "memory.write_agent",
        {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": uuid.uuid4().hex},
    )
    assert written["status"] == "admitted", written
    record_id: str = written["record_id"]
    return record_id


INITIALIZE = rpc(
    "initialize",
    {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t"}},
)


# --- proofs -------------------------------------------------------------------


def test_the_image_runs_as_the_profile_requires() -> None:
    """The image config. The door is pinned by the profile, not baked into the image."""

    config = json.loads(_docker("image", "inspect", IMAGE).stdout)[0]["Config"]
    assert config["User"] == "10001:10001"
    assert "8200/tcp" in config["ExposedPorts"]
    assert config["Entrypoint"] == ["/usr/local/bin/l9-memory-carrier"]
    revision = config["Labels"]["org.opencontainers.image.revision"]
    assert len(revision) == 40
    assert all(c in "0123456789abcdef" for c in revision)
    environment = dict(item.split("=", 1) for item in config["Env"])
    assert environment["L9_MEMORY_STORE_BACKEND"] == "postgres"
    assert environment["L9_MEMORY_HTTP_AUTH_REQUIRED"] == "true"
    assert "L9_MEMORY_HTTP_AUTH_MODE" not in environment
    assert "L9_MEMORY_HTTP_OAUTH_ISSUER" not in environment


def test_readiness_follows_the_canonical_postgres_store(tmp_path, database, issuer) -> None:
    with carrier(tmp_path, database, issuer) as c:
        ready = _wait_ready(c)
        families = ready["readiness"]["families"]
        store = next(family for family in families if family["name"] == "canonical")
        assert store["healthy"] is True
        assert store["detail"]["shared_store"] is True
        assert httpx2.get(f"{c.url}/healthz", timeout=10).json()["store"]["name"] == "postgres"
        # Serving wrote nothing to the container filesystem: no ledger, no state.
        _written(c, issuer, "a write that must land in PostgreSQL, not on local disk")
        # The one entry Docker itself makes is the mount point of the run's
        # trust store; anything else would be a write by the service.
        changed = set(_docker("diff", c.container).stdout.split("\n")) - {""}
        assert changed <= {"C /run", f"A {ISSUER_MOUNT}"}, changed
        _docker("stop", database.container)
        try:
            # Not ready while the store is gone: never 200, which is what the
            # l9-deploy health probe and Caddy rely on.
            _wait_not_ready(c)
        finally:
            _docker("start", database.container)
            _wait_for_postgres(database.container)
        _wait_ready(c)


def _refused_requests(issuer: Issuer) -> dict[str, dict[str, str]]:
    fake = issuer.fake
    now = int(time.time())
    return {
        "no credential": mcp_headers(),
        "a malformed token": _bearer("not.a.token"),
        "a wrong issuer": _bearer(fake.access_token(iss=OTHER_TEST_ISSUER)),
        "a wrong audience": _bearer(fake.access_token(aud=OTHER_RESOURCE)),
        # The trailing-slash spelling is another resource string (ADR-102).
        "a wrong resource": _bearer(fake.access_token(aud=MEMORY_RESOURCE_IDENTIFIER + "/")),
        "an expired token": _bearer(fake.access_token(iat=now - 7200, exp=now - 3600)),
        "a foreign signature": _bearer(fake.access_token(key=rsa_key(1))),
        "a client-credentials token": _bearer(
            fake.access_token(sub=f"{CLIENT_ID}@clients", gty="client-credentials")
        ),
        "a valid signed-agent credential": {**mcp_headers(), **credentials(WRITER)},
        "a static bearer token": _bearer(STATIC_BEARER),
    }


def test_oauth_admits_bound_subjects_and_refuses_every_bad_credential(
    tmp_path, database, issuer
) -> None:
    fake = issuer.fake
    with carrier(tmp_path, database, issuer) as c:
        for case, headers in _refused_requests(issuer).items():
            response = _post(c, INITIALIZE, headers)
            assert response.status_code == 401, (case, response.text)
            challenge = response.headers["WWW-Authenticate"]
            assert challenge.startswith('Bearer realm="l9-graphite-memory"'), case
            assert "resource_metadata=" in challenge, case

        metadata = httpx2.get(f"{c.url}{METADATA_PATH}", timeout=10)
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == MEMORY_RESOURCE_IDENTIFIER
        assert metadata.json()["authorization_servers"] == [TEST_ISSUER]
        # One canonical resource: the trailing-slash path is not an endpoint.
        writer_token = fake.access_token(sub=WRITER_SUBJECT)
        assert _post(c, INITIALIZE, _bearer(writer_token), path="/mcp/").status_code == 404

        session = _post(c, INITIALIZE, _bearer(writer_token))
        assert session.status_code == 200, session.text
        assert session.json()["result"]["serverInfo"]["name"] == "l9-graphite-memory"

        content = f"carrier proof {_token()}: the kingfisher nests by the sluice"
        record_id = _written(c, issuer, content)
        reader_token = fake.access_token(sub=READER_SUBJECT)
        got = _call(c, reader_token, "memory.get", {"record_id": record_id})
        assert got["found"] is True
        assert got["record"]["content"] == content
        assert got["record"]["provenance"]["source_agent_id"] == WRITER_ACTOR
        hits = _call(
            c,
            reader_token,
            "memory.search",
            {"query": "kingfisher", "namespaces": [HOME_NAMESPACE]},
        )
        assert record_id in [hit["record"]["record_id"] for hit in hits["hits"]]

        foreign = _call(
            c,
            writer_token,
            "memory.write_agent",
            {"namespace": FOREIGN_NAMESPACE, "content": "outside the grant"},
        )
        assert foreign["status"] == "rejected"
        assert foreign["record_id"] is None
        assert foreign["authorization"]["allowed"] is False
        # The reader's subject has no actor binding: a subject is not an actor.
        unbound = _post(
            c,
            tool("memory.write_agent", {"namespace": HOME_NAMESPACE, "content": "no actor"}),
            _bearer(reader_token),
        )
        error = unbound.json()["error"]
        assert error["data"]["type"] == "AuthorizationError", error


def test_records_survive_the_container_being_replaced(tmp_path, database, issuer) -> None:
    content = f"carrier persistence {_token()}"
    with carrier(tmp_path, database, issuer) as first:
        record_id = _written(first, issuer, content)
    with carrier(tmp_path, database, issuer) as second:
        token = issuer.fake.access_token(sub=READER_SUBJECT)
        got = _call(second, token, "memory.get", {"record_id": record_id})
        assert got["found"] is True
        assert got["record"]["content"] == content


def test_no_secret_reaches_the_container_log(tmp_path, database, issuer) -> None:
    started = _start(tmp_path, database, issuer)
    presented = credentials(WRITER)
    tokens = [
        issuer.fake.access_token(sub=WRITER_SUBJECT),
        issuer.fake.access_token(sub=READER_SUBJECT, aud=OTHER_RESOURCE),
    ]
    try:
        _wait_ready(started)
        _written(started, issuer, "a write whose credentials must not be logged")
        for token in tokens:
            _post(started, rpc("ping"), _bearer(token))
        _post(started, rpc("ping"), {**mcp_headers(), **presented})
        _post(started, rpc("ping"), _bearer("leaked.123.x.y"))
    finally:
        logs = _stop(started)
    assert logs.strip(), "the container wrote no log to inspect"
    for secret in [
        *AGENT_KEYS.values(),
        database.password,
        *tokens,
        presented["Authorization"].split(" ", 1)[1],
        presented["L9-Identity-Assertion-HMAC"],
        STATIC_BEARER,
        "leaked.123.x.y",
    ]:
        assert secret not in logs
    # Subjects appear only as fingerprints.
    assert WRITER_SUBJECT not in logs and READER_SUBJECT not in logs


ADMIN_GRANTS = {WRITER_SUBJECT: {**GRANTS[WRITER_SUBJECT], "is_admin": True}}
CLIENT_AS_ACTOR = {
    WRITER_SUBJECT: {CLIENT_ID: {"actor_ref": f"l9.actor-registry/global@1#{CLIENT_ID}"}}
}
NOT_OAUTH = "L9_MEMORY_HTTP_AUTH_MODE must be oauth, the hosted door (ADR-100, ADR-102)"
# case -> (profile environment or None for the profile's, runtime.env overrides, refusal)
REFUSED_STARTS: dict[str, tuple[dict[str, str] | None, dict[str, str | None], str]] = {
    "no auth mode": (
        _without(PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE"),
        {"L9_MEMORY_HTTP_AUTH_MODE": None},
        NOT_OAUTH,
    ),
    "signed-agent auth in the profile": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE": "signed-agent"},
        {},
        "L9_MEMORY_HTTP_AUTH_MODE=signed-agent is not a hosted door (ADR-100)",
    ),
    "signed-agent auth from runtime.env alone": (
        _without(PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE"),
        {},
        "L9_MEMORY_HTTP_AUTH_MODE=signed-agent is not a hosted door (ADR-100)",
    ),
    "bearer auth in the profile": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE": "bearer"},
        {},
        "L9_MEMORY_HTTP_AUTH_MODE=bearer is not a hosted door (ADR-100)",
    ),
    # runtime.env already carries the static bearer token map.
    "bearer auth from runtime.env alone": (
        _without(PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE"),
        {"L9_MEMORY_HTTP_AUTH_MODE": "bearer"},
        "L9_MEMORY_HTTP_AUTH_MODE=bearer is not a hosted door (ADR-100)",
    ),
    "another auth mode": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_MODE": "oauth2"},
        {},
        NOT_OAUTH,
    ),
    "oauth without an issuer": (
        _without(PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_OAUTH_ISSUER"),
        {},
        "L9_MEMORY_HTTP_OAUTH_ISSUER is required by the hosted OAuth door (ADR-102)",
    ),
    "an issuer that is not https": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_OAUTH_ISSUER": f"http://{ISSUER_HOST}/"},
        {},
        "L9_MEMORY_HTTP_OAUTH_ISSUER must be an https URL",
    ),
    "no subject grant map": (
        None,
        {"L9_MEMORY_OAUTH_GRANTS_JSON": None},
        "requires L9_MEMORY_OAUTH_GRANTS_JSON",
    ),
    "an administrator grant": (
        None,
        {"L9_MEMORY_OAUTH_GRANTS_JSON": json.dumps(ADMIN_GRANTS)},
        "administrator authority is not reachable over HTTP",
    ),
    "a client id bound as its own actor": (
        None,
        {"L9_MEMORY_OAUTH_ACTORS_JSON": json.dumps(CLIENT_AS_ACTOR)},
        "an OAuth client is not an actor",
    ),
    "no PostgreSQL DSN": (
        None,
        {"L9_MEMORY_POSTGRES_DSN": None},
        "L9_MEMORY_POSTGRES_DSN is required",
    ),
    "a SQLite store": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_STORE_BACKEND": "sqlite"},
        {},
        "L9_MEMORY_STORE_BACKEND must be postgres",
    ),
    "auth disabled": (
        {**PROFILE_ENVIRONMENT, "L9_MEMORY_HTTP_AUTH_REQUIRED": "false"},
        {},
        "L9_MEMORY_HTTP_AUTH_REQUIRED must be true",
    ),
    "an unreachable database": (
        None,
        {"L9_MEMORY_POSTGRES_DSN": "host=l9-carrier-nowhere port=5432 user=x connect_timeout=3"},
        "postgres connection failed",
    ),
    "a stale graph backend in runtime.env": (
        UNPINNED_PROFILE,
        {"L9_MEMORY_GRAPH_BACKEND": "neo4j"},
        "L9_MEMORY_GRAPH_BACKEND must be none",
    ),
    "a stale active-memory backend in runtime.env": (
        UNPINNED_PROFILE,
        {"L9_MEMORY_ACTIVE_BACKEND": "redis"},
        "L9_MEMORY_ACTIVE_BACKEND must be none",
    ),
}


@pytest.mark.parametrize("case", REFUSED_STARTS, ids=REFUSED_STARTS.keys())
def test_the_container_refuses_to_serve_a_misconfigured_store_or_door(
    tmp_path, database, issuer, case
) -> None:
    """Every mode but oauth, and every incomplete OAuth or store setting, stops startup."""

    profile, runtime, refusal = REFUSED_STARTS[case]
    started = _start(tmp_path, database, issuer, profile=profile, **runtime)
    valid = issuer.fake.access_token(sub=WRITER_SUBJECT)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = _docker("inspect", "-f", "{{.State.Running}}", started.container)
            if state.stdout.strip() != "true":
                break
            response = _readyz(started)
            assert response is None or response.status_code != 200, f"{case}: served ready"
            try:
                served = _post(started, INITIALIZE, _bearer(valid))
            except httpx2.HTTPError:
                served = None
            assert served is None or served.status_code != 200, f"{case}: served /mcp"
            time.sleep(0.5)
        else:
            pytest.fail(f"{case}: the container kept running instead of refusing to start")
        exit_code = _docker("inspect", "-f", "{{.State.ExitCode}}", started.container)
        assert exit_code.stdout.strip() not in {"", "0"}, case
    finally:
        logs = _stop(started)
    assert refusal in logs, logs[-2000:]
    assert database.password not in logs
    assert valid not in logs
    assert not any(key in logs for key in AGENT_KEYS.values())
