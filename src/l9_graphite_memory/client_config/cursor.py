# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/client_config/cursor.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-27

"""Atomic, fail-closed lifecycle for the managed Cursor MCP entry.

The configurator owns exactly one key inside ``mcpServers`` and never
touches unrelated servers or unknown top-level keys. Every mutation is
guarded by a fresh inspection, performed through a fsynced temporary file
and ``os.replace``, bound to pre/post SHA-256 digests, and emitted as a
frozen :class:`ClientConfigReceipt`. Secrets never enter the generated
entry: the launch command carries no ``env`` block by construction.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from l9_graphite_memory.errors import ConfigurationError

from .contracts import (
    ClientConfigAction,
    ClientConfigReceipt,
    ClientConfigStatus,
    CursorConfigInspection,
    ManagedServerEntry,
)

MANAGED_SERVER_KEY = "l9-graphite-memory"
_SERVER_ARGS = ("-m", "l9_graphite_memory.server", "--transport", "stdio")
_MODE = 0o600


def default_cursor_config_path() -> Path:
    """Return the canonical Cursor MCP config path for this user."""
    return Path.home() / ".cursor" / "mcp.json"


def managed_server_entry(interpreter: str | None = None) -> ManagedServerEntry:
    """Build the exact managed entry: argv array only, never a shell string."""
    command = interpreter or sys.executable
    if not command or not str(command).strip():
        raise ConfigurationError("interpreter for the managed entry is empty")
    return ManagedServerEntry(
        key=MANAGED_SERVER_KEY, command=str(command), args=_SERVER_ARGS
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


class CursorClientConfigurator:
    """Scoped lifecycle manager for the managed Cursor MCP server entry."""

    def __init__(
        self, path: Path | None = None, *, interpreter: str | None = None
    ) -> None:
        self.path = path or default_cursor_config_path()
        self.entry = managed_server_entry(interpreter)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------
    def inspect(self) -> CursorConfigInspection:
        """Read-only fail-closed analysis of the target config file."""
        path = self.path
        blockers: list[str] = []
        is_symlink = path.is_symlink()
        parent_is_symlink = path.parent.is_symlink()
        exists = path.exists() or is_symlink
        is_regular = path.is_file() and not is_symlink
        if is_symlink:
            blockers.append("target path is a symlink")
        if parent_is_symlink:
            blockers.append("target parent directory is a symlink")
        if exists and not is_symlink and not path.is_file():
            blockers.append("target path exists but is not a regular file")

        parseable = False
        root_is_object = False
        servers_is_object = False
        managed_present = False
        managed_current = False
        managed_has_env = False
        unmanaged: tuple[str, ...] = ()
        unknown_top_level: tuple[str, ...] = ()
        digest: str | None = None
        if is_regular:
            raw = path.read_bytes()
            digest = _sha256_bytes(raw)
            try:
                decoded = json.loads(raw.decode("utf-8"))
                parseable = True
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                blockers.append(f"existing config is not valid JSON: {exc}")
                decoded = None
            if parseable:
                if isinstance(decoded, dict):
                    root_is_object = True
                    unknown_top_level = tuple(
                        sorted(key for key in decoded if key != "mcpServers")
                    )
                    servers = decoded.get("mcpServers")
                    if servers is None:
                        servers_is_object = True
                    elif isinstance(servers, dict):
                        servers_is_object = True
                        managed = servers.get(MANAGED_SERVER_KEY)
                        managed_present = managed is not None
                        if isinstance(managed, dict):
                            managed_has_env = "env" in managed
                            managed_current = managed == self.entry.as_config()
                        unmanaged = tuple(
                            sorted(
                                key
                                for key in servers
                                if key != MANAGED_SERVER_KEY
                            )
                        )
                    else:
                        blockers.append("mcpServers is not a JSON object")
                else:
                    blockers.append("config root is not a JSON object")
        return CursorConfigInspection(
            path=str(path),
            exists=exists,
            is_regular_file=is_regular,
            is_symlink=is_symlink,
            parent_is_symlink=parent_is_symlink,
            parseable=parseable,
            root_is_object=root_is_object,
            servers_is_object=servers_is_object,
            managed_entry_present=managed_present,
            managed_entry_current=managed_current,
            managed_entry_has_env=managed_has_env,
            unmanaged_server_keys=unmanaged,
            unknown_top_level_keys=unknown_top_level,
            config_sha256=digest,
            blockers=tuple(blockers),
        )

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------
    def install(self, *, dry_run: bool = False) -> ClientConfigReceipt:
        """Idempotently install the managed entry with atomic evidence."""
        inspection = self.inspect()
        if inspection.blockers:
            return self._blocked(ClientConfigAction.INSTALL, inspection)
        pre_sha = inspection.config_sha256
        existing = self._load_verified(expected_sha=pre_sha)
        servers = existing.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise ConfigurationError("mcpServers is not a JSON object")
        already_current = servers.get(MANAGED_SERVER_KEY) == self.entry.as_config()
        preserved = tuple(
            sorted(key for key in servers if key != MANAGED_SERVER_KEY)
        )
        if already_current:
            return ClientConfigReceipt(
                action=ClientConfigAction.INSTALL,
                status=(
                    ClientConfigStatus.DRY_RUN
                    if dry_run
                    else ClientConfigStatus.UNCHANGED
                ),
                path=str(self.path),
                changed=False,
                managed_entry_present=True,
                command_argv=(self.entry.command, *self.entry.args),
                pre_sha256=pre_sha,
                post_sha256=pre_sha,
                preserved_server_keys=preserved,
                reasons=("managed entry already current",),
            )
        servers[MANAGED_SERVER_KEY] = self.entry.as_config()
        if dry_run:
            return ClientConfigReceipt(
                action=ClientConfigAction.INSTALL,
                status=ClientConfigStatus.DRY_RUN,
                path=str(self.path),
                changed=False,
                managed_entry_present=True,
                command_argv=(self.entry.command, *self.entry.args),
                pre_sha256=pre_sha,
                post_sha256=None,
                preserved_server_keys=preserved,
                reasons=("dry run: no bytes written",),
            )
        backup_path, backup_sha = self._backup(pre_sha)
        post_sha = self._atomic_write(existing, expected_pre_sha=pre_sha)
        return ClientConfigReceipt(
            action=ClientConfigAction.INSTALL,
            status=ClientConfigStatus.COMPLETE,
            path=str(self.path),
            changed=True,
            managed_entry_present=True,
            command_argv=(self.entry.command, *self.entry.args),
            pre_sha256=pre_sha,
            post_sha256=post_sha,
            backup_path=backup_path,
            backup_sha256=backup_sha,
            preserved_server_keys=preserved,
        )

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------
    def uninstall(
        self, *, dry_run: bool = False, restore_backup: Path | None = None
    ) -> ClientConfigReceipt:
        """Remove only the managed entry, or restore a digest-verified backup."""
        if restore_backup is not None:
            return self._restore(restore_backup, dry_run=dry_run)
        inspection = self.inspect()
        if inspection.blockers:
            return self._blocked(ClientConfigAction.UNINSTALL, inspection)
        pre_sha = inspection.config_sha256
        if not inspection.managed_entry_present:
            return ClientConfigReceipt(
                action=ClientConfigAction.UNINSTALL,
                status=(
                    ClientConfigStatus.DRY_RUN
                    if dry_run
                    else ClientConfigStatus.UNCHANGED
                ),
                path=str(self.path),
                changed=False,
                managed_entry_present=False,
                pre_sha256=pre_sha,
                post_sha256=pre_sha,
                preserved_server_keys=inspection.unmanaged_server_keys,
                reasons=("managed entry not present",),
            )
        existing = self._load_verified(expected_sha=pre_sha)
        servers = existing.get("mcpServers")
        if not isinstance(servers, dict):
            raise ConfigurationError("mcpServers is not a JSON object")
        servers.pop(MANAGED_SERVER_KEY, None)
        preserved = tuple(sorted(servers))
        if dry_run:
            return ClientConfigReceipt(
                action=ClientConfigAction.UNINSTALL,
                status=ClientConfigStatus.DRY_RUN,
                path=str(self.path),
                changed=False,
                managed_entry_present=False,
                pre_sha256=pre_sha,
                post_sha256=None,
                preserved_server_keys=preserved,
                reasons=("dry run: no bytes written",),
            )
        backup_path, backup_sha = self._backup(pre_sha)
        post_sha = self._atomic_write(existing, expected_pre_sha=pre_sha)
        return ClientConfigReceipt(
            action=ClientConfigAction.UNINSTALL,
            status=ClientConfigStatus.COMPLETE,
            path=str(self.path),
            changed=True,
            managed_entry_present=False,
            pre_sha256=pre_sha,
            post_sha256=post_sha,
            backup_path=backup_path,
            backup_sha256=backup_sha,
            preserved_server_keys=preserved,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def status(self) -> ClientConfigReceipt:
        """Derive install state strictly from observable config evidence."""
        inspection = self.inspect()
        reasons: list[str] = list(inspection.blockers)
        if inspection.managed_entry_current:
            status = ClientConfigStatus.COMPLETE
            reasons.append("managed entry present and current")
        elif inspection.managed_entry_present:
            status = ClientConfigStatus.BLOCKED
            reasons.append("managed entry present but drifted from canonical form")
        elif inspection.blockers:
            status = ClientConfigStatus.BLOCKED
        else:
            status = ClientConfigStatus.UNCHANGED
            reasons.append("managed entry not installed")
        warnings: tuple[str, ...] = ()
        if inspection.managed_entry_has_env:
            warnings = ("managed entry carries an env block; secrets are forbidden",)
        return ClientConfigReceipt(
            action=ClientConfigAction.STATUS,
            status=status,
            path=str(self.path),
            changed=False,
            managed_entry_present=inspection.managed_entry_present,
            command_argv=(self.entry.command, *self.entry.args),
            pre_sha256=inspection.config_sha256,
            post_sha256=inspection.config_sha256,
            preserved_server_keys=inspection.unmanaged_server_keys,
            reasons=tuple(reasons),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _blocked(
        self, action: ClientConfigAction, inspection: CursorConfigInspection
    ) -> ClientConfigReceipt:
        return ClientConfigReceipt(
            action=action,
            status=ClientConfigStatus.BLOCKED,
            path=str(self.path),
            changed=False,
            managed_entry_present=inspection.managed_entry_present,
            pre_sha256=inspection.config_sha256,
            post_sha256=inspection.config_sha256,
            preserved_server_keys=inspection.unmanaged_server_keys,
            reasons=inspection.blockers,
        )

    def _load_verified(self, *, expected_sha: str | None) -> dict[str, object]:
        """Re-read the file and fail closed on TOCTOU digest divergence."""
        if not self.path.is_file():
            if expected_sha is not None:
                raise ConfigurationError(
                    "config file disappeared between inspection and write"
                )
            return {}
        raw = self.path.read_bytes()
        if expected_sha is None or _sha256_bytes(raw) != expected_sha:
            raise ConfigurationError(
                "config file changed between inspection and write; retry"
            )
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ConfigurationError("config root is not a JSON object")
        return decoded

    def _backup(self, pre_sha: str | None) -> tuple[str | None, str | None]:
        if pre_sha is None or not self.path.is_file():
            return None, None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.path.with_name(
            f"{self.path.name}.backup.{stamp}.{pre_sha[:12]}"
        )
        payload = self.path.read_bytes()
        if _sha256_bytes(payload) != pre_sha:
            raise ConfigurationError(
                "config file changed while creating backup; retry"
            )
        fd = os.open(
            str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL, _MODE
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            backup.unlink(missing_ok=True)
            raise
        return str(backup), pre_sha

    def _atomic_write(
        self, config: dict[str, object], *, expected_pre_sha: str | None
    ) -> str:
        """Serialize, fsync a sibling temp file, then atomically replace."""
        current = _sha256_file(self.path) if self.path.is_file() else None
        if current != expected_pre_sha:
            raise ConfigurationError(
                "config file changed between inspection and write; retry"
            )
        payload = (json.dumps(config, indent=2) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent)
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, _MODE)
            os.replace(temp_path, self.path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise
        directory_fd = os.open(str(self.path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return _sha256_bytes(payload)

    def _restore(
        self, backup: Path, *, dry_run: bool
    ) -> ClientConfigReceipt:
        """Restore a backup only when its digest matches its embedded binding."""
        if not backup.is_file() or backup.is_symlink():
            raise ConfigurationError("backup path is not a regular file")
        name_parts = backup.name.rsplit(".", 1)
        expected_prefix = name_parts[-1] if len(name_parts) == 2 else ""
        payload = backup.read_bytes()
        digest = _sha256_bytes(payload)
        if len(expected_prefix) != 12 or not digest.startswith(expected_prefix):
            raise ConfigurationError(
                "backup digest does not match its filename binding; refusing restore"
            )
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ConfigurationError("backup root is not a JSON object")
        if dry_run:
            return ClientConfigReceipt(
                action=ClientConfigAction.UNINSTALL,
                status=ClientConfigStatus.DRY_RUN,
                path=str(self.path),
                changed=False,
                backup_path=str(backup),
                backup_sha256=digest,
                reasons=("dry run: verified backup not restored",),
            )
        pre_sha = _sha256_file(self.path) if self.path.is_file() else None
        post_sha = self._atomic_write(decoded, expected_pre_sha=pre_sha)
        servers = decoded.get("mcpServers")
        present = isinstance(servers, dict) and MANAGED_SERVER_KEY in servers
        return ClientConfigReceipt(
            action=ClientConfigAction.UNINSTALL,
            status=ClientConfigStatus.COMPLETE,
            path=str(self.path),
            changed=True,
            managed_entry_present=present,
            pre_sha256=pre_sha,
            post_sha256=post_sha,
            backup_path=str(backup),
            backup_sha256=digest,
            reasons=("restored digest-verified backup",),
        )
