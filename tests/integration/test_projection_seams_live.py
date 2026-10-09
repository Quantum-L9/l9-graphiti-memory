# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_projection_seams_live.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.6.0
#   updated: 2026-07-22

"""Projection seams of the full-capability deployment, end to end (Phase 5).

One ``build_runtime()`` from environment binds the shared PostgreSQL canonical
store and the admitted manifest ``config/projections/facts-v8.yaml`` (Graphiti
MCP active target, Zep shadow target). Each seam is then driven through the
public surfaces (``MemoryService``, the outbox worker as ``l9-memory-worker``
composes it, retrieval, readiness) and checked at every handoff: the durable
outbox intent in PostgreSQL, the compiled target binding, the provider copy,
the per-target link, and what retrieval returns.

Backends:

- PostgreSQL is required (``L9_MEMORY_TEST_POSTGRES_DSN``); the suite skips
  without it.
- The Graphiti MCP endpoint is ``L9_MEMORY_TEST_GRAPHITI_MCP_URL`` (with
  ``L9_MEMORY_TEST_GRAPHITI_MCP_TOKEN``) when the environment has a live
  server; otherwise the official-dialect in-process server of
  ``test_graphiti_http_projection_loop`` stands in, and every receipt here
  says ``provider=composition`` rather than ``live``. The outage cases need
  the in-process server, because only it can be stopped and restarted here.
- Zep has no live endpoint in any environment this repository controls. The
  shadow target is bound to an unreachable local port through the real
  ``zep-cloud`` client, which is exactly the failure-accounting seam a shadow
  target must survive without touching authoritative retrieval.
- Neo4j (``L9_MEMORY_TEST_NEO4J_URI``) is used only when the Graphiti endpoint
  is live, to read the persisted graph structures back.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from typing import Any
from uuid import UUID

import pytest

from l9_graphite_memory.adapters.graphiti_projection import episode_name_locator
from l9_graphite_memory.contracts import (
    DeletionRequest,
    DeletionStatus,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryState,
    MemoryWriteRequest,
    OperationStatus,
    OutboxStatus,
    Provenance,
    WriteStatus,
)
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.retrieval.planner import RetrievalPlanner
from l9_graphite_memory.runtime import MemoryRuntime, build_runtime
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
from l9_graphite_memory.transport import HttpMcpTransport
from tests.integration.test_graphiti_http_projection_loop import (
    TOKEN,
    FakeGraphitiState,
    _handler,
)

POSTGRES_DSN_ENV = "L9_MEMORY_TEST_POSTGRES_DSN"
GRAPHITI_URL_ENV = "L9_MEMORY_TEST_GRAPHITI_MCP_URL"
GRAPHITI_TOKEN_ENV = "L9_MEMORY_TEST_GRAPHITI_MCP_TOKEN"
NEO4J_URI_ENV = "L9_MEMORY_TEST_NEO4J_URI"
MANIFEST = "config/projections/facts-v8.yaml"
GRAPHITI = "facts:v8:graphiti_mcp:primary"
ZEP = "facts:v8:zep:primary"
TENANT = "tenant-seam"
#: Shadow target bound to a port nothing listens on: every delivery fails.
UNREACHABLE_ZEP = "http://127.0.0.1:1"


def _require(env: str, what: str) -> str:
    value = os.environ.get(env, "").strip()
    if not value:
        pytest.skip(f"{env} is not set; the projection seams need {what}")
    return value


class Clock:
    """Advances the worker past every retry delay; the service keeps real time."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def now(self) -> datetime:
        # Real time plus everything advanced so far: never behind the service
        # clock that stamped the intents, always past the retry delays.
        return datetime.now(timezone.utc) + self.offset

    def advance(self, seconds: float) -> None:
        self.offset += timedelta(seconds=seconds)


class GraphitiEndpoint:
    """The Graphiti MCP endpoint under test: live, or the in-process dialect server."""

    def __init__(self) -> None:
        live = os.environ.get(GRAPHITI_URL_ENV, "").strip()
        self.live = bool(live)
        self.state: FakeGraphitiState | None = None
        self._server: ThreadingHTTPServer | None = None
        self._port = 0
        if live:
            self.url = live
            self.token = os.environ.get(GRAPHITI_TOKEN_ENV, "").strip() or None
        else:
            self.state = FakeGraphitiState()
            self.token = TOKEN
            self.start()

    def start(self) -> None:
        assert self.state is not None
        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), _handler(self.state))
        self._port = self._server.server_port
        self.url = f"http://127.0.0.1:{self._port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def provider(self) -> str:
        return "live" if self.live else "composition"

    def transport(self) -> HttpMcpTransport:
        return HttpMcpTransport(url=self.url, token=self.token, timeout_seconds=30)

    def episodes(self, group: str) -> dict[str, dict[str, Any]]:
        """Provider copies in ``group`` keyed by episode name, read over the wire."""

        result = self.transport().call_tool(
            "get_episodes", {"group_ids": [group], "max_episodes": 100}
        )
        episodes = result.get("episodes", []) if isinstance(result, dict) else []
        return {str(item["name"]): dict(item) for item in episodes}


@pytest.fixture(scope="module")
def graphiti() -> Any:
    endpoint = GraphitiEndpoint()
    try:
        yield endpoint
    finally:
        endpoint.stop()


@pytest.fixture
def seam_env(monkeypatch, tmp_path, graphiti):
    dsn = _require(POSTGRES_DSN_ENV, "PostgreSQL")
    pytest.importorskip("zep_cloud", reason="the manifest's Zep shadow target needs the zep extra")
    schema = f"l9_seam_{uuid.uuid4().hex}"

    import psycopg2
    import psycopg2.sql

    def _schema(statement: str) -> None:
        connection = psycopg2.connect(dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(psycopg2.sql.SQL(statement).format(psycopg2.sql.Identifier(schema)))
            connection.commit()
        finally:
            connection.close()

    _schema("CREATE SCHEMA {}")
    for key, value in {
        "L9_MEMORY_DATA_DIR": str(tmp_path / "data"),
        "L9_MEMORY_STATE_DIR": str(tmp_path / "state"),
        "L9_MEMORY_STORE_BACKEND": "postgres",
        "L9_MEMORY_POSTGRES_DSN": f"{dsn} options=-csearch_path={schema}",
        "L9_MEMORY_PROJECTION_RUNTIME": "manifest",
        "L9_MEMORY_PROJECTION_MANIFEST": MANIFEST,
        "L9_MEMORY_PROJECTION_BACKEND": "none",
        "GRAPHITI_MCP_URL": graphiti.url,
        "GRAPHITI_MCP_TOKEN": graphiti.token or "",
        "ZEP_API_KEY": "shadow-target-unreachable",
        "ZEP_API_URL": UNREACHABLE_ZEP,
        "L9_MEMORY_OUTBOX_MAX_ATTEMPTS": "3",
        "L9_MEMORY_OUTBOX_BASE_DELAY_SECONDS": "1",
        "L9_MEMORY_OUTBOX_LEASE_SECONDS": "5",
        "L9_MEMORY_HTTP_AUTH_REQUIRED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("L9_MEMORY_GRAPH_BACKEND", "L9_MEMORY_ACTIVE_BACKEND"):
        monkeypatch.delenv(key, raising=False)
    try:
        yield {"schema": schema, "dsn": dsn}
    finally:
        _schema("DROP SCHEMA {} CASCADE")


class Seam:
    """One composed process plus the worker ``l9-memory-worker`` would run."""

    def __init__(self, runtime: MemoryRuntime, graphiti: GraphitiEndpoint, dsn: str) -> None:
        self.runtime = runtime
        self.service: MemoryService = runtime.service
        self.graphiti = graphiti
        self.dsn = dsn
        self.clock = Clock()
        self.namespace = f"seam-{uuid.uuid4().hex[:8]}"
        self.group = graph_group_id(TENANT, self.namespace)
        self.worker = self.new_worker("worker-1")

    def new_worker(self, worker_id: str) -> OutboxWorker:
        return OutboxWorker(
            self.service.store,
            self.service.projections,
            self.runtime.settings,
            clock=self.clock,
            worker_id=worker_id,
        )

    def principal(self, *, read: bool = True, write: bool = True) -> MemoryPrincipal:
        return MemoryPrincipal(
            principal_id="seam-agent",
            tenant_id=TENANT,
            read_namespaces=(self.namespace,) if read else (),
            write_namespaces=(self.namespace,) if write else (),
            maintain_namespaces=(self.namespace,),
        )

    def admin(self) -> MemoryPrincipal:
        return MemoryPrincipal(
            principal_id="seam-admin",
            tenant_id=TENANT,
            read_namespaces=("*",),
            write_namespaces=("*",),
            promote_namespaces=("*",),
            is_admin=True,
        )

    def write(self, content: str, **kwargs: Any):
        return self.service.write(
            self.principal(),
            MemoryWriteRequest(
                namespace=self.namespace,
                content=content,
                provenance=Provenance(source="seam"),
                **kwargs,
            ),
        )

    def drain(self, worker: OutboxWorker | None = None, rounds: int = 6) -> dict[str, int]:
        """Run the worker until nothing is claimable.

        Against the in-process endpoint every delivery settles at once. A live
        Graphiti ingests asynchronously, so a lifecycle operation that must
        find the copy (retire, erase) fails closed and is retried until the
        provider has it; real time has to pass between those rounds.
        """

        totals = {"claimed": 0, "delivered": 0, "retried": 0, "dead": 0}
        budget = rounds if not self.graphiti.live else max(rounds, 60)
        idle = 0
        for _ in range(budget):
            result = (worker or self.worker).run_once()
            for key in totals:
                totals[key] += result.get(key, 0)
            self.clock.advance(60)
            if result.get("claimed", 0) == 0:
                idle += 1
                if not self.graphiti.live or idle >= 2:
                    break
            elif self.graphiti.live and result.get("retried", 0):
                time.sleep(3)
        return totals

    def wait_for(self, predicate, *, what: str, timeout: float = 240.0) -> None:
        """Block until ``predicate`` holds; immediate against the in-process endpoint."""

        deadline = time.monotonic() + (timeout if self.graphiti.live else 0.0)
        while True:
            if predicate():
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f"timed out waiting for {what}")
            time.sleep(3)

    def copy_present(self, record_id: UUID) -> None:
        self.wait_for(
            lambda: f"memory:{record_id}" in self.provider_names(),
            what=f"the provider copy of {record_id}",
        )

    def copy_absent(self, record_id: UUID) -> None:
        self.wait_for(
            lambda: f"memory:{record_id}" not in self.provider_names(),
            what=f"the withdrawal of {record_id}",
        )

    def outbox(self, record_id: UUID) -> dict[str, list[dict[str, Any]]]:
        """Durable intents for one record, by target identity, straight from PostgreSQL."""

        import psycopg2

        connection = psycopg2.connect(self.runtime.settings.postgres_dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event_type, status, attempts, last_error, event_json "
                    "FROM outbox_events WHERE aggregate_id = %s ORDER BY created_at",
                    (str(record_id),),
                )
                rows = cursor.fetchall()
        finally:
            connection.close()
        by_target: dict[str, list[dict[str, Any]]] = {}
        for event_type, status, attempts, last_error, event_json in rows:
            payload = json.loads(event_json)
            target = str(payload.get("payload", {}).get("target_identity"))
            by_target.setdefault(target, []).append(
                {
                    "event_type": event_type,
                    "status": status,
                    "attempts": attempts,
                    "last_error": last_error,
                }
            )
        return by_target

    def links(self, record_id: UUID) -> dict[str, str]:
        return {
            link.target_identity: link.locator
            for link in self.service.store.list_projection_links(record_id)
        }

    def search(self, query: str, principal: MemoryPrincipal | None = None, **kwargs: Any):
        return self.service.search(
            principal or self.principal(),
            MemorySearchRequest(query=query, namespaces=(self.namespace,), **kwargs),
        )

    def provider_names(self) -> set[str]:
        return set(self.graphiti.episodes(self.group))

    def close(self) -> None:
        self.runtime.close()


@pytest.fixture
def seam(seam_env, graphiti) -> Any:
    runtime = build_runtime()
    composed = Seam(runtime, graphiti, seam_env["dsn"])
    try:
        yield composed
    finally:
        composed.close()


def _only_projection_hits(monkeypatch, seam: Seam) -> None:
    """Let only a provider hit surface a record, so retrieval proves the seam."""

    monkeypatch.setattr(seam.service.store, "search_records", lambda *a, **k: [])


# --- seam 1: canonical -> projection ----------------------------------------


def test_seam1_canonical_write_reaches_the_compiled_target_through_the_outbox(seam) -> None:
    assert seam.service.projections.enabled
    assert {t.identity for t in seam.service.projections.targets} == {GRAPHITI, ZEP}
    receipt = seam.write("the billing service owner is the payments team")
    assert receipt.status is WriteStatus.ADMITTED
    stored = seam.service.store.get_record(receipt.record_id)
    assert stored is not None and stored.state is MemoryState.ACTIVE

    # The durable intent: one project event per delivering target, pending.
    intents = seam.outbox(receipt.record_id)
    assert set(intents) == {GRAPHITI, ZEP}
    for target in (GRAPHITI, ZEP):
        assert [e["event_type"] for e in intents[target]] == ["memory.record.project"]
        assert intents[target][0]["status"] == OutboxStatus.PENDING.value

    totals = seam.drain()
    assert totals["delivered"] >= 1
    intents = seam.outbox(receipt.record_id)
    assert intents[GRAPHITI][0]["status"] == OutboxStatus.DELIVERED.value
    # The shadow target is unreachable: its intent is retried, then dead, and
    # the failure is recorded on the intent, never on the record.
    zep_intent = intents[ZEP][0]
    assert zep_intent["status"] in {OutboxStatus.RETRY.value, OutboxStatus.DEAD.value}
    assert zep_intent["last_error"]

    # The provider copy and the per-target link agree on the locator.
    links = seam.links(receipt.record_id)
    assert set(links) == {GRAPHITI}
    assert episode_name_locator(seam.group, receipt.record_id).endswith(
        f"memory:{receipt.record_id}"
    )
    seam.copy_present(receipt.record_id)
    link = seam.service.store.get_projection_link(receipt.record_id, GRAPHITI)
    assert link is not None and link.provider_type == "graphiti_mcp"
    assert link.namespace == seam.namespace
    if seam.graphiti.state is not None:
        body = seam.graphiti.state.episodes[str(receipt.record_id)]["episode_body"]
        # The provider received the compiled facts.render.v3 rendering (not the
        # canonical record), scoped to the tenant group.
        assert f'record_id="{receipt.record_id}"' in body
        assert f'namespace="{seam.namespace}"' in body and f'tenant_id="{TENANT}"' in body
        assert 'schema_version="' in body and "provenance=" in body
        assert seam.graphiti.state.episodes[str(receipt.record_id)]["group_id"] == seam.group


def test_seam1_readiness_reports_the_projection_family_from_the_live_probe(seam) -> None:
    import asyncio

    report = asyncio.run(seam.runtime.readiness())
    projection = report.family("projection")
    assert projection.selected and projection.healthy and projection.ready
    assert projection.detail["runtime_mode"] == "manifest"
    targets = {t["target_identity"]: t for t in projection.detail["targets"]}
    assert targets[GRAPHITI]["mode"] == "active" and targets[GRAPHITI]["verified"] is True
    # A shadow target never degrades the family (ADR-084).
    assert targets[ZEP]["mode"] == "shadow"


# --- seam 3: projection -> retrieval ----------------------------------------


def test_seam3_retrieval_resolves_provider_hits_to_authorized_canonical_records(
    seam, monkeypatch
) -> None:
    first = seam.write("who owns the billing service: the payments team")
    seam.drain()
    seam.copy_present(first.record_id)
    _only_projection_hits(monkeypatch, seam)

    hits = seam.search("billing owner payments")
    assert [h.record.record_id for h in hits.hits] == [first.record_id]
    assert "projection" in hits.hits[0].matched_by
    assert hits.status is OperationStatus.COMPLETE
    evidence = {e.target_identity: e for e in hits.projection_evidence}
    assert GRAPHITI in evidence and evidence[GRAPHITI].succeeded
    assert evidence[GRAPHITI].contributed == 1
    assert ZEP not in evidence, "shadow targets are never queried by default"

    # Unauthorized: a principal without READ on the namespace gets nothing.
    with pytest.raises(AuthorizationError):
        seam.search("billing owner payments", principal=seam.principal(read=False))

    # Superseded: withdrawn from the provider and excluded from current truth.
    second = seam.write(
        "who owns the billing service: the platform team", supersedes=(first.record_id,)
    )
    seam.drain()
    assert seam.service.store.get_record(first.record_id).state is MemoryState.SUPERSEDED
    seam.copy_absent(first.record_id)
    seam.copy_present(second.record_id)
    current = seam.search("billing owner")
    assert [h.record.record_id for h in current.hits] == [second.record_id]
    # ... but reachable on explicit request, from canonical state.
    monkeypatch.undo()
    history = seam.search("billing owner", include_superseded=True)
    assert {h.record.record_id for h in history.hits} >= {first.record_id, second.record_id}

    # Archived: retired from the provider and excluded.
    seam.service.transition_lifecycle(
        seam.principal(),
        seam.namespace,
        record_ids=(second.record_id,),
        new_state=MemoryState.ARCHIVED,
        reason="seam archive",
    )
    seam.drain()
    seam.copy_absent(second.record_id)
    assert seam.search("billing owner").hits == ()
    assert [
        h.record.record_id for h in seam.search("billing owner", include_archived=True).hits
    ] == [second.record_id]


# --- seam 4: zep shadow path -------------------------------------------------


def test_seam4_shadow_failures_are_accounted_and_never_influence_retrieval(
    seam, monkeypatch
) -> None:
    # Content that names entities and a relation: a live Graphiti surfaces a
    # record through the facts it extracted (ADR-091 item 5), so a bare
    # statement that yields no entity is unreachable through the projection
    # and would prove nothing about the shadow path.
    written = seam.write("the release engineering team owns the tuesday deploy window")
    totals = seam.drain(rounds=8)
    intents = seam.outbox(written.record_id)
    zep_intent = intents[ZEP][0]
    # Independent delivery: Graphiti settled, Zep retried to exhaustion.
    assert intents[GRAPHITI][0]["status"] == OutboxStatus.DELIVERED.value
    assert zep_intent["status"] == OutboxStatus.DEAD.value
    assert zep_intent["attempts"] == seam.runtime.settings.outbox_max_attempts
    assert totals["dead"] == 1 and totals["retried"] >= 1
    assert ZEP not in seam.links(written.record_id)
    seam.copy_present(written.record_id)

    _only_projection_hits(monkeypatch, seam)
    seam.wait_for(
        lambda: (
            [h.record.record_id for h in seam.search("deploy window").hits] == [written.record_id]
        ),
        what="the provider to surface the record through its extracted facts",
    )
    baseline = seam.search("deploy window")
    assert [h.record.record_id for h in baseline.hits] == [written.record_id]
    assert not any(label.startswith(ZEP) for label in baseline.stores_attempted)

    # Measurement on: the shadow failure is recorded as evidence only.
    measured_service = MemoryService(
        seam.service.store,
        seam.service.projections,
        retrieval=RetrievalPlanner(
            seam.service.store, seam.service.projections, shadow_measurement=True
        ),
    )
    measured = measured_service.search(
        seam.principal(),
        MemorySearchRequest(query="deploy window", namespaces=(seam.namespace,)),
    )
    assert [h.record.record_id for h in measured.hits] == [written.record_id]
    # Scores carry a recency term evaluated at call time; the ordering and the
    # contributing hits are what the shadow target must not change.
    assert [h.score for h in measured.hits] == pytest.approx([h.score for h in baseline.hits])
    assert measured.status is OperationStatus.COMPLETE
    shadow = [e for e in measured.projection_evidence if e.target_identity == ZEP]
    assert shadow and all(e.mode == "shadow" and e.contributed == 0 for e in shadow)
    assert all(e.succeeded is False for e in shadow)


# --- seam 5: lifecycle propagation ------------------------------------------


def test_seam5_deletion_completes_only_after_every_held_copy_is_erased(seam) -> None:
    written = seam.write("subject data to be erased")
    seam.drain()
    assert set(seam.links(written.record_id)) == {GRAPHITI}
    seam.copy_present(written.record_id)

    deletion = seam.service.delete(
        seam.admin(),
        DeletionRequest(
            record_id=written.record_id, reason="subject request", verification_reference="seam"
        ),
    )
    assert deletion.status is DeletionStatus.PENDING_PROJECTION
    record = seam.service.store.get_record(written.record_id)
    assert record is not None and record.state is not MemoryState.DELETED
    intents = seam.outbox(written.record_id)
    assert [e["event_type"] for e in intents[GRAPHITI]][-1] == "memory.record.erase"
    assert [e["event_type"] for e in intents[ZEP]][-1] == "memory.record.erase"

    seam.drain(rounds=8)
    seam.copy_absent(written.record_id)
    assert seam.links(written.record_id) == {}
    tombstone = seam.service.store.get_record(written.record_id)
    assert tombstone is not None and tombstone.state is MemoryState.DELETED
    assert tombstone.content.startswith("[deleted:")
    assert seam.search("subject data").hits == ()
    # The erase intent for a target that never held a copy settles as a no-op.
    assert seam.outbox(written.record_id)[ZEP][-1]["status"] == OutboxStatus.DELIVERED.value


def test_seam5_rebuild_restores_a_lost_copy_without_duplicating_the_rest(seam) -> None:
    kept = seam.write("kept record stays projected once")
    lost = seam.write("lost record is restored by rebuild")
    seam.drain()
    seam.copy_present(kept.record_id)
    seam.copy_present(lost.record_id)

    # Reconciliation with nothing missing queues nothing.
    untouched = seam.service.rebuild_projection(
        seam.principal(), seam.namespace, apply=True, target=GRAPHITI
    )
    assert untouched.queued_record_ids == ()

    # The provider loses a copy and canonical state loses its link.
    seam.graphiti.transport().call_tool(
        "delete_episode",
        {"uuid": seam.graphiti.episodes(seam.group)[f"memory:{lost.record_id}"]["uuid"]},
    )
    seam.service.store.delete_projection_link(lost.record_id, GRAPHITI)
    rebuild = seam.service.rebuild_projection(
        seam.principal(), seam.namespace, apply=True, target=GRAPHITI
    )
    assert rebuild.queued_record_ids == (lost.record_id,)
    seam.drain()
    seam.copy_present(lost.record_id)
    names = seam.provider_names()
    assert {f"memory:{kept.record_id}", f"memory:{lost.record_id}"} <= names
    assert len([n for n in names if n == f"memory:{kept.record_id}"]) == 1
    assert set(seam.links(lost.record_id)) == {GRAPHITI}

    # Repeating the rebuild is idempotent.
    again = seam.service.rebuild_projection(
        seam.principal(), seam.namespace, apply=True, target=GRAPHITI
    )
    assert again.queued_record_ids == ()


# --- seam 6: failure and recovery -------------------------------------------


def test_seam6_duplicate_and_stale_events_never_project_twice_or_project_dead_records(
    seam,
) -> None:
    # Entity-bearing content, as in every live seam: against the real server
    # the extraction model decides what the episode becomes, and a bare
    # phrase once made it emit a Document entity with a null description that
    # upstream's queue rejected after acknowledging the write (an upstream
    # finding recorded in the Phase 5 receipt, not a package behaviour).
    keyed = seam.write("Falcon maintains the idempotency service", idempotency_key="seam-op-1")
    replay = seam.write("Falcon maintains the idempotency service", idempotency_key="seam-op-1")
    assert replay.status is WriteStatus.DUPLICATE and replay.record_id == keyed.record_id
    seam.drain()
    assert len(seam.outbox(keyed.record_id)[GRAPHITI]) == 1
    seam.copy_present(keyed.record_id)
    before = seam.provider_names()
    # A second drain re-delivers nothing: delivered intents are settled.
    assert seam.drain()["delivered"] == 0
    assert seam.provider_names() == before

    # Stale: the record is archived before its project intent is delivered.
    stale = seam.write("Osprey archived the reporting service before delivery")
    seam.service.transition_lifecycle(
        seam.principal(),
        seam.namespace,
        record_ids=(stale.record_id,),
        new_state=MemoryState.ARCHIVED,
        reason="stale before delivery",
    )
    seam.drain()
    assert f"memory:{stale.record_id}" not in seam.provider_names()
    assert seam.links(stale.record_id) == {}
    assert seam.outbox(stale.record_id)[GRAPHITI][0]["status"] == OutboxStatus.DELIVERED.value


def test_seam6_outage_backlog_restart_and_recovery(seam) -> None:
    if seam.graphiti.live:
        pytest.skip("the outage case stops the in-process endpoint; a live server is not stopped")
    written = seam.write("written while the provider is down")
    seam.graphiti.stop()
    try:
        first = seam.drain(rounds=1)
        assert first["retried"] >= 1 and first["delivered"] == 0
        intents = seam.outbox(written.record_id)
        assert intents[GRAPHITI][0]["status"] == OutboxStatus.RETRY.value
        assert intents[GRAPHITI][0]["last_error"]
        assert seam.service.store.outbox_backlog() >= 1
        # Canonical memory is complete and readable throughout the outage.
        record = seam.service.store.get_record(written.record_id)
        assert record is not None and record.state is MemoryState.ACTIVE
        health = seam.service.health()
        assert health.status is OperationStatus.PARTIAL
        assert "projection is unhealthy" in health.degraded_reasons
    finally:
        seam.graphiti.start()
    # A different worker (a restarted process) recovers the backlog.
    restarted = seam.new_worker("worker-2")
    totals = seam.drain(restarted)
    assert totals["delivered"] >= 1
    seam.copy_present(written.record_id)
    assert set(seam.links(written.record_id)) == {GRAPHITI}
    assert seam.service.health().status is OperationStatus.COMPLETE


def test_seam6_an_abandoned_lease_is_recovered_by_the_next_worker(seam) -> None:
    written = seam.write("claimed by a worker that died")
    store = seam.service.store
    now = seam.clock.now()
    claimed = store.claim_outbox(limit=10, now=now, lease_seconds=5, lease_owner="dead-worker")
    assert {e.aggregate_id for e in claimed} == {written.record_id}
    # While the lease is live another worker cannot take the events.
    assert seam.worker.run_once()["claimed"] == 0
    seam.clock.advance(10)
    totals = seam.drain(seam.new_worker("worker-3"))
    assert totals["delivered"] >= 1
    assert seam.outbox(written.record_id)[GRAPHITI][0]["status"] == OutboxStatus.DELIVERED.value
    seam.copy_present(written.record_id)


# --- seam 7: deterministic reconciliation -----------------------------------


def test_seam7_expected_versus_observed_targets_links_and_copies_agree(seam) -> None:
    records = [seam.write(f"reconcile fact {i}") for i in range(3)]
    seam.drain(rounds=8)
    active = {r.record_id for r in records}
    expected_links = {(rid, GRAPHITI) for rid in active}
    observed_links = {(rid, target) for rid in active for target in seam.links(rid)}
    assert observed_links == expected_links
    for rid in active:
        seam.copy_present(rid)
    expected_names = {f"memory:{rid}" for rid in active}
    assert expected_names <= seam.provider_names()
    assert seam.service.store.outbox_backlog() == 0 or all(
        e["status"] == OutboxStatus.DEAD.value for rid in active for e in seam.outbox(rid)[ZEP]
    )
    # Two reconciliations in a row change nothing.
    for _ in range(2):
        result = seam.service.rebuild_projection(
            seam.principal(), seam.namespace, apply=True, target=GRAPHITI
        )
        assert result.queued_record_ids == ()
    assert {(rid, target) for rid in active for target in seam.links(rid)} == expected_links


# --- seam 2: graphiti -> neo4j (live endpoint only) --------------------------


def test_seam2_live_graphiti_persists_scoped_graph_structures_in_neo4j(seam) -> None:
    if not seam.graphiti.live:
        pytest.skip(f"{GRAPHITI_URL_ENV} is not set; seam 2 needs a live Graphiti endpoint")
    uri = _require(NEO4J_URI_ENV, "Neo4j")
    import neo4j

    written = seam.write("Falcon reports to Osprey on the billing platform team")
    seam.drain()
    auth = (
        os.environ.get("L9_MEMORY_TEST_NEO4J_USER", "neo4j"),
        os.environ.get("L9_MEMORY_TEST_NEO4J_PASSWORD", ""),
    )
    deadline = time.monotonic() + 240
    with neo4j.GraphDatabase.driver(uri, auth=auth) as driver:
        while True:
            rows = driver.execute_query(
                "MATCH (e:Episodic {name: $name, group_id: $group}) "
                "OPTIONAL MATCH (e)-[:MENTIONS]->(n:Entity) "
                "RETURN e.uuid AS uuid, count(n) AS entities",
                name=f"memory:{written.record_id}",
                group=seam.group,
            ).records
            if rows and rows[0]["entities"] > 0:
                break
            if time.monotonic() > deadline:
                raise AssertionError("Graphiti did not persist the scoped episode and entities")
            time.sleep(5)
    # The MCP server's add_memory answers "queued" without an id, so the link
    # holds the episode-name locator (ADR-091); the Episodic node Graphiti
    # persisted carries that name in the scoped group, with the entities it
    # extracted hanging off it.
    link = seam.service.store.get_projection_link(written.record_id, GRAPHITI)
    assert link is not None
    assert link.locator == episode_name_locator(seam.group, written.record_id)
    assert rows[0]["uuid"]
