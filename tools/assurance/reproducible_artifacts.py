#!/usr/bin/env python3
"""Make a freshly built wheel and sdist byte-reproducible, or check that they are.

ADR-094 admits a release by the sha256 of its wheel and sdist, recorded before
the tag and compared with what a workflow builds from it. That comparison can
only pass when every sanctioned build of one commit yields the same bytes.
setuptools alone does not give that: its sdist carries each file's checkout
mtime and umask-dependent mode, pax ``mtime`` records, and build-time mtimes on
the members it generates (PKG-INFO, SOURCES.txt, setup.cfg); its wheel carries
umask-dependent modes in each entry's external attributes.

``canonicalize`` rewrites both archives into one canonical form and proves the
rewrite changed no content:

* sdist: members sorted by name; mtime = SOURCE_DATE_EPOCH; uid/gid 0 with
  empty uname/gname; mode 0755 for directories and files with any executable
  bit, 0644 otherwise; POSIX pax format whose only extended records are the
  ones a long or non-ASCII name needs (never a time); gzip level 9 with header
  mtime 0 and no file name.
* wheel: entries in the order setuptools wrote them (RECORD stays last);
  date_time from SOURCE_DATE_EPOCH (UTC); Unix external attributes 0100755 or
  0100644 by executable bit; deflate level 9. RECORD hashes file contents, not
  attributes, so it stays valid unchanged.

The member set, every member's type, link target, executable bit and bytes are
compared before and after; any difference fails closed. ``check`` reports
whether an artifact already is canonical (canonicalizing it again is a no-op).

This is a build step, not validation: it runs inside the one build entry point
(``scripts/build_release_artifacts.sh``) before any digest is recorded. The
admission verifier and release validation only read its output.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import sys
import tarfile
import time
import zipfile
import zlib
from pathlib import Path

COMPRESSION_LEVEL = 9
# The earliest instant a zip DOS timestamp can carry.
_ZIP_EPOCH_FLOOR = 315532800  # 1980-01-01T00:00:00Z
_TIME_PAX_KEYS = frozenset({"mtime", "atime", "ctime"})


class ReproducibilityError(Exception):
    """A canonical form could not be produced or proven content-identical."""


def source_date_epoch(value: str | None) -> int:
    """Parse SOURCE_DATE_EPOCH, failing closed when it is unset or not an integer."""
    if value is None or value.strip() == "":
        raise ReproducibilityError("SOURCE_DATE_EPOCH is unset; a release build needs a fixed epoch")
    text = value.strip()
    if not text.isdigit():
        raise ReproducibilityError(f"SOURCE_DATE_EPOCH must be a non-negative integer, got {value!r}")
    epoch = int(text)
    if epoch < _ZIP_EPOCH_FLOOR:
        raise ReproducibilityError(
            f"SOURCE_DATE_EPOCH {epoch} predates 1980-01-01, which a wheel timestamp cannot carry"
        )
    return epoch


def _canonical_mode(executable: bool) -> int:
    return 0o755 if executable else 0o644


# --- sdist ----------------------------------------------------------------------


def _sdist_content(data: bytes) -> dict[str, tuple[str, str, bool, bytes]]:
    """name -> (kind, link target, executable, bytes) for every member."""
    content: dict[str, tuple[str, str, bool, bytes]] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name in content:
                raise ReproducibilityError(f"sdist has a duplicate member: {member.name}")
            if member.isfile():
                extracted = tar.extractfile(member)
                assert extracted is not None
                content[member.name] = ("file", "", bool(member.mode & 0o111), extracted.read())
            elif member.isdir():
                content[member.name] = ("dir", "", True, b"")
            elif member.issym():
                content[member.name] = ("symlink", member.linkname, False, b"")
            else:
                raise ReproducibilityError(
                    f"sdist member {member.name} has an unsupported type {member.type!r}"
                )
    return content


def canonical_sdist(data: bytes, epoch: int) -> bytes:
    """Return the canonical bytes of an sdist (.tar.gz)."""
    members: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            info = tarfile.TarInfo(member.name)
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            payload: bytes | None = None
            if member.isfile():
                info.type = tarfile.REGTYPE
                info.mode = _canonical_mode(bool(member.mode & 0o111))
                extracted = tar.extractfile(member)
                assert extracted is not None
                payload = extracted.read()
                info.size = len(payload)
            elif member.isdir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
            elif member.issym():
                info.type = tarfile.SYMTYPE
                info.linkname = member.linkname
                info.mode = 0o777
            else:
                raise ReproducibilityError(
                    f"sdist member {member.name} has an unsupported type {member.type!r}"
                )
            members.append((info, payload))
    members.sort(key=lambda item: item[0].name)

    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w", format=tarfile.PAX_FORMAT) as out:
        for info, payload in members:
            out.addfile(info, io.BytesIO(payload) if payload is not None else None)

    gz_bytes = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz_bytes, compresslevel=COMPRESSION_LEVEL, mtime=0) as gz:
        gz.write(tar_bytes.getvalue())
    return gz_bytes.getvalue()


def _assert_sdist_canonical_shape(data: bytes, epoch: int) -> None:
    if data[3] & 0x08:  # FNAME flag
        raise ReproducibilityError("canonical sdist gzip header carries a file name")
    if int.from_bytes(data[4:8], "little") != 0:
        raise ReproducibilityError("canonical sdist gzip header carries a timestamp")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        if tar.pax_headers:
            raise ReproducibilityError("canonical sdist carries global pax headers")
        names = []
        for member in tar.getmembers():
            names.append(member.name)
            leaked = _TIME_PAX_KEYS & set(member.pax_headers)
            if leaked:
                raise ReproducibilityError(f"sdist member {member.name} carries pax time records {sorted(leaked)}")
            if member.mtime != epoch or member.uid or member.gid or member.uname or member.gname:
                raise ReproducibilityError(f"sdist member {member.name} is not normalised")
        if names != sorted(names):
            raise ReproducibilityError("canonical sdist members are not sorted")


# --- wheel ----------------------------------------------------------------------


def _wheel_content(data: bytes) -> list[tuple[str, bool, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return [
            (info.filename, bool((info.external_attr >> 16) & 0o111), zf.read(info))
            for info in zf.infolist()
        ]


def canonical_wheel(data: bytes, epoch: int) -> bytes:
    """Return the canonical bytes of a wheel (.whl)."""
    date_time = time.gmtime(epoch)[:6]
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        seen: set[str] = set()
        for entry in src.infolist():
            if entry.filename in seen:
                raise ReproducibilityError(f"wheel has a duplicate entry: {entry.filename}")
            seen.add(entry.filename)
            if entry.is_dir():
                raise ReproducibilityError(f"wheel has a directory entry: {entry.filename}")
            info = zipfile.ZipInfo(entry.filename, date_time=date_time)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = bool((entry.external_attr >> 16) & 0o111)
            info.external_attr = (0o100000 | _canonical_mode(executable)) << 16
            dst.writestr(info, src.read(entry), compresslevel=COMPRESSION_LEVEL)
    return out.getvalue()


# --- driver ---------------------------------------------------------------------


def canonical_bytes(path: Path, epoch: int) -> bytes:
    """Canonicalize one artifact and prove the rewrite changed no content."""
    data = path.read_bytes()
    if path.name.endswith(".tar.gz"):
        result = canonical_sdist(data, epoch)
        if _sdist_content(result) != _sdist_content(data):
            raise ReproducibilityError(f"{path.name}: canonical sdist content differs from the build")
        _assert_sdist_canonical_shape(result, epoch)
    elif path.name.endswith(".whl"):
        result = canonical_wheel(data, epoch)
        if _wheel_content(result) != _wheel_content(data):
            raise ReproducibilityError(f"{path.name}: canonical wheel content differs from the build")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            bad = zf.testzip()
        if bad is not None:
            raise ReproducibilityError(f"{path.name}: canonical wheel entry {bad} fails its CRC")
    else:
        raise ReproducibilityError(f"not a release artifact: {path.name}")
    return result


def _artifacts(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ReproducibilityError(f"not a directory: {directory}")
    found = sorted(directory.iterdir())
    wheels = [p for p in found if p.name.endswith(".whl")]
    sdists = [p for p in found if p.name.endswith(".tar.gz")]
    others = [p for p in found if p not in wheels and p not in sdists]
    if len(wheels) != 1 or len(sdists) != 1 or others:
        raise ReproducibilityError(
            f"{directory} must hold exactly one wheel and one sdist and nothing else, "
            f"found {[p.name for p in found]}"
        )
    return [*wheels, *sdists]


def canonicalize(directory: Path, epoch: int) -> list[str]:
    lines = []
    for path in _artifacts(directory):
        result = canonical_bytes(path, epoch)
        if canonical_bytes_from(result, path.name, epoch) != result:
            raise ReproducibilityError(f"{path.name}: canonical form is not a fixed point")
        tmp = path.with_name(path.name + ".canonical")
        tmp.write_bytes(result)
        os.replace(tmp, path)
        lines.append(f"{hashlib.sha256(result).hexdigest()}  {path.name}")
    return lines


def canonical_bytes_from(data: bytes, name: str, epoch: int) -> bytes:
    if name.endswith(".tar.gz"):
        return canonical_sdist(data, epoch)
    return canonical_wheel(data, epoch)


def check(directory: Path, epoch: int) -> list[str]:
    """Return the names of artifacts in ``directory`` that are not canonical."""
    return [
        path.name
        for path in _artifacts(directory)
        if canonical_bytes(path, epoch) != path.read_bytes()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("canonicalize", "check"))
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        epoch = source_date_epoch(os.environ.get("SOURCE_DATE_EPOCH"))
        print(
            f"reproducible-artifacts: SOURCE_DATE_EPOCH={epoch} python={sys.version.split()[0]} "
            f"zlib={zlib.ZLIB_RUNTIME_VERSION} level={COMPRESSION_LEVEL}"
        )
        if args.command == "canonicalize":
            for line in canonicalize(args.artifact_dir, epoch):
                print(line)
            return 0
        drift = check(args.artifact_dir, epoch)
    except ReproducibilityError as exc:
        print(f"reproducible-artifacts: FAIL: {exc}", file=sys.stderr)
        return 1
    if drift:
        print(f"reproducible-artifacts: FAIL: not canonical: {', '.join(drift)}", file=sys.stderr)
        return 1
    print("reproducible-artifacts: PASS: artifact set is canonical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
