# MLflow-Inference Cutover Cleanup Phase 8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove obsolete MLflow Gateway inference control-plane artifacts and duplicated routing lifecycle code while preserving MLflow exclusively as the trace/artifact backend and keeping Lima/k3s plus AgentGateway lifecycle coverage authoritative.

**Architecture:** Treat AgentGateway as the sole inference endpoint and retain MLflow, its SQLite PVC, artifact destination, and OpenTelemetry path only for telemetry and artifacts. Delete the old MLflow Gateway desired-state/reconciler/bootstrap surface, simplify `devcluster up` to the already-validated Lima/k3s → migration → telemetry/runtime → AgentGateway lifecycle, and update tests/docs/env examples to assert the new boundary rather than the removed implementation.

**Tech Stack:** Kubernetes Kustomize, Lima, k3s, POSIX shell, Python/pytest, OpenCode JSONC, Caddy documentation/configuration.

**Spec:** User request: cleanup phase 8 of the successful MLflow-inference to standalone AgentGateway cutover.

## Global Constraints

- AgentGateway is already deployed and validated; do not redesign its routes, models, secret boundary, or endpoint.
- MLflow remains for OpenCode traces and artifacts only; retain its SQLite backend, artifact destination, PVC, service, and OTel integration.
- Remove MLflow Gateway config, reconciler, bootstrap artifacts, duplicated gateway files, MLflow-inference tests/docs, and obsolete inference environment variables.
- Consolidate lifecycle tests around Lima/k3s and AgentGateway; preserve migration safety and writer-stop ordering.
- Do not delete or recreate the bound `ai-dev/mlflow-pvc`; retain `storageClassName: local-path` in every relevant manifest.
- Do not expose, print, commit, or inspect credential contents; retain only existing bounded secret/file interfaces.
- This plan is documentation only: implementation must separately be approved/executed; no deployment, commit, or publication is part of this phase.

## Review Focus

- MLflow remains reachable for tracing and artifact persistence after inference cleanup; pin via manifest and trace tests.
- AgentGateway is the only inference provider/model surface; pin via OpenCode/manifests and absence tests.
- `devcluster up` cannot reference deleted MLflow Gateway Jobs, scripts, APIs, or secrets; pin via command-order and static tests.
- Migration still runs with MLflow/OTel writers stopped and before runtime startup; pin via lifecycle tests.
- Obsolete variables are removed without deleting telemetry variables such as `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_ID`, and `x-mlflow-experiment-id`; pin via bounded env/doc scans.

---

### Task 1: Inventory and classify cleanup artifacts before editing

**Files:**
- Inspect only: `.config/k8s/`, `.config/dotfiles/tests/`, `.config/lima/`, `.config/opencode/`, `.config/caddy/`, `.local/bin/devcluster`, related `docs/` plans/readmes.
- Expected deletion candidates to confirm from the tracked tree: `.config/mlflow/gateway.yaml`, `.local/bin/mlflow-gateway-sync`, `.config/k8s/gateway-bootstrap/`, and any duplicated gateway manifests/configuration discovered in the bounded paths.

**Interfaces:**
- Consumes: current AgentGateway manifests, MLflow telemetry manifests, lifecycle script/tests, and prior cutover plans.
- Produces: an implementation checklist naming each obsolete artifact, each retained MLflow telemetry artifact, and each retained AgentGateway artifact. No product files are changed in this task.

- [ ] **Step 1: Search bounded paths for obsolete control-plane names and inference variables**

Run bounded searches for `mlflow-gateway`, `gateway-bootstrap`, `MLFLOW_GATEWAY`, `MLFLOW_INFERENCE`, `MLFLOW_INFER`, `ai-factory-secrets`, direct MLflow Gateway API paths, and duplicated gateway filenames. Separately search for retained telemetry names (`MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_ID`, `OPENCODE_OTLP`, `x-mlflow-experiment-id`, `artifacts-destination`).

- [ ] **Step 2: Classify every match**

Mark each match as delete, update, or retain. Delete only inference/control-plane material; retain MLflow tracking/artifact and OTel material, AgentGateway manifests/configuration, Lima/k3s configuration, MCP resources, and existing credential boundaries.

- [ ] **Step 3: Record the bounded file map in the implementation review**

The implementer must use the confirmed map to avoid speculative refactors or touching unrelated dotfile roles.

**Acceptance criteria:** The cleanup set is explicit, no `.env` secret file is read or altered, and the implementation has a verified list of retained telemetry and AgentGateway contracts.

---

### Task 2: Remove MLflow Gateway control-plane and duplicated inference artifacts

**Files:**
- Delete: confirmed `.config/mlflow/gateway.yaml` (if present).
- Delete: confirmed `.local/bin/mlflow-gateway-sync` (if present).
- Delete: confirmed `.config/k8s/gateway-bootstrap/` Kustomization/Job manifests (if present).
- Modify/Delete: any duplicated gateway manifests or old MLflow-inference configuration discovered under the bounded paths, while retaining canonical `.config/k8s/base/agentgateway.yaml` and `.config/k8s/base/agentgateway-deployment.yaml`.
- Modify: `.config/k8s/kustomization.yaml`, `.config/k8s/base/kustomization.yaml`, `.config/k8s/runtime/kustomization.yaml`, and `.local/bin/devcluster` only where references to removed bootstrap/reconciler resources exist.

**Interfaces:**
- Consumes: canonical AgentGateway deployment/config and existing migration/runtime overlays.
- Produces: a renderable Kustomize tree with no MLflow Gateway bootstrap/reconciler dependency and a lifecycle script that invokes only cluster-native Lima/k3s operations plus canonical AgentGateway runtime resources.

- [ ] **Step 1: Add/update negative manifest and lifecycle assertions before deletion**

Extend the focused tests to assert that root/runtime renders contain AgentGateway plus MLflow/OTel telemetry resources, but contain no `mlflow-gateway-bootstrap`, Gateway reconciler ConfigMap/script, MLflow Gateway API URL, or `ai-factory-secrets` unless a retained AgentGateway contract explicitly requires a similarly named key (do not conflate the two).

- [ ] **Step 2: Delete obsolete control-plane files and references**

Remove the confirmed desired-state YAML, reconciler executable, bootstrap Kustomization/Job, and only their references. Do not remove `.config/k8s/base/agentgateway.yaml`, its Deployment, AgentGateway PVC, or canonical AgentGateway secret wiring.

- [ ] **Step 3: Preserve MLflow telemetry/artifact configuration**

Verify that `.config/k8s/base/mlflow.yaml` retains MLflow v3.17.0, SQLite backend, `/mlflow/artifacts`, `mlflow-pvc`, service/node port, and readiness probes; no inference-specific MLflow arguments or environment variables may be introduced.

- [ ] **Step 4: Render and run focused manifest tests**

Run:
```bash
pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py -v
 devcluster-kubectl kustomize .config/k8s
 devcluster-kubectl kustomize .config/k8s/runtime
```

Expected: renders succeed; canonical AgentGateway and MLflow/OTel resources remain; removed control-plane resources are absent.

**Acceptance criteria:** No deleted artifact is referenced by Kustomize or `devcluster`; AgentGateway remains the sole inference deployment; MLflow telemetry/artifact manifests are unchanged except for removal of obsolete inference coupling.

---

### Task 3: Simplify `devcluster up` lifecycle around Lima/k3s, migration, telemetry, and AgentGateway

**Files:**
- Modify: `.local/bin/devcluster` symbols `cmd_up`, `wait_for_writers_to_stop`, `run_job_phase`, `wait_for_runtime`, `provision_agentgateway_secrets` as needed.
- Modify: `.config/dotfiles/tests/test_devcluster.py`.
- Modify: `.config/dotfiles/tests/conftest.py` only if obsolete MLflow Gateway environment cleanup is required.

**Interfaces:**
- Consumes: Lima/k3s kubeconfig synchronization, `mlflow-db-migrate`, canonical AgentGateway secret inputs, root safe base, and runtime overlay.
- Produces: deterministic lifecycle: namespace/Workspace secret → safe base → stop/wait MLflow and OTel writers → migration Job → AgentGateway secret → runtime overlay → MLflow/OTel/AgentGateway readiness, with no MLflow Gateway reconciliation phase.

- [ ] **Step 1: Rewrite lifecycle tests for the post-cutover order**

Replace assertions that expect `mlflow-gateway-bootstrap`, MLflow Gateway secrets, or reconciler commands with assertions for: root apply; writer termination; migration apply/complete/delete; AgentGateway secret creation from the existing required inputs; runtime apply; and readiness of `mlflow`, `otel-collector`, and `agentgateway`. Retain tests for migration failure, active/failed Job handling, redaction, exact Vertex source validation, `.env` fallback precedence, and no host-side `uv`/Python/`mlflow db` operations.

- [ ] **Step 2: Remove obsolete lifecycle phase and inputs**

Delete calls, waits, diagnostics, environment validation, or secret materialization that exist solely for MLflow Gateway reconciliation. Keep AgentGateway provider validation (`ENMAAS_*`, `OPENAI_API_KEY`, `VERTEX_*`, `AGENTGATEWAY_API_KEY`) and the exact read-only Vertex credential materialization contract.

- [ ] **Step 3: Keep migration safety invariant**

Ensure `cmd_up` applies the safe base, waits until MLflow and OTel writer Pods are gone, runs and cleans up `mlflow-db-migrate`, then starts runtime. A migration failure must prevent runtime and AgentGateway startup; a missing AgentGateway input must fail before runtime apply while leaving the migration phase behavior explicit and tested.

- [ ] **Step 4: Run focused lifecycle tests and shell validation**

Run:
```bash
pytest .config/dotfiles/tests/test_devcluster.py .config/dotfiles/tests/test_devcluster_kubectl.py -v
sh -n .local/bin/devcluster
```

Expected: all lifecycle order, safety, redaction, kubeconfig, and AgentGateway secret-boundary tests pass; shell syntax passes.

**Acceptance criteria:** Every `devcluster up` has no MLflow Gateway bootstrap/reconciler step, still protects the RWO MLflow migration, and reports readiness for MLflow telemetry, OTel, and AgentGateway.

---

### Task 4: Consolidate tests around AgentGateway and retain MLflow trace/artifact coverage

**Files:**
- Modify: `.config/dotfiles/tests/test_ai_infrastructure_manifests.py`.
- Modify/Delete: MLflow-inference-specific test files discovered under `.config/dotfiles/tests/` (for example old Gateway response/reconciler/manifest tests), while retaining `.config/dotfiles/tests/test_mlflow_traces.py`.
- Modify: `.config/dotfiles/tests/test_mlflow_traces.py` only to remove inference assumptions, never to remove trace/artifact verification.
- Modify: `.config/dotfiles/tests/conftest.py` only for obsolete variable cleanup.

**Interfaces:**
- Consumes: canonical AgentGateway manifests, OpenCode provider configuration, MLflow telemetry script/configuration, and the simplified lifecycle.
- Produces: one coherent test surface proving AgentGateway inference and MLflow telemetry independently.

- [ ] **Step 1: Remove MLflow-inference tests and obsolete fixtures**

Delete tests whose only purpose is MLflow Gateway desired-state reconciliation, management API contract, MLflow inference response routing, or bootstrap Job behavior. Remove fixtures/env cleanup that exists only for deleted variables. Do not delete tests for MLflow trace commands, experiment handling, artifacts, SQLite/artifact manifests, OTel, or AgentGateway.

- [ ] **Step 2: Strengthen AgentGateway manifest/config assertions**

Keep/assert canonical AgentGateway model aliases, route/fallback declarations, `agentgateway-secrets`, Vertex mounted-file boundary, SQLite request database, and OpenCode provider/model references. Assert no MLflow provider remains in `.config/opencode/opencode.jsonc` or agent frontmatter.

- [ ] **Step 3: Add explicit telemetry-only boundary tests**

Assert MLflow references that remain are limited to tracking/traces/artifacts/OTel: `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_ID`, OTLP headers, MLflow service/PVC/artifact destination, and `mlflow-traces`. Assert obsolete Gateway control-plane names and inference variables are absent from the bounded configuration and test paths.

- [ ] **Step 4: Run the consolidated test suite**

Run:
```bash
pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py \
  .config/dotfiles/tests/test_mlflow_traces.py \
  .config/dotfiles/tests/test_devcluster.py \
  .config/dotfiles/tests/test_devcluster_kubectl.py -v
```

Expected: AgentGateway inference, telemetry retention, and Lima/k3s lifecycle tests pass; deleted MLflow-inference tests are no longer collected.

**Acceptance criteria:** Test ownership matches the new architecture: AgentGateway owns inference tests; MLflow tests cover traces/artifacts only; lifecycle tests cover Lima/k3s, migration, telemetry writers, and AgentGateway.

---

### Task 5: Remove obsolete environment variables and update operational documentation

**Files:**
- Modify: `.config/k8s/env.example` (tracked example only; do not read or modify `.config/k8s/.env`).
- Modify: `.config/opencode/env.example`.
- Modify: `.config/k8s/README.md`.
- Modify: `.config/opencode/README.md`.
- Modify: `.config/dotfiles/README.md`.
- Modify: relevant `.config/caddy/sites/*.caddy` or examples only if they describe MLflow inference; retain MLflow telemetry/artifact proxying and canonical AgentGateway public endpoint.
- Archive or clearly mark obsolete prior plan references only if repository convention requires it; do not rewrite historical plans to falsify history.

**Interfaces:**
- Consumes: final manifest/lifecycle/test contracts from Tasks 2–4.
- Produces: operator documentation that describes AgentGateway as inference and MLflow as telemetry/artifacts, with no executable instructions for removed MLflow Gateway components.

- [ ] **Step 1: Remove obsolete example variables**

Remove only MLflow Gateway control-plane/inference variables such as `MLFLOW_GATEWAY_BASE_URL`, `MLFLOW_GATEWAY_API_KEY`, and any MLflow inference endpoint/model aliases. Retain `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_ID`, `OPENCODE_ENABLE_TELEMETRY`, OTLP endpoint/protocol/headers, resource attributes, and AgentGateway provider variables.

- [ ] **Step 2: Rewrite lifecycle and architecture docs**

Document the supported flow as Lima/k3s cluster creation, safe-base writer stop, MLflow DB migration, AgentGateway secret provisioning, runtime startup, and readiness validation. Remove bootstrap/reconciler commands, MLflow Gateway URLs, management API references, and MLflow inference troubleshooting.

- [ ] **Step 3: Preserve telemetry and artifact runbooks**

Keep MLflow trace/artifact usage, port-forward/debugging guidance, OTel routing, SQLite PVC/local-path safety, and warnings about sensitive telemetry logging. Make explicit that MLflow is not used for inference and AgentGateway is the only model API.

- [ ] **Step 4: Validate documentation/configuration references**

Run bounded searches:
```bash
rg -n 'mlflow-gateway|gateway-bootstrap|MLFLOW_GATEWAY|MLFLOW_INFERENCE|MLFLOW_INFER|mlflow inference|MLflow Gateway|ai-factory-secrets' \
  .config/k8s .config/dotfiles/tests .config/lima .config/opencode .config/caddy .local/bin/devcluster docs
rg -n 'MLFLOW_TRACKING_URI|MLFLOW_EXPERIMENT_ID|OPENCODE_OTLP|x-mlflow-experiment-id|artifacts-destination|AgentGateway' \
  .config/k8s .config/dotfiles/tests .config/opencode .config/caddy .local/bin/devcluster docs
```

Expected: first search returns no active implementation/docs references except intentionally preserved historical plan records or negative assertions; second search confirms retained telemetry and AgentGateway documentation.

**Acceptance criteria:** New operators cannot follow documentation into a removed MLflow inference path; telemetry/artifact and AgentGateway operational instructions remain complete and accurate.

---

### Task 6: Final bounded validation and safety review

**Files:**
- No new product files; review all files changed by Tasks 2–5.

**Interfaces:**
- Consumes: completed cleanup changes and consolidated tests/docs.
- Produces: evidence that the repository is internally consistent and safe to hand to the orchestrator for execution.

- [ ] **Step 1: Run all bounded regression tests**

Run:
```bash
pytest .config/dotfiles/tests -v
```

Expected: the full bounded suite passes, with no collection/import failures caused by removed MLflow-inference tests.

- [ ] **Step 2: Validate all relevant Kustomize renders**

Run:
```bash
devcluster-kubectl kustomize .config/k8s > /dev/null
devcluster-kubectl kustomize .config/k8s/runtime > /dev/null
devcluster-kubectl kustomize .config/k8s/migration > /dev/null
```

Expected: all renders succeed; no obsolete bootstrap resource appears; MLflow PVC remains `local-path`; AgentGateway, MLflow, OTel, and MCP resources remain represented.

- [ ] **Step 3: Perform static safety checks**

Run bounded checks for deleted paths, stale references, raw credential material, direct `kubectl` misuse in `devcluster`, and accidental host-side MLflow operations. Do not inspect `.config/k8s/.env`; use only tracked examples and source text.

- [ ] **Step 4: Verify explicit non-actions**

Confirm no deployment, cluster mutation, commit, push, publication, or modification outside the requested bounded paths occurred during implementation. Any live validation must be a separate orchestrator-approved phase after this plan.

**Acceptance criteria:** Test/render/static checks pass; AgentGateway remains the only inference path; MLflow remains telemetry/artifacts-only; no unsafe destructive recovery or deployment action is introduced.

## Optional Improvements (not required for Phase 8)

- Add a separate future plan for historical-plan archival/indexing if the repository needs a cleaner documentation history; do not rewrite accepted historical plans as though the old architecture never existed.
- Add a live disposable-cluster smoke test for AgentGateway requests and MLflow trace/artifact round trips, but keep it outside this cleanup plan because the current state is already deployed and validated and this request forbids deployment.

## Self-review

- Requirement coverage: Tasks 1–2 inventory and delete MLflow Gateway artifacts; Task 3 removes bootstrap lifecycle coupling; Task 4 consolidates tests; Task 5 removes obsolete variables/docs while preserving telemetry; Task 6 validates the bounded tree.
- Concrete boundaries: every task names exact paths/symbols, distinguishes canonical AgentGateway from obsolete gateway artifacts, and includes commands plus observable results.
- Safety: `.config/k8s/.env` is explicitly off-limits; no credential contents are inspected; no deployment, commit, or publication is planned; MLflow PVC/migration safety is preserved.
- Unresolved implementation choice: exact duplicated gateway files and exact MLflow-inference test/docs filenames must be confirmed by the implementer’s bounded inventory because several expected artifacts are already absent in the current checkout and historical plans still mention them.
