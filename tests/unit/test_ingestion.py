# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_ingestion.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from pathlib import Path

from l9_graphite_memory.contracts import MemoryClass
from l9_graphite_memory.ingestion import DocumentIngestor


def test_document_ingestor_preserves_source_lines(tmp_path: Path) -> None:
    path = tmp_path / "source.md"
    path.write_text("# One\n\nFirst paragraph.\n\nSecond paragraph.\n")
    requests = DocumentIngestor().requests(
        path, namespace="repo-a", memory_class=MemoryClass.SEMANTIC
    )
    assert len(requests) >= 2
    assert requests[0].provenance.source_digest
    assert requests[0].provenance.source_range is not None
    assert requests[0].evidence[0].source_range is not None
