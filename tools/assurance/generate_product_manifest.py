#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/generate_product_manifest.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Derive the ProductManifest from the authoritative ProductTopology.

Global law names ``l9-semantic-compiler`` as the ProductManifest owner, but no
such compiler exists. Release progression must not depend on it, so this
repository derives its ``l9.product-manifest/v1`` deterministically here and
records exactly that in the manifest's ``compiler`` block (ADR-085 amendment).
An admitted global compiler, if one ever exists, supersedes this generator.

Inputs are read, never copied: ``product-topology.yaml`` from this repository,
and the bound global semantics from a ``Quantum-L9/.github`` checkout passed as
``--authority-root``. The generator never edits the topology and never invents
a coordinate. Each of the 17 ``resolved_manifest_gate`` conditions in
``l9.schema/product-manifest@1`` is evaluated mechanically:

* ``resolved_manifest_gate.result`` is ``pass`` only when every condition holds;
* every failing condition is listed in ``unresolved`` with its reasons.

Per the schema, a manifest may exist while unresolved, but only a ``pass``
manifest may be consumed for release progression.

Apply mode (default) writes ``release-work/product-manifest.json`` and is part
of explicit release PREPARATION. ``--check`` renders the same bytes in memory,
compares them with the committed artifact and writes nothing. The output is
deterministic: no timestamps, sorted keys, and a ``manifest_digest`` over the
canonical JSON of everything else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import validate_product_topology as topology_law

OUTPUT = Path("release-work") / "product-manifest.json"
TOPOLOGY = Path("product-topology.yaml")
PROFILE_ID = "l9.compilation/product-build@1"
GENERATOR = Path("tools") / "assurance" / "generate_product_manifest.py"
GATE = (
    "source_product_topology_valid",
    "product_kind_resolved",
    "product_archetype_resolved",
    "governance_profile_separate_from_identity",
    "identity_resolution_contract_resolved",
    "identity_topology_resolved",
    "hard_requirements_resolved",
    "capability_closure_resolved",
    "architecture_obligations_resolved",
    "required_ports_resolved",
    "required_adapters_resolved",
    "product_relationships_resolved",
    "provider_bindings_admissible",
    "admission_requirements_resolved",
    "conformance_requirements_resolved",
    "authority_boundaries_valid",
    "unresolved_hard_semantic_gaps_empty",
)
SHA256_PREFIX = "sha256:"
DIMENSION_KEY = {
    "product_identity": "product",
    "release_identity": "release",
    "runtime_identity": "runtime",
    "constellation_identity": "constellation",
    "actor_identity": "actor",
    "surface_identity": "surface",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_digest(data: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha256_digest(canonical(value))


def file_digest(path: Path) -> str:
    return sha256_digest(path.read_bytes())


class Law:
    """The bound global semantics this derivation consumes, read from the checkout."""

    def __init__(self, authority: Path) -> None:
        self.root = authority
        semantics = authority / "semantics"
        self.revision = topology_law.head_revision(authority)
        self.kinds = topology_law._load(semantics / "product_kinds.yaml")
        self.vocabulary = topology_law._load(semantics / "vocabulary.yaml")
        self.technologies = topology_law._load(semantics / "technology_capabilities.yaml")
        self.profiles = topology_law._load(semantics / "compilation_profiles.yaml")
        self.known = topology_law._global_ids(authority)
        self.consumed: list[str] = sorted(
            {
                *topology_law.MATERIAL_AUTHORITY_FILES,
                "semantics/vocabulary.yaml",
                "semantics/technology_capabilities.yaml",
                "semantics/compilation_profiles.yaml",
                "semantics/product_manifest.schema.yaml",
            }
        )

    def kind(self, name: str) -> dict[str, Any] | None:
        if name not in self.kinds["catalog_status"]["admitted_kinds"]:
            return None
        kind: dict[str, Any] = self.kinds["kinds"][name]
        return kind

    def archetype(self, kind: dict[str, Any], ref: str) -> dict[str, Any] | None:
        catalog = topology_law._load(self.root / "semantics" / kind["archetype_catalog"])
        found: dict[str, Any] | None = {a["id"]: a for a in catalog["archetypes"]}.get(ref)
        return found

    def technology_ids(self) -> set[str]:
        return {str(t["id"]) for t in self.technologies.get("technologies", [])}

    def relations(self) -> set[str]:
        relationship = self.vocabulary.get("terms", {}).get("product_relationship", {})
        return {str(r) for r in relationship.get("relations", [])}

    def profile(self) -> dict[str, Any]:
        for profile in self.profiles["profiles"]:
            if profile["id"] == PROFILE_ID:
                found: dict[str, Any] = profile
                return found
        raise ValueError(f"{PROFILE_ID} is not defined by the authority checkout")

    def authority_files(self) -> list[dict[str, str]]:
        files = []
        for relative in self.consumed:
            data = (self.root / relative).read_bytes()
            files.append(
                {
                    "path": relative,
                    "blob": topology_law.blob_id(data),
                    "digest": sha256_digest(data),
                }
            )
        return files


def _resolves(value: Any, known: set[str], repo: Path) -> bool:
    if not isinstance(value, str) or not value or value == "unknown":
        return False
    if topology_law.GLOBAL_REF.match(value):
        return value in known
    if value.startswith(topology_law.REPO_PREFIX):
        return (repo / value[len(topology_law.REPO_PREFIX) :].split("#", 1)[0]).exists()
    return True


Gate = dict[str, list[str]]
NO_ARCHETYPE: dict[str, Any] = {
    "requires": {"architecture_patterns": [], "conformance_classes": []}
}


def _kind_and_archetype(
    topo: dict[str, Any], law: Law, failing: Gate
) -> tuple[dict[str, Any], dict[str, Any]]:
    product = topo.get("product", {})
    kind = law.kind(str(product.get("kind")))
    archetype = None
    if kind is None:
        failing["product_kind_resolved"].append(f"ProductKind not admitted: {product.get('kind')}")
        kind = {"identity_dimensions": [], "required_patterns": [], "forbidden": []}
    else:
        archetype = law.archetype(kind, str(product.get("archetype_ref")))
    if archetype is None:
        failing["product_archetype_resolved"].append(
            f"archetype not in the kind's catalog: {product.get('archetype_ref')}"
        )
        archetype = NO_ARCHETYPE
    return kind, archetype


def _identity(
    topo: dict[str, Any], kind: dict[str, Any], law: Law, repo: Path, failing: Gate
) -> None:
    identity = topo.get("identity", {})
    profiles = set(topo.get("governance", {}).get("profile_refs") or [])
    failing["governance_profile_separate_from_identity"] = [
        f"identity carries a governance profile reference at identity.{where}"
        for where, value in topology_law._walk(identity)
        if where.rsplit(".", 1)[-1] == "governance_profile_ref" or value in profiles
    ]
    resolution = identity.get("resolution", {})
    failing["identity_resolution_contract_resolved"] = [
        f"identity.resolution.{key} unresolved"
        for key in ("contract_ref", "assertion_schema_ref")
        if not _resolves(resolution.get(key), law.known, repo)
    ]
    dimensions = identity.get("dimensions", {})
    reasons = [
        f"required identity dimension not declared: {name}"
        for name in kind.get("identity_dimensions", [])
        if dimensions.get(DIMENSION_KEY.get(name, name), {}).get("applicable") is not True
    ]
    forbids_constellation = "independent_constellation_identity_as_dependency" in kind.get(
        "forbidden", []
    )
    if forbids_constellation and dimensions.get("constellation", {}).get("applicable") is not False:
        reasons.append("dependency declares a constellation identity")
    rule = kind.get("runtime_identity_rule")
    if rule and dimensions.get("runtime", {}).get("rule") != rule:
        reasons.append("runtime identity does not carry the kind's rule")
    failing["identity_topology_resolved"] = reasons


def _requirements(topo: dict[str, Any], law: Law, repo: Path) -> list[str]:
    requirements = topo.get("requirements", {})
    constraints = [
        *requirements.get("hard_constraints", []),
        *requirements.get("operational_requirements", []),
        *requirements.get("security_requirements", []),
    ]
    reasons = [
        f"hard requirement unresolved: {c.get('id')}"
        for c in constraints
        if c.get("hardness") != "hard" or not _resolves(c.get("source_ref"), law.known, repo)
    ]
    refs = [*requirements.get("invariant_refs", []), *requirements.get("contract_refs", [])]
    reasons += [
        f"requirement reference unresolved: {ref}"
        for ref in refs
        if not _resolves(ref, law.known, repo)
    ]
    return reasons


def _capabilities(topo: dict[str, Any]) -> list[str]:
    owner = topo.get("identity", {}).get("semantic_owner")
    provided = {c["id"]: c for c in topo.get("capabilities", {}).get("provides", [])}
    reasons = [
        f"purpose capability not provided: {ref}"
        for ref in topo.get("purpose", {}).get("capability_refs", [])
        if ref not in provided
    ]
    reasons += [
        f"capability not owned by the product: {cap_id}"
        for cap_id, capability in provided.items()
        if capability.get("semantic_owner") != owner
    ]
    return reasons


def _ports_and_adapters(topo: dict[str, Any], failing: Gate) -> None:
    def entries(section: str) -> list[dict[str, Any]]:
        groups = topo.get(section, {}).values()
        return [item for group in groups if isinstance(group, list) for item in group]

    ports = {port["id"] for port in entries("ports")}
    adapters = entries("adapters")
    served = {adapter.get("port_ref") for adapter in adapters}
    failing["required_ports_resolved"] = [
        f"declared port has no adapter: {port}" for port in sorted(ports - served)
    ]
    failing["required_adapters_resolved"] = [
        f"adapter binds an undeclared port: {a.get('id')} -> {a.get('port_ref')}"
        for a in adapters
        if a.get("port_ref") not in ports
    ]


def _relationships(topo: dict[str, Any], kind: dict[str, Any], law: Law) -> list[str]:
    relations = law.relations()
    remote_forbidden = "remote_invocation_as_canonical_consumption" in kind.get("forbidden", [])
    reasons: list[str] = []
    for relationship in topo.get("relationships", {}).get("products", []):
        relation = relationship.get("relation")
        if relation not in relations:
            reasons.append(f"relation not in the vocabulary: {relation}")
        if relation == "invoke" and remote_forbidden:
            reasons.append("dependency consumed by remote invocation")
    return reasons


def _provider_bindings(topo: dict[str, Any], law: Law) -> list[str]:
    technologies = law.technology_ids()
    return [
        f"provider binding {b.get('target_id')} has no admitted technology coordinate"
        f" ({b.get('technology_ref')}; {b.get('unknown_ref', 'no unknown ref')})"
        for b in topo.get("bindings", {}).get("provider_bindings", [])
        if b.get("technology_ref") not in technologies
    ]


def _admission(topo: dict[str, Any], law: Law, repo: Path) -> list[str]:
    admission = topo.get("admission", {})
    reasons = [
        f"admission.{key} unresolved"
        for key in ("subject", "authority_ref", "decision_ref")
        if not _resolves(admission.get(key), law.known, repo)
    ]
    if not admission.get("requirements"):
        reasons.append("admission.requirements empty")
    return reasons


def _conformance(
    topo: dict[str, Any], archetype: dict[str, Any], law: Law, repo: Path
) -> list[str]:
    conformance = topo.get("conformance", {})
    reasons = [
        f"conformance profile unresolved: {ref}"
        for ref in conformance.get("profile_refs", [])
        if not _resolves(ref, law.known, repo) or not str(ref).startswith("l9.")
    ]
    required = set(archetype["requires"]["conformance_classes"])
    missing = required - set(conformance.get("required_classes", []))
    return reasons + [f"conformance class missing: {c}" for c in sorted(missing)]


def _boundaries(topo: dict[str, Any]) -> list[str]:
    boundary = topo.get("boundary", {})
    owns, disowns = set(boundary.get("owns", [])), set(boundary.get("does_not_own", []))
    reasons = [] if owns and disowns else ["boundary owns/does_not_own must both be declared"]
    return reasons + [f"owned and disowned: {s}" for s in sorted(owns & disowns)]


def evaluate_gate(
    topo: dict[str, Any], law: Law, repo: Path, topology_path: Path
) -> dict[str, list[str]]:
    """Return every gate condition with the reasons it fails (empty = holds)."""

    failing: Gate = {name: [] for name in GATE}
    failing["source_product_topology_valid"] = topology_law.validate(repo, law.root, topology_path)
    kind, archetype = _kind_and_archetype(topo, law, failing)
    _identity(topo, kind, law, repo, failing)
    failing["hard_requirements_resolved"] = _requirements(topo, law, repo)
    failing["capability_closure_resolved"] = _capabilities(topo)
    failing["architecture_obligations_resolved"] = topology_law.check_kind(
        topo, law.kinds, law.root
    )
    _ports_and_adapters(topo, failing)
    failing["product_relationships_resolved"] = _relationships(topo, kind, law)
    failing["provider_bindings_admissible"] = _provider_bindings(topo, law)
    failing["admission_requirements_resolved"] = _admission(topo, law, repo)
    failing["conformance_requirements_resolved"] = _conformance(topo, archetype, law, repo)
    failing["authority_boundaries_valid"] = _boundaries(topo)
    failing["unresolved_hard_semantic_gaps_empty"] = [
        f"material Unknown {u.get('id')}: {u.get('subject')}"
        for u in topo.get("unknowns", {}).get("material") or []
    ]
    return failing


def derive(repo: Path, authority: Path) -> dict[str, Any]:
    topology_path = repo / TOPOLOGY
    topo = topology_law._load(topology_path)
    law = Law(authority)
    failing = evaluate_gate(topo, law, repo, topology_path)
    product = topo["product"]
    kind = law.kind(str(product.get("kind"))) or {}
    archetype = law.archetype(kind, str(product.get("archetype_ref"))) if kind else None
    profile = law.profile()
    required_patterns = sorted(
        {
            *kind.get("required_patterns", []),
            *((archetype or {}).get("requires", {}).get("architecture_patterns", [])),
        }
    )
    manifest: dict[str, Any] = {
        "schema": "l9.product-manifest/v1",
        "product": {k: product.get(k) for k in ("id", "kind", "archetype_ref", "name")},
        "source_topology": {
            "ref": f"{topology_law.REPO_PREFIX}{TOPOLOGY.as_posix()}",
            "digest": file_digest(topology_path),
        },
        "authority": {
            "repository": "Quantum-L9/.github",
            "revision": law.revision,
            "files": law.authority_files(),
            "product_semantic_owner": topo["identity"]["semantic_owner"],
        },
        "identity": {
            **topo["identity"],
            "kind_identity_dimensions": kind.get("identity_dimensions", []),
            "runtime_identity_rule": kind.get("runtime_identity_rule"),
        },
        "requirements": topo["requirements"],
        "capabilities": topo["capabilities"],
        "architecture": {
            **topo["architecture"],
            "resolved_required_pattern_refs": required_patterns,
        },
        "ports": topo.get("ports", {}),
        "adapters": topo.get("adapters", {}),
        "relationships": topo["relationships"],
        "technology": topo.get("technology", {}),
        "bindings": topo.get("bindings", {}),
        "providers": topo.get("providers", {}),
        "state": topo.get("state", {}),
        "runtime": topo.get("runtime", {}),
        "communication": topo.get("communication", {}),
        "security": topo.get("security", {}),
        "failure": topo.get("failure", {}),
        "receipts": topo.get("receipts", {}),
        "observability": topo.get("observability", {}),
        "admission": {
            **topo["admission"],
            "product_release_admission": kind.get("admission_model", {}).get(
                "product_release_admission", []
            ),
            "consumer_binding": kind.get("admission_model", {}).get("consumer_binding", []),
        },
        "lifecycle": topo["lifecycle"],
        "conformance": topo["conformance"],
        "compatibility": topo.get("compatibility", {}),
        "distribution": topo.get("distribution", {}),
        "build": topo.get("build", {}),
        "governance": topo.get("governance", {}),
        "compiler": {
            "profile_ref": PROFILE_ID,
            "profile_digest": digest(profile),
            "compiler_version": f"{topology_law.REPO_PREFIX}{GENERATOR.as_posix()}@{file_digest(repo / GENERATOR)}",
            "realization": "repository-local deterministic derivation; no l9-semantic-compiler exists (ADR-085)",
        },
        "provenance": {
            "derivation": "deterministic",
            "inputs": [
                {
                    "ref": f"{topology_law.REPO_PREFIX}{TOPOLOGY.as_posix()}",
                    "digest": file_digest(topology_path),
                },
                *(
                    {"ref": f"Quantum-L9/.github/{f['path']}@{f['blob']}", "digest": f["digest"]}
                    for f in law.authority_files()
                ),
            ],
        },
        "resolved_manifest_gate": {
            "result": "pass" if not any(failing.values()) else "fail",
            "conditions": {
                name: {"holds": not reasons, "reasons": reasons}
                for name, reasons in failing.items()
            },
        },
        "unresolved": [
            {"condition": name, "reasons": reasons} for name, reasons in failing.items() if reasons
        ],
    }
    manifest["manifest_digest"] = digest(manifest)
    return manifest


def render(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Recompute the digest a manifest carries, for consumers that verify it."""

    return digest({k: v for k, v in manifest.items() if k != "manifest_digest"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="compare with the committed artifact")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    manifest = derive(repo, args.authority_root.resolve())
    rendered = render(manifest)
    target = repo / OUTPUT
    gate = manifest["resolved_manifest_gate"]["result"]
    if args.check:
        if not target.is_file() or target.read_bytes() != rendered:
            sys.stdout.write(f"FAIL: {OUTPUT} is stale; re-run explicit preparation\n")
            return 1
        sys.stdout.write(
            f"PASS: {OUTPUT} matches the derivation ({manifest['manifest_digest']}, gate {gate})\n"
        )
        return 0
    target.write_bytes(rendered)
    sys.stdout.write(
        f"Generated {OUTPUT} {manifest['manifest_digest']} (resolved_manifest_gate: {gate})\n"
    )
    for item in manifest["unresolved"]:
        sys.stdout.write(f"  unresolved {item['condition']}: {'; '.join(item['reasons'])}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
