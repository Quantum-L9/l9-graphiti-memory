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
* ``provenance`` pins the authority revision of the checkout and the git blob
  ids of the four material authority files;
* every ``unknown`` value is backed by a declared material Unknown.

Product-owned ``l9-graphiti-memory:`` identifiers are owned by this
repository (ProductTopology NM-001) and are not resolved globally.

Read-only. Exit 0 only when every check passes. Prints the topology sha256.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

REPO_PREFIX = "Quantum-L9/l9-graphiti-memory/"
MATERIAL_AUTHORITY_FILES = (
    "semantics/contracts.yaml",
    "semantics/product_topology.schema.yaml",
    "semantics/product_kinds.yaml",
    "semantics/dependency_archetypes.yaml",
)
GLOBAL_REF = re.compile(r"^(l9\.[a-z0-9-]+(/[A-Za-z0-9_.-]+)?(@\d+)?|L9-[A-Z]+-\d{3})$")


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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _global_ids(authority: Path) -> set[str]:
    ids: set[str] = set()
    for ledger in sorted((authority / "semantics").glob("*.yaml")):
        for _, value in _walk(_load(ledger)):
            if isinstance(value, str) and GLOBAL_REF.match(value):
                ids.add(value)
        text = ledger.read_text(encoding="utf-8")
        ids.update(re.findall(r"(?m)^\s*-?\s*(?:id|artifact_id):\s*([^\s#]+)", text))
        ids.update(re.findall(r"(?m)^(L9-[A-Z]+-\d{3}):", text))
    return ids


def _required(schema_node: dict[str, Any]) -> list[str]:
    return [str(key) for key in schema_node.get("required", [])]


def validate(repo: Path, authority: Path, topology_path: Path) -> list[str]:
    failures: list[str] = []
    schema = _load(authority / "semantics" / "product_topology.schema.yaml")
    kinds = _load(authority / "semantics" / "product_kinds.yaml")
    topo = _load(topology_path)
    if not isinstance(topo, dict):
        return ["topology is not a mapping"]

    props: dict[str, Any] = schema["properties"]
    if topo.get("schema") != props["schema"]["const"]:
        failures.append(f"schema must be {props['schema']['const']}")
    for key in _required(schema):
        if key not in topo:
            failures.append(f"missing required top-level key: {key}")
    for key in topo:
        if key not in props:
            failures.append(f"top-level key outside the topology vocabulary: {key}")
    for key, spec in props.items():
        if isinstance(spec, dict) and isinstance(topo.get(key), dict):
            for sub in _required(spec):
                if sub not in topo[key]:
                    failures.append(f"missing required key: {key}.{sub}")
    resolution_spec = props["identity"]["fields"]["resolution"]
    for sub in _required(resolution_spec):
        if sub not in topo.get("identity", {}).get("resolution", {}):
            failures.append(f"missing required key: identity.resolution.{sub}")
    dimension_keys = set(props["identity"]["fields"]["dimensions"]["fields"])
    for dim in topo.get("identity", {}).get("dimensions", {}):
        if dim not in dimension_keys:
            failures.append(f"identity dimension outside the schema: {dim}")

    vocab = _load(authority / "semantics" / "vocabulary.yaml")
    vocab_text = yaml.safe_dump(vocab)
    for field in ("consumption", "deployment"):
        value = topo.get(field, {}).get("model")
        if not value or not re.search(rf"\b{re.escape(str(value))}\b", vocab_text):
            failures.append(f"{field}.model is not an admitted vocabulary value: {value}")

    product = topo.get("product", {})
    kind_name = product.get("kind")
    admitted = kinds["catalog_status"]["admitted_kinds"]
    if kind_name not in admitted:
        failures.append(f"product.kind is not an admitted ProductKind: {kind_name}")
    else:
        kind = kinds["kinds"][kind_name]
        if topo["consumption"]["model"] != kind["consumption_model"]:
            failures.append("consumption.model contradicts the declared ProductKind")
        if topo["deployment"]["model"] != kind["deployment_model"]:
            failures.append("deployment.model contradicts the declared ProductKind")
        catalog = _load(authority / "semantics" / kind["archetype_catalog"])
        archetypes = {a["id"]: a for a in catalog["archetypes"]}
        archetype = archetypes.get(product.get("archetype_ref"))
        if archetype is None:
            failures.append("product.archetype_ref is not in the kind's archetype catalog")
        required_patterns = set(kind.get("required_patterns", []))
        required_classes: set[str] = set()
        optional_patterns: set[str] = set()
        if archetype is not None:
            required_patterns |= set(archetype["requires"]["architecture_patterns"])
            required_classes = set(archetype["requires"]["conformance_classes"])
            optional_patterns = set(archetype.get("optional_patterns", []))
        arch = topo.get("architecture", {})
        declared_required = set(arch.get("required_pattern_refs", []))
        for pattern in sorted(required_patterns - declared_required):
            failures.append(f"required pattern missing: {pattern}")
        for pattern in sorted(set(arch.get("optional_pattern_refs", [])) - optional_patterns):
            failures.append(f"optional pattern not offered by the archetype: {pattern}")
        clash = declared_required & set(arch.get("forbidden_pattern_refs", []))
        for pattern in sorted(clash):
            failures.append(f"pattern both required and forbidden: {pattern}")
        declared_classes = set(topo.get("conformance", {}).get("required_classes", []))
        for cls in sorted(required_classes - declared_classes):
            failures.append(f"required conformance class missing: {cls}")
        release_states = set(kind["admission_model"]["product_release_admission"])
    if kind_name not in admitted:
        release_states = set()

    known = _global_ids(authority)
    for where, value in _walk(topo):
        if not isinstance(value, str):
            continue
        if GLOBAL_REF.match(value) and value not in known:
            failures.append(f"unresolved global reference at {where}: {value}")
        if value.startswith(REPO_PREFIX):
            rel = value[len(REPO_PREFIX) :].split("#", 1)[0]
            if not (repo / rel).exists():
                failures.append(f"repository reference does not exist at {where}: {value}")
    for state in topo.get("lifecycle", {}).get("applicable_state_refs", []):
        if state not in release_states:
            failures.append(f"lifecycle state is not a {kind_name} release state: {state}")

    subjects = {str(u.get("subject")) for u in topo.get("unknowns", {}).get("material") or []}
    for where, value in _walk(topo):
        if value != "unknown" or where.startswith("unknowns"):
            continue
        field = re.sub(r"\[\d+\]", "[*]", where)
        if field not in subjects and re.sub(r"\[\*\]$", "", field) not in subjects:
            failures.append(f"explicit unknown at {where} has no material Unknown subject")

    provenance = topo.get("provenance", {})
    head = _git(authority, "rev-parse", "HEAD")
    if provenance.get("authority_ref") != f"Quantum-L9/.github@{head}":
        failures.append(f"provenance.authority_ref does not pin the authority checkout {head}")
    pinned = "\n".join(provenance.get("source_refs", []))
    for rel in MATERIAL_AUTHORITY_FILES:
        blob = _git(authority, "rev-parse", f"HEAD:{rel}")
        if f"Quantum-L9/.github/{rel}@{blob}" not in pinned:
            failures.append(f"provenance.source_refs does not pin {rel}@{blob}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--authority-root", type=Path, required=True)
    args = parser.parse_args()
    topology = args.repo_root / "product-topology.yaml"
    digest = hashlib.sha256(topology.read_bytes()).hexdigest()
    failures = validate(args.repo_root, args.authority_root, topology)
    authority = _git(args.authority_root, "rev-parse", "HEAD")
    sys.stdout.write(f"topology: product-topology.yaml sha256:{digest}\n")
    sys.stdout.write(f"authority: Quantum-L9/.github@{authority}\n")
    if failures:
        sys.stdout.write("".join(f"FAIL: {failure}\n" for failure in failures))
        return 1
    sys.stdout.write("PASS: product-topology.yaml is mechanically valid against ")
    sys.stdout.write("l9.schema/product-topology@1\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
