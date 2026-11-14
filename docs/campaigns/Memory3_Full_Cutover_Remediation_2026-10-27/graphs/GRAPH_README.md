# Graph Files and Reading Guide

`remediation_graph.json` and `.yaml` are the canonical editable work catalog. `campaign_graph.yaml` is the updated C1 campaign-level projection.

- **143 granular nodes, 293 required prerequisite edges.**
- `00_WORKSTREAMS.svg`: compact architecture and ownership.
- `01_PR_PIPELINE.svg`: ordered governed coding work and deployment handoff.
- `02_DETAILED_DAG.svg`: all detailed nodes and dependencies (large, zoomable).
- `00_WORKSTREAMS.mmd`, `01_PR_PIPELINE.mmd`, `02_DETAILED_DAG.mmd`: edit-ready Mermaid diagrams.
- `ledgers/edge_ledger.csv`: exact edge evidence.

## Edge semantics

`must_precede`: source must reach its own acceptance before target may be claimed. `governs`: semantic owner constrains target. `verifies`: source provides evidence for target, does not grant authority. `qualifies`: conditional provider proof. No edge authorizes code mutation or deployment.

## Conditional branches

PROJ-11 decides whether Zep is removed or retained. Only if retained do PROJ-12/13 require code tests. Graphiti is outbound provider MCP and is not banned by the inbound Memory stdio retirement.

## Milestones

* `CUT-13`: core C1 OAuth shared Memory.
* `CUT-14`: full audited correctness, including provider/retention and source coverage.
* `CUT-15`: independently approved final release and operating state.

The SVGs are presentation aids, not a substitute for machine-readable acceptance and failure receipts.
