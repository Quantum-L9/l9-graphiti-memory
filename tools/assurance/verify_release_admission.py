#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/verify_release_admission.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-15

"""Refuse publication unless an admission receipt binds this exact release.

ADR-094 makes release admission an explicit authority decision bound to the
exact frozen candidate subject set: PACKAGE_VERSION, source revision, wheel
sha256 and sdist sha256. The release binding states that publication requires
it and that published digests equal admitted digests. The decision is recorded
as ``docs/receipts/l9-memory-release-<version>.md`` (the 2.6.0 receipt is the
established form) and takes effect when it merges to the protected default
branch. This tool only reads that record; it never makes or infers a decision.

Publication passes only when every one of these holds:

* the release tag is exactly ``v<version>``;
* the receipt exists, parses, and names each coordinate exactly once;
* ``Package`` is ``l9-graphite-memory <version>``;
* ``Admitted source`` is the 40-hex revision being published;
* the artifact directory holds exactly one wheel and one sdist and nothing
  else, and each file name and sha256 equals the receipt's.

Anything missing, malformed, duplicated or different fails closed. On failure
the observed tuple is printed so an authority can review it; printing it
admits nothing. Read-only: exit 0 only on an exact match.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

DISTRIBUTION = "l9-graphite-memory"
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")
REQUIRED = ("Package", "Admitted source", "Wheel", "Wheel sha256", "Sdist", "Sdist sha256")


def parse_receipt(text: str) -> tuple[dict[str, str], list[str]]:
    """Coordinate rows of the receipt table, backticks removed; duplicates fail."""

    rows: dict[str, str] = {}
    failures: list[str] = []
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if match is None:
            continue
        key, value = match.group(1).strip(), match.group(2).replace("`", " ").strip()
        if key in {"Coordinate", "---"} or set(key) <= {"-", ":", " "}:
            continue
        if key in rows:
            failures.append(f"receipt names {key!r} more than once")
        rows[key] = " ".join(value.split())
    failures += [f"receipt does not name {key!r}" for key in REQUIRED if not rows.get(key)]
    return rows, failures


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifacts(artifact_dir: Path) -> tuple[Path | None, Path | None, list[str]]:
    if not artifact_dir.is_dir():
        return None, None, [f"artifact directory does not exist: {artifact_dir}"]
    entries = sorted(artifact_dir.iterdir())
    wheels = [p for p in entries if p.is_file() and p.name.endswith(".whl")]
    sdists = [p for p in entries if p.is_file() and p.name.endswith(".tar.gz")]
    failures = [
        f"artifact directory holds an unadmitted entry: {p.name}"
        for p in entries
        if p not in wheels and p not in sdists
    ]
    if len(wheels) != 1:
        failures.append(f"exactly one wheel is required, found {len(wheels)}")
    if len(sdists) != 1:
        failures.append(f"exactly one sdist is required, found {len(sdists)}")
    wheel = wheels[0] if len(wheels) == 1 else None
    sdist = sdists[0] if len(sdists) == 1 else None
    return wheel, sdist, failures


def verify(
    receipt: Path, artifact_dir: Path, version: str, source_revision: str, tag: str
) -> tuple[list[str], dict[str, str]]:
    """Return (failures, observed tuple); no failures means an exact admitted match."""

    failures: list[str] = []
    observed = {"version": version, "source revision": source_revision, "tag": tag}
    if tag != f"v{version}":
        failures.append(f"release tag {tag!r} is not v{version}")
    if not SHA.match(source_revision):
        failures.append(f"source revision is not a 40-hex commit: {source_revision!r}")
    wheel, sdist, artifact_failures = _artifacts(artifact_dir)
    failures += artifact_failures
    for label, path in (("wheel", wheel), ("sdist", sdist)):
        if path is not None:
            observed[label] = path.name
            observed[f"{label} sha256"] = _sha256(path)
    if not receipt.is_file():
        return [*failures, f"no release admission receipt at {receipt}"], observed
    rows, receipt_failures = parse_receipt(receipt.read_text(encoding="utf-8"))
    failures += receipt_failures
    if receipt_failures:
        return failures, observed
    if rows["Package"] != f"{DISTRIBUTION} {version}":
        failures.append(f"receipt admits {rows['Package']!r}, not {DISTRIBUTION} {version}")
    if rows["Admitted source"] != source_revision:
        failures.append(
            f"receipt admits source {rows['Admitted source']!r}, not {source_revision!r}"
        )
    for label, name_key, digest_key in (
        ("wheel", "Wheel", "Wheel sha256"),
        ("sdist", "Sdist", "Sdist sha256"),
    ):
        if not DIGEST.match(rows[digest_key]):
            failures.append(f"receipt {digest_key} is not a sha256 digest: {rows[digest_key]!r}")
        if label not in observed:
            continue
        if rows[name_key] != observed[label]:
            failures.append(f"receipt admits {label} {rows[name_key]!r}, not {observed[label]!r}")
        if rows[digest_key] != observed[f"{label} sha256"]:
            failures.append(
                f"{label} sha256 {observed[f'{label} sha256']} is not the admitted"
                f" {rows[digest_key]}"
            )
    return failures, observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    failures, observed = verify(
        args.receipt, args.artifact_dir, args.version, args.source_revision, args.tag
    )
    if failures:
        sys.stdout.write("".join(f"FAIL: {failure}\n" for failure in failures))
        sys.stdout.write("observed release (admits nothing):\n")
        sys.stdout.write("".join(f"  {key}: {value}\n" for key, value in observed.items()))
        return 1
    sys.stdout.write(
        f"PASS: {args.receipt} admits {DISTRIBUTION} {args.version} at {args.source_revision}"
        f" with wheel {observed['wheel sha256']} and sdist {observed['sdist sha256']}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
