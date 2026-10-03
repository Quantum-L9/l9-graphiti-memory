#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/authority/project_l9_repository_corpus.py
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-10-02
"""Project the canonical Quantum-L9 repository corpus into this package."""
from __future__ import annotations
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping
import yaml
REGISTRY_ARTIFACT = "l9.repository-registry/global@1"
CLASSES_ARTIFACT = "l9.repository-classes/global@1"
VIEW_REF = "l9.repository-view/memory-namespace-l9@1"
OUTPUT_ARTIFACT = "l9.projection/memory-repository-corpus@1"
OUTPUT_SCHEMA = "l9.projection.memory-repository-corpus/v1"
RECEIPT_SCHEMA = "l9.projection-receipt/v1"
GENERATOR_ID = "l9-graphiti-memory.repository-corpus-projector/v1"
class ProjectionError(RuntimeError):
    pass
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "src/l9_graphite_memory/resources/repository_corpus.yaml"
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path(
            "src/l9_graphite_memory/resources/repository_corpus.receipt.yaml"
        ),
    )
    parser.add_argument("--source-revision")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()
def main() -> int:
    args = parse_args()
    authority_root = args.authority_root.resolve()
    registry_path = authority_root / "semantics" / "repository_registry.yaml"
    classes_path = authority_root / "semantics" / "repository_classes.yaml"
    registry_bytes = _read_required(registry_path)
    classes_bytes = _read_required(classes_path)
    registry = _yaml_mapping(registry_bytes, registry_path)
    classes = _yaml_mapping(classes_bytes, classes_path)
    source_revision = args.source_revision or _git_revision(authority_root)
    corpus = project(
        registry=registry,
        classes=classes,
        source_revision=source_revision,
        registry_digest=_digest(registry_bytes),
        classes_digest=_digest(classes_bytes),
    )
    output_bytes = _dump_yaml(corpus)
    receipt = build_receipt(
        corpus=corpus,
        output_path=args.output,
        output_digest=_digest(output_bytes),
    )
    receipt_bytes = _dump_yaml(receipt)
    if args.check:
        errors: list[str] = []
        if not args.output.is_file():
            errors.append(f"missing generated projection: {args.output}")
        elif args.output.read_bytes() != output_bytes:
            errors.append(f"stale generated projection: {args.output}")
        if not args.receipt.is_file():
            errors.append(f"missing projection receipt: {args.receipt}")
        elif args.receipt.read_bytes() != receipt_bytes:
            errors.append(f"stale projection receipt: {args.receipt}")
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print("repository corpus projection is current")
        return 0
    _write(args.output, output_bytes)
    _write(args.receipt, receipt_bytes)
    print(args.output)
    print(args.receipt)
    return 0
def project(
    *,
    registry: Mapping[str, Any],
    classes: Mapping[str, Any],
    source_revision: str,
    registry_digest: str,
    classes_digest: str,
) -> dict[str, Any]:
    if registry.get("artifact_id") != REGISTRY_ARTIFACT:
        raise ProjectionError(
            f"expected {REGISTRY_ARTIFACT}, got {registry.get('artifact_id')}"
        )
    if classes.get("artifact_id") != CLASSES_ARTIFACT:
        raise ProjectionError(
            f"expected {CLASSES_ARTIFACT}, got {classes.get('artifact_id')}"
        )
    if registry.get("canonical") is not True:
        raise ProjectionError("repository registry must be canonical")
    if classes.get("canonical") is not True:
        raise ProjectionError("repository classes must be canonical")
    if registry.get("class_catalog_ref") != CLASSES_ARTIFACT:
        raise ProjectionError(
            "repository registry does not reference the expected class catalog"
        )
    views = _mapping(classes.get("derived_views"), "derived_views")
    view = _mapping(views.get("l9_memory_namespace"), "l9_memory_namespace")
    if view.get("id") != VIEW_REF:
        raise ProjectionError(
            f"expected repository view {VIEW_REF}, got {view.get('id')}"
        )
    selector = _mapping(view.get("selector"), "selector")
    class_ref = _required_string(selector, "class_ref")
    lifecycle_in = selector.get("lifecycle_in")
    if not isinstance(lifecycle_in, list) or not lifecycle_in:
        raise ProjectionError("repository view lifecycle_in must be a non-empty list")
    allowed_lifecycles = {
        str(value)
        for value in lifecycle_in
        if isinstance(value, str) and value
    }
    output = _mapping(view.get("output"), "view.output")
    logical_namespace = _required_string(output, "namespace")
    class_catalog = _mapping(classes.get("classes"), "classes")
    l9_class = _mapping(class_catalog.get("l9"), "classes.l9")
    if l9_class.get("id") != class_ref:
        raise ProjectionError("repository view class_ref does not resolve to classes.l9")
    obligations = _mapping(l9_class.get("obligations"), "classes.l9.obligations")
    memory = _mapping(obligations.get("memory"), "classes.l9.obligations.memory")
    if memory.get("namespace") != logical_namespace:
        raise ProjectionError(
            "repository class memory namespace disagrees with derived repository view"
        )
    if memory.get("membership") != "required":
        raise ProjectionError(
            "L9 repository class must require memory namespace membership"
        )
    raw_repositories = registry.get("repositories")
    if not isinstance(raw_repositories, list):
        raise ProjectionError("repository registry repositories must be a list")
    projected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_coordinates: set[str] = set()
    for raw_repository in raw_repositories:
        repository = _mapping(raw_repository, "repository")
        repository_id = _required_string(repository, "id")
        if repository_id in seen_ids:
            raise ProjectionError(f"duplicate repository id: {repository_id}")
        seen_ids.add(repository_id)
        coordinate = _mapping(repository.get("coordinate"), f"{repository_id}.coordinate")
        provider = _required_string(coordinate, "provider")
        organization = _required_string(coordinate, "organization")
        repository_name = _required_string(coordinate, "repository")
        coordinate_key = f"{provider}:{organization}/{repository_name}"
        if coordinate_key in seen_coordinates:
            raise ProjectionError(f"duplicate repository coordinate: {coordinate_key}")
        seen_coordinates.add(coordinate_key)
        lifecycle = _required_string(repository, "lifecycle")
        repository_class_ref = _required_string(repository, "class_ref")
        if repository_class_ref != class_ref:
            continue
        if lifecycle not in allowed_lifecycles:
            continue
        projected.append(
            {
                "id": repository_id,
                "coordinate": {
                    "provider": provider,
                    "organization": organization,
                    "repository": repository_name,
                },
                "lifecycle": lifecycle,
                "class_ref": repository_class_ref,
            }
        )
    projected.sort(key=lambda item: item["id"])
    return {
        "schema": OUTPUT_SCHEMA,
        "artifact_id": OUTPUT_ARTIFACT,
        "canonical": False,
        "authority": {
            "authority_class": "derived",
            "canonical_owner": "Quantum-L9/.github",
            "consumer": "Quantum-L9/l9-graphiti-memory",
        },
        "projection": {
            "view_ref": VIEW_REF,
            "source_repository": "Quantum-L9/.github",
            "source_revision": source_revision,
            "sources": {
                "repository_registry": {
                    "artifact_ref": REGISTRY_ARTIFACT,
                    "digest": registry_digest,
                },
                "repository_classes": {
                    "artifact_ref": CLASSES_ARTIFACT,
                    "digest": classes_digest,
                },
            },
        },
        "namespace": {
            "logical": logical_namespace,
        },
        "repository_class_ref": class_ref,
        "repositories": projected,
    }
def build_receipt(
    *,
    corpus: Mapping[str, Any],
    output_path: Path,
    output_digest: str,
) -> dict[str, Any]:
    projection = _mapping(corpus.get("projection"), "projection")
    return {
        "schema": RECEIPT_SCHEMA,
        "projection": {
            "artifact_ref": OUTPUT_ARTIFACT,
            "view_ref": projection["view_ref"],
            "source_repository": projection["source_repository"],
            "source_revision": projection["source_revision"],
            "sources": projection["sources"],
        },
        "output": {
            "path": output_path.as_posix(),
            "schema": OUTPUT_SCHEMA,
            "digest": output_digest,
        },
        "generator": {
            "id": GENERATOR_ID,
            "deterministic": True,
        },
    }
def _git_revision(root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        raise ProjectionError("git is required to resolve the authority source revision")
    result = subprocess.run(  # noqa: S603
        [git, "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise ProjectionError(
            f"unable to resolve source revision: {result.stderr.strip()}"
        )
    revision = result.stdout.strip()
    if len(revision) != 40:
        raise ProjectionError(f"unexpected git revision: {revision}")
    return revision
def _read_required(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise ProjectionError(f"required canonical source is missing: {path}") from exc
def _yaml_mapping(raw: bytes, path: Path) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ProjectionError(f"invalid YAML in {path}: {exc}") from exc
    return _mapping(value, str(path))
def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectionError(f"{label} must be a mapping")
    return value
def _required_string(value: Mapping[str, Any], key: str) -> str:
    resolved = value.get(key)
    if not isinstance(resolved, str) or not resolved:
        raise ProjectionError(f"{key} must be a non-empty string")
    return resolved
def _digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"
def _dump_yaml(value: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(
        dict(value),
        sort_keys=False,
        allow_unicode=True,
        width=100,
    ).encode("utf-8")
def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
if __name__ == "__main__":
    raise SystemExit(main())
