# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_profiles.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.contracts import (
    BehaviorPolicy,
    ConsentGrant,
    DomainMemory,
    EvidenceKind,
    EvidenceRef,
    IdentityProfile,
    MemoryClass,
    PreferenceRecord,
    ProfileFact,
    Provenance,
    SessionContext,
)
from l9_graphite_memory.ingestion import ProfileIngestor


def _consent(source_id: str) -> ConsentGrant:
    return ConsentGrant(
        subject_id="user-1",
        namespace="repo-a",
        purpose="memory personalization",
        evidence=EvidenceRef(
            kind=EvidenceKind.EXPLICIT,
            description="User granted memory consent",
            source_id=source_id,
        ),
    )


def test_profile_ingestor_emits_atomic_identity_and_domain_requests() -> None:
    provenance = Provenance(source="profile-test", source_id="profile-1")
    identity = IdentityProfile(
        namespace="repo-a",
        subject_id="user-1",
        facts=(
            ProfileFact(key="role", value="architect"),
            ProfileFact(key="location", value="Charlotte"),
        ),
        provenance=provenance,
        consent=_consent("profile-1"),
    )
    domain = DomainMemory(
        namespace="repo-a",
        domain="memory-architecture",
        facts=(ProfileFact(key="source_of_truth", value="canonical ledger"),),
        provenance=provenance,
    )

    identity_requests = ProfileIngestor.identity(identity)
    domain_requests = ProfileIngestor.domain(domain)

    assert len(identity_requests) == 2
    assert {request.memory_class for request in identity_requests} == {
        MemoryClass.IDENTITY
    }
    assert identity_requests[0].assertion is not None
    assert len(domain_requests) == 1
    assert domain_requests[0].memory_class is MemoryClass.SEMANTIC
    assert domain_requests[0].metadata["domain"] == "memory-architecture"


def test_preference_behavior_and_session_are_separate_contracts() -> None:
    provenance = Provenance(source="profile-test", source_id="profile-2")
    preference = ProfileIngestor.preference(
        PreferenceRecord(
            namespace="repo-a",
            subject_id="user-1",
            preference="concise architecture reviews",
            applies_to="communication",
            provenance=provenance,
            consent=_consent("profile-2"),
        )
    )
    behavior = ProfileIngestor.behavior(
        BehaviorPolicy(
            namespace="repo-a",
            policy_id="policy-1",
            condition="a release claim is made",
            directive="require validation evidence",
            provenance=provenance,
        )
    )
    session = ProfileIngestor.session(
        SessionContext(
            namespace="repo-a",
            session_id="session-1",
            objective="complete the rewrite",
            active_constraints=("preserve compatibility",),
            active_decisions=("use one canonical service",),
            provenance=provenance,
        )
    )

    assert preference.memory_class is MemoryClass.PREFERENCE
    assert behavior.memory_class is MemoryClass.CONSTRAINT
    assert [request.memory_class for request in session] == [
        MemoryClass.EPISODIC,
        MemoryClass.CONSTRAINT,
        MemoryClass.DECISION,
    ]
