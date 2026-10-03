# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_repository_corpus.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-10-02
from __future__ import annotations
import pytest
from l9_graphite_memory.repository_corpus import (
    RepositoryCorpus,
    RepositoryCorpusError,
    normalize_repository_coordinate,
)
def binding_document() -> dict:
    return {
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
    }
def corpus_document() -> dict:
    return {
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
    }
def test_resolves_repository_by_registry_id() -> None:
    corpus = RepositoryCorpus.from_documents(
        corpus_document(),
        binding_document(),
    )
    member = corpus.resolve("cursor-governance")
    assert member is not None
    assert member.coordinate.canonical == "Quantum-L9/Cursor-Governance"
    assert member.current is True
@pytest.mark.parametrize(
    "value",
    [
        "Quantum-L9/Cursor-Governance",
        "https://github.com/Quantum-L9/Cursor-Governance",
        "https://github.com/Quantum-L9/Cursor-Governance.git",
        "git@github.com:Quantum-L9/Cursor-Governance.git",
        "ssh://git@github.com/Quantum-L9/Cursor-Governance.git",
    ],
)
def test_resolves_supported_github_coordinates(value: str) -> None:
    corpus = RepositoryCorpus.from_documents(
        corpus_document(),
        binding_document(),
    )
    member = corpus.resolve(value)
    assert member is not None
    assert member.id == "cursor-governance"
def test_current_members_exclude_retired_repository() -> None:
    corpus = RepositoryCorpus.from_documents(
        corpus_document(),
        binding_document(),
    )
    assert [member.id for member in corpus.current_members()] == [
        "cursor-governance"
    ]
def test_require_current_member_rejects_retired_repository() -> None:
    corpus = RepositoryCorpus.from_documents(
        corpus_document(),
        binding_document(),
    )
    with pytest.raises(RepositoryCorpusError, match="not ingestion eligible"):
        corpus.require_current_member("golden-repo")
def test_require_current_member_rejects_unknown_repository() -> None:
    corpus = RepositoryCorpus.from_documents(
        corpus_document(),
        binding_document(),
    )
    with pytest.raises(RepositoryCorpusError, match="not a member"):
        corpus.require_current_member("Quantum-L9/not-registered")
def test_runtime_namespace_comes_from_local_binding() -> None:
    corpus = RepositoryCorpus.from_documents(
        corpus_document(),
        binding_document(),
    )
    assert corpus.logical_namespace == "l9"
    assert corpus.runtime_namespace == "project-group/l9"
def test_projection_cannot_promote_itself_to_canonical() -> None:
    document = corpus_document()
    document["canonical"] = True
    with pytest.raises(RepositoryCorpusError, match="must be non-canonical"):
        RepositoryCorpus.from_documents(document, binding_document())
def test_projection_view_must_match_governing_binding() -> None:
    document = corpus_document()
    document["projection"]["view_ref"] = "l9.repository-view/other@1"
    with pytest.raises(RepositoryCorpusError, match="projection view mismatch"):
        RepositoryCorpus.from_documents(document, binding_document())
def test_repository_class_must_match_governing_binding() -> None:
    document = corpus_document()
    document["repositories"][0]["class_ref"] = (
        "l9.repository-class/org-auxiliary@1"
    )
    with pytest.raises(RepositoryCorpusError, match="unexpected repository class"):
        RepositoryCorpus.from_documents(document, binding_document())
def test_coordinate_normalization_preserves_canonical_identity() -> None:
    assert (
        normalize_repository_coordinate(
            "git@github.com:Quantum-L9/l9-graphiti-memory.git"
        )
        == "Quantum-L9/l9-graphiti-memory"
    )
