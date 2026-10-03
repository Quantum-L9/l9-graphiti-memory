# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/repository.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02
"""Bootstrap repository architecture and ADRs through canonical ingestion."""
from __future__ import annotations
import subprocess
from pathlib import Path
from l9_graphite_memory.contracts import MemoryClass, MemoryPrincipal, WriteReceipt
from l9_graphite_memory.errors import L9MemoryError
from l9_graphite_memory.repository_corpus import (
    RepositoryCorpus,
    RepositoryCorpusError,
    load_repository_corpus,
)
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
    def __init__(
        self,
        service: MemoryService,
        ingestor: DocumentIngestor | None = None,
        corpus: RepositoryCorpus | None = None,
    ) -> None:
        self.service = service
        self.ingestor = ingestor or DocumentIngestor()
        self.corpus = corpus or load_repository_corpus()
    @staticmethod
    def repository_name(path: Path) -> str:
        try:
            result = subprocess.run(  # noqa: S603
                ["git", "-C", str(path), "remote", "get-url", "origin"],  # noqa: S607
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
        observed_repository = self.repository_name(root)
        member = self.corpus.resolve(observed_repository)
        if member is not None:
            if not member.current:
                raise L9MemoryError(
                    f"L9 repository {member.id} is {member.lifecycle}; "
                    "only current corpus members are ingestion eligible"
                )
            if namespace != self.corpus.runtime_namespace:
                raise L9MemoryError(
                    f"L9 repository {member.id} is governed by namespace "
                    f"{self.corpus.runtime_namespace}; requested {namespace}"
                )
            repository = member.coordinate.canonical
        else:
            if namespace == self.corpus.runtime_namespace:
                raise L9MemoryError(
                    f"repository {observed_repository} is not admitted to the "
                    "canonical L9 repository corpus"
                )
            repository = observed_repository
        receipts: list[WriteReceipt] = []
        for source in self.sources(root):
            memory_class = (
                MemoryClass.DECISION if "adr" in source.parts else MemoryClass.META
            )
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
__all__ = [
    "RepositoryBootstrapper",
    "RepositoryCorpusError",
]
