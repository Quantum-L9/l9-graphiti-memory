# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_stdio_namespace_resolution.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-09-19

"""The local transport resolves authorization per request, not per spawn.

``memory.write_agent`` takes a ``namespace`` argument, which implies per-call
addressing. Before this suite it did not get it: ``run_stdio`` resolved the
principal once before its stdin loop and the Tier 3 fallback resolved grants
from the process's working directory, so every later ``namespace`` argument was
checked against whichever repository the host happened to launch the server in.
An agent could not durably record a fact about a second repository in its own
session, and the rejection was indistinguishable from a malformed call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.group_resolver import registered_namespaces, resolve_namespace_request
from l9_graphite_memory.runtime import resolve_local_context_for_namespace
from l9_graphite_memory.server import (
    StdioPrincipalResolver,
    _requested_namespace,
    _stdio_principal,
)

# Two registered repositories, neither of which is the directory the tests run
# in once ``chdir`` has moved the process somewhere unresolvable.
HOME_REPO = "l9-graphiti-memory"
OTHER_REPO = "cursor-governance"


def _tools_call(namespace: str | None) -> dict[str, object]:
    arguments: dict[str, object] = {"content": "a durable fact"}
    if namespace is not None:
        arguments["namespace"] = namespace
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "memory.write_agent", "arguments": arguments},
    }


@pytest.fixture(autouse=True)
def _no_doors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Tier 3. Tiers 1 and 2 read the environment, not the filesystem."""

    for name in (
        "L9_MEMORY_HUMAN_DOOR_SECRET",
        "L9_MEMORY_AGENTS_DOOR_SECRET",
        "L9_MEMORY_NAMESPACE",
        "GRAPHITI_GROUP_ID",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def unresolvable_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run from a directory that matches no registered repository.

    This is the shape of the bug: the server's cwd is not the repository the
    caller is addressing. Here it is not *any* repository, which makes the
    assertions unambiguous — any write grant that appears can only have come
    from the requested namespace.
    """

    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# registry reverse lookup
# ---------------------------------------------------------------------------


def test_registered_namespaces_contains_every_repo_slug() -> None:
    namespaces = registered_namespaces()
    assert HOME_REPO in namespaces
    assert OTHER_REPO in namespaces


def test_registered_namespaces_excludes_forbidden() -> None:
    namespaces = registered_namespaces()
    for forbidden in ("main", "default", "test", ""):
        assert forbidden not in namespaces


@pytest.mark.parametrize("namespace", ["main", "default", "test", ""])
def test_namespace_request_refuses_forbidden(namespace: str) -> None:
    resolution = resolve_namespace_request(namespace)
    assert resolution.group_id is None
    assert resolution.readonly is True
    assert resolution.error


def test_namespace_request_refuses_unregistered() -> None:
    resolution = resolve_namespace_request("not-a-registered-repository")
    assert resolution.group_id is None
    assert resolution.error is not None
    assert "not a registered repository" in resolution.error


def test_namespace_request_reads_the_registry_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """One YAML parse per request, not two.

    This resolution now runs on every request, so reading and parsing the
    registry twice per call is overhead paid on every agent write. Asserted
    rather than commented, because the second read was invisible at the call
    site — it was inside a helper that loaded the registry for itself.
    """

    from l9_graphite_memory import group_resolver

    real = group_resolver.load_registry
    calls = 0

    def counting(settings: object = None) -> dict:
        nonlocal calls
        calls += 1
        return real(settings)  # type: ignore[arg-type]

    monkeypatch.setattr(group_resolver, "load_registry", counting)
    resolution = group_resolver.resolve_namespace_request(OTHER_REPO)

    assert resolution.group_id == OTHER_REPO
    assert calls == 1


def test_namespace_request_resolves_registered_slug_without_cwd(unresolvable_cwd: Path) -> None:
    resolution = resolve_namespace_request(OTHER_REPO)
    assert resolution.group_id == OTHER_REPO
    assert resolution.readonly is False
    assert resolution.method == "namespace_request"


# ---------------------------------------------------------------------------
# the regression: a second repository is writable in the same session
# ---------------------------------------------------------------------------


def test_requested_namespace_is_writable_though_cwd_is_elsewhere(
    unresolvable_cwd: Path,
) -> None:
    """The fix, stated as the failure it repairs.

    Against the pre-fix resolver this principal's grants came from ``cwd``,
    which here resolves to nothing, so ``write_namespaces`` was empty and the
    write was rejected with "namespace did not match any write grant".
    """

    settings = MemorySettings()
    resolver = StdioPrincipalResolver(settings)

    principal = resolver.for_request(_tools_call(OTHER_REPO))

    assert principal.auth_method == "stdio-local"
    assert OTHER_REPO in principal.write_namespaces
    assert OTHER_REPO in principal.read_namespaces
    assert principal.is_admin is False


def test_two_namespaces_in_one_session_each_get_their_own_grant(
    unresolvable_cwd: Path,
) -> None:
    """One process, two roots. This is the multi-root session the bug broke."""

    resolver = StdioPrincipalResolver(MemorySettings())

    first = resolver.for_request(_tools_call(HOME_REPO))
    second = resolver.for_request(_tools_call(OTHER_REPO))

    assert first.write_namespaces == (HOME_REPO,)
    assert second.write_namespaces == (OTHER_REPO,)


def test_unregistered_namespace_still_falls_back_to_cwd(unresolvable_cwd: Path) -> None:
    """Widening is narrow: only a registered slug resolves.

    Everything else keeps the previous behaviour, which is what preserves read
    access to the workspace namespace and to namespaces a custom registry does
    not list.
    """

    resolver = StdioPrincipalResolver(MemorySettings())
    principal = resolver.for_request(_tools_call("not-a-registered-repository"))

    assert principal.write_namespaces == ()


def test_request_without_a_namespace_falls_back_to_cwd(unresolvable_cwd: Path) -> None:
    resolver = StdioPrincipalResolver(MemorySettings())
    principal = resolver.for_request(_tools_call(None))

    assert principal.write_namespaces == ()


@pytest.mark.parametrize(
    "request_payload",
    [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": "not-an-object"},
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "x"}},
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "x", "arguments": {"namespace": 7}},
        },
    ],
)
def test_requested_namespace_reads_nothing_it_should_not(request_payload: dict) -> None:
    assert _requested_namespace(request_payload) is None


def test_requested_namespace_reads_a_tools_call_argument() -> None:
    assert _requested_namespace(_tools_call(OTHER_REPO)) == OTHER_REPO


# ---------------------------------------------------------------------------
# what the fix must NOT widen
# ---------------------------------------------------------------------------


def test_configured_local_claims_are_never_widened_by_a_request(
    unresolvable_cwd: Path,
) -> None:
    """ADR-006: configured ``local_*_namespaces`` are the sole ACL source.

    An explicit operator grant is a ceiling, not a default. A request naming
    another registered repository must not climb over it.
    """

    settings = MemorySettings(
        local_read_namespaces=(HOME_REPO,),
        local_write_namespaces=(HOME_REPO,),
    )
    resolver = StdioPrincipalResolver(settings)

    principal = resolver.for_request(_tools_call(OTHER_REPO))

    assert principal.write_namespaces == (HOME_REPO,)
    assert OTHER_REPO not in principal.write_namespaces


@pytest.mark.parametrize("namespace", ["main", "default", "test"])
def test_forbidden_namespace_is_never_granted(namespace: str, unresolvable_cwd: Path) -> None:
    resolver = StdioPrincipalResolver(MemorySettings())
    principal = resolver.for_request(_tools_call(namespace))

    assert namespace not in principal.write_namespaces


def test_door_principal_is_static_across_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1/2 claims come from the environment, so they do not vary per call."""

    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "hunter2")
    resolver = StdioPrincipalResolver(MemorySettings())

    assert resolver.door_principal is not None
    first = resolver.for_request(_tools_call(HOME_REPO))
    second = resolver.for_request(_tools_call(OTHER_REPO))
    assert first == second
    assert first.auth_method == "stdio-human-door"


def test_the_frozen_path_is_what_the_resolver_replaces(unresolvable_cwd: Path) -> None:
    """The regression, proven against the pre-fix code rather than asserted.

    ``_stdio_principal`` is the spawn-time resolution unchanged — the exact
    call ``run_stdio`` used to make once before its stdin loop. Running both
    from the same directory shows the difference is the fix and not the
    fixture: the frozen principal has no grant for the requested repository,
    the per-request one does.
    """

    settings = MemorySettings()

    frozen = _stdio_principal(settings)
    per_request = StdioPrincipalResolver(settings).for_request(_tools_call(OTHER_REPO))

    assert OTHER_REPO not in frozen.write_namespaces
    assert OTHER_REPO in per_request.write_namespaces


def test_resolve_local_context_for_namespace_reports_the_resolution(
    unresolvable_cwd: Path,
) -> None:
    resolution, principal = resolve_local_context_for_namespace(MemorySettings(), OTHER_REPO)

    assert resolution.group_id == OTHER_REPO
    assert resolution.method == "namespace_request"
    assert OTHER_REPO in principal.write_namespaces
