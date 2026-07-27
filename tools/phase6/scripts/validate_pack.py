#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/phase6/scripts/validate_pack.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: pack_validator
# tags: [validation, packaging, provenance, zero-stub]
# owner: igor_beylin
# status: active
# version: 3.2.0
# updated: 2026-07-26
# Purpose: validate the exact Phase 6H.2 pack, executable policy, schemas, trust separation, and checksum manifest.
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REQUIRED = {
    "SKILL.md",
    "README.md",
    "RUNBOOK.md",
    "MANIFEST.md",
    "AGENT_EXECUTION_PROMPT.md",
    "requirements.txt",
    "references/EXECUTION_CONTRACT.yaml",
    "references/EVIDENCE_CONTRACT.yaml",
    "references/SCENARIO_MATRIX.md",
    "references/GO_NO_GO_POLICY.yaml",
    "references/TRUST_MODEL.md",
    "scripts/phase6_integrity.py",
    "scripts/generate_signing_key.py",
    "scripts/build_evidence_record.py",
    "scripts/phase6ctl.py",
    "scripts/package_evidence.sh",
    "scripts/self_test.sh",
    "scripts/run_adversarial_tests.py",
    "scripts/verify_oidc_claims.py",
    "scripts/collect_repository_evidence.py",
    "scripts/collect_github_evidence.py",
    "scripts/collect_infisical_audit.py",
    "scripts/collect_workflow_evidence.py",
    "scripts/validate_receipts.py",
    "scripts/collect_final_convergence.py",
    "scripts/collect_host_evidence.py",
    "schemas/host-health.schema.json",
    "schemas/phase6-input.schema.json",
    "schemas/proof-envelope.schema.json",
    "config/phase6-inputs.example.json",
    "tests/test_hardening.py",
    "source-evidence/PLAN_LOCKED.md",
    "MANIFEST.sha256",
}
FORBIDDEN_NAMES = {
    "openai.yaml", "runtime.env", ".env", "id_rsa", "id_ed25519",
    "oidc.jwt", "token.txt", "signing-private.pem", "ledger-private.pem", "evidence-private.pem",
}
FORBIDDEN_MARKERS = ["TODO", "FIXME", "TBD", "INSERT_HERE", "YOUR_VALUE_HERE"]
STALE_COMMANDS = [
    "phase6ctl.py preflight",
    "--trusted-public-key",
    "phase6ctl.py add-evidence --run-dir \"$RUN_DIR\" --file evidence-record.json\n",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_manifest_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts and bool(path.parts)


def validate_manifest(root: Path, errors: list[str]) -> None:
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        errors.append("MANIFEST.sha256 missing")
        return
    entries: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-f0-9]{64})  (.+)", line)
        if not match:
            errors.append(f"invalid MANIFEST.sha256 line {line_number}")
            continue
        digest, relative = match.groups()
        relative = relative.removeprefix("./")
        if not safe_manifest_path(relative):
            errors.append(f"unsafe manifest path: {relative}")
            continue
        if relative in entries:
            errors.append(f"duplicate manifest path: {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256" and "__pycache__" not in path.parts
    }
    listed = set(entries)
    for relative in sorted(actual - listed):
        errors.append(f"file missing from manifest: {relative}")
    for relative in sorted(listed - actual):
        errors.append(f"manifest references missing file: {relative}")
    for relative in sorted(actual & listed):
        if sha256_file(root / relative) != entries[relative]:
            errors.append(f"manifest digest mismatch: {relative}")


def validate_policy(root: Path, errors: list[str]) -> None:
    policy_path = root / "references/GO_NO_GO_POLICY.yaml"
    try:
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid GO/NO-GO policy YAML: {exc}")
        return
    if not isinstance(policy, dict) or policy.get("schema") != "l9.deploy.phase6-policy/v3":
        errors.append("GO/NO-GO policy schema mismatch")
        return
    checks = policy.get("checks")
    if not isinstance(checks, dict) or len(checks) != 18:
        errors.append("GO/NO-GO policy must define exactly 18 checks")
        return
    external_count = 0
    for check_id, spec in checks.items():
        if not isinstance(spec, dict) or not re.fullmatch(r"[a-z][a-z0-9_]+", str(check_id)):
            errors.append(f"invalid policy check: {check_id}")
            continue
        if spec.get("source") in {"config", "derived"}:
            continue
        external_count += 1
        required = {"scenario", "evidence_class", "assertions", "allowed_sources", "producer_id", "producer_script", "locator_pattern", "artifact_requirements"}
        missing = sorted(required - set(spec))
        if missing:
            errors.append(f"policy check {check_id} missing: {', '.join(missing)}")
            continue
        allowed = spec.get("allowed_sources")
        if not isinstance(allowed, list) or not allowed or "derived" in allowed or "synthetic_test" in allowed:
            errors.append(f"policy check {check_id} has unsafe live source configuration")
        producer = root / str(spec.get("producer_script"))
        if not producer.is_file():
            errors.append(f"policy producer missing for {check_id}: {spec.get('producer_script')}")
        try:
            re.compile(str(spec.get("locator_pattern")))
        except re.error as exc:
            errors.append(f"invalid locator pattern for {check_id}: {exc}")
        requirements = spec.get("artifact_requirements")
        if not isinstance(requirements, dict) or int(requirements.get("min_items", 0)) < 1:
            errors.append(f"policy check {check_id} does not require proof artifacts")
        roles = requirements.get("required_roles", []) if isinstance(requirements, dict) else []
        if not isinstance(roles, list) or not roles:
            errors.append(f"policy check {check_id} has no required artifact roles")
        elif len(set(roles)) != len(roles):
            errors.append(f"policy check {check_id} has duplicate artifact roles")
        elif int(requirements.get("min_items", 0)) < len(roles):
            errors.append(f"policy check {check_id} min_items is smaller than its required role count")
    if external_count != 15:
        errors.append(f"expected 15 external evidence checks, observed {external_count}")
    terminal = policy.get("immediate_no_go")
    if not isinstance(terminal, dict) or len(terminal) < 6:
        errors.append("immediate_no_go must contain at least six executable rules")
    else:
        for rule_id, rule in terminal.items():
            conditions = rule.get("conditions") if isinstance(rule, dict) else None
            if not isinstance(conditions, list) or not conditions:
                errors.append(f"immediate NO-GO rule {rule_id} has no conditions")
                continue
            for condition in conditions:
                if not isinstance(condition, dict) or condition.get("source") not in {"record", "config"} or not condition.get("path") or "equals" not in condition:
                    errors.append(f"immediate NO-GO rule {rule_id} has a non-executable condition")


def validate_schemas(root: Path, errors: list[str]) -> None:
    evidence_schemas = list((root / "schemas").glob("*-evidence.schema.json"))
    if len(evidence_schemas) != 9:
        errors.append(f"expected 9 evidence-class schemas, observed {len(evidence_schemas)}")
    for path in sorted((root / "schemas").glob("*.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            errors.append(f"invalid JSON Schema {path.relative_to(root)}: {exc}")
            continue
        if path.name.endswith("-evidence.schema.json"):
            required = set(schema.get("required", []))
            for field in {"run_binding", "artifacts", "attestation"} - required:
                errors.append(f"{path.name} does not require {field}")
            artifacts = schema.get("properties", {}).get("artifacts", {})
            if int(artifacts.get("minItems", 0)) < 1:
                errors.append(f"{path.name} permits empty proof artifacts")
            kind = schema.get("properties", {}).get("source", {}).get("properties", {}).get("kind", {})
            if "derived" in kind.get("enum", []):
                errors.append(f"{path.name} permits derived live evidence")


def validate_host_health_schema(root: Path, errors: list[str]) -> None:
    path = root / "schemas/host-health.schema.json"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        errors.append(f"invalid host-health schema: {exc}")
        return
    required = set(schema.get("required", []))
    expected = {
        "repository", "commit_sha", "environment", "workflow_run_id", "artifact_id",
        "health", "active_image_digest", "active_config_identity", "base_url",
        "health_path", "http_status", "checked_at", "production_contact",
    }
    missing = sorted(expected - required)
    if missing:
        errors.append("host-health schema missing required bindings: " + ", ".join(missing))


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    present = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    missing = sorted(REQUIRED - present)
    if missing:
        errors.append("missing required files: " + ", ".join(missing))
    if (root / "agents").exists():
        errors.append("agents/ folder is forbidden")
    if any(path.is_symlink() for path in root.rglob("*")):
        errors.append("symbolic links are forbidden in the portable pack")
    if any(path.is_dir() and path.name == "__pycache__" for path in root.rglob("__pycache__")):
        errors.append("__pycache__ directories are forbidden")

    skill = (root / "SKILL.md").read_text(encoding="utf-8") if (root / "SKILL.md").exists() else ""
    if not skill.startswith("---\n"):
        errors.append("SKILL.md frontmatter missing")
    for required in ["name: l9-deploy-phase6-operator", "description:", "skill_schema: 1", "role: skill_entrypoint"]:
        if required not in skill:
            errors.append(f"SKILL.md metadata missing: {required}")
    for reference in sorted((root / "references").glob("*")):
        if reference.is_file() and reference.name not in skill:
            errors.append(f"reference not linked from SKILL.md: references/{reference.name}")

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if path.name in FORBIDDEN_NAMES or (path.suffix == ".pem" and "public" not in path.name):
            errors.append(f"forbidden file: {relative}")
        if path.stat().st_size == 0:
            errors.append(f"empty file: {relative}")
        if path.suffix.lower() in {".md", ".py", ".sh", ".yaml", ".yml", ".json"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.name != "validate_pack.py":
                for marker in FORBIDDEN_MARKERS:
                    if re.search(rf"\b{re.escape(marker)}\b", text):
                        errors.append(f"unfinished marker {marker}: {relative}")
            if path.suffix == ".json":
                try:
                    json.loads(text)
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid JSON {relative}: {exc}")
    doc_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [root / "README.md", root / "SKILL.md", root / "AGENT_EXECUTION_PROMPT.md", root / "references/LIVE_COMMANDS.md", root / "references/PREFLIGHT.md"]
        if path.is_file()
    )
    for stale in STALE_COMMANDS:
        if stale in doc_text:
            errors.append(f"stale operator command remains: {stale!r}")

    validate_policy(root, errors)
    validate_schemas(root, errors)
    validate_host_health_schema(root, errors)
    validate_manifest(root, errors)
    result = {"status": "PASS" if not errors else "FAIL", "file_count": len(present), "errors": sorted(set(errors))}
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
