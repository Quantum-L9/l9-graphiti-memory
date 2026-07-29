#!/usr/bin/env python3
# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tools/assurance/render_active_memory_redis_acl.py
#   layer: assurance
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Render a reset-first least-privilege Redis 7.2+ ACL."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


def load(path):
    manifest_path = Path(path)
    if manifest_path.is_symlink():
        raise ValueError(f"manifest path must not be a symlink: {manifest_path}")
    if not manifest_path.is_file():
        raise ValueError(f"manifest path must be a regular file: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "commands",
        "key_patterns",
        "channel_patterns",
        "prohibited_commands",
        "minimum_redis_version",
    ):
        if key not in data:
            raise ValueError("manifest missing " + key)
    return data


def render(args, manifest):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", args.username):
        raise ValueError("invalid username")
    if not re.fullmatch(r"[0-9a-f]{16,64}", args.deployment_hash):
        raise ValueError("deployment hash must be 16-64 lowercase hex")
    if args.password_hash and not re.fullmatch(r"[0-9a-fA-F]{64}", args.password_hash):
        raise ValueError("password hash must be 64 hex characters")
    if bool(args.password_hash) == bool(args.allow_nopass_development):
        raise ValueError("choose exactly one authentication option")
    auth = "#" + args.password_hash.lower() if args.password_hash else "nopass"
    keys = [
        x.format(key_prefix=args.key_prefix, deployment_hash=args.deployment_hash)
        for x in manifest["key_patterns"]
    ]
    channels = [
        x.format(
            channel_prefix=args.channel_prefix or args.key_prefix,
            deployment_hash=args.deployment_hash,
        )
        for x in manifest["channel_patterns"]
    ]
    commands = sorted(
        {c.lower() for group in manifest["commands"].values() for c in group}
    )
    overlap = {c.upper() for c in commands} & {
        c.upper() for c in manifest["prohibited_commands"]
    }
    if overlap:
        raise ValueError("allowed/prohibited overlap: " + str(sorted(overlap)))
    rules = (
        ["reset", "on", auth, "resetkeys"]
        + ["~" + x for x in keys]
        + ["resetchannels"]
        + ["&" + x for x in channels]
        + ["-@all"]
        + ["+" + x for x in commands]
    )
    prefix = (
        ("user " + args.username + " ")
        if args.format == "acl-file"
        else ("ACL SETUSER " + args.username + " ")
    )
    return prefix + " ".join(rules)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--key-prefix", required=True)
    p.add_argument("--channel-prefix")
    p.add_argument("--deployment-hash", required=True)
    p.add_argument("--password-hash")
    p.add_argument("--allow-nopass-development", action="store_true")
    p.add_argument("--format", choices=["acl-file", "setuser"], default="acl-file")
    p.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "src/l9_graphite_memory/resources/active_memory_redis_capabilities.yaml"
        ),
    )
    p.add_argument("--output", type=Path)
    p.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    try:
        line = render(a, load(a.manifest))
        text = (
            ("user default off\n" + line + "\n")
            if a.format == "acl-file"
            else line + "\n"
        )
    except (OSError, ValueError, yaml.YAMLError) as e:
        sys.stderr.write("ERROR: " + str(e) + "\n")
        return 1
    if a.check or not a.output:
        sys.stdout.write(text)
        return 0
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(text, encoding="utf-8")
    a.output.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
