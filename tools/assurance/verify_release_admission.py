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

* the version is a plain ``MAJOR.MINOR.PATCH`` and the release tag is exactly
  ``v<version>``;
* the receipt, located by this tool at
  ``<admission-root>/docs/receipts/l9-memory-release-<version>.md`` and never
  outside ``<admission-root>``, exists, parses, and names each coordinate
  exactly once;
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
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"\d+\.\d+\.\d+")
RECEIPTS = Path("docs") / "receipts"
REQUIRED = ("Package", "Admitted source", "Wheel", "Wheel sha256", "Sdist", "Sdist sha256")


def parse_receipt(text: str) -> tuple[dict[str, str], list[str]]:
    """Coordinate rows of the receipt table, backticks removed; duplicates fail."""

    rows: dict[str, str] = {}
    failures: list[str] = []
    for line in text.splitlines():
        cells = line.strip().split("|")
        # A two-column table row is "| key | value |": empty edges, two cells.
        if len(cells) != 4 or cells[0].strip() or cells[3].strip():
            continue
        key, value = cells[1].strip(), cells[2].replace("`", " ").strip()
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


def receipt_path(admission_root: Path, version: str) -> Path | None:
    """The receipt for ``version`` under ``admission_root``; None if not confined."""

    if not VERSION.fullmatch(version):
        return None
    root = admission_root.resolve()
    path = (root / RECEIPTS / f"l9-memory-release-{version}.md").resolve()
    return path if path.is_relative_to(root) else None


def _observe(artifact_dir: Path, observed: dict[str, str]) -> list[str]:
    wheel, sdist, failures = _artifacts(artifact_dir)
    for label, path in (("wheel", wheel), ("sdist", sdist)):
        if path is not None:
            observed[label] = path.name
            observed[f"{label} sha256"] = _sha256(path)
    return failures


def _compare(rows: dict[str, str], observed: dict[str, str]) -> list[str]:
    version, source = observed["version"], observed["source revision"]
    failures: list[str] = []
    if rows["Package"] != f"{DISTRIBUTION} {version}":
        failures.append(f"receipt admits {rows['Package']!r}, not {DISTRIBUTION} {version}")
    if rows["Admitted source"] != source:
        failures.append(f"receipt admits source {rows['Admitted source']!r}, not {source!r}")
    for label, name_key, digest_key in (
        ("wheel", "Wheel", "Wheel sha256"),
        ("sdist", "Sdist", "Sdist sha256"),
    ):
        admitted = rows[digest_key]
        if not DIGEST.fullmatch(admitted):
            failures.append(f"receipt {digest_key} is not a sha256 digest: {admitted!r}")
        if label not in observed:
            continue
        if rows[name_key] != observed[label]:
            failures.append(f"receipt admits {label} {rows[name_key]!r}, not {observed[label]!r}")
        if admitted != observed[f"{label} sha256"]:
            failures.append(
                f"{label} sha256 {observed[f'{label} sha256']} is not the admitted {admitted}"
            )
    return failures


def verify(
    admission_root: Path, artifact_dir: Path, version: str, source_revision: str, tag: str
) -> tuple[list[str], dict[str, str]]:
    """Return (failures, observed tuple); no failures means an exact admitted match."""

    observed = {"version": version, "source revision": source_revision, "tag": tag}
    failures: list[str] = []
    if tag != f"v{version}":
        failures.append(f"release tag {tag!r} is not v{version}")
    if not SHA.fullmatch(source_revision):
        failures.append(f"source revision is not a 40-hex commit: {source_revision!r}")
    failures += _observe(artifact_dir, observed)
    receipt = receipt_path(admission_root, version)
    if receipt is None:
        return [*failures, f"version {version!r} does not name a receipt"], observed
    if not receipt.is_file():
        return [*failures, f"no release admission receipt at {receipt}"], observed
    rows, receipt_failures = parse_receipt(receipt.read_text(encoding="utf-8"))
    if receipt_failures:
        return [*failures, *receipt_failures], observed
    return [*failures, *_compare(rows, observed)], observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--admission-root",
        type=Path,
        required=True,
        help="checkout of the protected default branch holding docs/receipts/",
    )
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    failures, observed = verify(
        args.admission_root, args.artifact_dir, args.version, args.source_revision, args.tag
    )
    if failures:
        sys.stdout.write("".join(f"FAIL: {failure}\n" for failure in failures))
        sys.stdout.write("observed release (admits nothing):\n")
        sys.stdout.write("".join(f"  {key}: {value}\n" for key, value in observed.items()))
        return 1
    sys.stdout.write(
        f"PASS: the default-branch receipt admits {DISTRIBUTION} {args.version}"
        f" at {args.source_revision}"
        f" with wheel {observed['wheel sha256']} and sdist {observed['sdist sha256']}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
