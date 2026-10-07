#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/validate_product_topology.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Mechanically validate product-topology.yaml against the bound global schema.

The global semantics are read from a Quantum-L9/.github checkout at run time
(``--authority-root``) and are never copied into this repository. The checks
are the ones the bound law states mechanically:

* ``schema`` const and every required top-level and nested key of
  ``l9.schema/product-topology@1``; no top-level key outside its vocabulary;
* ``consumption.model`` / ``deployment.model`` within the admitted
  vocabulary values;
* ProductKind admitted, coherent with its consumption and deployment model,
  and the archetype a member of the kind's own archetype catalog;
* the kind's and archetype's required patterns and conformance classes
  present; no pattern both required and forbidden;
* identity dimensions limited to the schema's dimension keys;
* every ``l9.*`` and ``L9-*`` reference resolves to an id or artifact_id in
  the authority checkout's ``semantics/`` ledgers (or a dependency release
  state of the declared kind);
* every ``Quantum-L9/l9-graphiti-memory/<path>`` reference names a file in
  this repository;
* ``provenance`` pins the authority checkout's HEAD revision and the git blob
  ids of the material authority files exactly as read;
* every ``unknown`` value is backed by a declared material Unknown.

Product-owned ``l9-graphiti-memory:`` identifiers are owned by this
repository (ProductTopology NM-001) and are not resolved globally.

Read-only and subprocess-free: git object ids are computed from the bytes
read. Exit 0 only when every check passes. Prints the topology sha256.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

REPO_PREFIX = "Quantum-L9/l9-graphiti-memory/"
MATERIAL_AUTHORITY_FILES = (
    "semantics/contracts.yaml",
    "semantics/authority_model.yaml",
    "semantics/product_topology.schema.yaml",
    "semantics/product_kinds.yaml",
    "semantics/dependency_archetypes.yaml",
)
GLOBAL_REF = re.compile(r"^(?:l9\.[a-z0-9-]+(?:/[A-Za-z0-9_.-]+)?(?:@\d+)?|L9-[A-Z]+-\d{3})$")
LEDGER_ID = re.compile(r"^[ \t]*(?:- )?(?:id|artifact_id):[ \t]*(\S+)", re.MULTILINE)
INVARIANT_KEY = re.compile(r"^(L9-[A-Z]+-\d{3}):", re.MULTILINE)
SHA = re.compile(r"^[0-9a-f]{40}$")


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


def blob_id(data: bytes) -> str:
    """Git object id of ``data`` as a blob, computed without invoking git."""

    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def head_revision(checkout: Path) -> str:
    """Resolve the checkout's HEAD commit id from its git metadata files."""

    git_dir = checkout / ".git"
    if git_dir.is_file():
        pointer = git_dir.read_text(encoding="utf-8").strip().removeprefix("gitdir:").strip()
        git_dir = (checkout / pointer).resolve()
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if SHA.match(head):
        return head
    ref = head.removeprefix("ref:").strip()
    loose = git_dir / ref
    if loose.is_file():
        return loose.read_text(encoding="utf-8").strip()
    for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
        if line.endswith(f" {ref}"):
            return line.split(" ", 1)[0]
    raise ValueError(f"cannot resolve HEAD of {checkout}")


def _global_ids(authority: Path) -> set[str]:
    ids: set[str] = set()
    for ledger in sorted((authority / "semantics").glob("*.yaml")):
        text = ledger.read_text(encoding="utf-8")
        ids.update(LEDGER_ID.findall(text))
        ids.update(INVARIANT_KEY.findall(text))
        ids.update(
            v for _, v in _walk(yaml.safe_load(text)) if isinstance(v, str) and GLOBAL_REF.match(v)
        )
    return ids


def _required(schema_node: dict[str, Any]) -> list[str]:
    return [str(key) for key in schema_node.get("required", [])]


def check_structure(
    topo: dict[str, Any], props: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    if topo.get("schema") != props["schema"]["const"]:
        failures.append(f"schema must be {props['schema']['const']}")
    failures += [f"missing required top-level key: {k}" for k in _required(schema) if k not in topo]
    failures += [
        f"top-level key outside the topology vocabulary: {k}" for k in topo if k not in props
    ]
    for key, spec in props.items():
        section = topo.get(key)
        if isinstance(spec, dict) and isinstance(section, dict):
            failures += [
                f"missing required key: {key}.{s}" for s in _required(spec) if s not in section
            ]
    identity_fields = props["identity"]["fields"]
    resolution = topo.get("identity", {}).get("resolution", {})
    failures += [
        f"missing required key: identity.resolution.{s}"
        for s in _required(identity_fields["resolution"])
        if s not in resolution
    ]
    dimension_keys = set(identity_fields["dimensions"]["fields"])
    failures += [
        f"identity dimension outside the schema: {d}"
        for d in topo.get("identity", {}).get("dimensions", {})
        if d not in dimension_keys
    ]
    return failures


def check_models(topo: dict[str, Any], vocabulary_text: str) -> list[str]:
    failures: list[str] = []
    for field in ("consumption", "deployment"):
        value = topo.get(field, {}).get("model")
        if not value or not re.search(rf"\b{re.escape(str(value))}\b", vocabulary_text):
            failures.append(f"{field}.model is not an admitted vocabulary value: {value}")
    return failures


def check_kind(topo: dict[str, Any], kinds: dict[str, Any], authority: Path) -> list[str]:
    product = topo.get("product", {})
    kind_name = product.get("kind")
    if kind_name not in kinds["catalog_status"]["admitted_kinds"]:
        return [f"product.kind is not an admitted ProductKind: {kind_name}"]
    kind = kinds["kinds"][kind_name]
    failures = [
        f"{field}.model contradicts the declared ProductKind"
        for field in ("consumption", "deployment")
        if topo.get(field, {}).get("model") != kind[f"{field}_model"]
    ]
    catalog = _load(authority / "semantics" / kind["archetype_catalog"])
    archetype = {a["id"]: a for a in catalog["archetypes"]}.get(product.get("archetype_ref"))
    if archetype is None:
        failures.append("product.archetype_ref is not in the kind's archetype catalog")
        archetype = {"requires": {"architecture_patterns": [], "conformance_classes": []}}
    arch = topo.get("architecture", {})
    required = set(kind.get("required_patterns", [])) | set(
        archetype["requires"]["architecture_patterns"]
    )
    declared = set(arch.get("required_pattern_refs", []))
    offered = set(archetype.get("optional_patterns", []))
    failures += [f"required pattern missing: {p}" for p in sorted(required - declared)]
    failures += [
        f"optional pattern not offered by the archetype: {p}"
        for p in sorted(set(arch.get("optional_pattern_refs", [])) - offered)
    ]
    failures += [
        f"pattern both required and forbidden: {p}"
        for p in sorted(declared & set(arch.get("forbidden_pattern_refs", [])))
    ]
    classes = set(topo.get("conformance", {}).get("required_classes", []))
    failures += [
        f"required conformance class missing: {c}"
        for c in sorted(set(archetype["requires"]["conformance_classes"]) - classes)
    ]
    states = set(kind["admission_model"]["product_release_admission"])
    failures += [
        f"lifecycle state is not a {kind_name} release state: {s}"
        for s in topo.get("lifecycle", {}).get("applicable_state_refs", [])
        if s not in states
    ]
    return failures


def check_references(topo: dict[str, Any], known: set[str], repo: Path) -> list[str]:
    failures: list[str] = []
    for where, value in _walk(topo):
        if not isinstance(value, str):
            continue
        if GLOBAL_REF.match(value) and value not in known:
            failures.append(f"unresolved global reference at {where}: {value}")
        if value.startswith(REPO_PREFIX):
            relative = value[len(REPO_PREFIX) :].split("#", 1)[0]
            if not (repo / relative).exists():
                failures.append(f"repository reference does not exist at {where}: {value}")
    return failures


def check_unknowns(topo: dict[str, Any]) -> list[str]:
    subjects = {str(u.get("subject")) for u in topo.get("unknowns", {}).get("material") or []}
    failures: list[str] = []
    for where, value in _walk(topo):
        if value != "unknown" or where.startswith("unknowns"):
            continue
        field = re.sub(r"\[\d+\]", "[*]", where)
        if field not in subjects and field.removesuffix("[*]") not in subjects:
            failures.append(f"explicit unknown at {where} has no material Unknown subject")
    return failures


def check_provenance(topo: dict[str, Any], authority: Path) -> list[str]:
    provenance = topo.get("provenance", {})
    head = head_revision(authority)
    failures: list[str] = []
    if provenance.get("authority_ref") != f"Quantum-L9/.github@{head}":
        failures.append(f"provenance.authority_ref does not pin the authority checkout {head}")
    pinned = set(provenance.get("source_refs", []))
    for relative in MATERIAL_AUTHORITY_FILES:
        blob = blob_id((authority / relative).read_bytes())
        if f"Quantum-L9/.github/{relative}@{blob}" not in pinned:
            failures.append(f"provenance.source_refs does not pin {relative}@{blob}")
    return failures


def validate(repo: Path, authority: Path, topology_path: Path) -> list[str]:
    topo = _load(topology_path)
    if not isinstance(topo, dict):
        return ["topology is not a mapping"]
    schema = _load(authority / "semantics" / "product_topology.schema.yaml")
    kinds = _load(authority / "semantics" / "product_kinds.yaml")
    vocabulary_text = (authority / "semantics" / "vocabulary.yaml").read_text(encoding="utf-8")
    return [
        *check_structure(topo, schema["properties"], schema),
        *check_models(topo, vocabulary_text),
        *check_kind(topo, kinds, authority),
        *check_references(topo, _global_ids(authority), repo),
        *check_unknowns(topo),
        *check_provenance(topo, authority),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--authority-root", type=Path, required=True)
    args = parser.parse_args()
    authority = args.authority_root.resolve()
    topology = args.repo_root / "product-topology.yaml"
    digest = hashlib.sha256(topology.read_bytes()).hexdigest()
    failures = validate(args.repo_root, authority, topology)
    sys.stdout.write(f"topology: product-topology.yaml sha256:{digest}\n")
    sys.stdout.write(f"authority: Quantum-L9/.github@{head_revision(authority)}\n")
    if failures:
        sys.stdout.write("".join(f"FAIL: {failure}\n" for failure in failures))
        return 1
    sys.stdout.write("PASS: product-topology.yaml is mechanically valid against ")
    sys.stdout.write("l9.schema/product-topology@1\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
