# MLflow AI Gateway Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the cloud OpenCode agents through the MLflow 3.16.1 AI Gateway at `https://mlflow.fous.ai`, using declarative EnMaaS primaries and Vertex AI fallbacks where available, while preserving local/LiteMaaS agents and the existing `vertex-dprod-opencode-opus-5` endpoint.

**Architecture:** OpenCode uses an OpenAI-compatible `mlflow` provider whose base URL is `https://mlflow.fous.ai/gateway/mlflow/v1`. The gateway reconciler reads `.config/mlflow/gateway.yaml`, manages only the declared secrets, model definitions, and endpoints through MLflow's `/ajax-api/3.0/mlflow/gateway/*` APIs, and leaves unrelated endpoints untouched. Each cloud endpoint has a PRIMARY EnMaaS or original-provider model and a sequential Vertex fallback. Requests use the stable logical model names `mlflow/<agent>`; MLflow selects the configured provider model and records the request alongside existing OpenCode tracing.

**Tech Stack:** MLflow 3.16.1 AI Gateway, OpenAI-compatible Chat Completions, EnMaaS OpenAI-compatible API, Vertex AI, Python 3.12 / inline `uv` script, PyYAML, Requests, Pytest, OpenCode v2 JSONC configuration, k3s / Lima `devcluster`, Caddy.

**Spec:** Supplied implementation findings and agent mappings in the assignment context. The live gateway endpoint is `POST https://mlflow.fous.ai/gateway/mlflow/v1/chat/completions`; control-plane APIs are the verified `/ajax-api/3.0/mlflow/gateway/{secrets,model-definitions,endpoints}` list/create/delete/get/update routes.

## Global Constraints

- All Git operations must run via `sandbox-git` (operating on bare repo `~/.dotfiles` from `$HOME`).
- Gateway configuration is declarative and committed without credentials. Secret values come only from environment variables or an explicitly supplied secret file; never print or persist them.
- The reconciler must be idempotent, support `--check` and `--dry-run`, report drift, fail safely on API errors, and manage only resources identified by the declaration. It must never modify or delete `vertex-dprod-opencode-opus-5` or other unrelated endpoints.
- Endpoint names are stable: `mlflow/orchestrator`, `mlflow/architect`, `mlflow/plan`, `mlflow/implement`, `mlflow/review`, and `mlflow/zweistein`.
- Gateway model configurations use `linkage_type` `PRIMARY` or `FALLBACK`, `fallback_order`, `weight`, and `fallback_config: {strategy: SEQUENTIAL}`. The primary has weight 1; the sequential fallback is attempted after primary failure.
- EnMaaS models verified available include `gemini-3.8-flash`; it does not provide `gpt-5.6-luna`, `gpt-5.6-terra`, or Qwen models.
- OpenAI availability is an explicit exception: `implement`, `review`, and `zweistein` retain their original OpenAI provider as PRIMARY and add Vertex `gemini-3.8-flash` as FALLBACK. This exception must be called out in configuration and documentation.
- `implement-cloud` is consolidated into `implement`; update all delegation and permission references atomically so no stale agent name remains.
- `implement-local` remains `omlx/Qwen3-Coder-Next-6bit`; `implement-maas` remains `litemaas/Qwen3.8-27B-NT`.
- Live operations must use the established cluster/API wrappers and safe credential handling; do not alter, delete, or recreate the existing `vertex-dprod-opencode-opus-5` endpoint.

## Review Focus

1. **Non-destructive reconciliation:** Resource identity must be based on an explicit managed-name set or stable declaration metadata, not “all endpoints”; absent declared resources must not trigger broad deletion.
2. **Secret safety:** Configuration may name environment variables but must not contain API keys. Logs and `--check` output must redact secret values and authorization headers.
3. **Provider/model correctness:** EnMaaS model IDs must match the verified live list. OpenAI models must remain primary for the three unavailable-model agents, with the documented Vertex fallback exception.
4. **Fallback semantics:** Every managed cloud endpoint needs exactly one PRIMARY and one sequential FALLBACK, with deterministic order and no accidental duplicate model definitions.
5. **Drift and idempotency:** `--check` detects missing, extra, or changed managed resources; a normal sync converges the declaration; a second sync produces no changes.
6. **Agent migration safety:** OpenCode model IDs, agent front matter, orchestrator permissions, delegation prose, and README references must agree after `implement-cloud` is removed.
7. **Live safety:** Before applying changes, verify the protected endpoint exists and capture the pre-sync managed-resource inventory. Verify it is unchanged after sync.

---

### Task 1: Environment and Declarative Gateway Configuration Schema

**Files:**
- Modify: `.config/zsh/10-env.zsh`
- Modify: `.config/opencode/env.example`
- Create: `.config/mlflow/gateway.yaml`

**Interfaces:**
- Consumes: shell environment and provider credentials.
- Produces: documented MLflow/EnMaaS endpoint settings and a machine-readable gateway declaration.

- [x] **Step 1: Define non-secret environment variables**

Add live/defaultable settings to `.config/zsh/10-env.zsh` and placeholders to `.config/opencode/env.example`, including `MLFLOW_GATEWAY_BASE_URL=https://mlflow.fous.ai`, `MLFLOW_GATEWAY_API_KEY` (if required by the control plane), `ENMAAS_BASE_URL=https://api.enmaas.devshift.net/v1`, `ENMAAS_API_KEY`, `VERTEX_PROJECT`, and `VERTEX_LOCATION`. Keep existing provider variables compatible and do not add literal credentials to tracked files.

- [x] **Step 2: Define `.config/mlflow/gateway.yaml` schema and resources**

Declare schema/version, gateway URL, managed endpoint names, secret references, model definitions, and endpoint model configurations. Use provider/model pairs for:

| Agent endpoint | Primary | Fallback | OpenCode model |
| --- | --- | --- | --- |
| `orchestrator` | EnMaaS `gemini-3.8-flash` | Vertex `gemini-3.8-flash` | `mlflow/orchestrator` |
| `architect` | EnMaaS `gemini-3.8-flash` | Vertex `gemini-3.8-flash` | `mlflow/architect` |
| `plan` | EnMaaS `gemini-3.8-flash` | Vertex `gemini-3.8-flash` | `mlflow/plan` |
| `implement` | OpenAI `gpt-5.6-luna` | Vertex `gemini-3.8-flash` | `mlflow/implement` |
| `review` | OpenAI `gpt-5.6-luna` | Vertex `gemini-3.8-flash` | `mlflow/review` |
| `zweistein` | OpenAI `gpt-5.6-terra` | Vertex `gemini-3.8-flash` | `mlflow/zweistein` |

Document the unavailable-EnMaaS exception beside the OpenAI declarations. Model definitions must identify the provider's upstream model ID and secret reference; endpoint configurations must express PRIMARY/FALLBACK linkage, `fallback_order`, `weight`, and sequential fallback strategy.

- [x] **Step 3: Document local and LiteMaaS exclusions**

Make clear in the schema comments/documentation that `implement-local` and `implement-maas` are not managed by this gateway declaration and retain their current providers.

- [x] **Step 4: Validate the schema fixture**

Run the schema-focused tests from Task 3 and verify YAML parses, all six managed endpoints are present exactly once, all referenced model definitions and secrets resolve, and no credential-looking value is committed.

---

### Task 2: Declarative Gateway Reconciler Script

**Files:**
- Create: `.local/bin/mlflow-gateway-sync`

**Interfaces:**
- Consumes: `.config/mlflow/gateway.yaml`, environment-backed secrets, and MLflow gateway REST APIs.
- Produces: converged MLflow secrets, model definitions, and managed endpoints; read-only drift reports for `--check`.

- [x] **Step 1: Add inline `uv` script metadata and CLI**

Implement a self-contained Python script with inline dependencies (at minimum `pyyaml` and `requests`) and arguments `--config`, `--check`, `--dry-run`, `--verbose`, and an explicit `--yes` or equivalent guard for live mutation. Resolve the repository root/config path robustly and provide actionable errors for missing environment variables or malformed declarations.

- [x] **Step 2: Implement authenticated API client**

Implement typed request helpers for list/create/delete secrets, list/create/delete model definitions, and list/create/get/update/delete endpoints. Normalize response envelopes, status failures, retries/timeouts, and redacted diagnostics. Use the verified MLflow paths under `/ajax-api/3.0/mlflow/gateway/` and never send secrets in logs.

- [x] **Step 3: Implement safe resource identity and planning**

Build a desired-state plan for only the declared managed names. Compare normalized current and desired secrets, model definitions, and endpoint `model_configs`; classify create/update/no-op/drift. Treat `vertex-dprod-opencode-opus-5` as an immutable protected resource and abort if a declaration attempts to claim it.

- [x] **Step 4: Implement `--check` and `--dry-run`**

`--check` must be read-only and exit non-zero when managed resources drift or are missing, while ignoring unrelated endpoint differences. `--dry-run` must print redacted create/update actions without mutating MLflow. Both modes must be safe when the protected endpoint is present.

- [x] **Step 5: Implement idempotent, non-destructive apply**

Create or update declared secrets and model definitions before endpoints, then converge endpoint model configurations. Delete only stale resources explicitly marked as managed by the declaration, if deletion is required by the schema; never perform an unscoped delete and never touch unrelated endpoints. Ensure repeated execution produces no changes.

- [x] **Step 6: Add operational output and exit behavior**

Report resource counts and action summaries, identify the endpoint/model causing drift, return non-zero for validation/API failures, and keep credentials, bearer tokens, and secret payloads redacted. Include a usage/help example in the script header.

- [x] **Step 7: Validate against mocked APIs**

Run the Task 3 reconciler tests, including create/update/no-op plans, `--check` drift, `--dry-run` non-mutation, API failure handling, protected endpoint preservation, and unrelated endpoint preservation.

---

### Task 3: Pytest Test Suite

**Files:**
- Create: `.config/dotfiles/tests/test_mlflow_gateway.py`

**Interfaces:**
- Consumes: gateway YAML, env examples, sync script, and mocked MLflow HTTP responses.
- Produces: executable regression coverage for the declarative routing contract.

- [x] **Step 1: Test configuration schema and mappings**

Test that the YAML parses, declares all six cloud endpoints, uses the exact `mlflow/<agent>` names, has one PRIMARY and one FALLBACK per endpoint, uses sequential fallback metadata, references only declared secret/model IDs, and records the OpenAI-unavailable exception. Test that local and LiteMaaS agents are not accidentally included.

- [x] **Step 2: Test CLI flags and safety defaults**

Test help/argument parsing for `--check`, `--dry-run`, `--config`, and verbosity/confirmation behavior. Verify missing credentials fail clearly and that check/dry-run paths do not invoke mutating HTTP methods.

- [x] **Step 3: Test mocked reconciliation**

Mock the MLflow client and verify list/create/update/delete calls, desired payloads, endpoint model configuration ordering, secret reference resolution, redaction, and non-zero behavior on HTTP errors. Include an already-converged response that produces no writes.

- [x] **Step 4: Test drift detection and protected resources**

Verify missing, changed, and stale managed resources are reported; unrelated endpoints and `vertex-dprod-opencode-opus-5` remain untouched; a declaration collision with the protected endpoint aborts before mutation.

- [x] **Step 5: Run the focused suite**

Run:
```bash
pytest .config/dotfiles/tests/test_mlflow_gateway.py -v
```
Expected: all gateway schema, CLI, mocked reconciler, drift, idempotency, and safety tests pass.

---

### Task 4: Agent Consolidation

**Files:**
- Delete: `.config/opencode/agents/implement-cloud.md`
- Create/rename: `.config/opencode/agents/implement.md`
- Modify: `.config/opencode/agents/orchestrator.md`
- Modify: `.config/opencode/README.md`
- Modify: any remaining references to `implement-cloud`

**Interfaces:**
- Consumes: current OpenCode agent front matter, delegation policy, and permissions.
- Produces: one cloud implementation agent named `implement` whose model is `mlflow/implement`.

- [x] **Step 1: Consolidate the agent definition**

Move the implementation behavior, permissions, workflow, and constraints from `implement-cloud.md` into `implement.md`; update its description to identify the MLflow-routed cloud implementation path and set `model: mlflow/implement`.

- [x] **Step 2: Update orchestrator delegation and permissions**

Replace allow-list and prose references from `implement-cloud` to `implement`, preserving the existing restrictions and explicit routing semantics. Ensure `implement-local` and `implement-maas` delegation remains unchanged.

- [x] **Step 3: Update documentation references**

Update `.config/opencode/README.md` and all bounded configuration/documentation references so the old agent name is absent except in migration notes where explicitly useful.

- [x] **Step 4: Validate agent files**

Run focused searches and configuration tests to verify `implement.md` exists, `implement-cloud.md` does not, orchestrator permissions target `implement`, and no stale delegation target remains.

---

### Task 5: OpenCode v2 Configuration Migration

**Files:**
- Modify: `.config/opencode/opencode.jsonc`
- Modify: `.config/opencode/agents/architect.md`
- Modify: `.config/opencode/agents/orchestrator.md`
- Modify: `.config/opencode/agents/plan.md`
- Modify: `.config/opencode/agents/implement.md`
- Modify: `.config/opencode/agents/review.md`
- Modify: `.config/opencode/agents/zweistein.md`

**Interfaces:**
- Consumes: MLflow gateway OpenAI-compatible endpoint and current OpenCode v2 provider/agent schema.
- Produces: cloud agent model routing through `mlflow`, while preserving local and LiteMaaS provider entries.

- [x] **Step 1: Add the `mlflow` OpenAI-compatible provider**

Add an OpenCode provider using the project’s established `@ai-sdk/openai-compatible` pattern, base URL `https://mlflow.fous.ai/gateway/mlflow/v1` (prefer an environment-backed equivalent), an API key reference if required, and models `orchestrator`, `architect`, `plan`, `implement`, `review`, and `zweistein` with stable IDs and suitable limits/capabilities.

- [x] **Step 2: Update cloud agent front matter**

Set the six cloud agent model fields to `mlflow/orchestrator`, `mlflow/architect`, `mlflow/plan`, `mlflow/implement`, `mlflow/review`, and `mlflow/zweistein`. Keep `implement-local` on `omlx/Qwen3-Coder-Next-6bit` and `implement-maas` on `litemaas/Qwen3.8-27B-NT`.

- [x] **Step 3: Preserve tracing and defaults**

Keep the existing OTEL plugin and environment-based endpoint behavior intact. Confirm default-agent behavior remains intentional and does not silently route local/LiteMaaS agents through MLflow.

- [x] **Step 4: Validate JSONC and model references**

Run the repository’s applicable OpenCode/config tests or parser validation. Assert each front matter model exists in `opencode.jsonc`, the MLflow base URL ends in `/gateway/mlflow/v1`, and no removed `implement-cloud` model/agent reference remains.

---

### Task 6: Execution, Live Gateway Sync, and End-to-End Validation

**Files:**
- None (operational execution and verification; update artifacts only if validation exposes a required configuration correction).

**Interfaces:**
- Consumes: running MLflow at `https://mlflow.fous.ai`, EnMaaS credentials, Vertex credentials, and the reconciler.
- Produces: verified live endpoints, successful fallback-capable inference, protected endpoint preservation, and tracing correlation evidence.

- [ ] **Step 1: Preflight live inventory**

Run the reconciler in `--check` or read-only inventory mode, verify the MLflow health/API reachability, confirm the existing `vertex-dprod-opencode-opus-5` endpoint is present, and save its normalized identity/configuration for before/after comparison.

- [ ] **Step 2: Apply the declaration safely**

Run `mlflow-gateway-sync` with the live configuration and explicit mutation approval. Review the plan before apply; confirm the output lists only declared resources and does not propose modifying or deleting the protected endpoint.

- [ ] **Step 3: Verify MLflow control-plane state**

List secrets, model definitions, and endpoints through the verified control-plane routes. Confirm all six managed endpoints contain the expected PRIMARY and sequential Vertex FALLBACK, and confirm the protected endpoint is byte-for-byte or semantically unchanged.

- [ ] **Step 4: Test gateway inference**

Send a minimal chat completion to `https://mlflow.fous.ai/gateway/mlflow/v1/chat/completions` using `model: mlflow/orchestrator` and a short messages payload. Verify a successful OpenAI-compatible response without exposing API keys in logs.

- [ ] **Step 5: Test routing and fallback behavior**

Exercise one EnMaaS-primary endpoint and one OpenAI-primary endpoint. If a controlled provider failure can be induced safely, verify sequential Vertex fallback; otherwise verify configuration and record fallback runtime testing as not safely inducible rather than disrupting production credentials.

- [ ] **Step 6: Test tracing correlation**

Invoke a routed OpenCode request with the existing OTEL/MLflow tracing environment enabled and verify the trace/request correlation reaches the configured MLflow experiment. Confirm the gateway request path and model name are visible without recording secrets.

- [ ] **Step 7: Re-run check and idempotency validation**

Run `--check`, then run a second sync or `--dry-run`. Expected: no managed drift, no writes for the converged state, and the unrelated/protected endpoint remains unchanged.

---

### Task 7: Documentation and Final Verification

**Files:**
- Modify: `.config/dotfiles/README.md` and/or create `docs/mlflow-gateway.md`
- Modify: `.config/opencode/env.example` if operational examples need completion

**Interfaces:**
- Consumes: final schema, reconciler CLI, agent mappings, and live validation results.
- Produces: operator documentation, troubleshooting guidance, rollback procedure, and an auditable final verification record.

- [ ] **Step 1: Document architecture and model routing**

Document the gateway URL, control-plane versus inference APIs, reconciler ownership boundary, and a table of all agents, primary models, fallbacks, and OpenCode model IDs. Explicitly state that OpenAI `gpt-5.6-luna`/`gpt-5.6-terra` are unavailable in EnMaaS and therefore remain original-provider primaries with Vertex fallback.

- [ ] **Step 2: Document configuration and operations**

Document required environment variables, secret handling, schema fields, commands for `--check`, `--dry-run`, and apply, expected idempotent output, and how to inspect MLflow gateway resources without leaking credentials.

- [ ] **Step 3: Document troubleshooting and rollback**

Cover authentication/API failures, missing model IDs, drift, fallback errors, and tracing correlation. Rollback must explain reverting OpenCode agent model fields and removing only managed gateway resources through the declaration/reconciler; it must explicitly preserve `vertex-dprod-opencode-opus-5`.

- [ ] **Step 4: Run final validation**

Run the focused gateway tests, applicable full dotfiles tests, JSONC/config validation, a redacted `--check`, and the live inference/tracing checks from Task 6. Record any provider fallback test limitation and confirm no secrets are staged.

---

## Plan Self-Review Checklist

- [ ] **Spec coverage:** Declarative environment/schema, reconciler CLI and safety, mocked Pytest suite, agent consolidation, OpenCode v2 provider migration, live sync/inference/tracing, and documentation are covered by Tasks 1-7.
- [ ] **Routing coverage:** Six cloud agents use the exact required primary/fallback mappings; local and LiteMaaS agents remain unchanged.
- [ ] **Exception coverage:** The unavailable EnMaaS OpenAI models and original-provider-primary/Vertex-fallback rule are explicit in schema, tests, and documentation.
- [ ] **Safety coverage:** Idempotency, drift detection, dry-run/check behavior, secret redaction, non-destructive unrelated-resource handling, and protected endpoint preservation are specified and tested.
- [ ] **Concrete file and symbol references:** Paths, API routes, endpoint names, provider IDs, model IDs, CLI flags, and fallback fields are explicit.
- [ ] **Discrete tasks:** Each task has bounded files, interfaces, executable steps, and validation criteria.
- [ ] **No unresolved architecture decisions:** Gateway URL, resource ownership, provider mappings, fallback strategy, agent names, and rollback boundary are fixed by the supplied live findings.
