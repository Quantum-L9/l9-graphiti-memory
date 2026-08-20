# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/service_capability.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-13

"""Service-issued capability required to perform canonical store mutations.

Canonical persistence (record/receipt/status/outbox commits, verified deletion,
retention archival, and phase-lock issuance) must flow through ``MemoryService``
so that namespace authorization and admission are always evaluated first. Store
adapters historically accepted these mutations with no proof that the caller had
passed through that control plane, which meant an in-process consumer could
import a concrete store and persist canonical state directly.

Every canonical-mutation method on a :class:`RecordStore` now requires a
:class:`ServiceWriteCapability`. The capability is minted once and held by the
service layer; callers that have not gone through ``MemoryService`` do not have a
reference to it. This makes the storage side effect *technically dependent* on a
service-issued capability rather than merely governed by a static scanner.

Trust boundary (see ADR-036): within a single trusted operating-system process,
arbitrary Python can reach any in-memory object through introspection, so this is
a defense-in-depth control that raises the bar against accidental and casual
bypass — not an operating-system privilege boundary. Deployments that must resist
hostile in-process code have to place canonical persistence behind a real process
or database privilege boundary. The capability, the release-blocking bypass
scanner, and the repository layering rules together enforce the invariant that
``MemoryService`` is the only authorized writer of canonical state.
"""

from __future__ import annotations

from typing import Final


class ServiceWriteCapability:
    """Opaque proof that a canonical mutation is issued by the control plane.

    Instances carry no state and are compared by identity against the single
    process-wide :data:`SERVICE_WRITE_CAPABILITY`. Construct nothing here
    directly; the service layer holds the one authorized instance.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "ServiceWriteCapability()"


#: The single capability the store adapters accept. It is imported by
#: ``MemoryService`` and passed on every canonical mutation. Code outside the
#: control plane must not import or forward this symbol; the canonical-write
#: bypass scanner enforces that restriction in repository source.
SERVICE_WRITE_CAPABILITY: Final[ServiceWriteCapability] = ServiceWriteCapability()


def require_service_write_capability(capability: object) -> None:
    """Reject a canonical store mutation that lacks the service capability.

    Raises:
        PermissionError: if ``capability`` is not :data:`SERVICE_WRITE_CAPABILITY`.
    """

    if capability is not SERVICE_WRITE_CAPABILITY:
        raise PermissionError(
            "canonical store mutation requires the MemoryService write "
            "capability; direct store writes bypass namespace authorization and "
            "admission and are prohibited (see ADR-036)"
        )
