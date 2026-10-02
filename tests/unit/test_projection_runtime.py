# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_projection_runtime.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-10-01
"""Projection runtime composition, target modes, and runtime selection (ADR-084)."""

from __future__ import annotations

import ast
import sys
import types
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from l9_graphite_memory.adapters import GraphitiProjection, NullProjection
from l9_graphite_memory.adapters.factory import build_projection_runtime
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.errors import ConfigurationError, ProjectionError
from l9_graphite_memory.projections import (
    ProjectionRuntime,
    TargetMode,
    compile_projection,
    compiled_projection_json,
    load_projection_manifest,
    parse_projection_manifest_data,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "projections" / "facts-v8.yaml"
GRAPHITI = "facts:v8:graphiti_mcp:primary"
ZEP = "facts:v8:zep:primary"


def manifest_data() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def with_modes(graphiti: str, zep: str, *, status: str = "active") -> dict[str, Any]:
    data = deepcopy(manifest_data())
    data["metadata"]["status"] = status
    data["spec"]["providers"][0]["mode"] = graphiti
    data["spec"]["providers"][1]["mode"] = zep
    return data


class StubAdapter:
    capabilities: tuple[str, ...] = ("graph-search", "semantic-search")

    def __init__(self, name: str, *, healthy: bool = True) -> None:
        self.name = name
        self._healthy = healthy
        self.health_calls = 0

    def health(self) -> dict[str, Any]:
        self.health_calls += 1
        return {"name": self.name, "healthy": self._healthy}


# -- T-01 compiler determinism ----------------------------------------------


def test_facts_v8_declares_graphiti_active_and_zep_shadow() -> None:
    compiled = compile_projection(load_projection_manifest(MANIFEST_PATH))

    assert compiled.status == "active"
    modes = {target.identity: (target.mode, target.required) for target in compiled.targets}
    assert modes == {GRAPHITI: ("active", False), ZEP: ("shadow", False)}


def test_target_mode_compiles_deterministically_and_is_digested() -> None:
    first = compile_projection(parse_projection_manifest_data(with_modes("active", "shadow")))
    second = compile_projection(parse_projection_manifest_data(with_modes("active", "shadow")))
    flipped = compile_projection(parse_projection_manifest_data(with_modes("active", "disabled")))

    assert compiled_projection_json(first) == compiled_projection_json(second)
    assert first.compiled_artifact_digest == second.compiled_artifact_digest
    assert [target.identity for target in first.targets] == [GRAPHITI, ZEP]
    # Mode is part of the compiled artifact, so changing it changes the digest
    # while target identity stays the same.
    assert flipped.compiled_artifact_digest != first.compiled_artifact_digest
    assert [target.identity for target in flipped.targets] == [GRAPHITI, ZEP]


def test_unset_mode_defaults_to_disabled() -> None:
    data = manifest_data()
    data["metadata"]["status"] = "shadow"
    for provider in data["spec"]["providers"]:
        provider.pop("mode")
    compiled = compile_projection(parse_projection_manifest_data(data))

    assert {target.mode for target in compiled.targets} == {"disabled"}


def test_duplicate_target_identity_fails() -> None:
    data = manifest_data()
    data["spec"]["providers"][1] = {**data["spec"]["providers"][0], "id": "graphiti-copy"}

    with pytest.raises(ConfigurationError, match="identities must be unique"):
        parse_projection_manifest_data(data)


@pytest.mark.parametrize(
    ("status", "graphiti", "zep", "message"),
    [
        ("shadow", "active", "shadow", "shadow projection cannot declare an active target"),
        ("retired", "disabled", "shadow", "retired projection can only declare disabled"),
        ("active", "shadow", "shadow", "active projection requires at least one active"),
    ],
)
def test_projection_status_binds_target_modes(
    status: str, graphiti: str, zep: str, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_projection_manifest_data(with_modes(graphiti, zep, status=status))


def test_required_is_separate_from_mode_and_limited_to_active_targets() -> None:
    data = with_modes("active", "shadow")
    data["spec"]["providers"][1]["required"] = True

    with pytest.raises(ConfigurationError, match="only an active target can be required"):
        parse_projection_manifest_data(data)

    data = with_modes("active", "shadow")
    data["spec"]["providers"][0]["required"] = True
    compiled = compile_projection(parse_projection_manifest_data(data))
    assert {target.identity: target.required for target in compiled.targets} == {
        GRAPHITI: True,
        ZEP: False,
    }


# -- T-02 runtime composition -----------------------------------------------


def _runtime(
    graphiti_mode: str = "active", zep_mode: str = "shadow", **adapters: Any
) -> ProjectionRuntime:
    compiled = compile_projection(
        parse_projection_manifest_data(with_modes(graphiti_mode, zep_mode))
    )
    bound = {GRAPHITI: adapters.get("graphiti"), ZEP: adapters.get("zep")}
    return ProjectionRuntime.from_compiled(compiled, bound)


def test_runtime_partitions_targets_by_mode() -> None:
    graphiti, zep = StubAdapter("graphiti"), StubAdapter("zep")
    runtime = _runtime(graphiti=graphiti, zep=zep)

    assert runtime.mode == "manifest"
    assert [binding.identity for binding in runtime.active_targets()] == [GRAPHITI]
    assert [binding.identity for binding in runtime.shadow_targets()] == [ZEP]
    assert [binding.identity for binding in runtime.delivery_targets()] == [GRAPHITI, ZEP]
    assert runtime.adapter_for(GRAPHITI) is graphiti
    assert runtime.adapter_for(ZEP) is zep
    binding = runtime.target(ZEP)
    assert (binding.provider_type, binding.projection_name, binding.projection_version) == (
        "zep",
        "facts",
        8,
    )
    assert binding.manifest_digest == runtime.compiled.manifest_digest


def test_disabled_target_neither_delivers_nor_retrieves_but_stays_addressable() -> None:
    graphiti = StubAdapter("graphiti")
    runtime = _runtime("active", "disabled", graphiti=graphiti, zep=None)

    assert [binding.identity for binding in runtime.delivery_targets()] == [GRAPHITI]
    assert runtime.shadow_targets() == ()
    disabled = runtime.target(ZEP)
    assert disabled.mode is TargetMode.DISABLED
    assert not disabled.delivers and not disabled.retrievable
    # Lifecycle work against an unconfigured disabled target fails explicitly.
    with pytest.raises(ProjectionError, match="not configured"):
        runtime.adapter_for(ZEP)


def test_delivering_target_without_adapter_fails_closed() -> None:
    with pytest.raises(ConfigurationError, match="has no adapter"):
        _runtime(graphiti=StubAdapter("graphiti"), zep=None)


def test_unknown_target_fails_closed() -> None:
    runtime = _runtime(graphiti=StubAdapter("graphiti"), zep=StubAdapter("zep"))

    with pytest.raises(ProjectionError, match="unknown projection target"):
        runtime.target("facts:v8:graphiti_mcp:secondary")
    with pytest.raises(ProjectionError, match="unknown projection target"):
        runtime.resolve_event_target("facts:v7:zep:primary")
    # An untargeted event cannot be attributed to one of two targets.
    with pytest.raises(ProjectionError, match="carries no target_identity"):
        runtime.resolve_event_target(None)


def test_legacy_adapter_becomes_one_active_target_named_as_before() -> None:
    adapter = StubAdapter("graphiti")
    runtime = ProjectionRuntime.legacy(adapter, required=True)

    (binding,) = runtime.targets
    assert (binding.identity, binding.provider_type, binding.mode, binding.required) == (
        "graphiti",
        "legacy",
        TargetMode.ACTIVE,
        True,
    )
    # Events written before target identity existed resolve to the one target.
    assert runtime.resolve_event_target(None) is binding
    assert ProjectionRuntime.legacy(NullProjection()).targets == ()
    assert not ProjectionRuntime.legacy(NullProjection()).enabled


def test_health_probes_delivering_targets_only_and_reports_identity() -> None:
    graphiti, zep = StubAdapter("graphiti"), StubAdapter("zep", healthy=False)
    health = _runtime(graphiti=graphiti, zep=zep).health()

    assert health["runtime_mode"] == "manifest"
    assert health["projection"]["name"] == "facts" and health["projection"]["version"] == 8
    # A shadow target's health never degrades the projection.
    assert health["healthy"] is True
    by_identity = {item["target_identity"]: item for item in health["targets"]}
    assert by_identity[GRAPHITI]["mode"] == "active" and by_identity[GRAPHITI]["verified"]
    assert by_identity[ZEP]["mode"] == "shadow" and not by_identity[ZEP]["verified"]

    disabled = _runtime("active", "disabled", graphiti=graphiti, zep=zep).health()
    entry = {item["target_identity"]: item for item in disabled["targets"]}[ZEP]
    # Configured but not probed: configuration alone is not health.
    assert entry["configured"] is True and entry["verified"] is False and entry["health"] is None
    assert zep.health_calls == 1


def test_runtime_has_no_canonical_store_access() -> None:
    import l9_graphite_memory.projections.runtime as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any("record_store" in name or "adapters" in name for name in imported)
    assert "store" not in ProjectionRuntime.__init__.__code__.co_varnames


# -- factory construction ---------------------------------------------------


@pytest.fixture
def fake_zep_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeZep:
        def __init__(self, **_kwargs: Any) -> None:
            self.graph = object()

    package = types.ModuleType("zep_cloud")
    client = types.ModuleType("zep_cloud.client")
    client.Zep = FakeZep  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zep_cloud", package)
    monkeypatch.setitem(sys.modules, "zep_cloud.client", client)


def _manifest_settings(tmp_path: Path, **overrides: Any) -> MemorySettings:
    return MemorySettings(
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        projection_runtime="manifest",
        projection_manifest=MANIFEST_PATH,
        **overrides,
    )


def test_factory_builds_one_adapter_per_target(tmp_path: Path, fake_zep_sdk: None) -> None:
    runtime = build_projection_runtime(
        _manifest_settings(
            tmp_path, graphiti_mcp_url="http://127.0.0.1:9/mcp", zep_api_key="test-key"
        )
    )

    graphiti, zep = runtime.adapter_for(GRAPHITI), runtime.adapter_for(ZEP)
    assert isinstance(graphiti, GraphitiProjection) and isinstance(zep, GraphitiProjection)
    assert graphiti is not zep
    assert graphiti.transport.name != zep.transport.name
    # Zep configuration is not connectivity proof.
    zep_health = {item["target_identity"]: item for item in runtime.health()["targets"]}[ZEP]
    assert zep_health["configured"] is True and zep_health["verified"] is False


def test_factory_fails_closed_when_a_delivering_target_is_unconfigured(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="ZEP_API_KEY is required"):
        build_projection_runtime(
            _manifest_settings(tmp_path, graphiti_mcp_url="http://127.0.0.1:9/mcp")
        )


# -- T-16 runtime selection and legacy mode ---------------------------------


@pytest.mark.parametrize("backend", ["none", "http", "zep"])
def test_legacy_scalar_backends_remain_valid(
    tmp_path: Path, backend: str, fake_zep_sdk: None
) -> None:
    settings = MemorySettings(
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        projection_backend=backend,
        graphiti_mcp_url="http://127.0.0.1:9/mcp",
        zep_api_key="test-key",
    )
    runtime = build_projection_runtime(settings)

    assert settings.projection_runtime == "legacy"
    assert runtime.mode == "legacy"
    expected = () if backend == "none" else ("graphiti",)
    assert tuple(binding.identity for binding in runtime.targets) == expected


def test_manifest_mode_requires_a_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires projection_manifest"):
        MemorySettings(
            data_dir=tmp_path / "data", state_dir=tmp_path / "state", projection_runtime="manifest"
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"projection_backend": "http"}, "mutually exclusive"),
        ({"projection_backend": "zep"}, "mutually exclusive"),
        ({"projection_required": True}, "legacy scalar policy"),
    ],
)
def test_manifest_mode_rejects_scalar_provider_selection(
    tmp_path: Path, overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _manifest_settings(tmp_path, **overrides)


def test_legacy_mode_rejects_a_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only valid with projection_runtime 'manifest'"):
        MemorySettings(
            data_dir=tmp_path / "data",
            state_dir=tmp_path / "state",
            projection_manifest=MANIFEST_PATH,
        )


def test_runtime_selection_is_explicit_in_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("L9_MEMORY_PROJECTION_MANIFEST", str(MANIFEST_PATH))
    # A manifest path alone never switches the runtime.
    with pytest.raises(ConfigurationError, match="only valid with projection_runtime"):
        load_settings()

    monkeypatch.setenv("L9_MEMORY_PROJECTION_RUNTIME", "manifest")
    settings = load_settings()
    assert settings.projection_runtime == "manifest"
    assert settings.projection_manifest == MANIFEST_PATH
