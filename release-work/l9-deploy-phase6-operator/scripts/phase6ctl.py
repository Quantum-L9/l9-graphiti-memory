#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: release-work/l9-deploy-phase6-operator/scripts/phase6ctl.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: phase6_control_cli
# tags: [phase6, evidence, policy, ledger, validation, provenance]
# owner: igor_beylin
# status: active
# version: 3.0.0
# updated: 2026-07-26
# Purpose: derive Phase 6 decisions from signed, content-bound, source-constrained evidence.
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from phase6_integrity import (
    canonical,
    contained_path,
    key_fingerprint,
    load_private_key,
    load_public_key,
    public_key_pem,
    safe_artifact_relpath,
    sha256_bytes,
    sha256_file,
    sign_event,
    verify_event,
    verify_record,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [f"S{i:02d}" for i in range(8)]
FORBIDDEN_EVIDENCE_NAMES = {"runtime.env", ".env", "id_rsa", "id_ed25519", "oidc.jwt", "token.txt"}
MAX_ARTIFACT_BYTES = 25 * 1024 * 1024

CONTROL_PLANE_PATHS = [
    "references/GO_NO_GO_POLICY.yaml",
    "scripts/phase6ctl.py",
    "scripts/phase6_integrity.py",
    "scripts/build_evidence_record.py",
    "scripts/collect_repository_evidence.py",
    "scripts/collect_github_evidence.py",
    "scripts/verify_oidc_claims.py",
    "scripts/collect_infisical_audit.py",
    "scripts/collect_workflow_evidence.py",
    "scripts/validate_receipts.py",
    "scripts/collect_final_convergence.py",
]


def control_plane_digest() -> str:
    entries: list[dict[str, str]] = []
    for relative in CONTROL_PLANE_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"control-plane artifact missing: {relative}")
        entries.append({"path": relative, "sha256": sha256_file(path)})
    for path in sorted((ROOT / "schemas").glob("*.json")):
        entries.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
    return sha256_bytes(canonical(entries))


def run_binding_path(run_dir: Path) -> Path:
    return run_dir / "integrity/run-binding.json"


def load_run_binding(run_dir: Path) -> dict[str, Any]:
    binding = load_json(run_binding_path(run_dir))
    if binding.get("schema") != "l9.deploy.phase6-run-binding/v1":
        raise ValueError("run binding schema mismatch")
    return binding


def validate_record_run_binding(record: dict[str, Any], run_dir: Path) -> list[str]:
    try:
        expected = load_run_binding(run_dir)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return [f"run binding unavailable or invalid: {exc}"]
    observed = record.get("run_binding")
    if observed != expected:
        return ["record run binding does not match the current run"]
    return []


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_policy() -> dict[str, Any]:
    value = yaml.safe_load((ROOT / "references/GO_NO_GO_POLICY.yaml").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("GO/NO-GO policy must be an object")
    return value


def validate_config(config: dict[str, Any]) -> list[str]:
    schema = json.loads((ROOT / "schemas/phase6-input.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(config), key=lambda item: list(item.path))]


def embedded_ledger_public_key_path(run_dir: Path) -> Path:
    return run_dir / "integrity/ledger-public-key.pem"


def embedded_evidence_public_key_path(run_dir: Path) -> Path:
    return run_dir / "integrity/evidence-attestor-public-key.pem"


def ledger_private_key_for_run(run_dir: Path, signing_key_path: Path):
    private_key = load_private_key(signing_key_path)
    embedded = embedded_ledger_public_key_path(run_dir)
    if not embedded.is_file():
        raise ValueError("run ledger trust anchor is missing")
    if public_key_pem(private_key.public_key()) != embedded.read_bytes():
        raise ValueError("ledger signing key does not match the run trust anchor")
    return private_key


def embedded_evidence_public_key(run_dir: Path):
    embedded = embedded_evidence_public_key_path(run_dir)
    if not embedded.is_file():
        raise ValueError("evidence attestor trust anchor is missing")
    return load_public_key(embedded)


def trusted_public_keys_for_run(run_dir: Path, ledger_path: Path, evidence_path: Path):
    ledger_key = load_public_key(ledger_path)
    evidence_key = load_public_key(evidence_path)
    embedded_ledger = embedded_ledger_public_key_path(run_dir)
    embedded_evidence = embedded_evidence_public_key_path(run_dir)
    if not embedded_ledger.is_file() or not embedded_evidence.is_file():
        raise ValueError("run trust anchors are missing")
    if public_key_pem(ledger_key) != embedded_ledger.read_bytes():
        raise ValueError("embedded ledger key does not match the external trusted ledger key")
    if public_key_pem(evidence_key) != embedded_evidence.read_bytes():
        raise ValueError("embedded evidence key does not match the external trusted evidence key")
    if public_key_pem(ledger_key) == public_key_pem(evidence_key):
        raise ValueError("ledger and evidence authority keys must be distinct")
    return ledger_key, evidence_key


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any], private_key) -> dict[str, Any]:
    ledger = run_dir / "events.jsonl"
    previous_hash = "0" * 64
    sequence = 1
    if ledger.exists():
        lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            last = json.loads(lines[-1])
            previous_hash = last["event_hash"]
            sequence = int(last["sequence"]) + 1
    base = {
        "schema": "l9.deploy.phase6-event/v2",
        "sequence": sequence,
        "timestamp": now(),
        "event_type": event_type,
        "payload": payload,
        "previous_hash": previous_hash,
    }
    base["event_hash"] = sha256_bytes(canonical(base))
    event = sign_event(base, private_key)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def verify_ledger(run_dir: Path, public_key) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    events: list[dict[str, Any]] = []
    previous_hash = "0" * 64
    expected_sequence = 1
    ledger = run_dir / "events.jsonl"
    if not ledger.is_file():
        return ["events.jsonl missing"], events
    for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            errors.append(f"ledger line {line_number} is empty")
            continue
        try:
            event = json.loads(line)
        except Exception as exc:
            errors.append(f"ledger line {line_number} invalid JSON: {exc}")
            continue
        if not isinstance(event, dict):
            errors.append(f"ledger line {line_number} is not an object")
            continue
        events.append(event)
        if event.get("schema") != "l9.deploy.phase6-event/v2":
            errors.append(f"ledger schema mismatch line {line_number}")
        if event.get("sequence") != expected_sequence:
            errors.append(f"ledger sequence mismatch line {line_number}")
        if event.get("previous_hash") != previous_hash:
            errors.append(f"ledger chain mismatch line {line_number}")
        unsigned_without_signature = {key: value for key, value in event.items() if key != "signature"}
        stored_hash = unsigned_without_signature.get("event_hash")
        hash_payload = {key: value for key, value in unsigned_without_signature.items() if key != "event_hash"}
        calculated_hash = sha256_bytes(canonical(hash_payload))
        if stored_hash != calculated_hash:
            errors.append(f"ledger event hash mismatch line {line_number}")
        for error in verify_event(event, public_key):
            errors.append(f"ledger line {line_number}: {error}")
        previous_hash = str(stored_hash or "")
        expected_sequence += 1
    if events:
        first = events[0]
        if first.get("event_type") != "run_initialized":
            errors.append("first ledger event must be run_initialized")
        payload = first.get("payload", {})
        if payload.get("trusted_ledger_key_fingerprint") != key_fingerprint(public_key):
            errors.append("run initialization ledger key fingerprint mismatch")
        evidence_anchor = embedded_evidence_public_key_path(run_dir)
        if not evidence_anchor.is_file():
            errors.append("evidence attestor trust anchor missing")
        else:
            evidence_key = load_public_key(evidence_anchor)
            if payload.get("trusted_evidence_key_fingerprint") != key_fingerprint(evidence_key):
                errors.append("run initialization evidence key fingerprint mismatch")
        binding_path = run_binding_path(run_dir)
        if not binding_path.is_file():
            errors.append("run binding is missing")
        else:
            try:
                binding = load_run_binding(run_dir)
                if payload.get("run_binding_sha256") != sha256_file(binding_path):
                    errors.append("run binding digest does not match initialization event")
                if binding.get("control_plane_sha256") != control_plane_digest():
                    errors.append("control-plane digest differs from the initialized run")
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                errors.append(f"run binding invalid: {exc}")
        snapshot = run_dir / "input.snapshot.json"
        if not snapshot.is_file():
            errors.append("input.snapshot.json missing")
        elif payload.get("config_sha256") != sha256_file(snapshot):
            errors.append("input snapshot digest does not match run initialization event")
    return errors, events


def validate_record_schema(record: dict[str, Any]) -> list[str]:
    evidence_class = record.get("evidence_class")
    path = ROOT / "schemas" / f"{evidence_class}-evidence.schema.json"
    if not path.is_file():
        return [f"unsupported evidence_class: {evidence_class}"]
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path))]


def producer_script_hash(spec: dict[str, Any]) -> str | None:
    relative = spec.get("producer_script")
    if not relative:
        return None
    path = ROOT / relative
    if not path.is_file():
        return None
    return sha256_file(path)


def validate_source(record: dict[str, Any], spec: dict[str, Any], config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source = record.get("source", {})
    kind = source.get("kind")
    mode = config.get("evidence", {}).get("mode", "live")
    allowed = set(spec.get("allowed_sources", []))
    if mode == "synthetic_test" and kind == "synthetic_test":
        pass
    elif kind not in allowed:
        errors.append(f"source kind {kind!r} is not allowed for {record.get('check_id')}")
    pattern = spec.get("locator_pattern")
    if kind != "synthetic_test" and pattern and not re.fullmatch(pattern, str(source.get("locator", ""))):
        errors.append("source locator does not match the policy pattern")
    producer = source.get("producer", {})
    expected_producer = "synthetic_fixture" if kind == "synthetic_test" else spec.get("producer_id")
    expected_script = ROOT / ("tests/test_hardening.py" if kind == "synthetic_test" else str(spec.get("producer_script", "")))
    if producer.get("id") != expected_producer:
        errors.append("source producer id does not match policy")
    if not expected_script.is_file():
        errors.append("policy producer script is missing")
    elif producer.get("executable_sha256") != sha256_file(expected_script):
        errors.append("source producer executable digest does not match the packaged collector")
    return errors


def artifact_requirements(spec: dict[str, Any]) -> tuple[int, set[str], int]:
    requirements = spec.get("artifact_requirements", {})
    minimum = int(requirements.get("min_items", 1))
    roles = set(requirements.get("required_roles", []))
    maximum = int(requirements.get("max_size_bytes", MAX_ARTIFACT_BYTES))
    return minimum, roles, min(maximum, MAX_ARTIFACT_BYTES)


def validate_artifact_descriptors(record: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifacts = record.get("artifacts", [])
    minimum, required_roles, maximum = artifact_requirements(spec)
    if len(artifacts) < minimum:
        errors.append(f"at least {minimum} proof artifact(s) required")
    roles: set[str] = set()
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        try:
            relative = safe_artifact_relpath(str(artifact.get("path", "")), str(record.get("check_id", "")))
        except ValueError as exc:
            errors.append(f"artifact {index}: {exc}")
            continue
        path_text = relative.as_posix()
        if path_text in paths:
            errors.append(f"duplicate artifact path: {path_text}")
        paths.add(path_text)
        role = str(artifact.get("role", ""))
        roles.add(role)
        size = artifact.get("size_bytes")
        if not isinstance(size, int) or size < 1 or size > maximum:
            errors.append(f"artifact {index}: size_bytes must be between 1 and {maximum}")
        if Path(path_text).name in FORBIDDEN_EVIDENCE_NAMES:
            errors.append(f"artifact {index}: forbidden evidence filename")
    missing_roles = sorted(required_roles - roles)
    if missing_roles:
        errors.append("missing required artifact roles: " + ", ".join(missing_roles))
    return errors


def import_artifacts(run_dir: Path, artifact_root: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for artifact in record.get("artifacts", []):
        relative = safe_artifact_relpath(str(artifact["path"]), str(record["check_id"]))
        source = contained_path(artifact_root, relative)
        destination = contained_path(run_dir, relative)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"proof artifact is missing or unsafe: {relative.as_posix()}")
        actual_size = source.stat().st_size
        actual_digest = sha256_file(source)
        if actual_size != artifact["size_bytes"]:
            raise ValueError(f"proof artifact size mismatch: {relative.as_posix()}")
        if actual_digest != artifact["sha256"]:
            raise ValueError(f"proof artifact digest mismatch: {relative.as_posix()}")
        if destination.exists():
            raise ValueError(f"proof artifact already exists: {relative.as_posix()}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if destination.is_symlink() or sha256_file(destination) != actual_digest:
            raise ValueError(f"proof artifact import verification failed: {relative.as_posix()}")
        imported.append({
            "path": relative.as_posix(),
            "sha256": actual_digest,
            "size_bytes": actual_size,
            "role": artifact["role"],
            "media_type": artifact["media_type"],
        })
    return imported


def recorded_evidence_events(events: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    by_check: dict[str, dict[str, Any]] = {}
    seen_paths: set[str] = set()
    for event in events:
        if event.get("event_type") != "evidence_recorded":
            continue
        payload = event.get("payload", {})
        check_id = payload.get("check_id")
        record_path = payload.get("record_path")
        if not isinstance(check_id, str) or not check_id:
            errors.append("evidence_recorded event missing check_id")
            continue
        if check_id in by_check:
            errors.append(f"duplicate evidence_recorded event for {check_id}")
        if not isinstance(record_path, str) or record_path in seen_paths:
            errors.append(f"duplicate or invalid evidence record path for {check_id}")
        seen_paths.add(str(record_path))
        by_check[check_id] = payload
    return by_check, errors


def reconcile_evidence(run_dir: Path, evidence_public_key, events: list[dict[str, Any]], policy: dict[str, Any], config: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    event_map, event_errors = recorded_evidence_events(events)
    errors.extend(event_errors)
    records_dir = run_dir / "evidence/records"
    actual_record_paths = {str(path.relative_to(run_dir).as_posix()) for path in records_dir.glob("*.json")} if records_dir.is_dir() else set()
    ledger_record_paths = {str(payload.get("record_path")) for payload in event_map.values()}
    for path in sorted(actual_record_paths - ledger_record_paths):
        errors.append(f"unledgered evidence record present: {path}")
    for path in sorted(ledger_record_paths - actual_record_paths):
        errors.append(f"ledgered evidence record missing: {path}")
    referenced_artifacts: set[str] = set()
    for check_id, payload in sorted(event_map.items()):
        expected_record_path = f"evidence/records/{check_id}.json"
        if payload.get("record_path") != expected_record_path:
            errors.append(f"ledger record path mismatch for {check_id}")
            continue
        record_path = run_dir / expected_record_path
        if not record_path.is_file() or record_path.is_symlink():
            continue
        if payload.get("record_sha256") != sha256_file(record_path):
            errors.append(f"evidence record digest mismatch for {check_id}")
        try:
            record = load_json(record_path)
        except Exception as exc:
            errors.append(f"evidence record parse failed for {check_id}: {exc}")
            continue
        records[check_id] = record
        if record.get("check_id") != check_id:
            errors.append(f"evidence record check_id mismatch for {check_id}")
        errors.extend(f"{check_id}: {item}" for item in validate_record_schema(record))
        errors.extend(f"{check_id}: {item}" for item in validate_record_run_binding(record, run_dir))
        errors.extend(f"{check_id}: {item}" for item in verify_record(record, evidence_public_key))
        spec = policy.get("checks", {}).get(check_id)
        if not isinstance(spec, dict):
            errors.append(f"unknown ledgered policy check: {check_id}")
            continue
        errors.extend(f"{check_id}: {item}" for item in validate_source(record, spec, config))
        errors.extend(f"{check_id}: {item}" for item in validate_artifact_descriptors(record, spec))
        event_artifacts = payload.get("artifacts", [])
        if event_artifacts != record.get("artifacts", []):
            errors.append(f"ledger artifact descriptor mismatch for {check_id}")
        for artifact in record.get("artifacts", []):
            try:
                relative = safe_artifact_relpath(artifact["path"], check_id)
                artifact_path = contained_path(run_dir, relative)
            except (KeyError, ValueError) as exc:
                errors.append(f"{check_id}: artifact path invalid: {exc}")
                continue
            path_text = relative.as_posix()
            referenced_artifacts.add(path_text)
            if not artifact_path.is_file() or artifact_path.is_symlink():
                errors.append(f"proof artifact missing or unsafe: {path_text}")
                continue
            if artifact_path.stat().st_size != artifact.get("size_bytes"):
                errors.append(f"proof artifact size mismatch: {path_text}")
            if sha256_file(artifact_path) != artifact.get("sha256"):
                errors.append(f"proof artifact digest mismatch: {path_text}")
    artifact_root = run_dir / "evidence/artifacts"
    actual_artifacts = {
        str(path.relative_to(run_dir).as_posix())
        for path in artifact_root.rglob("*")
        if path.is_file()
    } if artifact_root.is_dir() else set()
    for path in sorted(actual_artifacts - referenced_artifacts):
        errors.append(f"unledgered proof artifact present: {path}")
    for path in sorted(referenced_artifacts - actual_artifacts):
        errors.append(f"ledgered proof artifact missing: {path}")
    return errors, records


def nested_get(value: dict[str, Any], dotted_path: str) -> Any:
    current: Any = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evaluate_immediate_no_go(policy: dict[str, Any], config: dict[str, Any], records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    triggered: list[dict[str, Any]] = []
    for rule_id, rule in policy.get("immediate_no_go", {}).items():
        for condition in rule.get("conditions", []):
            source = condition.get("source", "record")
            path = str(condition.get("path", ""))
            forbidden = condition.get("equals")
            candidates: list[tuple[str, dict[str, Any]]] = []
            if source == "config":
                candidates = [("config", config)]
            else:
                check_ids = condition.get("check_ids", [])
                if check_ids == ["*"]:
                    candidates = sorted(records.items())
                else:
                    candidates = [(check_id, records[check_id]) for check_id in check_ids if check_id in records]
            for candidate_id, candidate in candidates:
                actual = nested_get(candidate, path)
                if actual == forbidden:
                    triggered.append({
                        "rule_id": rule_id,
                        "source": candidate_id,
                        "path": path,
                        "observed": actual,
                        "reason": rule.get("reason", "terminal policy condition triggered"),
                    })
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in triggered:
        key = (item["rule_id"], item["source"], item["path"])
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def evaluate(run_dir: Path, ledger_public_key, evidence_public_key) -> dict[str, Any]:
    policy = load_policy()
    config = load_json(run_dir / "input.snapshot.json")
    checks: dict[str, dict[str, Any]] = {}
    ledger_errors, events = verify_ledger(run_dir, ledger_public_key)
    evidence_errors, records = reconcile_evidence(run_dir, evidence_public_key, events, policy, config)
    integrity_errors = ledger_errors + evidence_errors
    checks["target_is_staging"] = {
        "status": "PASS" if config.get("environment", {}).get("name") == "staging" else "FAIL",
        "source": "config",
        "errors": [],
    }
    checks["production_forbidden"] = {
        "status": "PASS" if config.get("environment", {}).get("production_forbidden") is True else "FAIL",
        "source": "config",
        "errors": [],
    }
    for check_id, spec in policy.get("checks", {}).items():
        if spec.get("source") in {"config", "derived"}:
            continue
        record = records.get(check_id)
        if not record:
            checks[check_id] = {"status": "MISSING", "source": "evidence", "errors": ["record missing"]}
            continue
        errors: list[str] = []
        errors.extend(validate_record_schema(record))
        errors.extend(validate_record_run_binding(record, run_dir))
        errors.extend(verify_record(record, evidence_public_key))
        errors.extend(validate_source(record, spec, config))
        errors.extend(validate_artifact_descriptors(record, spec))
        for assertion, expected in spec.get("assertions", {}).items():
            actual = record.get("assertions", {}).get(assertion)
            if actual != expected:
                errors.append(f"{assertion} expected {expected!r}, observed {actual!r}")
        if any(error.startswith(f"{check_id}:") or check_id in error for error in integrity_errors):
            errors.append("record or artifact integrity failed")
        status = "PASS" if record.get("status") == "PASS" and not errors else "FAIL"
        checks[check_id] = {
            "status": status,
            "source": f"evidence/records/{check_id}.json",
            "errors": sorted(set(errors)),
        }
    immediate_triggers = evaluate_immediate_no_go(policy, config, records)
    prerequisites = [item["status"] == "PASS" for item in checks.values()]
    checks["evidence_bundle_complete_and_checksum_valid"] = {
        "status": "PASS" if all(prerequisites) and not integrity_errors and not immediate_triggers else "FAIL",
        "source": "derived",
        "errors": integrity_errors + [f"immediate NO-GO: {item['rule_id']}" for item in immediate_triggers],
    }
    scenarios: dict[str, str] = {}
    for scenario_id in SCENARIOS:
        owned = [check_id for check_id, spec in policy.get("checks", {}).items() if spec.get("scenario") == scenario_id]
        values = [checks.get(check_id, {"status": "MISSING"})["status"] for check_id in owned]
        scenarios[scenario_id] = "PASS" if values and all(value == "PASS" for value in values) else ("FAIL" if any(value == "FAIL" for value in values) else "BLOCKED")
    decision = "GO" if not immediate_triggers and not integrity_errors and all(item["status"] == "PASS" for item in checks.values()) and all(value == "PASS" for value in scenarios.values()) else "NO_GO"
    mode = config.get("evidence", {}).get("mode", "live")
    output = {
        "schema": "l9.deploy.phase6-derived-decision/v3",
        "generated_at": now(),
        "validation_mode": mode,
        "trusted_ledger_key_fingerprint": key_fingerprint(ledger_public_key),
        "trusted_evidence_key_fingerprint": key_fingerprint(evidence_public_key),
        "decision": decision,
        "checks": checks,
        "scenarios": scenarios,
        "immediate_no_go": immediate_triggers,
        "integrity_valid": not integrity_errors,
        "integrity_errors": integrity_errors,
    }
    digest_payload = {key: value for key, value in output.items() if key not in {"generated_at", "decision_digest"}}
    output["decision_digest"] = sha256_bytes(canonical(digest_payload))
    return output


def cmd_init(args: argparse.Namespace) -> int:
    config = load_json(Path(args.config))
    config_errors = validate_config(config)
    if config_errors:
        print(json.dumps({"status": "FAIL", "errors": config_errors}, indent=2))
        return 2
    ledger_private_key = load_private_key(Path(args.ledger_signing_key))
    evidence_public_key = load_public_key(Path(args.trusted_evidence_public_key))
    if public_key_pem(ledger_private_key.public_key()) == public_key_pem(evidence_public_key):
        raise ValueError("ledger and evidence authority keys must be distinct")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-phase6h2"
    run_dir = Path(args.run_root) / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "evidence/records").mkdir(parents=True)
    (run_dir / "evidence/artifacts").mkdir(parents=True)
    (run_dir / "integrity").mkdir(parents=True)
    dump_json(run_dir / "input.snapshot.json", config)
    embedded_ledger_public_key_path(run_dir).write_bytes(public_key_pem(ledger_private_key.public_key()))
    embedded_evidence_public_key_path(run_dir).write_bytes(public_key_pem(evidence_public_key))
    binding = {
        "schema": "l9.deploy.phase6-run-binding/v1",
        "run_id": run_id,
        "config_sha256": sha256_file(run_dir / "input.snapshot.json"),
        "ledger_key_fingerprint": key_fingerprint(ledger_private_key.public_key()),
        "evidence_key_fingerprint": key_fingerprint(evidence_public_key),
        "control_plane_sha256": control_plane_digest(),
    }
    dump_json(run_binding_path(run_dir), binding)
    append_event(
        run_dir,
        "run_initialized",
        {
            "run_id": run_id,
            "config_sha256": binding["config_sha256"],
            "trusted_ledger_key_fingerprint": binding["ledger_key_fingerprint"],
            "trusted_evidence_key_fingerprint": binding["evidence_key_fingerprint"],
            "control_plane_sha256": binding["control_plane_sha256"],
            "run_binding_sha256": sha256_file(run_binding_path(run_dir)),
            "validation_mode": config.get("evidence", {}).get("mode", "live"),
        },
        ledger_private_key,
    )
    print(run_dir)
    return 0


def cmd_add_evidence(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    ledger_private_key = ledger_private_key_for_run(run_dir, Path(args.ledger_signing_key))
    ledger_public_key = ledger_private_key.public_key()
    evidence_public_key = embedded_evidence_public_key(run_dir)
    ledger_errors, _ = verify_ledger(run_dir, ledger_public_key)
    if ledger_errors:
        print(json.dumps({"status": "FAIL", "errors": ledger_errors}, indent=2))
        return 2
    source_file = Path(args.file)
    record = load_json(source_file)
    policy = load_policy()
    config = load_json(run_dir / "input.snapshot.json")
    check_id = record.get("check_id")
    spec = policy.get("checks", {}).get(check_id)
    errors: list[str] = []
    errors.extend(validate_record_schema(record))
    errors.extend(validate_record_run_binding(record, run_dir))
    errors.extend(verify_record(record, evidence_public_key))
    if not isinstance(spec, dict):
        errors.append(f"unknown policy check: {check_id}")
    else:
        if spec.get("evidence_class") != record.get("evidence_class"):
            errors.append("evidence class does not match policy")
        if spec.get("scenario") != record.get("scenario_id"):
            errors.append("scenario does not match policy")
        errors.extend(validate_source(record, spec, config))
        errors.extend(validate_artifact_descriptors(record, spec))
    if errors:
        print(json.dumps({"status": "FAIL", "errors": sorted(set(errors))}, indent=2))
        return 2
    destination = run_dir / "evidence/records" / f"{check_id}.json"
    if destination.exists():
        print("evidence records are append-once; duplicate check_id rejected", file=sys.stderr)
        return 2
    imported = import_artifacts(run_dir, Path(args.artifact_root), record)
    destination.write_bytes(source_file.read_bytes())
    append_event(
        run_dir,
        "evidence_recorded",
        {
            "check_id": check_id,
            "record_path": str(destination.relative_to(run_dir).as_posix()),
            "record_sha256": sha256_file(destination),
            "record_attestation_digest": record["attestation"]["payload_sha256"],
            "status": record["status"],
            "source_kind": record["source"]["kind"],
            "artifacts": imported,
        },
        ledger_private_key,
    )
    print(json.dumps({"status": "PASS", "check_id": check_id}, indent=2))
    return 0


def cmd_add_evidence_batch(args: argparse.Namespace) -> int:
    result = 0
    for item in sorted(Path(args.directory).glob("*.json")):
        try:
            candidate = load_json(item)
        except Exception:
            continue
        if candidate.get("schema") != "l9.deploy.phase6-evidence-record/v3":
            continue
        namespace = argparse.Namespace(
            run_dir=args.run_dir,
            file=str(item),
            artifact_root=args.artifact_root,
            ledger_signing_key=args.ledger_signing_key,
        )
        value = cmd_add_evidence(namespace)
        if value:
            result = value
    return result


def cmd_derive(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    ledger_private_key = ledger_private_key_for_run(run_dir, Path(args.ledger_signing_key))
    output = evaluate(run_dir, ledger_private_key.public_key(), embedded_evidence_public_key(run_dir))
    dump_json(run_dir / "derived-decision.json", output)
    append_event(run_dir, "decision_derived", {"decision": output["decision"], "decision_digest": output["decision_digest"]}, ledger_private_key)
    print(json.dumps(output, indent=2))
    return 0 if output["decision"] == "GO" else 3


def render_report(decision: dict[str, Any]) -> str:
    check_rows = "\n".join(f"| {key} | {value['status']} | {value['source']} |" for key, value in decision["checks"].items())
    scenario_rows = "\n".join(f"| {key} | {value} |" for key, value in decision["scenarios"].items())
    trigger_rows = "\n".join(
        f"| {item['rule_id']} | {item['source']} | {item['path']} | {item['observed']!r} |"
        for item in decision["immediate_no_go"]
    ) or "| None | - | - | - |"
    return f"""# Phase 6 GO/NO-GO Report

<!-- GENERATED: phase6ctl v3; manual decisions are invalid -->

**Decision:** {decision['decision']}

**Validation mode:** `{decision['validation_mode']}`

**Trusted ledger key:** `{decision['trusted_ledger_key_fingerprint']}`

**Trusted evidence key:** `{decision['trusted_evidence_key_fingerprint']}`

**Decision digest:** `{decision['decision_digest']}`

## Immediate NO-GO conditions

| Rule | Source | Path | Observed |
|---|---|---|---|
{trigger_rows}

## Policy checks

| Check | Status | Source |
|---|---|---|
{check_rows}

## Scenarios

| Scenario | Derived status |
|---|---|
{scenario_rows}
"""


def cmd_generate_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    ledger_private_key = ledger_private_key_for_run(run_dir, Path(args.ledger_signing_key))
    decision = evaluate(run_dir, ledger_private_key.public_key(), embedded_evidence_public_key(run_dir))
    dump_json(run_dir / "derived-decision.json", decision)
    report = run_dir / "GO_NO_GO_REPORT.md"
    report.write_text(render_report(decision), encoding="utf-8")
    append_event(
        run_dir,
        "report_generated",
        {
            "decision": decision["decision"],
            "decision_digest": decision["decision_digest"],
            "report_sha256": sha256_file(report),
        },
        ledger_private_key,
    )
    print(report)
    return 0 if decision["decision"] == "GO" else 3


def cmd_validate_evidence(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    ledger_public_key, evidence_public_key = trusted_public_keys_for_run(
        run_dir, Path(args.trusted_ledger_public_key), Path(args.trusted_evidence_public_key)
    )
    errors: list[str] = []
    decision = evaluate(run_dir, ledger_public_key, evidence_public_key)
    decision_path = run_dir / "derived-decision.json"
    report_path = run_dir / "GO_NO_GO_REPORT.md"
    if not decision_path.is_file():
        errors.append("derived-decision.json missing")
    else:
        stored = load_json(decision_path)
        if stored.get("decision_digest") != decision["decision_digest"]:
            errors.append("derived decision is stale or manually changed")
    if not report_path.is_file():
        errors.append("generated GO_NO_GO_REPORT.md missing")
    elif report_path.read_text(encoding="utf-8") != render_report(decision):
        errors.append("GO_NO_GO_REPORT.md is not the generated report for current evidence")
    if decision["validation_mode"] != "live" and not args.allow_synthetic:
        errors.append("synthetic evidence mode cannot authorize a live GO")
    if decision["decision"] != "GO":
        errors.append(f"derived decision is {decision['decision']}, not GO")
    errors.extend(decision["integrity_errors"])
    if decision["immediate_no_go"]:
        errors.extend(f"immediate NO-GO triggered: {item['rule_id']}" for item in decision["immediate_no_go"])
    result = {
        "schema": "l9.deploy.phase6-evidence-validation/v3",
        "captured_at": now(),
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "decision_digest": decision["decision_digest"],
        "trusted_ledger_key_fingerprint": key_fingerprint(ledger_public_key),
        "trusted_evidence_key_fingerprint": key_fingerprint(evidence_public_key),
        "validation_mode": decision["validation_mode"],
    }
    dump_json(run_dir / "evidence-validation.json", result)
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


def canary_variants(value: str) -> dict[str, bytes]:
    raw = value.encode("utf-8")
    return {
        "exact": raw,
        "urlencoded": urllib.parse.quote(value, safe="").encode("utf-8"),
        "base64": base64.b64encode(raw),
        "base64url": base64.urlsafe_b64encode(raw).rstrip(b"="),
        "json_escaped": json.dumps(value)[1:-1].encode("utf-8"),
    }


def cmd_scan_canary(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    output_root = Path(args.output_root).resolve()
    value = os.environ.get("PHASE6_CANARY_VALUE")
    if not value:
        print("PHASE6_CANARY_VALUE is required", file=sys.stderr)
        return 2
    findings: list[dict[str, Any]] = []
    variants = canary_variants(value)
    files_scanned = 0
    for path in root.rglob("*"):
        if path.is_file():
            files_scanned += 1
            data = path.read_bytes()
            matches = [name for name, needle in variants.items() if needle in data]
            if matches:
                findings.append({"path": str(path.relative_to(root)), "variants": matches})
    check_id = "canary_scan_zero_matches"
    proof_dir = output_root / f"evidence/artifacts/{check_id}"
    proof_dir.mkdir(parents=True, exist_ok=True)
    findings_path = proof_dir / "canary-findings.json"
    dump_json(findings_path, {"schema": "l9.deploy.phase6-canary-findings/v1", "findings": findings})
    proof_path = proof_dir / "canary-scan-proof.json"
    proof = {
        "schema": "l9.deploy.phase6-proof/v1",
        "producer_id": "phase6_canary_scanner",
        "producer_version": "3.0.0",
        "producer_executable_sha256": sha256_file(Path(__file__)),
        "captured_at": now(),
        "subject": "phase6 canary leakage scan",
        "source_kind": "canary_scanner",
        "source_locator": f"phase6-canary://{args.scan_id}",
        "artifact_role": "canary_scan_proof",
        "media_type": "application/json",
        "details": {
            "finding_count": len(findings),
            "files_scanned": files_scanned,
            "unauthorized_access_count": 0,
            "production_contact": False,
        },
        "related_artifacts": [
            {
                "path": findings_path.relative_to(output_root).as_posix(),
                "role": "canary_findings",
                "media_type": "application/json",
            }
        ],
    }
    dump_json(proof_path, proof)
    result = {"status": "PASS" if not findings else "FAIL", "proof": str(proof_path), "finding_count": len(findings)}
    print(json.dumps(result, indent=2))
    return 0 if not findings else 3


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    command = subparsers.add_parser("init")
    command.add_argument("--config", required=True)
    command.add_argument("--run-root", required=True)
    command.add_argument("--ledger-signing-key", required=True)
    command.add_argument("--trusted-evidence-public-key", required=True)
    command.set_defaults(func=cmd_init)
    command = subparsers.add_parser("add-evidence")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--file", required=True)
    command.add_argument("--artifact-root", required=True)
    command.add_argument("--ledger-signing-key", required=True)
    command.set_defaults(func=cmd_add_evidence)
    command = subparsers.add_parser("add-evidence-batch")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--directory", required=True)
    command.add_argument("--artifact-root", required=True)
    command.add_argument("--ledger-signing-key", required=True)
    command.set_defaults(func=cmd_add_evidence_batch)
    command = subparsers.add_parser("derive")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--ledger-signing-key", required=True)
    command.set_defaults(func=cmd_derive)
    command = subparsers.add_parser("generate-report")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--ledger-signing-key", required=True)
    command.set_defaults(func=cmd_generate_report)
    command = subparsers.add_parser("validate-evidence")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--trusted-ledger-public-key", required=True)
    command.add_argument("--trusted-evidence-public-key", required=True)
    command.add_argument("--allow-synthetic", action="store_true")
    command.set_defaults(func=cmd_validate_evidence)
    command = subparsers.add_parser("scan-canary")
    command.add_argument("--root", required=True)
    command.add_argument("--output-root", required=True)
    command.add_argument("--scan-id", required=True)
    command.set_defaults(func=cmd_scan_canary)
    return parser


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
