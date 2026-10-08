#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/check_repository_corpus_governance.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-10-02
"""Fail closed when repository-corpus projection governance is invalid."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BINDING_PATH = ROOT / "src" / "l9_graphite_memory" / "resources" / "repository_corpus_binding.yaml"
CORPUS_PATH = ROOT / "src" / "l9_graphite_memory" / "resources" / "repository_corpus.yaml"
RECEIPT_PATH = ROOT / "src" / "l9_graphite_memory" / "resources" / "repository_corpus.receipt.yaml"
REPOSITORY_INGESTION_PATH = ROOT / "src" / "l9_graphite_memory" / "ingestion" / "repository.py"


def main() -> int:
    failures: list[str] = []
    for path in (
        BINDING_PATH,
        CORPUS_PATH,
        RECEIPT_PATH,
        REPOSITORY_INGESTION_PATH,
    ):
        if not path.is_file():
            failures.append(f"missing required repository corpus governance file: {path}")
    if failures:
        return _report(failures)
    binding = _load_yaml(BINDING_PATH, failures)
    corpus = _load_yaml(CORPUS_PATH, failures)
    receipt = _load_yaml(RECEIPT_PATH, failures)
    if failures:
        return _report(failures)
    if binding.get("schema") != "l9.memory.repository-corpus-binding/v1":
        failures.append("invalid repository corpus binding schema")
    if binding.get("canonical") is not True:
        failures.append("downstream repository corpus binding must be locally canonical")
    generated = _mapping(binding.get("generated_projection"))
    expected_artifact_ref = generated.get("artifact_ref")
    if corpus.get("schema") != "l9.projection.memory-repository-corpus/v1":
        failures.append("invalid generated repository corpus schema")
    if corpus.get("canonical") is not False:
        failures.append("generated repository corpus must be non-canonical")
    if corpus.get("artifact_id") != expected_artifact_ref:
        failures.append("generated repository corpus artifact id disagrees with binding")
    authority = _mapping(corpus.get("authority"))
    if authority.get("authority_class") != "derived":
        failures.append("generated repository corpus must have derived authority")
    upstream = _mapping(binding.get("upstream"))
    expected_owner = upstream.get("owner")
    expected_view = _mapping(upstream.get("repository_view")).get("ref")
    projection = _mapping(corpus.get("projection"))
    if projection.get("source_repository") != expected_owner:
        failures.append("generated repository corpus source owner disagrees with binding")
    if projection.get("view_ref") != expected_view:
        failures.append("generated repository corpus view disagrees with binding")
    source_revision = projection.get("source_revision")
    if not isinstance(source_revision, str) or len(source_revision) != 40:
        failures.append("generated repository corpus does not carry a pinned git revision")
    repository_class = _mapping(binding.get("repository_class"))
    required_class_ref = repository_class.get("required_ref")
    if corpus.get("repository_class_ref") != required_class_ref:
        failures.append("generated repository class disagrees with binding")
    namespace_binding = _mapping(binding.get("namespace_binding"))
    logical_binding = _mapping(namespace_binding.get("logical"))
    runtime_binding = _mapping(namespace_binding.get("runtime"))
    corpus_namespace = _mapping(corpus.get("namespace"))
    if corpus_namespace.get("logical") != logical_binding.get("expected"):
        failures.append("generated logical namespace disagrees with binding")
    runtime_namespace = runtime_binding.get("namespace")
    if runtime_namespace != "project-group/l9":
        failures.append("runtime namespace must resolve to project-group/l9")
    repositories = corpus.get("repositories")
    if not isinstance(repositories, list):
        failures.append("generated repositories must be a list")
        repositories = []
    ids: set[str] = set()
    coordinates: set[str] = set()
    for repository in repositories:
        item = _mapping(repository)
        repository_id = item.get("id")
        class_ref = item.get("class_ref")
        lifecycle = item.get("lifecycle")
        coordinate = _mapping(item.get("coordinate"))
        if not isinstance(repository_id, str) or not repository_id:
            failures.append("repository entry has no id")
            continue
        if repository_id in ids:
            failures.append(f"duplicate repository id: {repository_id}")
        ids.add(repository_id)
        if class_ref != required_class_ref:
            failures.append(f"{repository_id} has non-governing repository class {class_ref}")
        if lifecycle not in {"current", "superseded", "retired"}:
            failures.append(f"{repository_id} has unsupported lifecycle {lifecycle}")
        provider = coordinate.get("provider")
        organization = coordinate.get("organization")
        repository_name = coordinate.get("repository")
        coordinate_key = f"{provider}:{organization}/{repository_name}"
        if coordinate_key in coordinates:
            failures.append(f"duplicate repository coordinate: {coordinate_key}")
        coordinates.add(coordinate_key)
    if receipt.get("schema") != "l9.projection-receipt/v1":
        failures.append("invalid repository corpus receipt schema")
    receipt_projection = _mapping(receipt.get("projection"))
    if receipt_projection.get("artifact_ref") != expected_artifact_ref:
        failures.append("receipt artifact reference disagrees with binding")
    if receipt_projection.get("view_ref") != expected_view:
        failures.append("receipt view reference disagrees with binding")
    if receipt_projection.get("source_revision") != source_revision:
        failures.append("receipt source revision disagrees with generated corpus")
    output = _mapping(receipt.get("output"))
    expected_digest = output.get("digest")
    actual_digest = f"sha256:{hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()}"
    if expected_digest != actual_digest:
        failures.append(
            f"generated corpus digest mismatch: expected {expected_digest}, got {actual_digest}"
        )
    ingestion_source = REPOSITORY_INGESTION_PATH.read_text(encoding="utf-8")
    required_markers = (
        "load_repository_corpus",
        "self.corpus.resolve",
        "self.corpus.runtime_namespace",
        "not admitted to the canonical L9 repository corpus",
    )
    for marker in required_markers:
        if marker not in ingestion_source:
            failures.append(
                f"repository ingestion is not bound to corpus governance: missing {marker}"
            )
    if failures:
        return _report(failures)
    sys.stdout.write(
        f"repository corpus governance: PASS ({len(repositories)} projected repositories)\n"
    )
    return 0


def _load_yaml(path: Path, failures: list[str]) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        failures.append(f"unable to load {path}: {exc}")
        return {}
    if not isinstance(value, Mapping):
        failures.append(f"{path} must contain a YAML mapping")
        return {}
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _report(failures: list[str]) -> int:
    for failure in failures:
        sys.stderr.write(f"FAIL repository-corpus-governance: {failure}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
