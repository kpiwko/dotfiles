# AgentGateway Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AgentGateway the authoritative resolved-model and cost telemetry source while retaining OpenCode session/tool tracing in MLflow.

**Architecture:** OpenCode uses an OpenAI-compatible provider and a native-Gemini provider, both pointed at AgentGateway. AgentGateway propagates W3C trace context and emits native LLM telemetry to the in-cluster OTel Collector, which maps realized-cost attributes into MLflow fields and exports every span to one fixed experiment.

**Tech Stack:** OpenCode V2, `@devtheops/opencode-plugin-otel`, AgentGateway v1.6.0, Kubernetes Kustomize, OpenTelemetry Collector, MLflow.

**Spec:** `docs/superpowers/specs/2026-10-12-agentgateway-telemetry-architecture.md`

## Global Constraints

- Do not inspect, rotate, commit, or modify credentials.
- `gemini` is direct Vertex Gemini 3.8 Flash only inside AgentGateway; it is never an automatic fallback.
- AgentGateway remains the sole inference endpoint; MLflow remains trace/artifact storage only.
- MLflow's SQLite backend, `mlflow-pvc`, `local-path`, and artifact configuration remain unchanged.
- Use the fixed existing MLflow experiment ID for both exporters; do not attempt dynamic per-session experiment headers.
- Do not deploy or publish as part of this implementation; live validation is a separately approved step.

## Review Focus

- New OpenCode sessions must select AgentGateway's native Gemini API while existing sessions retain their stored model selection.
- Native Gemini requests must use `models/{model}:generateContent` through AgentGateway and preserve multi-turn function-call continuations.
- AgentGateway tracing must preserve a single fixed `x-mlflow-experiment-id` header without leaking any secret into ConfigMaps.
- Gateway-to-collector OTLP must be accepted over an in-cluster port and must not require a new host NodePort.
- Cost mapping must prefer AgentGateway `agw.ai.usage.cost.*` fields and retain absent costs as absent rather than manufacturing zero costs.
- Enmaas cost entries must be marked unpriced until its billable rates are verified; a public upstream price is not a substitute for a reseller bill.

---

### Task 1: Add AgentGateway's native Gemini protocol adapter

**Files:**
- Modify: `.config/opencode/opencode.jsonc`
- Modify: `.config/opencode/agents/orchestrator.md`
- Modify: `.config/opencode/agents/plan.md`
- Modify: `.config/opencode/agents/orchestrator.md` permissions
- Modify: `.config/dotfiles/tests/test_ai_infrastructure_manifests.py`

**Interfaces:**
- Consumes: AgentGateway's existing public `gemini` alias and its native Gemini endpoint at `/v1beta/models/gemini:generateContent`.
- Produces: an `agentgateway-gemini/gemini` OpenCode model that uses the native Gemini wire format but remains routed through AgentGateway.

- [ ] **Step 1: Add failing agent-model assertions**

Update `test_opencode_agents_reference_only_agentgateway_models` to assert both provider definitions target AgentGateway and that:

```python
assert config["model"] == "agentgateway-gemini/gemini"
assert agent_models["orchestrator"] == "agentgateway-gemini/gemini"
assert agent_models["plan"] == "agentgateway-gemini/gemini"
assert "implement-local" not in orchestrator_permissions
assert "implement-maas" not in orchestrator_permissions
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py -v`

Expected: failure because the native Gemini provider and its model do not yet exist, the root/orchestrator/planner still select `agentgateway/worker`, and legacy delegation permissions remain.

- [ ] **Step 3: Update OpenCode model selection and permissions**

Define `agentgateway-gemini` with OpenCode's native Google runtime, a base URL ending in `/v1beta`, and AgentGateway bearer authentication. Define its `gemini` model with `modelID: "gemini"` and tool capability. The deployed AgentGateway endpoint is already validated for a native Gemini function-call continuation; validate the OpenCode adapter after the normal shared-service restart rather than creating a temporary standalone service.

Set the top-level `model` in `.config/opencode/opencode.jsonc` and the frontmatter model in `orchestrator.md` and `plan.md` to `agentgateway-gemini/gemini`. Remove only `implement-local` and `implement-maas` subagent permission exceptions from `orchestrator.md`; preserve the remaining delegation policy.

- [ ] **Step 4: Run the focused test and confirm it passes**

Run: `uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py -v`

Expected: PASS.

### Task 2: Add the AgentGateway-to-Collector trace path

**Files:**
- Modify: `.config/k8s/base/agentgateway.yaml`
- Modify: `.config/k8s/base/agentgateway-deployment.yaml`
- Modify: `.config/k8s/base/otel-collector.yaml`
- Modify: `.local/bin/devcluster`
- Modify: `.config/k8s/env.example`
- Modify: `.config/dotfiles/tests/test_ai_infrastructure_manifests.py`
- Modify: `.config/dotfiles/tests/test_devcluster.py`
- Modify: `.config/dotfiles/tests/test_otel_collector_manifests.py`

**Interfaces:**
- Consumes: `MLFLOW_EXPERIMENT_ID` as the existing fixed numeric MLflow experiment identifier.
- Produces: AgentGateway OTLP/gRPC exports to the in-cluster collector, carrying the same fixed experiment header as OpenCode telemetry.

- [ ] **Step 1: Add failing manifest/lifecycle assertions**

Assert that the Collector enables an OTLP gRPC receiver on `4317`, exposes it through the in-cluster Service, and keeps the existing HTTP/4318 NodePort unchanged. Assert that AgentGateway uses `frontendPolicies.tracing`, exports to `otel-collector.ai-dev.svc.cluster.local:4317`, and sets `x-mlflow-experiment-id` from `MLFLOW_EXPERIMENT_ID`. Assert the lifecycle materializes the non-secret `MLFLOW_EXPERIMENT_ID` in `agentgateway-secrets` and never logs its value.

- [ ] **Step 2: Run focused manifest/lifecycle tests and confirm they fail**

Run: `uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py .config/dotfiles/tests/test_otel_collector_manifests.py .config/dotfiles/tests/test_devcluster.py -v`

Expected: failure because AgentGateway tracing, Collector gRPC, and fixed-header secret wiring are absent.

- [ ] **Step 3: Configure the trace route**

In `agentgateway.yaml`, add `frontendPolicies.tracing` with gRPC host `otel-collector.ai-dev.svc.cluster.local:4317`, sampling enabled, and a request-header modifier setting `x-mlflow-experiment-id` from `$MLFLOW_EXPERIMENT_ID`. Add `MLFLOW_EXPERIMENT_ID` to the existing `agentgateway-secrets` provisioning and Deployment environment. Add `MLFLOW_EXPERIMENT_ID=` to the tracked Kubernetes example.

In `otel-collector.yaml`, add the gRPC OTLP receiver on `0.0.0.0:4317` with metadata enabled and add a ClusterIP Service port for 4317. Preserve HTTP/4318 NodePort 17903 for OpenCode.

- [ ] **Step 4: Run focused tests and render validation**

Run:

```bash
uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py .config/dotfiles/tests/test_otel_collector_manifests.py .config/dotfiles/tests/test_devcluster.py -v
devcluster-kubectl kustomize .config/k8s
devcluster-kubectl kustomize .config/k8s/runtime
```

Expected: tests and renders pass; no additional public NodePort is added.

### Task 3: Attribute realized AgentGateway cost without alias-priced telemetry

**Files:**
- Modify: `.config/opencode/opencode.jsonc`
- Modify: `.config/k8s/base/otel-collector.yaml`
- Create: `.config/k8s/base/agentgateway-cost-overrides.json` only after rates are verified
- Modify: `.config/k8s/base/kustomization.yaml` only if the override file is loaded through a ConfigMap
- Modify: `.config/dotfiles/tests/test_ai_infrastructure_manifests.py`
- Modify: `.config/dotfiles/tests/test_otel_collector_manifests.py`

**Interfaces:**
- Consumes: AgentGateway trace attributes `agw.ai.usage.cost.total`, `agw.ai.usage.cost.input`, and `agw.ai.usage.cost.output` when a catalog lookup is priced.
- Produces: MLflow `mlflow.llm.cost` with realized components and no misleading OpenCode alias cost metrics.

- [ ] **Step 1: Add failing collector/OpenCode assertions**

Assert that the OTel plugin enables W3C propagation for both `agentgateway` and `agentgateway-gemini` and disables its `cost.usage`, `session.cost.total`, and `model.usage` metrics. Assert collector transformations read AgentGateway cost attributes before the existing legacy `cost_usd` fallback and do not substitute zero for a missing AgentGateway cost.

- [ ] **Step 2: Run focused tests and confirm they fail**

Run: `uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py .config/dotfiles/tests/test_otel_collector_manifests.py -v`

Expected: failure because OpenCode has no propagation/cost policy and the Collector has no AgentGateway cost mapping.

- [ ] **Step 3: Configure trace propagation and cost mapping**

Add `tracePropagationProviders: ["agentgateway", "agentgateway-gemini"]` plus disabled alias-cost metrics to the OTel plugin options in `opencode.jsonc`.

In the Collector transform, map AgentGateway's `agw.ai.usage.cost.total` to `gen_ai.usage.cost` and construct `mlflow.llm.cost` from its available input/output/total components. Keep the legacy `cost_usd` and `session.total_cost_usd` paths only as fallbacks. Never write a zero-valued cost object when no cost attribute exists.

- [ ] **Step 4: Verify catalog lookup identity before adding rates**

After separate deployment approval, issue one request per AgentGateway route and inspect `agentgateway_cost_catalog_lookups_total` and the exported trace attributes. Record the actual provider/model label pairs. Add a tracked override only for pairs reported as `Missing` or `Unpriced` and only with Enmaas rates confirmed from its billing contract; do not substitute public OpenAI/Vertex prices for Enmaas billing.

- [ ] **Step 5: Run focused tests**

Run: `uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py .config/dotfiles/tests/test_otel_collector_manifests.py -v`

Expected: PASS. Cost overlay assertions are added only if the verified rate file exists.

### Task 4: Document and validate the fixed-experiment architecture

**Files:**
- Modify: `.config/k8s/README.md`
- Modify: `.config/opencode/README.md`
- Modify: `.config/opencode/env.example`
- Modify: `.config/dotfiles/tests/test_mlflow_traces.py` only if existing examples need a fixed-experiment clarification

**Interfaces:**
- Consumes: Tasks 1–3 configuration contracts.
- Produces: operational documentation explaining correlated OpenCode/AgentGateway spans, cost ownership, fixed experiment routing, and required OpenCode restart/new-session behavior.

- [ ] **Step 1: Add documentation contract assertions**

Add focused assertions for the documented `agentgateway` trace propagation provider, one fixed MLflow experiment header, AgentGateway as cost authority, and the statement that per-session experiments are unsupported by the shared service.

- [ ] **Step 2: Run documentation assertions and confirm they fail**

Run: `uv run --project .config/dotfiles pytest .config/dotfiles/tests/test_ai_infrastructure_manifests.py .config/dotfiles/tests/test_mlflow_traces.py -v`

Expected: failure because the new operational contract is not documented.

- [ ] **Step 3: Update operator documentation**

Document the two exporters, W3C correlation, AgentGateway cost ownership, cost-catalog verification, and fixed experiment rule in `.config/k8s/README.md`. Document both OpenCode protocol adapters, native Gemini function-call rationale, disabled alias cost metrics, trace propagation, and need for a new session/service restart in `.config/opencode/README.md`. Update `env.example` comments without adding credentials or a hard-coded numeric experiment ID.

- [ ] **Step 4: Run complete bounded validation**

Run:

```bash
uv run --project .config/dotfiles pytest .config/dotfiles/tests
sh -n .local/bin/devcluster
devcluster-kubectl kustomize .config/k8s
devcluster-kubectl kustomize .config/k8s/runtime
devcluster-kubectl kustomize .config/k8s/migration
```

Expected: all tests and Kustomize renders pass.

### Post-implementation live validation (separately approved)

Restart the shared OpenCode service once after the configuration is installed, start a new session, and select the default `agentgateway-gemini/gemini` model. Run one native Gemini function-call continuation through OpenCode. This validates the OpenCode provider adapter without disrupting the session that performed the implementation.

## Self-review

- Spec coverage: Tasks 1–4 cover model selection, trace correlation, AgentGateway-native cost attribution, fixed experiment routing, and the two requested operational documents.
- Rate safety: the plan does not invent Enmaas cost rates. It exposes catalog status and adds rates only after confirmation from the actual billing contract.
- Scope: no task deploys, publishes, rotates credentials, changes MLflow storage, or enables Gemini fallback.
