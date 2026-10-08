# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/repository_corpus.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-10-02
"""Verified downstream view of the canonical Quantum-L9 repository corpus."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from l9_graphite_memory.errors import L9MemoryError

CORPUS_RESOURCE = "repository_corpus.yaml"
RECEIPT_RESOURCE = "repository_corpus.receipt.yaml"
BINDING_RESOURCE = "repository_corpus_binding.yaml"
EXPECTED_CORPUS_SCHEMA = "l9.projection.memory-repository-corpus/v1"
EXPECTED_RECEIPT_SCHEMA = "l9.projection-receipt/v1"
EXPECTED_BINDING_SCHEMA = "l9.memory.repository-corpus-binding/v1"


class RepositoryCorpusError(L9MemoryError):
    """Raised when repository-corpus authority cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class RepositoryCoordinate:
    provider: str
    organization: str
    repository: str

    @property
    def canonical(self) -> str:
        return f"{self.organization}/{self.repository}"


@dataclass(frozen=True, slots=True)
class RepositoryMember:
    id: str
    coordinate: RepositoryCoordinate
    lifecycle: str
    class_ref: str

    @property
    def current(self) -> bool:
        return self.lifecycle == "current"


@dataclass(frozen=True, slots=True)
class RepositoryCorpus:
    artifact_id: str
    projection_view_ref: str
    source_repository: str
    source_revision: str
    logical_namespace: str
    runtime_namespace: str
    required_class_ref: str
    members: tuple[RepositoryMember, ...]

    def current_members(self) -> tuple[RepositoryMember, ...]:
        return tuple(member for member in self.members if member.current)

    def resolve(self, value: str) -> RepositoryMember | None:
        normalized = normalize_repository_coordinate(value)
        for member in self.members:
            if value == member.id:
                return member
            if normalized == member.coordinate.canonical:
                return member
        return None

    def require_current_member(self, value: str) -> RepositoryMember:
        member = self.resolve(value)
        if member is None:
            raise RepositoryCorpusError(
                f"repository is not a member of the governed L9 corpus: {value}"
            )
        if not member.current:
            raise RepositoryCorpusError(
                f"repository is not current and is not ingestion eligible: "
                f"{member.id} ({member.lifecycle})"
            )
        return member

    @classmethod
    def from_documents(
        cls,
        corpus_document: Mapping[str, Any],
        binding_document: Mapping[str, Any],
    ) -> RepositoryCorpus:
        if corpus_document.get("schema") != EXPECTED_CORPUS_SCHEMA:
            raise RepositoryCorpusError("invalid repository corpus schema")
        if binding_document.get("schema") != EXPECTED_BINDING_SCHEMA:
            raise RepositoryCorpusError("invalid repository corpus binding schema")
        if corpus_document.get("canonical") is not False:
            raise RepositoryCorpusError("repository corpus projection must be non-canonical")
        authority = _mapping(corpus_document.get("authority"), "authority")
        if authority.get("authority_class") != "derived":
            raise RepositoryCorpusError("repository corpus projection must have derived authority")
        projection = _mapping(corpus_document.get("projection"), "projection")
        upstream = _mapping(binding_document.get("upstream"), "upstream")
        view = _mapping(upstream.get("repository_view"), "upstream.repository_view")
        expected_view_ref = _required_string(view, "ref")
        actual_view_ref = _required_string(projection, "view_ref")
        if actual_view_ref != expected_view_ref:
            raise RepositoryCorpusError(
                f"projection view mismatch: expected {expected_view_ref}, got {actual_view_ref}"
            )
        source_repository = _required_string(projection, "source_repository")
        expected_owner = _required_string(upstream, "owner")
        if source_repository != expected_owner:
            raise RepositoryCorpusError(
                f"projection owner mismatch: expected {expected_owner}, got {source_repository}"
            )
        repository_class = _mapping(
            binding_document.get("repository_class"),
            "repository_class",
        )
        required_class_ref = _required_string(repository_class, "required_ref")
        namespace = _mapping(corpus_document.get("namespace"), "namespace")
        logical_namespace = _required_string(namespace, "logical")
        namespace_binding = _mapping(
            binding_document.get("namespace_binding"),
            "namespace_binding",
        )
        logical_binding = _mapping(
            namespace_binding.get("logical"),
            "namespace_binding.logical",
        )
        expected_logical_namespace = _required_string(logical_binding, "expected")
        if logical_namespace != expected_logical_namespace:
            raise RepositoryCorpusError(
                "projected logical namespace does not match the local governing binding"
            )
        runtime_binding = _mapping(
            namespace_binding.get("runtime"),
            "namespace_binding.runtime",
        )
        runtime_namespace = _required_string(runtime_binding, "namespace")
        raw_members = corpus_document.get("repositories")
        if not isinstance(raw_members, list):
            raise RepositoryCorpusError("repositories must be a list")
        members: list[RepositoryMember] = []
        ids: set[str] = set()
        coordinates: set[str] = set()
        for raw_member in raw_members:
            member_map = _mapping(raw_member, "repository")
            member_id = _required_string(member_map, "id")
            lifecycle = _required_string(member_map, "lifecycle")
            class_ref = _required_string(member_map, "class_ref")
            if class_ref != required_class_ref:
                raise RepositoryCorpusError(
                    f"{member_id} has unexpected repository class {class_ref}"
                )
            if lifecycle not in {"current", "superseded", "retired"}:
                raise RepositoryCorpusError(f"{member_id} has unsupported lifecycle {lifecycle}")
            coordinate_map = _mapping(member_map.get("coordinate"), "coordinate")
            coordinate = RepositoryCoordinate(
                provider=_required_string(coordinate_map, "provider"),
                organization=_required_string(coordinate_map, "organization"),
                repository=_required_string(coordinate_map, "repository"),
            )
            if member_id in ids:
                raise RepositoryCorpusError(f"duplicate repository id: {member_id}")
            if coordinate.canonical in coordinates:
                raise RepositoryCorpusError(
                    f"duplicate repository coordinate: {coordinate.canonical}"
                )
            ids.add(member_id)
            coordinates.add(coordinate.canonical)
            members.append(
                RepositoryMember(
                    id=member_id,
                    coordinate=coordinate,
                    lifecycle=lifecycle,
                    class_ref=class_ref,
                )
            )
        return cls(
            artifact_id=_required_string(corpus_document, "artifact_id"),
            projection_view_ref=actual_view_ref,
            source_repository=source_repository,
            source_revision=_required_string(projection, "source_revision"),
            logical_namespace=logical_namespace,
            runtime_namespace=runtime_namespace,
            required_class_ref=required_class_ref,
            members=tuple(members),
        )


def normalize_repository_coordinate(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:")
    elif candidate.startswith("ssh://git@github.com/"):
        candidate = candidate.removeprefix("ssh://git@github.com/")
    elif candidate.startswith("https://github.com/"):
        candidate = candidate.removeprefix("https://github.com/")
    elif candidate.startswith("http://github.com/"):
        candidate = candidate.removeprefix("http://github.com/")
    candidate = candidate.removesuffix(".git").strip("/")
    return candidate


def load_repository_corpus() -> RepositoryCorpus:
    corpus_bytes = _resource_bytes(CORPUS_RESOURCE)
    receipt_bytes = _resource_bytes(RECEIPT_RESOURCE)
    binding_bytes = _resource_bytes(BINDING_RESOURCE)
    corpus_document = _yaml_mapping(corpus_bytes, CORPUS_RESOURCE)
    receipt_document = _yaml_mapping(receipt_bytes, RECEIPT_RESOURCE)
    binding_document = _yaml_mapping(binding_bytes, BINDING_RESOURCE)
    _verify_receipt(
        corpus_bytes=corpus_bytes,
        corpus_document=corpus_document,
        receipt_document=receipt_document,
        binding_document=binding_document,
    )
    return RepositoryCorpus.from_documents(corpus_document, binding_document)


def _verify_receipt(
    *,
    corpus_bytes: bytes,
    corpus_document: Mapping[str, Any],
    receipt_document: Mapping[str, Any],
    binding_document: Mapping[str, Any],
) -> None:
    if receipt_document.get("schema") != EXPECTED_RECEIPT_SCHEMA:
        raise RepositoryCorpusError("invalid repository corpus receipt schema")
    generated_projection = _mapping(
        binding_document.get("generated_projection"),
        "generated_projection",
    )
    expected_artifact_ref = _required_string(generated_projection, "artifact_ref")
    if corpus_document.get("artifact_id") != expected_artifact_ref:
        raise RepositoryCorpusError("generated corpus artifact id does not match binding")
    projection = _mapping(receipt_document.get("projection"), "receipt.projection")
    if projection.get("artifact_ref") != expected_artifact_ref:
        raise RepositoryCorpusError("receipt artifact reference does not match binding")
    corpus_projection = _mapping(corpus_document.get("projection"), "projection")
    if projection.get("view_ref") != corpus_projection.get("view_ref"):
        raise RepositoryCorpusError("receipt projection view does not match corpus")
    if projection.get("source_revision") != corpus_projection.get("source_revision"):
        raise RepositoryCorpusError("receipt source revision does not match corpus")
    output = _mapping(receipt_document.get("output"), "receipt.output")
    expected_digest = _required_string(output, "digest")
    actual_digest = f"sha256:{hashlib.sha256(corpus_bytes).hexdigest()}"
    if actual_digest != expected_digest:
        raise RepositoryCorpusError(
            f"repository corpus digest mismatch: expected {expected_digest}, got {actual_digest}"
        )


def _resource_bytes(name: str) -> bytes:
    resource = resources.files("l9_graphite_memory").joinpath("resources", name)
    try:
        return resource.read_bytes()
    except FileNotFoundError as exc:
        raise RepositoryCorpusError(
            f"required repository corpus resource is missing: {name}"
        ) from exc


def _yaml_mapping(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RepositoryCorpusError(f"invalid YAML in {label}: {exc}") from exc
    return _mapping(value, label)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RepositoryCorpusError(f"{label} must be a mapping")
    return value


def _required_string(value: Mapping[str, Any], key: str) -> str:
    resolved = value.get(key)
    if not isinstance(resolved, str) or not resolved:
        raise RepositoryCorpusError(f"{key} must be a non-empty string")
    return resolved
