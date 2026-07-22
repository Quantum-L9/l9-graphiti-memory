# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/profiles.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Convert typed profile objects into independently governed memory requests."""

from __future__ import annotations

from l9_graphite_memory.contracts import (
    BehaviorPolicy,
    DomainMemory,
    EvidenceKind,
    EvidenceRef,
    IdentityProfile,
    MemoryAssertion,
    MemoryClass,
    MemoryWriteRequest,
    PreferenceRecord,
    SessionContext,
)


class ProfileIngestor:
    """Emit atomic writes instead of storing one monolithic profile blob."""

    @staticmethod
    def identity(profile: IdentityProfile) -> tuple[MemoryWriteRequest, ...]:
        requests: list[MemoryWriteRequest] = []
        for fact in profile.facts:
            evidence = fact.evidence or (
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description=f"Identity profile assertion {fact.key}",
                    source_id=profile.provenance.source_id,
                ),
            )
            requests.append(
                MemoryWriteRequest(
                    namespace=profile.namespace,
                    memory_class=MemoryClass.IDENTITY,
                    content=f"{profile.subject_id} {fact.key}: {fact.value}",
                    assertion=MemoryAssertion(
                        subject=profile.subject_id,
                        predicate=fact.key,
                        object=fact.value,
                    ),
                    provenance=profile.provenance,
                    evidence=evidence,
                    confidence=fact.confidence,
                    valid_from=fact.valid_from,
                    valid_to=fact.valid_to,
                    tags=tuple({*fact.tags, "profile", "identity"}),
                    metadata={**fact.metadata, "profile_subject": profile.subject_id},
                    idempotency_key=(
                        f"identity:{profile.namespace}:{profile.subject_id}:{fact.key}:{fact.value}"
                    ),
                    consent=profile.consent,
                )
            )
        return tuple(requests)

    @staticmethod
    def preference(record: PreferenceRecord) -> MemoryWriteRequest:
        evidence = record.evidence or (
            EvidenceRef(
                kind=EvidenceKind.EXPLICIT,
                description="Explicit preference assertion",
                source_id=record.provenance.source_id,
            ),
        )
        return MemoryWriteRequest(
            namespace=record.namespace,
            memory_class=MemoryClass.PREFERENCE,
            content=f"{record.subject_id} prefers {record.preference} for {record.applies_to}",
            assertion=MemoryAssertion(
                subject=record.subject_id,
                predicate=f"prefers:{record.applies_to}",
                object=record.preference,
            ),
            provenance=record.provenance,
            evidence=evidence,
            confidence=record.confidence,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            tags=("profile", "preference", record.applies_to.casefold()),
            metadata={
                "profile_subject": record.subject_id,
                "applies_to": record.applies_to,
            },
            idempotency_key=(
                f"preference:{record.namespace}:{record.subject_id}:{record.applies_to}:{record.preference}"
            ),
            consent=record.consent,
        )

    @staticmethod
    def behavior(policy: BehaviorPolicy) -> MemoryWriteRequest:
        return MemoryWriteRequest(
            namespace=policy.namespace,
            memory_class=MemoryClass.CONSTRAINT,
            content=f"When {policy.condition}, {policy.directive}",
            assertion=MemoryAssertion(
                subject=policy.policy_id,
                predicate="requires_when",
                object=f"{policy.condition} => {policy.directive}",
            ),
            provenance=policy.provenance,
            evidence=policy.evidence,
            valid_from=policy.valid_from,
            valid_to=policy.valid_to,
            tags=("behavior-policy", "constraint"),
            metadata={"condition": policy.condition, "directive": policy.directive},
            idempotency_key=f"behavior:{policy.namespace}:{policy.policy_id}",
        )

    @staticmethod
    def session(context: SessionContext) -> tuple[MemoryWriteRequest, ...]:
        values: list[tuple[MemoryClass, str, str]] = [
            (MemoryClass.EPISODIC, "objective", context.objective),
            *(
                (MemoryClass.CONSTRAINT, "constraint", item)
                for item in context.active_constraints
            ),
            *(
                (MemoryClass.DECISION, "decision", item)
                for item in context.active_decisions
            ),
        ]
        requests: list[MemoryWriteRequest] = []
        for index, (memory_class, predicate, value) in enumerate(values):
            requests.append(
                MemoryWriteRequest(
                    namespace=context.namespace,
                    memory_class=memory_class,
                    content=f"Session {context.session_id} {predicate}: {value}",
                    assertion=MemoryAssertion(
                        subject=context.session_id,
                        predicate=predicate,
                        object=value,
                    ),
                    provenance=context.provenance.model_copy(
                        update={"session_id": context.session_id}
                    ),
                    evidence=(
                        EvidenceRef(
                            kind=EvidenceKind.EXPLICIT,
                            description=f"Session context {predicate}",
                            source_id=context.provenance.source_id,
                        ),
                    ),
                    valid_to=context.expires_at,
                    tags=("session-context", predicate),
                    metadata={"session_id": context.session_id},
                    idempotency_key=(
                        f"session:{context.namespace}:{context.session_id}:{predicate}:{index}"
                    ),
                )
            )
        return tuple(requests)

    @staticmethod
    def domain(bundle: DomainMemory) -> tuple[MemoryWriteRequest, ...]:
        requests: list[MemoryWriteRequest] = []
        for fact in bundle.facts:
            requests.append(
                MemoryWriteRequest(
                    namespace=bundle.namespace,
                    memory_class=MemoryClass.SEMANTIC,
                    content=f"{bundle.domain} {fact.key}: {fact.value}",
                    assertion=MemoryAssertion(
                        subject=bundle.domain,
                        predicate=fact.key,
                        object=fact.value,
                    ),
                    provenance=bundle.provenance,
                    evidence=fact.evidence,
                    confidence=fact.confidence,
                    valid_from=fact.valid_from,
                    valid_to=fact.valid_to,
                    tags=tuple({*fact.tags, "domain-memory", bundle.domain.casefold()}),
                    metadata={**fact.metadata, "domain": bundle.domain},
                    idempotency_key=(
                        f"domain:{bundle.namespace}:{bundle.domain}:{fact.key}:{fact.value}"
                    ),
                )
            )
        return tuple(requests)
