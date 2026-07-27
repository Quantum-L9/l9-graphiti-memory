<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/l9-deploy-phase6-operator/references/REPO_WIRING_DECISION.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

<!--
skill_schema: 1
parent: l9-deploy-phase6-operator
layer: reference
role: wiring_decision
tags: [wiring, portability, phase6]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-07-26
-->
# Repository Wiring Decision

This is a portable out-of-repository handoff pack. It is deliberately not wired into `Quantum-L9/l9-deploy` because the locked Phase 6 plan permits zero target-repository source-file changes. The global `l9-wire-skill-into-repo` utility was not available in this execution environment.

The receiving agent may install the skill in an external agent skills directory or invoke `AGENT_EXECUTION_PROMPT.md` directly. Do not add skill registry files, agent manifests, or probe workflows to `l9-deploy` during Phase 6.
