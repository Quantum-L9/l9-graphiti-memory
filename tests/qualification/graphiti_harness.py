# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/qualification/graphiti_harness.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Deterministic harness for qualifying the stack against real Graphiti v0.30.2.

What is real: ``graphiti_core`` 0.30.2 itself — its ``add_episode`` pipeline,
node/edge resolution, persistence Cypher, indices, search, and
``remove_episode`` — writing into a real Neo4j 5.26 (+ GDS 2.13).

What is substituted, and why: the LLM, embedder, and cross-encoder. Graphiti
calls an LLM to extract entities and relations; no LLM credential exists in
the qualification environment, and a live model would make the graph
non-deterministic. ``ScriptedExtractionLLM`` answers each Graphiti prompt from
explicit ``[[Source->Target]]`` markers in the episode content, so the graph
Graphiti builds is known in advance. Embeddings are deterministic hash
vectors. This qualifies schema, scoping, provenance, and lifecycle — not LLM
extraction quality.

``GraphitiCoreTransport`` is test-only: it adapts ``graphiti_core.Graphiti``
to the ``MemoryTransport`` shape the production ``GraphitiProjection`` already
drives, exposing the official MCP tool names with the official server's
semantics — including that ``add_memory`` reports "queued" and swallows an
ingestion failure (ADR-090). It is not a production provider.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType

_REL = re.compile(r"\[\[([A-Za-z][A-Za-z0-9]*)\s*->\s*([A-Za-z][A-Za-z0-9]*)\]\]")
_SECTION = {
    "json": re.compile(r"<JSON>\s*(.*?)\s*</JSON>", re.DOTALL),
    "current": re.compile(r"<CURRENT[_ ]MESSAGE>\s*(.*?)\s*</CURRENT[_ ]MESSAGE>", re.DOTALL),
    "entities": re.compile(r"<ENTITIES>\s*(.*?)\s*</ENTITIES>", re.DOTALL),
    "existing": re.compile(r"<EXISTING ENTITIES>\s*(.*?)\s*</EXISTING ENTITIES>", re.DOTALL),
    "existing_facts": re.compile(r"<EXISTING FACTS>\s*(.*?)\s*</EXISTING FACTS>", re.DOTALL),
    "new_fact": re.compile(r"<NEW FACT>\s*(.*?)\s*</NEW FACT>", re.DOTALL),
}
_FACT = re.compile(r"""['"]idx['"]\s*:\s*(\d+)\s*,\s*['"]fact['"]\s*:\s*['"](.*?)['"]\s*[,}]""")


def _current_content(text: str) -> str:
    for key in ("json", "current"):
        match = _SECTION[key].search(text)
        if match:
            return match.group(1)
    return ""


def _relations(text: str) -> list[tuple[str, str]]:
    return _REL.findall(_current_content(text))


def _json_section(key: str, text: str) -> list[dict[str, Any]]:
    match = _SECTION[key].search(text)
    if not match:
        return []
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def relation_fact(source: str, target: str) -> str:
    return f"{source} relates to {target}"


class ScriptedExtractionLLM(LLMClient):
    """Answers Graphiti's extraction prompts from ``[[A->B]]`` markers."""

    def __init__(self) -> None:
        super().__init__(LLMConfig(api_key="qualification", model="scripted"), cache=False)
        self.calls: list[str] = []

    async def _generate_response(
        self,
        messages: list[Any],
        response_model: Any = None,
        max_tokens: int = 0,
        model_size: Any = None,
    ) -> dict[str, Any]:
        text = "\n".join(str(getattr(m, "content", "")) for m in messages)
        name = getattr(response_model, "__name__", "")
        self.calls.append(name)
        relations = _relations(text)
        if name == "ExtractedEntities":
            names: list[str] = []
            for source, target in relations:
                for entity in (source, target):
                    if entity not in names:
                        names.append(entity)
            return {
                "extracted_entities": [
                    {"name": entity, "entity_type_id": 0, "episode_indices": [0]}
                    for entity in names
                ]
            }
        if name == "NodeResolutions":
            existing = {
                str(item.get("name", "")).lower(): item.get("candidate_id")
                for item in _json_section("existing", text)
            }
            return {
                "entity_resolutions": [
                    {
                        "id": item.get("id", index),
                        "name": item.get("name", ""),
                        "duplicate_candidate_id": existing.get(
                            str(item.get("name", "")).lower(), -1
                        ),
                    }
                    for index, item in enumerate(_json_section("entities", text))
                ]
            }
        if name == "ExtractedEdges":
            return {
                "edges": [
                    {
                        "source_entity_name": source,
                        "target_entity_name": target,
                        "relation_type": "RELATED_TO",
                        "fact": relation_fact(source, target),
                        "valid_at": None,
                        "invalid_at": None,
                    }
                    for source, target in relations
                ]
            }
        if name == "EdgeDuplicate":
            new_fact = _SECTION["new_fact"].search(text)
            new_text = new_fact.group(1) if new_fact else ""
            existing = _SECTION["existing_facts"].search(text)
            duplicates = [
                int(idx)
                for idx, fact in _FACT.findall(existing.group(1) if existing else "")
                if fact and fact in new_text
            ]
            return {"duplicate_facts": duplicates, "contradicted_facts": []}
        if name == "SummarizedEntities":
            return {"summaries": []}
        if name in {"EdgeTimestamps"}:
            return {"valid_at": None, "invalid_at": None}
        if name == "BatchEdgeTimestamps":
            return {"timestamps": []}
        return _empty_instance(response_model)


def _empty_instance(model: Any) -> dict[str, Any]:
    """Minimal valid payload for any other Graphiti response model."""

    if model is None:
        return {}
    payload: dict[str, Any] = {}
    for field_name, field in getattr(model, "model_fields", {}).items():
        if not field.is_required():
            continue
        annotation = str(field.annotation)
        if "list" in annotation:
            payload[field_name] = []
        elif "int" in annotation:
            payload[field_name] = -1
        elif "bool" in annotation:
            payload[field_name] = False
        elif "dict" in annotation:
            payload[field_name] = {}
        else:
            payload[field_name] = ""
    return payload


class HashEmbedder(EmbedderClient):
    """Deterministic unit vectors from token hashes (same text, same vector)."""

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def create(self, input_data: Any) -> list[float]:
        if isinstance(input_data, list):
            input_data = " ".join(str(item) for item in input_data)
        return self._embed(str(input_data))

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input_data_list]


class OverlapReranker(CrossEncoderClient):
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        terms = set(query.lower().split())
        scored = [
            (passage, len(terms & set(passage.lower().split())) / max(1, len(terms)))
            for passage in passages
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)


class GraphitiCoreTransport:
    """Test-only ``MemoryTransport`` over ``graphiti_core`` (official tool names)."""

    name = "graphiti-core-qualification"

    def __init__(self, uri: str, user: str | None, password: str | None) -> None:
        self.loop = asyncio.new_event_loop()
        self.llm = ScriptedExtractionLLM()
        # add_memory calls whose background ingestion failed, as the official
        # MCP server logs and drops them after replying "queued".
        self.dropped: list[tuple[str, str]] = []
        self.graphiti = Graphiti(
            uri,
            user,
            password,
            llm_client=self.llm,
            embedder=HashEmbedder(),
            cross_encoder=OverlapReranker(),
        )
        self.run(self.graphiti.build_indices_and_constraints())

    def run(self, coroutine: Any) -> Any:
        return self.loop.run_until_complete(coroutine)

    def health(self) -> dict[str, Any]:
        return {"healthy": True, "graphiti": "0.30.2"}

    def list_tools(self) -> list[str]:
        return [
            "add_memory",
            "get_episodes",
            "search_memory_facts",
            "search_nodes",
            "delete_episode",
        ]

    def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: Any) -> Any:
        name = str(kwargs.get("name") or "memory")
        try:
            self.run(
                self.graphiti.add_episode(
                    name=name,
                    episode_body=body,
                    source_description=str(kwargs.get("source_description") or "l9"),
                    reference_time=datetime.now(timezone.utc),
                    source=EpisodeType.json,
                    group_id=group_id,
                    uuid=kwargs.get("uuid"),
                )
            )
        except Exception as exc:  # noqa: BLE001 - mirrors the MCP queue worker
            self.dropped.append((name, type(exc).__name__))
        # The official add_memory reply names the episode and nothing else.
        return {"message": f"Episode '{name}' queued for processing in group '{group_id}'"}

    def search(self, query: str, group_id: str, limit: int = 10) -> list[dict[str, Any]]:
        raise AssertionError("GraphitiProjection uses strategy-specific tools")

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        arguments = arguments or {}
        if name == "delete_episode":
            self.run(self.graphiti.remove_episode(str(arguments["uuid"])))
            return {"message": "deleted"}
        group_ids = list(arguments.get("group_ids") or [])
        if name == "get_episodes":
            from graphiti_core.nodes import EpisodicNode

            episodes = self.run(
                EpisodicNode.get_by_group_ids(
                    self.graphiti.driver, group_ids, limit=int(arguments.get("max_episodes", 10))
                )
            )
            return {
                "episodes": [
                    {"uuid": e.uuid, "name": e.name, "group_id": e.group_id} for e in episodes
                ]
            }
        query = str(arguments.get("query", ""))
        if name == "search_memory_facts":
            edges = self.run(
                self.graphiti.search(
                    query, group_ids=group_ids, num_results=int(arguments.get("max_facts", 10))
                )
            )
            return {
                "facts": [
                    {
                        "uuid": e.uuid,
                        "fact": e.fact,
                        "episodes": list(e.episodes),
                        "group_id": e.group_id,
                    }
                    for e in edges
                ]
            }
        if name == "search_nodes":
            from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF

            results = self.run(
                self.graphiti.search_(query, config=NODE_HYBRID_SEARCH_RRF, group_ids=group_ids)
            )
            return {
                "nodes": [
                    {"uuid": n.uuid, "name": n.name, "summary": n.summary, "group_id": n.group_id}
                    for n in results.nodes
                ]
            }
        raise KeyError(name)

    def close(self) -> None:
        self.run(self.graphiti.close())
        self.loop.close()
