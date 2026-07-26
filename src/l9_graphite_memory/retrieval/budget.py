# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/retrieval/budget.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Class-aware context budget allocator."""

from __future__ import annotations

import math
from collections import defaultdict

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.contracts import ContextSection, HydrationResult, SearchReceipt
from l9_graphite_memory.contracts.receipts import SearchHit

_CLASS_ORDER = {
    "constraint": 0,
    "decision": 1,
    "procedural": 2,
    "identity": 3,
    "preference": 4,
    "meta": 5,
    "semantic": 6,
    "insight": 7,
    "observation": 8,
    "episodic": 9,
}


class ContextBudgetAllocator:
    """Allocate complete atomic memories without arbitrary list splitting."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Conservative language-neutral estimate; avoids a mandatory tokenizer dependency.
        return max(1, math.ceil(len(text.encode("utf-8")) / 3.5))

    def allocate(
        self, search: SearchReceipt, *, task: str, token_budget: int
    ) -> HydrationResult:
        grouped: dict[str, list[tuple[str, SearchHit]]] = defaultdict(list)
        remaining = token_budget
        used = 0
        for hit in sorted(
            search.hits,
            key=lambda item: (
                _CLASS_ORDER[item.record.memory_class.value],
                -item.score,
            ),
        ):
            content = hit.record.content.strip()
            tokens = self.estimate_tokens(content)
            if tokens > remaining:
                continue
            grouped[hit.record.memory_class.value].append((content, hit))
            remaining -= tokens
            used += tokens

        sections: list[ContextSection] = []
        for class_name in sorted(grouped, key=lambda item: _CLASS_ORDER[item]):
            values = grouped[class_name]
            text_parts = [content for content, _ in values]
            hits = [hit for _, hit in values]
            sections.append(
                ContextSection(
                    memory_class=hits[0].record.memory_class,
                    content="\n\n".join(text_parts),
                    record_ids=tuple(hit.record.record_id for hit in hits),
                    tokens_estimated=sum(
                        self.estimate_tokens(part) for part in text_parts
                    ),
                    highest_score=max(hit.score for hit in hits),
                )
            )

        warnings: list[str] = []
        if search.hits and not sections:
            warnings.append("no complete memory record fit within the token budget")
        status = search.status
        digest = sha256_text(
            canonical_json(
                {
                    "task": task,
                    "sections": [
                        section.model_dump(mode="json") for section in sections
                    ],
                    "search_receipt_id": str(search.receipt_id),
                }
            )
        )
        return HydrationResult(
            status=status,
            task=task,
            sections=tuple(sections),
            token_budget=token_budget,
            tokens_used=used,
            search_receipt_id=search.receipt_id,
            result_digest=digest,
            warnings=tuple(warnings),
        )
