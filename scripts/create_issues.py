#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: scripts/create_issues.py
#   layer: operations
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

logger = logging.getLogger("l9.create_issues")


def run(args: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the remaining-proof issue set with GitHub CLI"
    )
    parser.add_argument("--repo", default="Quantum-L9/l9-graphiti-memory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--create-labels", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    issues = json.loads((ROOT / "issues.json").read_text(encoding="utf-8"))
    labels = json.loads((ROOT / "labels.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in issues["issues"]}

    if not args.dry_run:
        run(["gh", "auth", "status"])
        run(["gh", "repo", "view", args.repo])

    if args.create_labels:
        for label in labels:
            cmd = [
                "gh",
                "label",
                "create",
                label["name"],
                "--repo",
                args.repo,
                "--color",
                label["color"],
                "--description",
                label["description"],
                "--force",
            ]
            if args.dry_run:
                logger.info("DRY-RUN: %s", " ".join(cmd))
            else:
                run(cmd)

    created: dict[str, str] = {}
    for issue_id in issues["creation_order"]:
        item = by_id[issue_id]
        body_path = ROOT / item["filename"]
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            args.repo,
            "--title",
            item["title"],
            "--body-file",
            str(body_path),
        ]
        for label in item["labels"]:
            cmd += ["--label", label]
        if args.dry_run:
            logger.info("DRY-RUN %s: %s", issue_id, " ".join(cmd))
            continue
        url = run(cmd, capture=True)
        created[issue_id] = url
        logger.info("%s: %s", issue_id, url)

    if not args.dry_run:
        lines = ["# Created Issues", "", f"Repository: `{args.repo}`", ""]
        for issue_id in issues["creation_order"]:
            lines.append(f"- `{issue_id}`: {created[issue_id]}")
        (ROOT / "CREATED_ISSUES.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
