# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/Website-Bot/transform.py
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from pathlib import Path

p = Path(".env.example")
if p.exists():
    text = p.read_text()
    block = """

# Governed cross-agent memory (l9-graphiti-memory)
L9_MEMORY_MODE=optional
L9_MEMORY_URL=http://127.0.0.1:8200
L9_MEMORY_TOKEN=
L9_MEMORY_TOKEN_BUDGET=1200
L9_MEMORY_MAX_RECORDS=40
"""
    if "L9_MEMORY_MODE=" not in text:
        p.write_text(text.rstrip() + block + "\n")
