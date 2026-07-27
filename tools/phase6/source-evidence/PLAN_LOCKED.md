<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: tools/phase6/source-evidence/PLAN_LOCKED.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

plan_status: ConditionallyReady

planning_mode:
  mode: Release
  rationale:
    - "The work changes secret handling, deployment transactions, rollback semantics, workflow authorization, operational documentation, and staging validation."
    - "The plan includes implementation, integration, merge, release, and deployment gates."
    - "The supplied PLAN kernel requires dependency ordering, validation, rollback, execution waves, and explicit Unknowns before implementation. PLAN.md"

plan_identifier: "L9-DEPLOY-REMEDIATION-PLAN-V2"

target_binding:
  repository: "Quantum-L9/l9-deploy"
  repository_url: "https://github.com/Quantum-L9/l9-deploy"
  inspected_source_snapshot: "quantum-l9-l9-deploy-8a5edab282632443.txt"
  branch: Unknown
  exact_commit_sha: Unknown
  source_release_observed: "0.1.5"
  target_type:
    - "Python deployment control plane"
    - "GitHub deployment workflows"
    - "Shell-based Infisical integration"
    - "Deployment templates and profiles"
    - "Operational documentation"
    - "Tests and generated release evidence"

objective: >-
  Correct l9-deploy so runtime configuration is immutable release-owned state,
  Infisical materialization is atomic and fail-closed, OIDC permissions are
  limited to the deployment job, rollback restores both image and configuration,
  and the complete behavior is documented and validated through protected staging.

desired_outcomes:
  required:
    - "A candidate deployment receives a release-specific runtime environment snapshot."
    - "The currently active runtime environment is not overwritten during preparation."
    - "Promotion activates the image and runtime configuration as one logical release."
    - "Rollback restores the prior image, prior runtime configuration, and prior state pointer."
    - "Infisical output is fully validated before publication."
    - "Duplicate, malformed, incomplete, or unsafe secrets fail without changing the destination."
    - "Only the secret-consuming deployment job receives GitHub OIDC token permission."
    - "Existing immutable plan, approval, health, receipt, and rollback behavior is preserved."
    - "Functional deployment workflows remain in scope."
    - "Scanners, linters, generalized CI installation, and deprecated CI pull requests remain out of scope."
    - "An agent operating guide is added during the documentation phase."
    - "Every build phase modifies no more than 20 files."
    - "Every build phase begins with a repository tree marking built, being built, and remaining work."
  optional:
    - "Consolidate duplicate Infisical logic only if inspection proves that Python and shell implementations own the same active responsibility."

authorized_scope:
  - "Runtime environment materialization"
  - "Deployment planning where configuration identity must be represented"
  - "Execution transaction"
  - "Promotion and rollback state"
  - "Infisical OIDC environment script"
  - "Minimum functional deployment workflows"
  - "Targeted unit, integration, security, and workflow tests"
  - "Agent, architecture, security, and runbook documentation"
  - "Generated release evidence after implementation stabilizes"
  - "Protected staging lifecycle validation"

excluded_scope:
  - "Quantum-L9/infra changes"
  - "Infisical project or identity provisioning"
  - "Application-side Infisical SDK"
  - "Kubernetes"
  - "New generalized secrets framework"
  - "Scanners"
  - "Linters"
  - "Formatting-only automation"
  - "General pull-request CI installation"
  - "Dependency upgrades unrelated to the correction"
  - "Seven deprecated CI pull requests"
  - "Production deployment without separate authorization"
  - "Repository-wide rewrite"

authority_and_contracts:
  governing_sources:
    - "AUDIT findings AUD-L9D-001 through AUD-L9D-007"
    - "README.md"
    - "ARCHITECTURE.md"
    - "SPECIFICATION.md"
    - "SECURITY.md"
    - ".l9/repo-spec.yaml"
    - "RUNBOOK.md"
    - "PLAN kernel version 1.0"
  preserved_contracts:
    - "Immutable OCI digest deployment"
    - "Deterministic deployment plans"
    - "Independent protected-environment approval"
    - "Create-only hash-chained receipts"
    - "Application consumption of ordinary environment variables"
    - "Database rollback remains explicitly separate from container rollback"
    - "Wire contracts use `schema`; governed Python aliases remain internal"
    - "Production hosts do not clone or build application source"
  authorized_contract_changes:
    - "Deployment state may record active runtime configuration identity."
    - "Release layout may include a release-specific runtime environment file."
    - "Rollback may restore configuration state in addition to image state."
  prohibited_contract_changes:
    - "Secret values in plans, receipts, state documents, logs, or workflow outputs"
    - "Implicit production defaults"
    - "Application-side secret fetching"
    - "Infisical provisioning from l9-deploy"

current_state_summary:
  confirmed:
    - "The execution engine writes runtime configuration to a fixed active runtime.env path before deployment completion."
    - "The observed rollback path restores the prior release but does not restore the prior runtime.env."
    - "scripts/infisical-oidc-env.sh truncates and appends to the final destination while validating entries."
    - "The deployment workflow grants `id-token: write` at workflow scope."
    - "Local historical validation reports 103 tests passing and 79.45% branch coverage."
    - "Credentialed staging, Infisical OIDC, SSH deployment, rollback, and backup restore remain unverified."
    - "Repository identity is inconsistent between l9-deploy and l9-deployment-platform."
  probable:
    - "The fixed runtime.env path is consumed by Compose and migrations across multiple deployment profiles."
    - "Generated evidence must be regenerated after source and documentation changes."
  unknown:
    - "Exact current main commit SHA"
    - "Exact working-tree state"
    - "Complete current RemoteExecutor.write_text atomicity behavior"
    - "Live Infisical claim restrictions"
    - "Live staging environment availability"

assumptions:
  - id: A-01
    statement: "Existing release directories can contain a protected runtime environment file."
    confidence: Probable
    affected_items:
      - P1-02
      - P1-03
    required_validation:
      - "Inspect current release layout and permissions before mutation."
  - id: A-02
    statement: "Compose and migration commands can receive an explicit env-file path."
    confidence: Probable
    affected_items:
      - P2-01
      - P2-02
    required_validation:
      - "Inspect current command construction and template context."
  - id: A-03
    statement: "The deployment state document can be extended additively with configuration identity."
    confidence: Probable
    affected_items:
      - P1-01
      - P2-03
    required_validation:
      - "Run schema compatibility and old-state loading tests."

unknowns:
  - id: U-01
    description: "Exact repository revision and clean baseline"
    reason: "The audit used a source snapshot without verified Git metadata."
    affected_plan_items:
      - P0-01
      - all implementation items
    minimum_evidence:
      - "git rev-parse HEAD"
      - "git branch --show-current"
      - "git status --short"
      - "git ls-files"
    blocks_planning: false
    blocks_implementation: true
    blocks_completion: true
    responsible_source: "Repository maintainer"

  - id: U-02
    description: "Canonical repository identity"
    reason: "Public repository and internal metadata use different names."
    affected_plan_items:
      - P4-02
      - P5-01
    minimum_evidence:
      - "Authorized decision selecting canonical name"
      - "Inventory of externally persisted legacy identifiers"
    blocks_planning: false
    blocks_implementation: false
    blocks_completion: true
    responsible_source: "Platform architecture owner"

  - id: U-03
    description: "Remote write atomicity and file-permission behavior"
    reason: "Complete implementation was not proven by the audit evidence."
    affected_plan_items:
      - P1-03
      - P2-01
    minimum_evidence:
      - "Complete RemoteExecutor.write_text implementation"
      - "Targeted remote-write tests"
    blocks_planning: false
    blocks_implementation: false
    blocks_completion: true
    responsible_source: "Execution owner"

  - id: U-04
    description: "Infisical OIDC claim restrictions"
    reason: "Identity policy is external to the repository."
    affected_plan_items:
      - P3-02
      - P6-01
    minimum_evidence:
      - "Redacted claim policy"
      - "Positive and negative OIDC exchange results"
    blocks_planning: false
    blocks_implementation: false
    blocks_completion: true
    responsible_source: "Platform security owner"

  - id: U-05
    description: "Protected staging environment availability"
    reason: "No live target was accessible during audit."
    affected_plan_items:
      - P6-01
    minimum_evidence:
      - "Staging inventory"
      - "Protected environment"
      - "Runner"
      - "Infisical identity"
      - "Deployable immutable image"
    blocks_planning: false
    blocks_implementation: false
    blocks_completion: true
    responsible_source: "Operations owner"

decisions:
  - id: D-01
    question: "What is the canonical repository identity?"
    required_by:
      - P4-02
      - P5-01
      - P6-01
    options:
      - option: "Quantum-L9/l9-deploy"
        benefits:
          - "Matches the current public repository URL."
          - "Reduces operator ambiguity."
        costs:
          - "Legacy documentation, OIDC policies, state keys, and generated evidence may require compatibility mappings."
        risks:
          - "Persisted references may break if renamed without inventory."
        compatibility_impact: "Potentially affects OIDC and external state references."
        validation_implications:
          - "Repository-wide identity scan"
          - "OIDC claim test"
          - "Remote-state accessibility check"
      - option: "Quantum-L9/l9-deployment-platform"
        benefits:
          - "Matches existing internal metadata."
        costs:
          - "Conflicts with the current repository address."
        risks:
          - "Continues external/internal naming mismatch."
        compatibility_impact: "No internal migration but preserves ambiguity."
        validation_implications:
          - "Document the public alias explicitly."
    recommendation: "Use Quantum-L9/l9-deploy as canonical and retain explicit compatibility references only where external persisted state requires them."
    authority: "Platform architecture owner"
    decision_deadline_type: BeforeRelease
    status: Recommended

  - id: D-02
    question: "How should release-specific runtime configuration be activated?"
    required_by:
      - P1-01
      - P1-02
      - P2-01
      - P2-03
    options:
      - option: "Versioned runtime.env inside each release directory, with the active release pointer selecting both image metadata and configuration"
        benefits:
          - "Configuration rollback follows release rollback."
          - "No separate mutable singleton must be restored."
          - "Supports auditability and secret rotation."
        costs:
          - "Requires Compose, migration, state, and cleanup changes."
        risks:
          - "Old release directories contain historical secrets and require retention policy."
        compatibility_impact: "Internal deployment layout change."
        validation_implications:
          - "Promotion, rollback, cleanup, and permission tests"
      - option: "Keep fixed runtime.env and maintain explicit previous/current backups"
        benefits:
          - "Smaller layout change."
        costs:
          - "Adds another mutable state machine."
          - "Rollback ordering becomes more complex."
        risks:
          - "Configuration and release pointers can diverge."
        compatibility_impact: "Lower immediate path impact but higher operational complexity."
        validation_implications:
          - "Extensive crash-consistency testing"
    recommendation: "Use versioned release-owned runtime.env."
    authority: "l9-deploy architecture owner"
    decision_deadline_type: BeforeImplementation
    status: Recommended

architecture_adapters:
  - id: AA-01
    name: "Deployment control-plane ownership"
    governing_source:
      - "README.md"
      - "ARCHITECTURE.md"
      - ".l9/repo-spec.yaml"
    applicable_scope: "All phases"
    mandatory_rules:
      - "l9-deploy consumes but does not provision Infisical resources."
      - "Applications consume ordinary environment variables."
      - "Deployment remains bound to immutable image digests and approved plans."
    prohibited_patterns:
      - "Application-side secret retrieval"
      - "Runtime source builds"
      - "Secrets in plans or receipts"
    precedence: "Repository architecture policy"

  - id: AA-02
    name: "Transactional deployment and rollback"
    governing_source:
      - "Audit finding AUD-L9D-002"
      - "Repository rollback contract"
    applicable_scope:
      - "Phase 1"
      - "Phase 2"
    mandatory_rules:
      - "Candidate state cannot mutate active state before promotion."
      - "Rollback restores image and runtime configuration."
      - "Health failure prevents promotion."
    prohibited_patterns:
      - "Fixed mutable runtime configuration outside release ownership"

  - id: AA-03
    name: "Secret materialization safety"
    governing_source:
      - "SPECIFICATION.md"
      - "SECURITY.md"
      - "Audit finding AUD-L9D-003"
    applicable_scope:
      - "Phase 1"
      - "Phase 3"
    mandatory_rules:
      - "Validate complete input before publication."
      - "Reject duplicate and unsafe keys."
      - "Write with restrictive permissions."
      - "Use atomic replacement."
      - "Do not log values."

  - id: AA-04
    name: "Workflow least privilege"
    governing_source:
      - "SPECIFICATION.md"
      - "Audit finding AUD-L9D-004"
    applicable_scope: "Phase 3"
    mandatory_rules:
      - "Only the deployment job receives id-token write permission."
      - "Validation jobs cannot obtain deployment identity."
      - "Protected approval remains independent."

responsibility_map:
  - component: "Planning and deployment state contracts"
    responsibility:
      - "Represent release and configuration identity without secret values."
    owner: "contracts/planning"
    source_of_truth:
      - "Python DTOs"
      - "schemas/v1"
    incoming_dependencies:
      - "D-02"
    outgoing_dependencies:
      - "Execution"
      - "Promotion"
      - "Rollback"
      - "Receipts"

  - component: "Infisical materialization"
    responsibility:
      - "Authenticate"
      - "Retrieve"
      - "Validate"
      - "Atomically publish a candidate runtime env file"
    owner:
      - "scripts/infisical-oidc-env.sh"
      - "Existing Infisical integration module"
    source_of_truth: "Infisical"
    outgoing_dependencies:
      - "Candidate release"

  - component: "Execution transaction"
    responsibility:
      - "Prepare candidate state"
      - "Run migration and deploy"
      - "Verify health"
      - "Promote"
      - "Roll back"
    owner: "src/l9_deploy/execution"
    incoming_dependencies:
      - "Approved plan"
      - "Candidate runtime env"
    outgoing_dependencies:
      - "Runtime host"
      - "Receipts"

  - component: "Deployment workflow"
    responsibility:
      - "Verify request and evidence"
      - "Obtain approval"
      - "Obtain short-lived identity"
      - "Invoke deployment"
    owner: ".github/workflows"
    incoming_dependencies:
      - "Protected environment"
      - "Infisical claim policy"
    outgoing_dependencies:
      - "Private deployment runner"

  - component: "Documentation and agents"
    responsibility:
      - "Describe ownership, commands, prohibitions, lifecycle, and recovery"
    owner:
      - "docs"
      - "Root documentation"
    incoming_dependencies:
      - "Stable implementation behavior"

dependency_graph:
  nodes:
    - P0-01
    - D-02
    - P1-01
    - P1-02
    - P1-03
    - P1-04
    - P2-01
    - P2-02
    - P2-03
    - P2-04
    - P3-01
    - P3-02
    - P3-03
    - D-01
    - P4-01
    - P4-02
    - P4-03
    - P5-01
    - P5-02
    - P6-01
  edges:
    - "P0-01 -> all implementation phases"
    - "D-02 -> P1-01"
    - "P1-01 -> P1-02"
    - "P1-02 -> P1-03"
    - "P1-03 -> P1-04"
    - "P1-04 -> P2-01"
    - "P2-01 -> P2-02"
    - "P2-02 -> P2-03"
    - "P2-03 -> P2-04"
    - "P2-04 -> P3-01"
    - "P3-01 -> P3-02"
    - "P3-02 -> P3-03"
    - "P2-04 -> P4-01"
    - "P3-03 -> P4-01"
    - "D-01 -> P4-02"
    - "P4-01 -> P4-03"
    - "P4-02 -> P4-03"
    - "P4-03 -> P5-01"
    - "P5-01 -> P5-02"
    - "P5-02 -> P6-01"
  cycle_status: "No cycle"
  critical_path:
    - P0-01
    - D-02
    - P1-01
    - P1-02
    - P1-03
    - P1-04
    - P2-01
    - P2-02
    - P2-03
    - P2-04
    - P3-01
    - P3-02
    - P3-03
    - P4-01
    - P4-03
    - P5-01
    - P5-02
    - P6-01
  independent_branches:
    - "After Phase 2 stabilizes, workflow hardening and documentation preparation may proceed independently."
  shared_write_conflicts:
    - "Execution engine and rollback tests"
    - "Deployment state schemas and generated evidence"
    - "Workflow files and workflow tests"
    - "Root documentation and generated inventories"

findings:
  confirmed:
    - id: AUD-L9D-002
      severity: High
      affected_artifacts:
        - "src/l9_deploy/execution/engine.py"
        - "src/l9_deploy/execution/rollback.py"
        - "runtime.env"
      root_cause: "Runtime configuration is a mutable singleton instead of release-owned state."
      planning_impact: "Phases 1 and 2 must precede secret-contract expansion."

    - id: AUD-L9D-003
      severity: High
      affected_artifacts:
        - "scripts/infisical-oidc-env.sh"
      root_cause: "Validation and publication are coupled."
      planning_impact: "Atomic materialization is part of Phase 1."

    - id: AUD-L9D-004
      severity: High
      affected_artifacts:
        - ".github/workflows/deploy-dispatch.yml"
      root_cause: "OIDC permission is declared at workflow scope."
      planning_impact: "Minimal workflow correction in Phase 3."

    - id: AUD-L9D-005
      severity: High
      affected_artifacts:
        - "Staging lifecycle"
      root_cause: "External validation evidence is absent."
      planning_impact: "Phase 6 is mandatory before release eligibility."

    - id: AUD-L9D-006
      severity: Medium
      affected_artifacts:
        - "docs/agents/deployment-agent.md"
      root_cause: "No dedicated agent operating contract."
      planning_impact: "Add during documentation phase."

    - id: AUD-L9D-007
      severity: Medium
      affected_artifacts:
        - "Repository metadata and documentation"
      root_cause: "Incomplete repository rename propagation."
      planning_impact: "Resolve identity before release evidence regeneration."

recommended_strategy:
  name: "Release-owned configuration with atomic secret preparation"
  approach:
    - "Bind the exact repository baseline before mutation."
    - "Define release configuration identity and state semantics."
    - "Make runtime.env a protected file inside the candidate release."
    - "Validate and write Infisical output to a temporary file, then atomically rename."
    - "Make migrations and Compose consume the candidate release env file."
    - "Promote release and configuration identity together."
    - "Make rollback select the previous release directory and its env file."
    - "Restrict OIDC permission to the deployment job."
    - "Add focused behavioral tests rather than new generalized CI."
    - "Document agent authority after implementation stabilizes."
    - "Regenerate governed evidence only after all authoritative source changes are final."
    - "Prove the lifecycle in protected staging."
  why_selected:
    correctness:
      - "Configuration and image state cannot diverge."
    security:
      - "Partial secret files are never published."
      - "OIDC follows least privilege."
    compatibility:
      - "Applications continue receiving normal environment variables."
      - "Existing deployment profiles and image contracts remain intact."
    scope:
      - "Corrects verified root causes without replacing the deployment engine."
    reversibility:
      - "Each source phase can be reverted independently before release."
    leverage:
      - "The release-owned configuration primitive enables safe deploy, rollback, and secret rotation."
  tradeoffs:
    - "Release directories retain protected historical configuration snapshots."
    - "Cleanup policy must preserve at least the active and rollback releases."
    - "State schema may need an additive field for configuration identity."

rejected_strategies:
  - strategy: "Keep a fixed runtime.env and copy it to runtime.env.previous"
    reasons:
      - "Creates a second mutable state machine."
      - "Crash ordering can still diverge from release state."
      - "Rollback correctness becomes harder to prove."

  - strategy: "Fetch secrets inside the application"
    reasons:
      - "Violates ownership boundaries."
      - "Duplicates authentication and refresh logic."
      - "Applications do not need Infisical awareness."

  - strategy: "Rewrite the deployment platform"
    reasons:
      - "Existing planning, approval, health, receipt, and rollback components are reusable."
      - "The verified defects are bounded."

  - strategy: "Install generalized CI in the same work"
    reasons:
      - "The user explicitly deferred scanners, linters, and generalized CI."
      - "It adds unrelated change surface."

workstreams:
  - id: WS-00
    objective: "Bind the exact implementation baseline."
    ownership_boundary: "Repository maintenance"
    included_plan_items:
      - P0-01
    external_dependencies: []
    shared_contracts: []
    completion_criteria:
      - "Exact SHA, branch, clean-tree state, and tracked-file tree recorded."
    integration_validation:
      - "Snapshot-to-checkout comparison."
    risk: Low
    status: Blocked

  - id: WS-01
    objective: "Establish release-owned runtime configuration and atomic materialization."
    ownership_boundary: "Contracts, secret integration, and release layout"
    included_plan_items:
      - P1-01
      - P1-02
      - P1-03
      - P1-04
    external_dependencies:
      - D-02
    shared_contracts:
      - "Deployment state"
      - "Release directory layout"
      - "runtime.env format"
    completion_criteria:
      - "Candidate env is validated and atomically created."
      - "Active env remains unchanged during preparation."
    integration_validation:
      - "Filesystem and contract tests."
    risk: High
    status: Proposed

  - id: WS-02
    objective: "Make execution, promotion, and rollback configuration-consistent."
    ownership_boundary: "Execution engine"
    included_plan_items:
      - P2-01
      - P2-02
      - P2-03
      - P2-04
    external_dependencies:
      - WS-01
    shared_contracts:
      - "Plan-step ordering"
      - "Active release state"
      - "Rollback state"
    completion_criteria:
      - "Migration, deploy, promotion, and rollback use one release-specific env identity."
    integration_validation:
      - "Failure-injection transaction tests."
    risk: High
    status: Proposed

  - id: WS-03
    objective: "Minimize workflow privilege and preserve functional deployment."
    ownership_boundary: "GitHub deployment workflows"
    included_plan_items:
      - P3-01
      - P3-02
      - P3-03
    external_dependencies:
      - "Infisical identity policy"
    shared_contracts:
      - "Protected environment"
      - "OIDC claims"
      - "Deployment CLI invocation"
    completion_criteria:
      - "Only deploy job receives id-token write."
      - "Deployment still resolves secrets and executes the approved plan."
    integration_validation:
      - "Static workflow tests and staging OIDC tests."
    risk: High
    status: Proposed

  - id: WS-04
    objective: "Complete operational documentation and repository identity alignment."
    ownership_boundary: "Documentation and metadata"
    included_plan_items:
      - P4-01
      - P4-02
      - P4-03
    external_dependencies:
      - D-01
      - "Stable implementation behavior"
    shared_contracts:
      - "Repository identity"
      - "Agent authority"
      - "Runbook behavior"
    completion_criteria:
      - "Agent guide and operator docs match implementation."
    integration_validation:
      - "Documentation and metadata scan."
    risk: Medium
    status: Proposed

  - id: WS-05
    objective: "Regenerate exact release evidence and prove staging lifecycle."
    ownership_boundary: "Validation and release"
    included_plan_items:
      - P5-01
      - P5-02
      - P6-01
    external_dependencies:
      - "Protected staging"
    shared_contracts:
      - "Manifest"
      - "Checksums"
      - "Receipts"
      - "Staging evidence"
    completion_criteria:
      - "Current source validation passes."
      - "Staging proves deploy and rollback convergence."
    integration_validation:
      - "Full local and protected staging lifecycle."
    risk: High
    status: Proposed

phase_plan:
  - phase: 0
    name: "Baseline binding"
    maximum_files: 0
    planned_files: 0
    tree_requirement: "Print full tracked repository tree and mark all files as existing before mutation."
    items:
      - P0-01

  - phase: 1
    name: "Runtime configuration primitive"
    maximum_files: 20
    estimated_files: "12-18"
    tree_before_phase: |
      l9-deploy/
      ├── scripts/
      │   └── infisical-oidc-env.sh                  🚧 being built
      ├── src/l9_deploy/
      │   ├── contracts/                             🚧 being built as required
      │   ├── execution/
      │   │   └── remote.py                          🚧 conditional
      │   └── planning/                              ⬜ to be built in later phase if needed
      ├── schemas/v1/                                🚧 being built as required
      ├── tests/
      │   ├── unit/                                  🚧 being built
      │   ├── security/                              🚧 being built
      │   └── contract/                              🚧 conditional
      ├── .github/workflows/                         ⬜ Phase 3
      └── docs/                                      ⬜ Phase 4
    allowed_artifact_classes:
      - "Secret materialization"
      - "Release layout"
      - "Configuration identity contract"
      - "Targeted tests"
    items:
      - P1-01
      - P1-02
      - P1-03
      - P1-04

  - phase: 2
    name: "Transactional execution and rollback"
    maximum_files: 20
    estimated_files: "12-18"
    tree_before_phase: |
      l9-deploy/
      ├── scripts/
      │   └── infisical-oidc-env.sh                  ✅ built
      ├── src/l9_deploy/
      │   ├── execution/
      │   │   ├── engine.py                          🚧 being built
      │   │   ├── compose.py                         🚧 being built
      │   │   ├── migrations.py                      🚧 being built
      │   │   ├── promotion.py                       🚧 being built
      │   │   ├── rollback.py                        🚧 being built
      │   │   └── remote.py                          ✅/🚧 depending Phase 1
      │   └── planning/                              🚧 conditional
      ├── tests/
      │   ├── integration/                           🚧 being built
      │   ├── unit/                                  🚧 being built
      │   └── security/                              ✅ Phase 1
      ├── .github/workflows/                         ⬜ Phase 3
      └── docs/                                      ⬜ Phase 4
    items:
      - P2-01
      - P2-02
      - P2-03
      - P2-04

  - phase: 3
    name: "Functional workflow hardening"
    maximum_files: 20
    estimated_files: "4-8"
    tree_before_phase: |
      l9-deploy/
      ├── src/l9_deploy/execution/                   ✅ built
      ├── scripts/infisical-oidc-env.sh              ✅ built
      ├── .github/
      │   ├── actions/collect-approval/              ✅ preserved
      │   └── workflows/
      │       ├── deploy-dispatch.yml                🚧 being built
      │       ├── deploy-manual.yml                  🚧 conditional
      │       ├── rollback.yml                       🚧 conditional
      │       ├── validation/scanner workflows       ⛔ excluded
      │       └── deprecated CI PR work              ⛔ excluded
      ├── tests/workflows/                           🚧 being built
      └── docs/                                      ⬜ Phase 4
    items:
      - P3-01
      - P3-02
      - P3-03

  - phase: 4
    name: "Documentation, agent contract, and identity alignment"
    maximum_files: 20
    estimated_files: "8-14"
    tree_before_phase: |
      l9-deploy/
      ├── src/                                       ✅ built
      ├── scripts/                                   ✅ built
      ├── .github/workflows/                         ✅ built
      ├── docs/
      │   └── agents/
      │       └── deployment-agent.md                🚧 being built
      ├── README.md                                  🚧 being built
      ├── ARCHITECTURE.md                            🚧 being built
      ├── SECURITY.md                                🚧 being built
      ├── RUNBOOK.md                                 🚧 being built
      ├── SPECIFICATION.md                           🚧 conditional
      ├── .l9/repo-spec.yaml                         🚧 conditional
      └── generated evidence                         ⬜ Phase 5
    items:
      - P4-01
      - P4-02
      - P4-03

  - phase: 5
    name: "Validation and generated evidence"
    maximum_files: 20
    estimated_files: "Generated set determined by repository tooling"
    tree_before_phase: |
      l9-deploy/
      ├── authoritative source                       ✅ built
      ├── tests/                                     ✅ built
      ├── docs/                                      ✅ built
      ├── MANIFEST.md                                🚧 regenerated
      ├── FINAL_TREE.md                              🚧 regenerated
      ├── TRACEABILITY_MAP.yaml                      🚧 regenerated
      ├── GAP_DEFECT_MATRIX.yaml                     🚧 regenerated
      ├── checksums.sha256                           🚧 regenerated
      └── validation/evidence/                       🚧 regenerated as required
    constraint: >-
      If the supported generator changes more than 20 tracked files, split
      generated artifacts into multiple generation-only subphases without
      manually editing derived files.
    items:
      - P5-01
      - P5-02

  - phase: 6
    name: "Protected staging lifecycle"
    maximum_files: 0
    planned_files: 0
    tree_before_phase: |
      l9-deploy/
      ├── source                                     ✅ validated
      ├── workflows                                  ✅ validated locally
      ├── docs                                       ✅ aligned
      └── staging environment                        🚧 being validated
    items:
      - P6-01

plan_items:
  - id: P0-01
    title: "Bind the exact repository baseline"
    objective: "Establish the exact source state for implementation."
    rationale: "Closes AUD-L9D-001 and prevents work against a stale snapshot."
    category: Discovery
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Repository maintenance"
    affected_artifacts:
      - "Entire checkout"
    prerequisites: []
    inputs:
      - "Writable or inspectable Git checkout"
    actions:
      - "Record commit SHA, branch, and working-tree status."
      - "Inventory tracked files."
      - "Identify unrelated local changes."
      - "Compare checkout with the audited snapshot."
      - "Print the phase-zero repository tree."
    preserved_invariants:
      - "No source mutation."
    expected_changes:
      - "None"
    prohibited_changes:
      - "No cleanup, reset, checkout, merge, or stash without authorization."
    acceptance_criteria:
      - "Exact SHA is recorded."
      - "Working-tree state is known."
      - "Tracked tree is available."
    validation:
      targeted:
        - "Git metadata inspection"
      integration: []
      regression: []
      expected_evidence:
        - "SHA"
        - "Branch"
        - "Status"
        - "Tracked tree"
    rollback_or_recovery: "NotApplicable: read-only."
    risk: Low
    risk_factors:
      - "Stale source"
    effort: Small
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "All implementation phases are bound to one baseline."
    closes_findings:
      - AUD-L9D-001
    status: Blocked

  - id: P1-01
    title: "Define release-owned runtime configuration identity"
    objective: "Represent runtime configuration as part of a release without exposing secret values."
    rationale: "Required by AUD-L9D-002 and D-02."
    category: Contract
    priority: Critical
    necessity: Required
    confidence: Probable
    owner_boundary: "Contracts and deployment state"
    affected_artifacts:
      - "Deployment state model"
      - "Relevant schemas"
      - "State tests"
    prerequisites:
      - P0-01
      - "D-02 approved"
    inputs:
      - "Current release state contract"
    actions:
      - "Add an additive configuration identity or release-env reference."
      - "Preserve loading of existing state documents."
      - "Prohibit secret values and value hashes."
      - "Define cleanup retention for active and rollback releases."
    preserved_invariants:
      - "Existing state remains readable."
      - "Secrets remain outside state."
    expected_changes:
      - "State can identify the active release-specific runtime env."
    prohibited_changes:
      - "No breaking state migration."
    acceptance_criteria:
      - "Old state fixtures load."
      - "New state round-trips."
      - "Secret-bearing fields are rejected."
    validation:
      targeted:
        - "Schema and model tests"
      integration:
        - "Old/new state compatibility"
      regression:
        - "Existing state tests"
      expected_evidence:
        - "Passing compatibility fixtures"
    rollback_or_recovery: "Revert additive state fields before release."
    risk: High
    risk_factors:
      - "Persistent operational state compatibility"
    effort: Medium
    uncertainty: Medium
    parallelization: Sequential
    postconditions:
      - "Configuration identity is a governed part of release state."
    closes_findings:
      - AUD-L9D-002
    status: Blocked

  - id: P1-02
    title: "Create the candidate release environment layout"
    objective: "Place runtime.env inside the candidate release with restrictive ownership and permissions."
    rationale: "Eliminates the fixed mutable singleton."
    category: Implementation
    priority: Critical
    necessity: Required
    confidence: Probable
    owner_boundary: "Release layout"
    affected_artifacts:
      - "Release path construction"
      - "Environment path helpers"
      - "Filesystem tests"
    prerequisites:
      - P1-01
    inputs:
      - "Release identifier"
      - "Target project and environment"
    actions:
      - "Derive a release-specific runtime.env path."
      - "Ensure directories are created with controlled ownership."
      - "Preserve active and previous release env snapshots."
      - "Exclude env files from receipts, archives, and debug bundles."
    preserved_invariants:
      - "Applications still receive the same environment variables."
    expected_changes:
      - "Each candidate release owns its runtime env."
    prohibited_changes:
      - "No secret values in path names or state."
    acceptance_criteria:
      - "Active and candidate paths cannot collide."
      - "File permissions satisfy security policy."
      - "Archive generation excludes the file."
    validation:
      targeted:
        - "Path and permission tests"
      integration:
        - "Release cleanup tests"
      regression:
        - "Existing layout tests"
      expected_evidence:
        - "Filesystem assertions"
    rollback_or_recovery: "Delete unpromoted release directory."
    risk: High
    risk_factors:
      - "Secret retention"
      - "Filesystem permissions"
    effort: Medium
    uncertainty: Medium
    parallelization: Sequential
    postconditions:
      - "Candidate configuration exists outside active state."
    closes_findings:
      - AUD-L9D-002
    status: Proposed

  - id: P1-03
    title: "Make Infisical materialization atomic and fail-closed"
    objective: "Validate the complete secret set before replacing the destination."
    rationale: "Directly closes AUD-L9D-003."
    category: Implementation
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Infisical integration"
    affected_artifacts:
      - "scripts/infisical-oidc-env.sh"
      - "Relevant Python integration if it shares active responsibility"
      - "Security tests"
    prerequisites:
      - P1-02
    inputs:
      - "Infisical JSON response"
      - "Candidate env destination"
    actions:
      - "Parse the complete response before writing."
      - "Reject duplicate keys."
      - "Reject invalid names, CR, LF, NUL, and prohibited empty values."
      - "Create a temporary file with restrictive mode."
      - "Write deterministic entries."
      - "Atomically rename only after successful validation."
      - "Remove temporary files on all failure paths."
      - "Prevent values from appearing in logs or errors."
    preserved_invariants:
      - "Existing OIDC exchange behavior"
      - "Environment file format"
    expected_changes:
      - "Destination changes only on complete success."
    prohibited_changes:
      - "No generalized provider framework."
    acceptance_criteria:
      - "Invalid final entry leaves the destination unchanged."
      - "Duplicate keys fail."
      - "Successful file is mode 0600."
      - "Canary values do not appear in output logs."
    validation:
      targeted:
        - "Shell or Python behavior tests"
        - "Canary redaction tests"
      integration:
        - "Valid and invalid Infisical payload fixtures"
      regression:
        - "Existing OIDC script tests"
      expected_evidence:
        - "Atomicity and failure-path test results"
    rollback_or_recovery: "Revert script and retain prior materialization behavior only before integration."
    risk: High
    risk_factors:
      - "Secret exposure"
      - "Partial configuration"
    effort: Medium
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "No partial destination can be published."
    closes_findings:
      - AUD-L9D-003
    status: Proposed

  - id: P1-04
    title: "Validate the runtime configuration primitive"
    objective: "Prove release identity, path isolation, atomic publication, permissions, and compatibility."
    rationale: "Phase 2 must not consume an unproven primitive."
    category: Validation
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Tests"
    affected_artifacts:
      - "Unit tests"
      - "Security tests"
      - "Contract tests"
    prerequisites:
      - P1-01
      - P1-02
      - P1-03
    inputs:
      - "Phase 1 implementation"
    actions:
      - "Add known-failure regression tests."
      - "Run targeted Phase 1 suites."
      - "Inspect Phase 1 diff and file count."
      - "Verify no secret fixtures leak."
    preserved_invariants:
      - "No unrelated test changes."
    expected_changes:
      - "Executable regression protection."
    prohibited_changes:
      - "No generalized CI."
    acceptance_criteria:
      - "All Phase 1 tests pass."
      - "Phase changes no more than 20 files."
      - "No canary value leaks."
    validation:
      targeted:
        - "Phase 1 tests"
      integration:
        - "Release-layout plus materialization"
      regression:
        - "Existing affected suites"
      expected_evidence:
        - "Test output"
        - "File-count report"
        - "Secret-canary scan"
    rollback_or_recovery: "Phase cannot proceed until failures are corrected."
    risk: Low
    risk_factors:
      - "False-green tests"
    effort: Medium
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "Phase 1 is safe for execution integration."
    closes_findings:
      - AUD-L9D-003
    status: Proposed

  - id: P2-01
    title: "Route migration and Compose execution through the candidate environment"
    objective: "Ensure all candidate operations consume the release-specific runtime env."
    rationale: "Prevents different deployment steps from using different configuration."
    category: Implementation
    priority: Critical
    necessity: Required
    confidence: Probable
    owner_boundary: "Execution adapters"
    affected_artifacts:
      - "execution/compose.py"
      - "execution/migrations.py"
      - "Environment path call sites"
    prerequisites:
      - P1-04
      - U-03 resolved
    inputs:
      - "Candidate runtime env path"
    actions:
      - "Pass the candidate env path explicitly."
      - "Reject fallback to the fixed active path during candidate execution."
      - "Ensure commands do not expose values on argv or logs."
    preserved_invariants:
      - "Migration ordering"
      - "Compose behavior"
    expected_changes:
      - "Candidate operations use one configuration snapshot."
    prohibited_changes:
      - "No migration-policy redesign."
    acceptance_criteria:
      - "Migration and deploy commands reference the same candidate env path."
      - "No fixed runtime.env reference remains in candidate flow."
    validation:
      targeted:
        - "Command-construction tests"
      integration:
        - "Candidate migration and Compose test"
      regression:
        - "Existing migration and Compose tests"
      expected_evidence:
        - "Sanitized command assertions"
    rollback_or_recovery: "Revert call-site changes."
    risk: High
    risk_factors:
      - "Migration correctness"
      - "Secret leakage"
    effort: Medium
    uncertainty: Medium
    parallelization: Sequential
    postconditions:
      - "Candidate execution is configuration-consistent."
    closes_findings:
      - AUD-L9D-002
    status: Blocked

  - id: P2-02
    title: "Prevent active-state mutation before health success"
    objective: "Keep the active release and configuration unchanged until candidate health passes."
    rationale: "Core transaction correction for AUD-L9D-002."
    category: Implementation
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Execution engine"
    affected_artifacts:
      - "execution/engine.py"
      - "Candidate transaction tests"
    prerequisites:
      - P2-01
    inputs:
      - "Candidate release"
      - "Candidate runtime env"
    actions:
      - "Prepare all candidate material before activation."
      - "Run candidate deployment without updating the active state pointer."
      - "Run health checks against the candidate."
      - "Promote only after health success."
      - "Clean candidate state on pre-promotion failure."
    preserved_invariants:
      - "Approved plan"
      - "Deployment lock"
      - "Backup and migration ordering"
    expected_changes:
      - "Active state remains stable until promotion."
    prohibited_changes:
      - "No silent health bypass."
    acceptance_criteria:
      - "Injected failures before promotion leave active state byte-for-byte unchanged."
      - "Successful candidate reaches health before promotion."
    validation:
      targeted:
        - "Engine ordering tests"
      integration:
        - "Failure injection at each phase"
      regression:
        - "Existing execution tests"
      expected_evidence:
        - "Ordered transaction trace"
    rollback_or_recovery: "Delete candidate release before promotion."
    risk: High
    risk_factors:
      - "Availability"
      - "Migration interaction"
    effort: Large
    uncertainty: Medium
    parallelization: Sequential
    postconditions:
      - "Candidate preparation cannot corrupt active release state."
    closes_findings:
      - AUD-L9D-002
    status: Proposed

  - id: P2-03
    title: "Promote image and configuration identity together"
    objective: "Atomically record one active release containing image and runtime configuration identity."
    rationale: "Prevents configuration/image divergence."
    category: Implementation
    priority: Critical
    necessity: Required
    confidence: Probable
    owner_boundary: "Promotion and state"
    affected_artifacts:
      - "execution/promotion.py"
      - "State writer"
      - "Promotion tests"
    prerequisites:
      - P2-02
    inputs:
      - "Healthy candidate release"
    actions:
      - "Update the active release pointer and state only after health success."
      - "Record configuration identity without values."
      - "Preserve the previous release as rollback target."
      - "Make state publication atomic."
    preserved_invariants:
      - "Receipt semantics"
      - "Immutable image digest"
    expected_changes:
      - "One promotion event activates image and configuration."
    prohibited_changes:
      - "No independent mutable configuration pointer."
    acceptance_criteria:
      - "State always points to a self-consistent release."
      - "Crash before publication leaves previous state active."
    validation:
      targeted:
        - "Atomic state-write tests"
      integration:
        - "Promotion crash tests"
      regression:
        - "Existing promotion tests"
      expected_evidence:
        - "State transition assertions"
    rollback_or_recovery: "Retain previous state document and release pointer."
    risk: High
    risk_factors:
      - "Crash consistency"
    effort: Medium
    uncertainty: Medium
    parallelization: Sequential
    postconditions:
      - "Active state identifies one coherent release."
    closes_findings:
      - AUD-L9D-002
    status: Proposed

  - id: P2-04
    title: "Restore prior image and configuration during rollback"
    objective: "Make rollback converge to the previous complete release."
    rationale: "Directly closes the observed rollback defect."
    category: Rollback
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Rollback"
    affected_artifacts:
      - "execution/rollback.py"
      - "execution/engine.py"
      - "Rollback tests"
    prerequisites:
      - P2-03
    inputs:
      - "Previous release identity"
      - "Previous runtime env"
    actions:
      - "Select the previous release directory."
      - "Use its runtime env for service recreation."
      - "Restore the previous state pointer only after rollback health succeeds."
      - "Emit a redacted rollback receipt."
      - "Preserve explicit database recovery separation."
    preserved_invariants:
      - "No automatic database downgrade."
      - "Rollback health verification"
    expected_changes:
      - "Image and runtime config return to the same prior release."
    prohibited_changes:
      - "No receipt secret metadata."
    acceptance_criteria:
      - "Injected post-activation failure restores image, configuration, state pointer, and health."
      - "Rollback failure is reported without false success."
    validation:
      targeted:
        - "Rollback state tests"
      integration:
        - "End-to-end failure and rollback"
      regression:
        - "Existing rollback tests"
      expected_evidence:
        - "Before/after state and health assertions"
    rollback_or_recovery: "Manual recovery uses the previous release directory and explicit database runbook."
    risk: High
    risk_factors:
      - "Availability"
      - "Expired previous credentials"
    effort: Large
    uncertainty: Medium
    parallelization: MustBeAtomic
    postconditions:
      - "Rollback restores a coherent prior release."
    closes_findings:
      - AUD-L9D-002
    status: Proposed

  - id: P3-01
    title: "Inventory the minimum functional deployment workflows"
    objective: "Separate required deployment workflows from deprecated or generalized CI."
    rationale: "User requires workflows in scope but excludes scanners and linters."
    category: Discovery
    priority: High
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Workflow maintenance"
    affected_artifacts:
      - ".github/workflows"
      - ".github/actions/collect-approval"
    prerequisites:
      - P2-04
    inputs:
      - "Current workflow tree"
    actions:
      - "Classify workflows as deployment-required, provisioning-related, deferred CI, or obsolete."
      - "Identify the exact workflow invoking Infisical and l9-deploy."
      - "Print the Phase 3 tree with statuses."
    preserved_invariants:
      - "Protected approval"
      - "Private runner isolation"
    expected_changes:
      - "No mutation in this item."
    prohibited_changes:
      - "No scanner or linter installation."
    acceptance_criteria:
      - "Every workflow has a documented disposition."
    validation:
      targeted:
        - "Workflow inventory review"
      integration: []
      regression: []
      expected_evidence:
        - "Workflow disposition matrix"
    rollback_or_recovery: "NotApplicable: read-only."
    risk: Low
    risk_factors:
      - "Removing a functional workflow accidentally"
    effort: Small
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "Phase 3 scope is exact."
    closes_findings: []
    status: Proposed

  - id: P3-02
    title: "Restrict OIDC permission to the deployment job"
    objective: "Grant id-token write only to the approved secret-consuming job."
    rationale: "Closes AUD-L9D-004."
    category: Configuration
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Workflow security"
    affected_artifacts:
      - ".github/workflows/deploy-dispatch.yml"
      - "Other active deployment workflow if it requests OIDC"
    prerequisites:
      - P3-01
    inputs:
      - "Functional workflow inventory"
    actions:
      - "Remove workflow-level id-token write."
      - "Declare minimal default permissions."
      - "Grant id-token write only on the deploy job."
      - "Ensure validation and approval jobs cannot request OIDC."
    preserved_invariants:
      - "Deployment job can still exchange identity."
      - "Approval remains independent."
    expected_changes:
      - "Least-privilege workflow permissions."
    prohibited_changes:
      - "No generalized CI."
      - "No scanner or linter jobs."
    acceptance_criteria:
      - "Only the deploy job has id-token write."
      - "Other jobs have explicit minimal permissions."
    validation:
      targeted:
        - "Workflow structure test"
      integration:
        - "Staging positive and negative OIDC tests"
      regression:
        - "Existing workflow tests"
      expected_evidence:
        - "Parsed permissions matrix"
    rollback_or_recovery: "Revert workflow permission patch before deployment."
    risk: High
    risk_factors:
      - "Deployment identity failure"
      - "Privilege expansion"
    effort: Small
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "OIDC token issuance is job-scoped."
    closes_findings:
      - AUD-L9D-004
    status: Proposed

  - id: P3-03
    title: "Prove minimum deployment workflow wiring"
    objective: "Verify approval, OIDC, secret materialization, and plan execution remain connected."
    rationale: "Workflow hardening must not break deployment."
    category: Validation
    priority: High
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Workflow tests"
    affected_artifacts:
      - "tests/workflows"
      - "Active deployment workflow fixtures"
    prerequisites:
      - P3-02
    inputs:
      - "Updated workflows"
    actions:
      - "Test job permissions."
      - "Test approval dependency."
      - "Test secret materialization occurs only in deploy."
      - "Test exact approved plan execution."
      - "Test deprecated scanner/linter workflows are not introduced."
    preserved_invariants:
      - "Functional deployment path"
    expected_changes:
      - "Focused workflow regression protection."
    prohibited_changes:
      - "No new CI framework."
    acceptance_criteria:
      - "Workflow tests pass."
      - "Deployment path remains connected."
    validation:
      targeted:
        - "Workflow tests"
      integration:
        - "Protected staging in Phase 6"
      regression:
        - "Existing workflow tests"
      expected_evidence:
        - "Workflow test output"
    rollback_or_recovery: "Block integration until workflow tests pass."
    risk: Medium
    risk_factors:
      - "Static tests may miss provider policy defects"
    effort: Medium
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "Workflow source is ready for staging validation."
    closes_findings:
      - AUD-L9D-004
    status: Proposed

  - id: P4-01
    title: "Document deployment-agent authority and restrictions"
    objective: "Provide one authoritative operating contract for agents."
    rationale: "Closes AUD-L9D-006."
    category: Documentation
    priority: High
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Documentation"
    affected_artifacts:
      - "docs/agents/deployment-agent.md"
      - "Nearest documentation index or README reference"
    prerequisites:
      - P2-04
      - P3-03
    inputs:
      - "Final execution and workflow behavior"
    actions:
      - "Document owned and excluded responsibilities."
      - "Document allowed read-only and mutation operations."
      - "Document plan, approval, and immutable-digest requirements."
      - "Document secret-handling prohibitions."
      - "Document phase ordering, validation, receipt handling, and rollback triggers."
      - "Prohibit direct infra ownership and direct production mutation."
    preserved_invariants:
      - "Human approval remains required."
    expected_changes:
      - "One agent operating guide."
    prohibited_changes:
      - "No autonomous production authority."
    acceptance_criteria:
      - "Guide maps to actual CLI and workflow behavior."
      - "No instruction conflicts with repository policy."
    validation:
      targeted:
        - "Documentation alignment review"
      integration:
        - "Cross-reference verification"
      regression:
        - "Documentation link checks if available"
      expected_evidence:
        - "Reviewer checklist"
    rollback_or_recovery: "Revert document if implementation changes invalidate it."
    risk: Medium
    risk_factors:
      - "Overgranting agent authority"
    effort: Medium
    uncertainty: Low
    parallelization: ParallelAfterPrerequisites
    postconditions:
      - "Agents can operate without reinterpretation."
    closes_findings:
      - AUD-L9D-006
    status: Proposed

  - id: P4-02
    title: "Reconcile canonical repository identity"
    objective: "Use one canonical name while preserving required legacy identifiers."
    rationale: "Closes AUD-L9D-007."
    category: Documentation
    priority: High
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Architecture metadata"
    affected_artifacts:
      - "README.md"
      - ".l9/repo-spec.yaml"
      - "Architecture documentation"
      - "Non-persistent generated metadata"
      - "OIDC documentation"
    prerequisites:
      - "D-01 approved"
    inputs:
      - "Legacy identifier inventory"
    actions:
      - "Declare the canonical repository name."
      - "Classify legacy references as replaceable or persistent."
      - "Update non-persistent references."
      - "Document compatibility mappings for state keys and external policies."
      - "Do not rename external state without migration evidence."
    preserved_invariants:
      - "Existing state remains reachable."
    expected_changes:
      - "Identity is coherent and explicit."
    prohibited_changes:
      - "No blind state key rename."
    acceptance_criteria:
      - "Repository-wide scan contains no unexplained identity mismatch."
      - "OIDC documentation uses the real repository claim."
    validation:
      targeted:
        - "Identity scan"
      integration:
        - "External policy review in Phase 6"
      regression:
        - "State key accessibility"
      expected_evidence:
        - "Identity inventory"
    rollback_or_recovery: "Restore prior metadata if external references break."
    risk: High
    risk_factors:
      - "OIDC mismatch"
      - "Remote state lookup failure"
    effort: Medium
    uncertainty: Medium
    parallelization: ParallelAfterPrerequisites
    postconditions:
      - "One canonical repository identity is documented."
    closes_findings:
      - AUD-L9D-007
    status: Blocked

  - id: P4-03
    title: "Align architecture, security, and runbook documentation"
    objective: "Document release-owned configuration, atomic secret preparation, workflow permissions, and rollback."
    rationale: "Operators require exact behavior before lifecycle validation."
    category: Documentation
    priority: High
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Operational documentation"
    affected_artifacts:
      - "ARCHITECTURE.md"
      - "SECURITY.md"
      - "RUNBOOK.md"
      - "README.md"
      - "SPECIFICATION.md if required"
    prerequisites:
      - P4-01
      - P4-02
    inputs:
      - "Final implementation"
    actions:
      - "Document candidate release preparation."
      - "Document configuration promotion and rollback."
      - "Document secret retention and cleanup."
      - "Document OIDC job scope."
      - "Document failure and recovery procedures."
      - "Keep database recovery separate."
    preserved_invariants:
      - "No unsupported production-readiness claim."
    expected_changes:
      - "Docs match validated behavior."
    prohibited_changes:
      - "No speculative features."
    acceptance_criteria:
      - "Every operational step maps to an actual command or workflow."
      - "Rollback description includes runtime configuration."
    validation:
      targeted:
        - "Documentation-to-code review"
      integration:
        - "Runbook staging exercise"
      regression:
        - "Reference scan"
      expected_evidence:
        - "Alignment checklist"
    rollback_or_recovery: "Regenerate documentation after behavior changes."
    risk: Medium
    risk_factors:
      - "Operational drift"
    effort: Medium
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "Operators and agents share one accurate model."
    closes_findings:
      - AUD-L9D-006
      - AUD-L9D-007
    status: Proposed

  - id: P5-01
    title: "Run exact-revision local validation"
    objective: "Prove implementation and documentation against the exact final source state."
    rationale: "Closes the local portion of AUD-L9D-001 and AUD-L9D-005."
    category: Validation
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Repository validation"
    affected_artifacts:
      - "Complete source tree"
    prerequisites:
      - P4-03
    inputs:
      - "Final implementation revision"
      - "Repository-native validation commands"
    actions:
      - "Run all mandatory repository-native tests and contract checks."
      - "Run workflow validation."
      - "Run shell syntax and behavior tests."
      - "Run secret-canary scan."
      - "Inspect complete diff and phase file counts."
      - "Record exact SHA and tool versions."
    preserved_invariants:
      - "No test weakening or unauthorized skip."
    expected_changes:
      - "None except test-owned ephemeral state."
    prohibited_changes:
      - "No scanner or linter installation solely for this plan."
    acceptance_criteria:
      - "All mandatory existing and new checks pass."
      - "No secret leakage."
      - "No phase exceeds 20 changed files."
    validation:
      targeted:
        - "All new tests"
      integration:
        - "Full repository test suite"
      regression:
        - "Existing validation"
      expected_evidence:
        - "Command outputs"
        - "SHA"
        - "Coverage"
        - "Canary report"
    rollback_or_recovery: "Failed validation blocks merge."
    risk: Low
    risk_factors:
      - "Stale or skipped checks"
    effort: Medium
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "Exact source state has current local evidence."
    closes_findings:
      - AUD-L9D-001
      - "Local portion of AUD-L9D-005"
    status: Proposed

  - id: P5-02
    title: "Regenerate governed release evidence"
    objective: "Align manifests, checksums, traceability, and release evidence with the final validated source."
    rationale: "Generated artifacts must follow authoritative source changes."
    category: Packaging
    priority: High
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Generated evidence"
    affected_artifacts:
      - "MANIFEST.md"
      - "FINAL_TREE.md"
      - "TRACEABILITY_MAP.yaml"
      - "GAP_DEFECT_MATRIX.yaml"
      - "checksums.sha256"
      - "validation/evidence"
    prerequisites:
      - P5-01
    inputs:
      - "Validated final source"
      - "Supported generators"
    actions:
      - "Use existing generation mechanisms."
      - "Regenerate derived artifacts."
      - "Verify source-to-generated alignment."
      - "Split into generation-only subphases if more than 20 tracked files change."
    preserved_invariants:
      - "Generated files remain derived."
    expected_changes:
      - "Fresh release evidence."
    prohibited_changes:
      - "No manual editing of generated output as source."
    acceptance_criteria:
      - "Checksums match."
      - "Tree and manifest match tracked files."
      - "No stale claim remains."
    validation:
      targeted:
        - "Generator checks"
      integration:
        - "Release-pack validation"
      regression:
        - "Deterministic regeneration"
      expected_evidence:
        - "Generated diff"
        - "Checksum verification"
    rollback_or_recovery: "Regenerate from the prior source revision."
    risk: Medium
    risk_factors:
      - "Stale or misleading evidence"
    effort: Medium
    uncertainty: Low
    parallelization: Sequential
    postconditions:
      - "Generated evidence matches validated source."
    closes_findings:
      - AUD-L9D-001
    status: Proposed

  - id: P6-01
    title: "Prove the complete protected staging lifecycle"
    objective: "Validate OIDC, deployment, configuration promotion, failure containment, rollback, receipts, and leakage controls."
    rationale: "Closes AUD-L9D-005 and provides release-readiness evidence."
    category: Release
    priority: Critical
    necessity: Required
    confidence: Confirmed
    owner_boundary: "Staging operations"
    affected_artifacts:
      - "Protected staging environment"
      - "Staging runner"
      - "Staging Infisical identity"
      - "Staging host"
      - "Deployment and rollback receipts"
    prerequisites:
      - P5-02
      - U-04 resolved
      - U-05 resolved
    inputs:
      - "Immutable staging image"
      - "Approved plan"
      - "Reversible test secrets"
    actions:
      - "Verify unauthorized jobs cannot obtain OIDC identity."
      - "Deploy a healthy candidate."
      - "Verify active state identifies the candidate env and image."
      - "Inject invalid secret material and prove no active mutation."
      - "Inject post-activation health failure and prove rollback restores image, env, state, and health."
      - "Perform secret-only rotation with unchanged image digest."
      - "Verify receipts and logs contain no canary secret."
      - "Review Infisical access logs."
    preserved_invariants:
      - "No production target."
      - "No customer secret."
    expected_changes:
      - "Temporary controlled staging mutations."
    prohibited_changes:
      - "No production promotion."
    acceptance_criteria:
      - "All staging scenarios pass."
      - "Unauthorized OIDC attempts fail."
      - "Rollback convergence is proven."
      - "Zero secret leakage."
    validation:
      targeted:
        - "Staging OIDC and deployment probes"
      integration:
        - "Complete lifecycle"
      regression:
        - "Prior stable staging release remains recoverable"
      expected_evidence:
        - "Workflow run IDs"
        - "Plan digest"
        - "Deployment receipt"
        - "Rollback receipt"
        - "Health evidence"
        - "Infisical access log"
        - "Canary scan"
    rollback_or_recovery: "Restore the prior staging release and revoke the staging identity if trust behavior is incorrect."
    risk: High
    risk_factors:
      - "Live infrastructure mutation"
      - "Credential and secret exposure"
      - "Rollback failure"
    effort: Large
    uncertainty: High
    parallelization: MustBeAtomic
    postconditions:
      - "The corrected implementation is eligible for a separate release decision."
    closes_findings:
      - AUD-L9D-004
      - AUD-L9D-005
    status: Blocked

execution_waves:
  - id: W-00
    plan_items:
      - P0-01
    reason: "Baseline must precede all mutation."
    entry_conditions:
      - "Repository checkout available."
    write_conflict_checks:
      - "Read-only."
    integration_checkpoints:
      - "Snapshot comparison."
    exit_conditions:
      - "Exact revision bound."
    failure_and_rollback: "Stop; no mutation occurred."

  - id: W-01
    plan_items:
      - P1-01
      - P1-02
      - P1-03
      - P1-04
    reason: "Contract and primitive must be completed as one bounded phase."
    entry_conditions:
      - "P0-01 complete."
      - "D-02 approved."
    write_conflict_checks:
      - "Single owner for runtime env path and state contract."
    integration_checkpoints:
      - "Phase 1 targeted tests."
      - "Maximum 20 files."
    exit_conditions:
      - "Atomic candidate env primitive validated."
    failure_and_rollback: "Revert Phase 1 as a unit."

  - id: W-02
    plan_items:
      - P2-01
      - P2-02
      - P2-03
      - P2-04
    reason: "Transaction ordering must be integrated sequentially."
    entry_conditions:
      - "W-01 passed."
    write_conflict_checks:
      - "Exclusive ownership of engine, promotion, and rollback files."
    integration_checkpoints:
      - "Failure injection before promotion."
      - "Failure injection after activation."
    exit_conditions:
      - "Rollback convergence validated."
    failure_and_rollback: "Revert execution transaction changes; retain Phase 1 primitive unused."

  - id: W-03
    plan_items:
      - P3-01
      - P3-02
      - P3-03
    reason: "Workflow correction is isolated after CLI and execution behavior stabilizes."
    entry_conditions:
      - "W-02 passed."
    write_conflict_checks:
      - "Ignore deprecated CI PR changes."
    integration_checkpoints:
      - "Workflow test matrix."
    exit_conditions:
      - "Functional least-privilege deployment workflow."
    failure_and_rollback: "Revert workflow patch."

  - id: W-04
    plan_items:
      - P4-01
      - P4-02
      - P4-03
    reason: "Documentation follows stable implementation; identity alignment has a separate decision."
    entry_conditions:
      - "W-02 and W-03 passed."
      - "D-01 approved before P4-02."
    write_conflict_checks:
      - "Coordinate root documentation ownership."
    integration_checkpoints:
      - "Documentation alignment review."
    exit_conditions:
      - "Agent and operator documentation complete."
    failure_and_rollback: "Revert or regenerate inaccurate documentation."

  - id: W-05
    plan_items:
      - P5-01
      - P5-02
    reason: "Validation precedes generation; generated output follows authoritative sources."
    entry_conditions:
      - "W-04 passed."
    write_conflict_checks:
      - "No manual generated-file edits."
    integration_checkpoints:
      - "Full validation."
      - "Release evidence verification."
    exit_conditions:
      - "Exact final source and evidence aligned."
    failure_and_rollback: "Block merge and regenerate after corrections."

  - id: W-06
    plan_items:
      - P6-01
    reason: "Live staging lifecycle must execute atomically."
    entry_conditions:
      - "W-05 passed."
      - "Protected staging available."
    write_conflict_checks:
      - "Exclusive staging deployment lock."
    integration_checkpoints:
      - "After successful deployment."
      - "After invalid secret attempt."
      - "After health-failure rollback."
      - "After secret rotation."
    exit_conditions:
      - "Independent staging evidence accepted."
    failure_and_rollback: "Restore prior staging release and revoke test identity if required."

critical_path:
  chain:
    - P0-01
    - D-02
    - P1-01
    - P1-02
    - P1-03
    - P1-04
    - P2-01
    - P2-02
    - P2-03
    - P2-04
    - P3-01
    - P3-02
    - P3-03
    - P4-01
    - P4-03
    - P5-01
    - P5-02
    - P6-01
  blockers:
    - U-01
    - D-02
    - U-03
    - U-04
    - U-05
  noncritical_decision:
    - "D-01 may complete before Phase 4 but must complete before release evidence regeneration."

validation_matrix:
  - item: P1-01
    validation:
      - "Old and new state fixture compatibility"
      - "No secret-bearing fields"
    pass_criteria: "Existing state loads; new state round-trips."
    evidence: "Contract test output"

  - item: P1-03
    validation:
      - "Atomic destination replacement"
      - "Duplicate and malformed-key rejection"
      - "Permission and redaction tests"
    pass_criteria: "Destination changes only on complete valid input."
    evidence: "Security test output"

  - item: P2-02
    validation:
      - "Pre-promotion failure injection"
    pass_criteria: "Active state remains unchanged."
    evidence: "Transaction event trace"

  - item: P2-04
    validation:
      - "Post-activation health failure"
      - "Rollback convergence"
    pass_criteria: "Prior image, env, state, and health restored."
    evidence: "Integration test state comparison"

  - item: P3-02
    validation:
      - "Workflow permissions parser"
      - "OIDC negative tests"
    pass_criteria: "Only deploy job can request OIDC."
    evidence: "Workflow test and staging identity logs"

  - item: P4-01
    validation:
      - "Agent guide alignment review"
    pass_criteria: "No undocumented or overbroad authority."
    evidence: "Documentation checklist"

  - item: P5-01
    validation:
      - "Full repository-native validation"
      - "Secret-canary scan"
      - "Diff and phase file-count review"
    pass_criteria: "All mandatory checks pass at exact SHA."
    evidence: "Validation bundle"

  - item: P6-01
    validation:
      - "Protected staging lifecycle"
    pass_criteria: "Deploy, failure containment, rollback, rotation, and leakage checks pass."
    evidence: "Workflow runs and receipts"

rollback_and_recovery:
  phase_1:
    rollback: "Revert additive contract, release-layout, script, and test changes as one unit."
    recovery: "Continue using the existing deployment path only in non-production environments."
  phase_2:
    rollback: "Revert execution integration while retaining unused Phase 1 primitives."
    recovery: "Do not deploy until transaction regression tests pass."
  phase_3:
    rollback: "Restore previous functional workflow permissions before staging."
    recovery: "Disable deployment workflow if OIDC restrictions cannot be proven."
  phase_4:
    rollback: "Revert documentation and metadata only."
    recovery: "Do not change persisted external identifiers without a separate migration."
  phase_5:
    rollback: "Regenerate evidence from the prior authoritative source revision."
    recovery: "Never hand-edit checksums or manifests to force alignment."
  phase_6:
    rollback: "Restore the prior staging release and revoke staging identity."
    recovery:
      - "Use explicit database recovery runbook if migration state changed."
  irreversible_steps:
    - "Publishing a secret-bearing receipt or archive"
    - "Renaming remote-state keys without migration"
    - "Promoting to production"
  controls:
    - "Secret-canary scans"
    - "Generated-evidence validation"
    - "Separate production authorization"

risk_register:
  - id: R-01
    risk: "Historical secret snapshots remain in old release directories."
    likelihood: Possible
    impact: High
    affected_items:
      - P1-02
      - P2-04
    mitigation:
      - "Restrictive ownership and mode"
      - "Bounded retention"
      - "Exclude from archives"
    detection:
      - "Filesystem and archive tests"
    rollback: "Delete unneeded retired release directories according to policy."
    owner: "Execution owner"

  - id: R-02
    risk: "Rollback uses expired previous credentials."
    likelihood: Possible
    impact: High
    affected_items:
      - P2-04
      - P6-01
    mitigation:
      - "Credential overlap during rotation where supported"
      - "Health verification"
      - "Explicit recovery runbook"
    detection:
      - "Rollback health failure"
    rollback: "Issue replacement credential or rotate provider value back."
    owner: "Operations owner"

  - id: R-03
    risk: "State schema change breaks existing deployments."
    likelihood: Possible
    impact: High
    affected_items:
      - P1-01
    mitigation:
      - "Additive field"
      - "Old-state fixture tests"
    detection:
      - "Compatibility suite"
    rollback: "Revert field before release."
    owner: "Contract owner"

  - id: R-04
    risk: "Workflow permission correction prevents valid deployment."
    likelihood: Possible
    impact: Medium
    affected_items:
      - P3-02
    mitigation:
      - "Job-scoped permission"
      - "Protected staging OIDC test"
    detection:
      - "OIDC exchange failure"
    rollback: "Revert workflow patch before production use."
    owner: "Workflow owner"

  - id: R-05
    risk: "Repository identity cleanup breaks OIDC or state lookup."
    likelihood: Possible
    impact: High
    affected_items:
      - P4-02
    mitigation:
      - "Inventory persisted references"
      - "Compatibility mappings"
    detection:
      - "OIDC and state-access tests"
    rollback: "Restore legacy identifiers."
    owner: "Platform architecture owner"

leverage_analysis:
  highest_leverage_dependency_unlock:
    item: P0-01
    reason: "Exact baseline unlocks safe mutation and current validation."

  highest_leverage_root_cause_repair:
    items:
      - P1-02
      - P2-03
      - P2-04
    reason: "Release-owned configuration resolves deployment divergence, rollback inconsistency, and secret-rotation safety."

  highest_leverage_scope_reduction:
    action: "Exclude generalized CI, scanners, linters, and deprecated PR work."
    benefit: "Keeps the correction focused on functional deployment safety."

  highest_leverage_validation_addition:
    item: P6-01
    reason: "One failure-injection staging lifecycle proves the full control path."

  justified_automation:
    - "Atomic materialization regression test"
    - "Job-level OIDC permission test"
    - "Secret-canary scan"
    - "Rollback convergence test"

lifecycle_plan:
  integration_target: "Current main branch after exact baseline binding"
  review_requirements:
    - "Execution and rollback review"
    - "Security review for secret materialization and OIDC"
    - "Contract review for state compatibility"
    - "Documentation review for agent authority"
  commit_strategy:
    - "One coherent commit or small commit series per phase"
    - "Do not combine unrelated dependency or CI work"
    - "Generated evidence in its own generation commit"
  merge_requirements:
    - "All phase validation passes"
    - "No phase exceeds 20 changed files"
    - "All required reviews complete"
    - "No unresolved High implementation finding"
    - "Exact source revision recorded"
  packaging_requirements:
    - "Deterministic source archive"
    - "Fresh manifest and checksums"
    - "No secret files included"
  release_requirements:
    - "Protected staging lifecycle passes"
    - "OIDC claim policy verified"
    - "Rollback convergence independently reviewed"
  deployment_requirements:
    - "Separate explicit production authorization"
    - "Immutable image digest"
    - "Approved plan digest"
    - "Protected production environment"
    - "Known rollback release"
  rollback_triggers:
    - "Secret leakage"
    - "Configuration/image divergence"
    - "Health failure"
    - "OIDC claim mismatch"
    - "State publication failure"
    - "Receipt integrity failure"

plan_quality_gates:
  target_and_objective_bound: Unknown
  authority_resolved: Passed
  current_state_understood: Passed
  requirements_and_contracts_defined: Passed
  scope_bounded: Passed
  ownership_clear: Passed
  architecture_aligned: Passed
  root_cause_strategy: Passed
  task_decomposition_complete: Passed
  dependencies_valid: Passed
  plan_items_executable: Unknown
  contracts_preserved_or_authorized: Passed
  validation_complete: Passed
  security_and_risk_addressed: Passed
  rollback_and_recovery_defined: Passed
  unknowns_and_decisions_explicit: Passed
  leverage_justified: Passed
  no_scope_drift: Passed
  plan_convergence_verified: Passed
  handoff_ready: Unknown
  overall_plan_readiness: Unknown
  explanation: >-
    The plan has converged and is implementation-complete, but exact target
    revision U-01 and architecture decision D-02 must be resolved before the
    first mutation item may be marked Ready.

implementation_handoff:
  downstream_profile: CHANGE
  required_authorization:
    - "Writable checkout of Quantum-L9/l9-deploy"
    - "Exact baseline SHA"
    - "Approval of D-02"
    - "Authorization to implement Phase 1"
  first_executable_item: P0-01
  first_mutation_item_after_prerequisites: P1-01
  blocking_decisions:
    - D-02
  deferred_decisions:
    - D-01
  phase_rules:
    - "Maximum 20 modified or created files per phase."
    - "Print repository tree before every phase."
    - "Mark paths as built, being built, to be built, preserved, or excluded."
    - "Run targeted validation before advancing."
    - "Do not begin the next phase while the current phase has failed or unknown mandatory validation."
  plan_revision: "L9-DEPLOY-REMEDIATION-PLAN-V2"
  implementation_started: false

minimum_safe_next_action:
  action: >-
    Bind an exact Git checkout of Quantum-L9/l9-deploy and record its commit SHA,
    branch, clean working-tree state, and complete tracked-file tree.
  resolves:
    - U-01
    - P0-01
    - "Target-and-objective binding gate"
  expected_evidence:
    - "git rev-parse HEAD"
    - "git branch --show-current"
    - "git status --short"
    - "git ls-files"

convergence:
  status: Converged
  completed_planning_passes:
    - "Converted all confirmed audit findings into correction items."
    - "Prioritized release-owned runtime configuration before contract expansion."
    - "Separated minimum functional workflows from deferred CI."
    - "Added agent documentation to the documentation phase."
    - "Bound every phase to a 20-file maximum."
    - "Defined phase trees, dependencies, validation, rollback, and staging lifecycle."
    - "Rejected duplicate secret frameworks and broad rewrites."
  skipped_passes:
    - pass: "Exact file enumeration per implementation phase"
      reason: "Requires the exact Git checkout and current tree."
    - pass: "Command-level validation binding"
      reason: "Repository-native commands must be confirmed from the exact checkout."
  remaining_material_planning_work: []
  evidence: >-
    The plan covers every confirmed audit finding, has no unresolved dependency
    cycle, defines closing validation for all required work, and limits remaining
    Unknowns to explicit implementation or release prerequisites.