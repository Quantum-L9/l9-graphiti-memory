# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/projections/runtime.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-10-01
"""Realize a compiled projection as independently addressable provider targets.

The runtime maps target identities to one-provider adapters and answers which
targets deliver, which may contribute to retrieval, and which are only
measured. It owns no canonical state: records, lifecycle decisions, links,
receipts, and outbox state stay with ``MemoryService`` and the ``RecordStore``
(ADR-084).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from l9_graphite_memory.contracts import LEGACY_PROVIDER_TYPE
from l9_graphite_memory.errors import ConfigurationError, ProjectionError
from l9_graphite_memory.ports.projection import ProjectionAdapter

from .contracts import CompiledProjection, TargetMode

RuntimeMode = Literal["legacy", "manifest"]


@dataclass(frozen=True)
class ProjectionTargetBinding:
    """One provider target and the adapter that speaks its dialect.

    ``adapter`` is None only for a disabled target whose provider is not
    configured; lifecycle work against such a target fails explicitly rather
    than being treated as done.
    """

    identity: str
    projection_name: str
    projection_version: int | None
    provider_type: str
    target: str
    mode: TargetMode
    required: bool
    adapter: ProjectionAdapter | None
    manifest_digest: str | None = None
    render_contract_digest: str | None = None

    @property
    def delivers(self) -> bool:
        return self.mode in {TargetMode.ACTIVE, TargetMode.SHADOW}

    @property
    def retrievable(self) -> bool:
        return self.mode == TargetMode.ACTIVE


class ProjectionRuntime:
    """Immutable mapping of target identity to provider adapter."""

    def __init__(
        self,
        bindings: Iterable[ProjectionTargetBinding],
        *,
        mode: RuntimeMode,
        compiled: CompiledProjection | None = None,
        legacy_adapter: ProjectionAdapter | None = None,
    ) -> None:
        targets = tuple(bindings)
        identities = [binding.identity for binding in targets]
        if len(set(identities)) != len(identities):
            raise ConfigurationError("projection target identities must be unique")
        if mode == "manifest" and compiled is None:
            raise ConfigurationError("manifest projection runtime requires a compiled projection")
        for binding in targets:
            if binding.delivers and binding.adapter is None:
                raise ConfigurationError(
                    f"projection target {binding.identity} is {binding.mode} but has no adapter"
                )
        self.mode: RuntimeMode = mode
        self.compiled = compiled
        self._targets = targets
        self._by_identity = {binding.identity: binding for binding in targets}
        self._legacy_adapter = legacy_adapter

    @classmethod
    def legacy(cls, adapter: ProjectionAdapter, *, required: bool = False) -> ProjectionRuntime:
        """Represent one scalar ``none``/``http``/``zep`` adapter as a runtime.

        The scalar adapter becomes one active target whose identity is its
        name, which is the key links were persisted under before ADR-084. The
        ``none`` adapter yields no targets at all.
        """

        if adapter.name == "none":
            return cls((), mode="legacy", legacy_adapter=adapter)
        binding = ProjectionTargetBinding(
            identity=adapter.name,
            projection_name=adapter.name,
            projection_version=None,
            provider_type=LEGACY_PROVIDER_TYPE,
            target=adapter.name,
            mode=TargetMode.ACTIVE,
            required=required,
            adapter=adapter,
        )
        return cls((binding,), mode="legacy", legacy_adapter=adapter)

    @classmethod
    def from_compiled(
        cls,
        compiled: CompiledProjection,
        adapters: Mapping[str, ProjectionAdapter | None],
    ) -> ProjectionRuntime:
        """Bind every compiled target to the adapter constructed for it."""

        unknown = set(adapters) - {target.identity for target in compiled.targets}
        if unknown:
            raise ConfigurationError(
                "adapters supplied for targets the projection does not declare: "
                + ", ".join(sorted(unknown))
            )
        bindings = []
        for target in compiled.targets:
            if target.identity not in adapters:
                raise ConfigurationError(f"no adapter binding for target {target.identity}")
            bindings.append(
                ProjectionTargetBinding(
                    identity=target.identity,
                    projection_name=compiled.name,
                    projection_version=compiled.version,
                    provider_type=str(target.provider_type),
                    target=target.target,
                    mode=TargetMode(target.mode),
                    required=target.required,
                    adapter=adapters[target.identity],
                    manifest_digest=compiled.manifest_digest,
                    render_contract_digest=compiled.render_contract_digest,
                )
            )
        return cls(bindings, mode="manifest", compiled=compiled)

    @classmethod
    def coerce(
        cls,
        projection: ProjectionAdapter | ProjectionRuntime,
        *,
        required: bool = False,
    ) -> ProjectionRuntime:
        """Accept either a runtime or a single legacy adapter."""

        if isinstance(projection, ProjectionRuntime):
            if required:
                raise ConfigurationError(
                    "projection_required applies to a legacy adapter; a projection "
                    "runtime declares required targets itself"
                )
            return projection
        return cls.legacy(projection, required=required)

    @property
    def targets(self) -> tuple[ProjectionTargetBinding, ...]:
        return self._targets

    @property
    def enabled(self) -> bool:
        """True when at least one target receives deliveries."""

        return any(binding.delivers for binding in self._targets)

    def delivery_targets(self) -> tuple[ProjectionTargetBinding, ...]:
        return tuple(binding for binding in self._targets if binding.delivers)

    def active_targets(self) -> tuple[ProjectionTargetBinding, ...]:
        return tuple(binding for binding in self._targets if binding.mode == TargetMode.ACTIVE)

    def shadow_targets(self) -> tuple[ProjectionTargetBinding, ...]:
        return tuple(binding for binding in self._targets if binding.mode == TargetMode.SHADOW)

    def target(self, identity: str) -> ProjectionTargetBinding:
        binding = self._by_identity.get(identity)
        if binding is None:
            raise ProjectionError(f"unknown projection target: {identity}")
        return binding

    def resolve_event_target(self, identity: object) -> ProjectionTargetBinding:
        """Resolve the one target an outbox event addresses.

        Events written before ADR-084 carry no target identity. They resolve
        only when this runtime has exactly one target, which is the shape that
        enqueued them; anything else fails closed rather than guessing.
        """

        if isinstance(identity, str) and identity.strip():
            return self.target(identity.strip())
        if len(self._targets) == 1:
            return self._targets[0]
        raise ProjectionError(
            "outbox event carries no target_identity and this runtime has "
            f"{len(self._targets)} targets; the event cannot be attributed to one target"
        )

    def adapter_for(self, identity: str) -> ProjectionAdapter:
        binding = self.target(identity)
        if binding.adapter is None:
            raise ProjectionError(
                f"projection target {identity} is {binding.mode} and its provider is not "
                "configured; configure it to complete lifecycle work for existing copies"
            )
        return binding.adapter

    def health(self) -> dict[str, Any]:
        """Report each target's probed health; configuration is not health."""

        if self.mode == "legacy":
            adapter = self._legacy_adapter
            base = adapter.health() if adapter is not None else {"name": "none", "healthy": True}
            return {
                **base,
                "runtime_mode": "legacy",
                "targets": [self._describe(binding, dict(base)) for binding in self._targets],
            }
        compiled = self.compiled
        assert compiled is not None
        targets: list[dict[str, Any]] = []
        active_healthy = True
        for binding in self._targets:
            probe: dict[str, Any] | None = None
            if binding.delivers and binding.adapter is not None:
                try:
                    probe = dict(binding.adapter.health())
                except Exception as exc:  # noqa: BLE001
                    probe = {"healthy": False, "error": str(exc)}
                if binding.mode == TargetMode.ACTIVE and not probe.get("healthy"):
                    active_healthy = False
            targets.append(self._describe(binding, probe))
        return {
            "name": compiled.name,
            "runtime_mode": "manifest",
            "healthy": active_healthy,
            "enabled": self.enabled,
            "projection": {
                "name": compiled.name,
                "version": compiled.version,
                "status": str(compiled.status),
                "manifest_digest": compiled.manifest_digest,
                "render_contract_digest": compiled.render_contract_digest,
                "compiled_artifact_digest": compiled.compiled_artifact_digest,
            },
            "targets": targets,
        }

    @staticmethod
    def _describe(binding: ProjectionTargetBinding, probe: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "target_identity": binding.identity,
            "provider_type": binding.provider_type,
            "mode": str(binding.mode.value),
            "required": binding.required,
            "configured": binding.adapter is not None,
            "verified": bool(probe and probe.get("healthy")),
            "health": probe,
        }
