# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/prune.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Compatibility helper for retention reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from l9_graphite_memory.group_resolver import resolve_group
from l9_graphite_memory.runtime import build_runtime, local_principal_for_resolution


def run_prune_report(*, dry_run: bool = True, cwd: Path | None = None) -> dict[str, Any]:
    runtime = build_runtime()
    try:
        resolution = resolve_group(cwd or Path.cwd(), settings=runtime.settings)
        if not resolution.group_id:
            return {
                "error": resolution.error or "namespace unresolved",
                "dry_run": dry_run,
            }
        principal = local_principal_for_resolution(runtime.settings, resolution)
        receipt = runtime.service.prune(principal, resolution.group_id, apply=not dry_run)
        return {
            "namespace": resolution.group_id,
            "dry_run": dry_run,
            "candidate_count": len(receipt.archived_record_ids),
            "record_ids": [str(value) for value in receipt.archived_record_ids],
            "receipt_id": str(receipt.receipt_id),
            "applied": receipt.applied,
        }
    finally:
        runtime.close()
