# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/qualification/graphiti_harness.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Harness for qualifying the stack against real Graphiti v0.30.2 (GI-080, ADR-092).

Everything is real: ``graphiti_core`` 0.30.2 — its ``add_episode`` pipeline,
LLM entity and relation extraction, node/edge resolution, embeddings,
reranking, persistence Cypher, indices, search and ``remove_episode`` —
writing into a real Neo4j 5.26 (+ GDS 2.13).

Model stack (settled by the GAR intelligence harvest, ADR-092):

- LLM: OpenAI, ``MODEL_NAME`` (default ``gpt-5.5``) and ``SMALL_MODEL_NAME``
  (default ``gpt-4.1-nano``) — graphiti-core 0.30.2's own defaults. They
  replace the harvested ``gpt-4o-mini``, which is a retired-generation model.
- Embedder: the model and dimension this repository's projection manifest
  pins (``config/projections/facts-v8.yaml``), not a second copy of them.
- Cross-encoder: ``OpenAIRerankerClient`` on the small model (it ranks with
  log-probabilities, so it needs an OpenAI-compatible endpoint).
- Route and credential (``L9_QUAL_MODEL_ROUTE``): ``openai`` (default, the
  settled route) calls api.openai.com with ``OPENAI_API_KEY``; ``openrouter``
  calls the same OpenAI models through OpenRouter's OpenAI-compatible API with
  ``OPENROUTER_API_KEY``. The route is explicit and recorded in the model-stack
  receipt; nothing falls back from one to the other. Keys are vault names in
  Infisical, read from the environment (CI imports the Actions secret) or
  supplied in-process through ``KEY_PROVIDER``; they are never logged or
  persisted.

Real extraction is not deterministic, so the qualification asserts
properties (scoping, provenance, support, lifecycle), never exact graphs.

``GraphitiCoreTransport`` is test-only: it adapts ``graphiti_core.Graphiti``
to the ``MemoryTransport`` shape the production ``GraphitiProjection`` already
drives, exposing the official MCP tool names with the official server's
semantics — including that ``add_memory`` reports "queued" and swallows an
ingestion failure (ADR-090). It is a transport, not a model stand-in.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EpisodeType

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_SMALL_MODEL = "gpt-4.1-nano"
MANIFEST = Path(__file__).resolve().parents[2] / "config" / "projections" / "facts-v8.yaml"
ROUTE_ENV = "L9_QUAL_MODEL_ROUTE"
#: route -> (credential vault name, OpenAI-compatible base URL, model prefix)
ROUTES: dict[str, tuple[str, str | None, str]] = {
    "openai": ("OPENAI_API_KEY", None, ""),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai/"),
}

#: In-process credential source for local runs: called with the vault name,
#: binds it without exporting it. CI leaves it unset and imports the env var.
KEY_PROVIDER: Callable[[str], str | None] | None = None


class QualificationCredentialMissing(RuntimeError):
    """Real qualification cannot run without the model credential."""


def route() -> tuple[str, str, str | None, str]:
    """(route name, credential name, base URL, model prefix) for this run."""

    name = os.environ.get(ROUTE_ENV, "openai").strip() or "openai"
    if name not in ROUTES:
        raise ValueError(f"{ROUTE_ENV}={name!r} is not one of {sorted(ROUTES)}")
    key_name, base_url, prefix = ROUTES[name]
    return name, key_name, base_url, prefix


def api_key() -> str:
    _name, key_name, _base_url, _prefix = route()
    value = (KEY_PROVIDER(key_name) if KEY_PROVIDER is not None else None) or os.environ.get(
        key_name, ""
    )
    if not value.strip():
        raise QualificationCredentialMissing(
            f"{key_name} is not bound: bind it from Infisical (capability_bind) or import "
            "it from the CI secret. Qualification never falls back to a stand-in model."
        )
    return value.strip()


def manifest_embedding() -> tuple[str, int]:
    """(model, dimensions) of the provider-managed embedding the manifest pins."""

    embedding = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["spec"]["embedding"]
    model = str(embedding["model"]).split("@", 1)[0]
    return model, int(embedding["dimensions"])


def model_stack() -> dict[str, Any]:
    """The model identities and route a run used, for the qualification receipt."""

    route_name, key_name, base_url, prefix = route()
    embedding_model, dimensions = manifest_embedding()
    small = os.environ.get("SMALL_MODEL_NAME") or DEFAULT_SMALL_MODEL
    return {
        "route": route_name,
        "credential": key_name,
        "base_url": base_url or "https://api.openai.com/v1",
        "llm": prefix + (os.environ.get("MODEL_NAME") or DEFAULT_MODEL),
        "small_llm": prefix + small,
        "embedder": prefix + embedding_model,
        "embedding_dim": dimensions,
        "reranker": f"openai-reranker:{prefix}{small}",
    }


def real_clients() -> dict[str, Any]:
    key = api_key()
    stack = model_stack()
    base_url = None if stack["route"] == "openai" else stack["base_url"]
    return {
        "llm_client": OpenAIClient(
            config=LLMConfig(
                api_key=key, model=stack["llm"], small_model=stack["small_llm"], base_url=base_url
            )
        ),
        "embedder": OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=key,
                embedding_model=stack["embedder"],
                embedding_dim=stack["embedding_dim"],
                base_url=base_url,
            )
        ),
        "cross_encoder": OpenAIRerankerClient(
            config=LLMConfig(api_key=key, model=stack["small_llm"], base_url=base_url)
        ),
    }


class GraphitiCoreTransport:
    """Test-only ``MemoryTransport`` over ``graphiti_core`` (official tool names)."""

    name = "graphiti-core-qualification"

    def __init__(self, uri: str, user: str | None, password: str | None) -> None:
        self.loop = asyncio.new_event_loop()
        # add_memory calls whose background ingestion failed, as the official
        # MCP server logs and drops them after replying "queued".
        self.dropped: list[tuple[str, str]] = []
        self.graphiti = Graphiti(uri, user, password, **real_clients())
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
