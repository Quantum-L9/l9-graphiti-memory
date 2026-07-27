#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/phase6/scripts/collect_infisical_audit.py
#   layer: repository
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

# skill_schema: 1
# parent: l9-deploy-phase6-operator
# layer: script
# role: infisical_audit_collector
# tags: [infisical, audit, oidc, evidence, redaction]
# owner: igor_beylin
# status: active
# version: 1.1.0
# updated: 2026-07-26
# Purpose: verify redaction and authorization in an Infisical staging audit export before emitting a bounded proof envelope.
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

from phase6_integrity import sha256_file

REDACTED_VALUES = {None, "", "***", "REDACTED", "[REDACTED]", "<redacted>"}
SENSITIVE_KEYS = {
    "token", "accesstoken", "refreshtoken", "idtoken", "password", "passphrase",
    "secret", "secretvalue", "clientsecret", "privatekey", "apikey", "authorization",
    "cookie", "credentials", "credential", "sessiontoken",
}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def scan_redaction(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if normalized_key(str(key)) in SENSITIVE_KEYS and item not in REDACTED_VALUES:
                findings.append(f"unredacted sensitive field at {child}")
            findings.extend(scan_redaction(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(scan_redaction(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                findings.append(f"secret-shaped value at {path}")
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-export", required=True, type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    value = json.loads(args.audit_export.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("audit export must be an object")
    events = value.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("audit export must contain a non-empty events array")
    if value.get("project_id") not in {None, args.project_id}:
        raise ValueError("audit export project_id does not match the authorized project")
    if value.get("environment") not in {None, "staging"}:
        raise ValueError("audit export is not restricted to staging")
    if value.get("audit_id") not in {None, args.audit_id}:
        raise ValueError("audit export audit_id does not match the requested audit slice")

    redaction_findings = scan_redaction(value)
    if redaction_findings:
        raise ValueError("audit export failed redaction verification: " + "; ".join(redaction_findings[:10]))
    unauthorized = [
        event
        for event in events
        if not isinstance(event, dict)
        or event.get("authorized") is not True
        or event.get("environment") != "staging"
    ]
    check_id = "infisical_audit_review_passed"
    export_copy = args.output_root / f"evidence/artifacts/{check_id}/infisical-audit-export.json"
    export_copy.parent.mkdir(parents=True, exist_ok=True)
    export_copy.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    proof_path = args.output_root / f"evidence/artifacts/{check_id}/infisical-audit-proof.json"
    details = {
        "project_id": args.project_id,
        "environment": "staging",
        "audit_review_clean": not unauthorized,
        "unauthorized_access_count": len(unauthorized),
        "event_count": len(events),
        "redaction_verified": True,
        "audit_export_sha256": sha256_file(export_copy),
        "production_contact": False,
    }
    proof = {
        "schema": "l9.deploy.phase6-proof/v1",
        "producer_id": "collect_infisical_audit",
        "producer_version": "1.1.0",
        "producer_executable_sha256": sha256_file(Path(__file__)),
        "captured_at": now(),
        "subject": "redacted Infisical staging audit export",
        "source_kind": "infisical_audit_collector",
        "source_locator": f"infisical-audit://{args.project_id}/staging/{args.audit_id}",
        "artifact_role": "infisical_audit_proof",
        "media_type": "application/json",
        "details": details,
        "related_artifacts": [
            {"path": export_copy.relative_to(args.output_root).as_posix(), "role": "infisical_audit_export", "media_type": "application/json"}
        ],
    }
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if not unauthorized else "FAIL", "proof": str(proof_path)}, indent=2))
    return 0 if not unauthorized else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
