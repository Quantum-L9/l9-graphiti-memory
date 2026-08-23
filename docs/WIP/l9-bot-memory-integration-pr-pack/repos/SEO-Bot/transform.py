# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: docs/WIP/l9-bot-memory-integration-pr-pack/repos/SEO-Bot/transform.py
#   layer: documentation
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"Expected anchor not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1))


# Add governed-memory configuration to the existing fail-fast env schema.
replace_once(
    "src/core/config.ts",
    "  PERPLEXITY_API_KEY: z.string().min(1),\n",
    "  PERPLEXITY_API_KEY: z.string().min(1),\n\n"
    "  // Governed cross-agent memory (l9-graphiti-memory HTTP MCP)\n"
    "  L9_MEMORY_MODE: z.enum(['disabled', 'optional', 'required']).default('optional'),\n"
    "  L9_MEMORY_URL: z.string().url().optional(),\n"
    "  L9_MEMORY_TOKEN: z.string().min(1).optional(),\n"
    "  L9_MEMORY_TOKEN_BUDGET: z.coerce.number().int().min(128).max(64000).default(1200),\n"
    "  L9_MEMORY_MAX_RECORDS: z.coerce.number().int().min(1).max(200).default(40),\n",
)

# Add operational receipt pointers only; canonical memory remains in l9-graphiti-memory.
replace_once(
    "src/core/database/schema.ts",
    "  learnings: text('learnings'),\n});",
    "  learnings: text('learnings'),\n"
    "  memoryRecordId: uuid('memory_record_id'),\n"
    "  memoryPromotedAt: timestamp('memory_promoted_at'),\n"
    "  memoryPromotionError: text('memory_promotion_error'),\n});",
)

# Allow modules to register their own job definitions before Scheduler.start().
replace_once(
    "src/core/scheduler.ts",
    "  registerHandler(jobName: string, handler: (job: Job) => Promise<void>): void {\n",
    "  registerDefinition(definition: JobDefinition): void {\n"
    "    const existing = JOB_DEFINITIONS.find(item => item.name === definition.name);\n"
    "    if (existing) {\n"
    "      if (JSON.stringify(existing) !== JSON.stringify(definition)) throw new Error(`Conflicting job definition: ${definition.name}`);\n"
    "      return;\n"
    "    }\n"
    "    JOB_DEFINITIONS.push(definition);\n"
    "    logger.debug({ jobName: definition.name }, 'Job definition registered');\n"
    "  }\n\n"
    "  registerHandler(jobName: string, handler: (job: Job) => Promise<void>): void {\n",
)

# Document runtime configuration without requiring it in optional mode.
env = Path(".env.example")
if env.exists():
    text = env.read_text()
    block = """

# Governed cross-agent memory
L9_MEMORY_MODE=optional
L9_MEMORY_URL=http://127.0.0.1:8200
L9_MEMORY_TOKEN=
L9_MEMORY_TOKEN_BUDGET=1200
L9_MEMORY_MAX_RECORDS=40
"""
    if "L9_MEMORY_MODE=" not in text:
        env.write_text(text.rstrip() + block + "\n")
