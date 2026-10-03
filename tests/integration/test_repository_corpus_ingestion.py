# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_repository_corpus_ingestion.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-10-02
from __future__ import annotations
from typing import Any
import pytest
from l9_graphite_memory.errors import L9MemoryError
from l9_graphite_memory.ingestion.repository import RepositoryBootstrapper
from l9_graphite_memory.repository_corpus import RepositoryCorpus
class EmptyIngestor:
    def requests(self, *_args: Any, **_kwargs: Any) -> tuple:
        return ()
class NoopService:
    def write(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("empty test ingestion must not write")
def corpus() -> RepositoryCorpus:
    return RepositoryCorpus.from_documents(
        {
            "schema": "l9.projection.memory-repository-corpus/v1",
            "artifact_id": "l9.projection/memory-repository-corpus@1",
            "canonical": False,
            "authority": {
                "authority_class": "derived",
            },
            "projection": {
                "view_ref": "l9.repository-view/memory-namespace-l9@1",
                "source_repository": "Quantum-L9/.github",
                "source_revision": "a" * 40,
            },
            "namespace": {
                "logical": "l9",
            },
            "repositories": [
                {
                    "id": "cursor-governance",
                    "coordinate": {
                        "provider": "github",
                        "organization": "Quantum-L9",
                        "repository": "Cursor-Governance",
                    },
                    "lifecycle": "current",
                    "class_ref": "l9.repository-class/l9@1",
                },
                {
                    "id": "golden-repo",
                    "coordinate": {
                        "provider": "github",
                        "organization": "Quantum-L9",
                        "repository": "golden-repo",
                    },
                    "lifecycle": "retired",
                    "class_ref": "l9.repository-class/l9@1",
                },
            ],
        },
        {
            "schema": "l9.memory.repository-corpus-binding/v1",
            "upstream": {
                "owner": "Quantum-L9/.github",
                "repository_view": {
                    "ref": "l9.repository-view/memory-namespace-l9@1",
                },
            },
            "repository_class": {
                "required_ref": "l9.repository-class/l9@1",
            },
            "namespace_binding": {
                "logical": {
                    "expected": "l9",
                },
                "runtime": {
                    "namespace": "project-group/l9",
                },
            },
        },
    )
@pytest.mark.integration
def test_current_l9_member_must_use_governed_namespace(tmp_path) -> None:
    repo = tmp_path / "cursor-governance"
    repo.mkdir()
    bootstrapper = RepositoryBootstrapper(
        NoopService(),  # type: ignore[arg-type]
        ingestor=EmptyIngestor(),  # type: ignore[arg-type]
        corpus=corpus(),
    )
    with pytest.raises(L9MemoryError, match="governed by namespace"):
        bootstrapper.bootstrap(
            object(),  # type: ignore[arg-type]
            repo,
            namespace="cursor-governance",
        )
@pytest.mark.integration
def test_current_l9_member_is_eligible_in_governed_namespace(tmp_path) -> None:
    repo = tmp_path / "cursor-governance"
    repo.mkdir()
    bootstrapper = RepositoryBootstrapper(
        NoopService(),  # type: ignore[arg-type]
        ingestor=EmptyIngestor(),  # type: ignore[arg-type]
        corpus=corpus(),
    )
    receipts = bootstrapper.bootstrap(
        object(),  # type: ignore[arg-type]
        repo,
        namespace="project-group/l9",
    )
    assert receipts == ()
@pytest.mark.integration
def test_nonmember_cannot_enter_l9_namespace(tmp_path) -> None:
    repo = tmp_path / "not-an-l9-repository"
    repo.mkdir()
    bootstrapper = RepositoryBootstrapper(
        NoopService(),  # type: ignore[arg-type]
        ingestor=EmptyIngestor(),  # type: ignore[arg-type]
        corpus=corpus(),
    )
    with pytest.raises(L9MemoryError, match="not admitted"):
        bootstrapper.bootstrap(
            object(),  # type: ignore[arg-type]
            repo,
            namespace="project-group/l9",
        )
@pytest.mark.integration
def test_retired_member_cannot_be_ingested(tmp_path) -> None:
    repo = tmp_path / "golden-repo"
    repo.mkdir()
    bootstrapper = RepositoryBootstrapper(
        NoopService(),  # type: ignore[arg-type]
        ingestor=EmptyIngestor(),  # type: ignore[arg-type]
        corpus=corpus(),
    )
    with pytest.raises(L9MemoryError, match="only current corpus members"):
        bootstrapper.bootstrap(
            object(),  # type: ignore[arg-type]
            repo,
            namespace="project-group/l9",
        )
