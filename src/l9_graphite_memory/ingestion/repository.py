# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/repository.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Bootstrap repository architecture and ADRs through canonical ingestion."""

from __future__ import annotations

import subprocess
from pathlib import Path

from l9_graphite_memory.contracts import MemoryClass, MemoryPrincipal, WriteReceipt
from l9_graphite_memory.services import MemoryService

from .document import DocumentIngestor


class RepositoryBootstrapper:
    PRIORITY_FILES = (
        "AGENTS.md",
        "ARCHITECTURE.md",
        "README.md",
        "RUNBOOK.md",
        "MANIFEST.md",
        "CHANGE_SUMMARY.md",
    )

    def __init__(self, service: MemoryService, ingestor: DocumentIngestor | None = None) -> None:
        self.service = service
        self.ingestor = ingestor or DocumentIngestor()

    @staticmethod
    def repository_name(path: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "remote", "get-url", "origin"],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return path.name
        return result.stdout.strip() if result.returncode == 0 else path.name

    def sources(self, repo: Path) -> tuple[Path, ...]:
        found: list[Path] = []
        for relative in self.PRIORITY_FILES:
            path = repo / relative
            if path.is_file():
                found.append(path)
        adr_dir = repo / "docs" / "adr"
        if adr_dir.is_dir():
            found.extend(sorted(adr_dir.glob("ADR-*.md")))
        return tuple(dict.fromkeys(found))

    def bootstrap(
        self,
        principal: MemoryPrincipal,
        repo: str | Path,
        *,
        namespace: str,
        dry_run: bool = False,
    ) -> tuple[WriteReceipt, ...]:
        root = Path(repo).expanduser().resolve()
        repository = self.repository_name(root)
        receipts: list[WriteReceipt] = []
        for source in self.sources(root):
            memory_class = MemoryClass.DECISION if "adr" in source.parts else MemoryClass.META
            for request in self.ingestor.requests(
                source,
                namespace=namespace,
                memory_class=memory_class,
                repository=repository,
                tags=("bootstrap", source.name.lower()),
                dry_run=dry_run,
            ):
                receipts.append(self.service.write(principal, request))
        return tuple(receipts)
