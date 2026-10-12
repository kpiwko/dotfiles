# Devcluster MLflow v3.17.0 AI-factory Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade devcluster MLflow to v3.17.0 safely, migrate its persistent SQL backend before any v3.17.0 writer starts, and reconcile the dynamic AI-factory desired state idempotently on every `devcluster up` using Kubernetes Jobs.

**Architecture:** Split cluster deployment into a safe stopped-writer base, a database-migration phase, a v3.17.0 runtime phase, a read-only Gateway API-contract validation phase, and a post-validation Gateway reconciliation phase. The migration Job mounts the existing MLflow PVC exclusively after all writers are stopped and runs the official image’s idempotent `mlflow db upgrade sqlite:////mlflow/mlflow.db`. Only a successful migration permits the runtime overlay to start MLflow and the OTel writer; only a successful v3.17 management-API contract check then permits a short-lived Gateway Job to use the Python reconciler to converge `.config/mlflow/gateway.yaml`.

**Tech Stack:** k3s/kind, Kustomize overlays, Kubernetes PVC/ConfigMap/Secret/Job/Deployment/Service, official `ghcr.io/mlflow/mlflow:v3.17.0`, MLflow `mlflow db upgrade`, SQLite, Python standard `sqlite3`, Requests, PyYAML, Pytest, OpenCode.

**Spec:** Approved user requirements: MLflow v3.17.0 everywhere; reconciliation on every `devcluster up`; a Kubernetes-native database-migration workload; MLflow release upgrade safeguards (stop writers, migrate before v3.17.0 writers/restart, no mixed versions); accepted data loss during this initial setup with no backup workflow; dynamic Gateway reconciliation through `/api/3.0/mlflow/gateway/...`; and Vertex credentials materialized from `itpc-ca-993e2467de-opencode-vertex.json` without committing credentials.

## Observed Backend and Resource Constraints

`.config/k8s/base/mlflow.yaml` uses `ghcr.io/mlflow/mlflow:v3.16.1`, a single-replica Deployment, and SQL backend URL `sqlite:////mlflow/mlflow.db`. The database and artifacts share the already-bound `ai-dev/mlflow-pvc`, a 10Gi `ReadWriteOnce` `local-path` PVC mounted at `/mlflow`. The manifest currently requests immutable `storageClassName: standard`, so a root safe-base apply fails before migration. The plan must change the manifest to `local-path` and never delete or recreate this PVC. The migration must run alone while the MLflow Pod is absent: a concurrent migration pod and server pod cannot safely share this RWO SQLite store. This initial setup explicitly accepts data loss and does not create or validate a backup.

`.config/k8s/base/otel-collector.yaml` exports traces to `http://mlflow:5000`; it is also a database writer once MLflow is available and must be stopped before migration. The existing kustomization also deploys MCP resources, which are not MLflow database writers and remain untouched. The MLflow Service in namespace `ai-dev` supports the internal URL `http://mlflow.ai-dev.svc.cluster.local:5000` (subject to an implementation-time DNS smoke check); it is the correct Gateway Job control-plane address. This internal Service URL is reachable from the Job without a NodePort/Caddy dependency, but does not determine OpenCode’s host/external inference URL.

## Current Gateway Model

`.config/mlflow/gateway.yaml` is the authoritative dynamic desired state: six named endpoints, scoped secret/model definitions, sequential primary/fallback mappings, and explicit exclusion/protection of `vertex-dprod-opencode-opus-5`. `.local/bin/mlflow-gateway-sync` is the idempotent Python reconciler. It must run in Kubernetes after MLflow v3.17.0 is available, not on the host.

MLflow v3.17.0’s public `MlflowClient` does **not** provide a documented Gateway management CRUD surface for secrets, model definitions, and endpoints. The existing reconciler currently constructs `/ajax-api/3.0/mlflow/gateway/...` requests, but that prefix is not a documented stable public API. The approved management base is `/api/3.0/mlflow/gateway/...`; implementation must centralize that base and run a pinned-v3.17 authenticated read-only contract test against its paths and schemas before every mutation. If the server rejects the approved `/api/` route/schema, the Job must fail without creating, updating, or deleting Gateway resources. Do not invent, private-call, or imply `MlflowClient` Gateway CRUD methods.

## Global Constraints

- All Git operations must use `sandbox-git` against the `$HOME` dotfiles work tree; implementation must not use raw Git.
- Pin every MLflow runtime/version reference affected by this stack to `v3.17.0`, including Kubernetes image references, tests, documentation, and any plan-derived operational commands. Do not leave a runnable v3.16.1 image path.
- Before `mlflow db upgrade`, stop and verify termination of every MLflow database writer: at minimum the MLflow Deployment and OTel Collector Deployment. Do not use a mixed-version rolling upgrade; start all writers only at v3.17.0 after the migration Job succeeds.
- Data loss is explicitly accepted for this initial setup: do not create, validate, or restore database backups. Never automatically run an MLflow schema downgrade. Migration failure leaves writers stopped; no recovery guarantee is provided by this lifecycle.
- Preserve the bound `ai-dev/mlflow-pvc` and its immutable `storageClassName: local-path`. Every rendered manifest and lifecycle phase must request `local-path`; never resolve the immutable-field mismatch by deleting/recreating the PVC.
- `devcluster` may provision Kubernetes Secrets and apply/wait for declarative Kustomizations/Jobs only. It must not run local Python/`uv`, direct MLflow REST calls, local database commands, or imperative `kubectl scale` operations.
- Gateway desired-state YAML, ConfigMaps, manifests, logs, tests, and docs contain no credentials. Shell or `$K8S_DIR/.env` values enter only `ai-factory-secrets` through `secretKeyRef`.
- The DB migration Job requires no provider or Gateway-control-plane credentials. Create `ai-factory-secrets` only after runtime MLflow readiness and immediately before the Gateway contract/reconcile phase. It contains required source provider credentials/configuration; `MLFLOW_GATEWAY_API_KEY` is optional and is injected only when control-plane authentication is enabled.
- Vertex provisioning is always mounted: `.config/zsh/10-env.zsh` resolves `GOOGLE_APPLICATION_CREDENTIALS` to `$HOME/.config/opencode/itpc-ca-993e2467de-opencode-vertex.json`. Before the Gateway Job, validate that exact bounded source file is readable, materialize its contents only into `ai-factory-secrets`, mount it as `/var/run/ai-factory/vertex/credentials.json`, and set `GOOGLE_APPLICATION_CREDENTIALS` to that in-container file path. Never commit, print, or use the host path inside the Job.
- Preserve MLflow tracking/artifact PVC data, Workspace MCP secret behavior, MCP workloads, OTel configuration apart from controlled replica lifecycle, local/LiteMaaS agent routes, sequential Gateway fallback semantics, and the protected external endpoint.

## Fixed Lifecycle Decisions

1. **Every-up lifecycle:** every `devcluster up` performs safe base apply → zero-writer confirmation → idempotent migration Job → v3.17.0 runtime apply/readiness → idempotent Gateway Job. Both Jobs use TTL cleanup, and `devcluster` waits for completion and cleanup, so the next up creates a fresh Job deterministically.
2. **Safe default manifests:** the root `.config/k8s` Kustomization represents a stopped-writer maintenance state (MLflow and OTel replicas zero). A new runtime overlay is the only manifest set that raises them to their normal replicas. This prevents an accidental root apply from starting a v3.17.0 server before migration.
3. **Initial-setup migration:** the migration Job mounts `/mlflow` exclusively and runs `mlflow db upgrade sqlite:////mlflow/mlflow.db` directly. It is valid for both first-install database initialization and repeat runs. By approved direction, it creates no backup, performs no storage preflight, and provides no restoration artifact.
4. **In-cluster versus external URLs:** the Gateway Job always targets `http://mlflow.ai-dev.svc.cluster.local:5000`; OpenCode keeps its existing external base URL unless a separate verified routing change is requested. These are different interfaces and must be tested independently.
5. **Pinned Job runtime:** both Jobs use the official `ghcr.io/mlflow/mlflow:v3.17.0` image. The migration Job uses `mlflow db upgrade` and Python stdlib only; the Gateway Job must verify Requests/PyYAML availability in that exact image before implementation. If unavailable, add a separately pinned/reviewed reconciler image—never install dependencies at Job runtime.
6. **Pinned direct-HTTP contract:** the reconciler uses `/api/3.0/mlflow/gateway/...` for management operations. The integration task verifies this v3.17 authenticated route, verbs, request payloads, and list/get response envelopes; the reconciler performs a read-only check before every apply, and any mismatch blocks all Gateway mutation.

## Review Focus

1. **No premature v3.17 writer:** rendered safe-base manifests must leave MLflow/OTel at zero, and `devcluster` must refuse runtime apply if scale-down or migration completion fails.
2. **Migration-failure containment:** a failed `mlflow db upgrade` must return a non-zero Job status, prevent the runtime/Gateway phases, and leave MLflow and OTel writer Deployments at zero replicas.
3. **No mixed-version rollout:** no path may start v3.17.0 while an older MLflow Pod is still Ready; every writer Pod after migration must use v3.17.0.
4. **Gateway contract gate:** unsupported path, authentication, verb, or response envelope prevents every create/update/delete before the reconciler evaluates desired-state drift.
5. **Gateway scope/fallback:** each reconciliation preserves the six endpoint configurations, sequential fallback, provider exceptions, secret redaction, and strict exclusion of unrelated/protected endpoints.
6. **Repeatability:** repeated `devcluster up` creates fresh Jobs, `mlflow db upgrade` is a no-op against the current revision, Gateway reconciliation makes no writes when converged, and PVC data remains intact.

---

### Task 1: Prepare MLflow v3.17.0 desired state and migration-safe Kustomize topology

**Files:**
- Modify: `.config/k8s/base/mlflow.yaml`
- Modify: `.config/k8s/base/otel-collector.yaml`
- Modify: `.config/k8s/kustomization.yaml`
- Create: `.config/k8s/runtime/kustomization.yaml`
- Create: `.config/k8s/runtime/writers-running.yaml`
- Modify: `.local/bin/mlflow-traces`
- Modify: `.config/dotfiles/tests/test_mlflow_manifests.py`
- Modify: `.config/dotfiles/tests/test_mlflow_traces.py`
- Modify: `.config/k8s/README.md`

**Interfaces:**
- Consumes: existing PVC (`mlflow-pvc`), service (`mlflow`), database URL (`sqlite:////mlflow/mlflow.db`), and normal writer replicas.
- Produces: root safe-base resources with all MLflow writers stopped and a runtime overlay that starts the same named resources only after Task 2 succeeds.

- [ ] **Step 1: Write failing safe-base/runtime render tests**

Extend `test_mlflow_manifests.py` to assert the MLflow server continues to use the supported `--backend-store-uri sqlite:////mlflow/mlflow.db` plus `--artifacts-destination /mlflow/artifacts` configuration and does **not** set a server-container `MLFLOW_TRACKING_URI` override. Also assert the MLflow image is exactly `ghcr.io/mlflow/mlflow:v3.17.0`; root rendering has `replicas: 0` for the MLflow and OTel writer Deployments; the runtime overlay patches those same resources to their intended normal counts; and PVC, backend URI, artifacts path, Service/NodePort, MCP resources, and OTel exporter remain present. Assert `mlflow-pvc` uses `storageClassName: local-path` and rendered resources never request `standard`. Extend `test_mlflow_traces.py` to assert the inline runtime dependency floor is v3.17.0. Assert no rendered/runtime image or dependency reference retains `3.16.1`.

- [ ] **Step 2: Preserve supported MLflow storage and artifact serving configuration**

Do not add `MLFLOW_TRACKING_URI` to the MLflow server container. Preserve `--backend-store-uri sqlite:////mlflow/mlflow.db`, `--artifacts-destination /mlflow/artifacts`, the PVC, Service, and OTel exporter configuration. Treat the observed `mlflow-artifacts` warning as non-actionable unless Task 3 controlled runtime verification demonstrates missing Gateway traces or failed artifact-bearing trace handling.

- [ ] **Step 3: Verify the supported manifest contract before other topology work**

Run: `pytest .config/dotfiles/tests/test_mlflow_manifests.py -v`.

Expected: no server self-tracking override is rendered; SQLite storage and artifact serving configuration are unchanged.

- [ ] **Step 4: Make root Kustomize maintenance-safe**

Update the MLflow Deployment image and set its safe-base replica count to zero. Change the declared `mlflow-pvc.storageClassName` from `standard` to the existing immutable `local-path` value, without changing its name, size, access mode, or bound-volume relationship. Add an equivalent zero-replica base state for the OTel Collector while retaining its configuration and Service. Keep the namespace, PVC, MLflow Service, MCP resources, and ConfigMaps in the root Kustomization so migration can access storage/service definitions without starting writers.

- [ ] **Step 4a: Raise the host trace-client runtime floor**

Change `.local/bin/mlflow-traces` inline MLflow dependency from its v3.16 floor to `mlflow>=3.17.0,<4`, retaining its tracking/read-only behavior and existing CLI interface. This avoids retaining a v3.16 runtime path after the server upgrade.

- [ ] **Step 5: Add the runtime overlay**

Create `.config/k8s/runtime/kustomization.yaml` that consumes the root safe base and applies `writers-running.yaml`, a strategic merge/JSON patch that sets exactly the existing MLflow and OTel Deployments to their approved runtime replica counts without changing their image or pod specification. Do not duplicate PVCs, Services, or Deployment names.

- [ ] **Step 6: Update operator documentation for safe direct usage**

State that `kubectl apply -k ~/.config/k8s` intentionally leaves writers stopped and that only `devcluster up` sequences the runtime overlay after migration. Document that the MLflow server retains supported SQLite backend and artifact-serving configuration; the `mlflow-artifacts` warning alone does not justify server self-tracking configuration changes. Replace v3.16.1 references with v3.17.0 while preserving the documented tracking/NodePort/telemetry interfaces.

- [ ] **Step 7: Validate manifests**

Run: `kubectl kustomize ~/.config/k8s`, `kubectl kustomize ~/.config/k8s/runtime`, and `pytest .config/dotfiles/tests/test_mlflow_manifests.py -v`.

Expected: both render, root is migration-safe, rendered PVC uses `local-path`, runtime contains only the intended replica patches, and all MLflow references are v3.17.0.

**Acceptance criteria:** Supported SQLite backend and artifact-serving configuration are preserved without server self-tracking override; root apply no longer fails on the immutable PVC storage-class mismatch and cannot start a v3.17.0 MLflow/OTel writer; the runtime overlay can start existing services without replacing `ai-dev/mlflow-pvc`, changing its `local-path` class, or changing tracking interfaces.

### Task 2: Add the exclusive MLflow database migration Job

**Files:**
- Create: `.config/k8s/migration/kustomization.yaml`
- Create: `.config/k8s/migration/mlflow-db-migrate.yaml`
- Modify: `.config/dotfiles/tests/test_mlflow_manifests.py`

**Interfaces:**
- Consumes: safe-base zero-writer state, `mlflow-pvc`, official v3.17.0 image, and `sqlite:////mlflow/mlflow.db`.
- Produces: a bounded Job named `mlflow-db-migrate` that exits zero only after successful idempotent `mlflow db upgrade`; Job completion is the runtime gate evidence.

- [ ] **Step 1: Write failing migration manifest/lifecycle tests**

Extend `test_mlflow_manifests.py` and the Task 6 command-order tests to assert that a Job named `mlflow-db-migrate` runs the exact command `mlflow db upgrade sqlite:////mlflow/mlflow.db`, mounts `mlflow-pvc` at `/mlflow`, and is required to complete before the runtime overlay is applied. Cover first-install and repeat-up success through mocked Job completion, plus non-zero migration failure preventing subsequent phases.

- [ ] **Step 2: Create the direct migration Job and Kustomization**

Create a Job using `ghcr.io/mlflow/mlflow:v3.17.0` that mounts `mlflow-pvc` at `/mlflow` and directly invokes `mlflow db upgrade sqlite:////mlflow/mlflow.db`. Set `restartPolicy: Never`, bounded `backoffLimit`/`activeDeadlineSeconds`, resource limits, and `ttlSecondsAfterFinished`. The Job needs no ConfigMap, network access, provider Secret, or Kubernetes RBAC. Its labels/log text must identify it as database migration, not Gateway reconciliation. Do not add backup, integrity-check, storage-preflight, restore, or downgrade commands.

- [ ] **Step 3: Add manifest contract tests**

Assert migration manifests mount only the existing `ai-dev/mlflow-pvc` (whose rendered class is `local-path`), use the v3.17.0 official image, invoke the exact upgrade command, contain no backup/restore/schema-downgrade command or credentials, and have TTL/failure bounds. Assert the migration Kustomization cannot start MLflow/OTel writers or request a replacement PVC.

- [ ] **Step 4: Run focused validation**

Run: `pytest .config/dotfiles/tests/test_mlflow_manifests.py .config/dotfiles/tests/test_devcluster.py -v` and `kubectl kustomize ~/.config/k8s/migration`.

Expected: first-install/repeat ordering and migration-failure containment are covered without a cluster; rendered Job is exclusive, pinned, direct, and bounded.

**Acceptance criteria:** Fresh and repeat runs safely execute the official idempotent migration command; no backup/recovery workflow is present; a failed migration leaves all writers stopped and prevents runtime/Gateway startup.

### Task 3: Add the architect Chat Completions response-shape regression gate

**Files:**
- Create: `.config/dotfiles/tests/test_mlflow_gateway_responses.py`
- Modify: `.config/dotfiles/tests/test_mlflow_gateway.py`
- Modify: `.config/k8s/README.md`

**Interfaces:**
- Consumes: the existing `architect` Gateway endpoint and the approved OpenAI-compatible inference URL; it does not mutate endpoint/model/provider configuration.
- Produces: a controlled integration assertion that a successful architect Chat Completions response contains usable generated content, plus sanitized evidence for a follow-up diagnosis only when it fails.

- [ ] **Step 1: Write the pre-remediation response-shape test**

Create an opt-in integration test that sends one minimal, non-sensitive Chat Completions request to the existing `architect` endpoint using its configured `mlflow/architect` model route. Require HTTP 200, a JSON `choices` array with at least one item, and a non-empty string at `choices[0].message.content`. An HTTP 200 with `choices: []` is a failure.

- [ ] **Step 2: Make failure diagnostics sanitized and read-only**

On response-shape failure, record only status code, endpoint/model identifier, correlation/request ID headers when available, response top-level keys, `choices` length, and redacted MLflow/Gateway pod log correlation. Never record prompt text, completion text, Authorization headers, provider keys, or credentials. Use read-only endpoint/config inspection only; this test must not alter Gateway resources or trigger a provider/model remap.

- [ ] **Step 3: Run bounded trace/artifact verification before response validation**

After the normal supported server configuration is deployed, use the HTTP tracking-service endpoint exposed by a bounded `kubectl port-forward svc/mlflow 15000:5000 -n ai-dev` session. With `MLFLOW_TRACKING_URI=http://127.0.0.1:15000` set only in the disposable verification client (never in the server container), create one uniquely named minimal trace, retrieve it through the HTTP service, then log and retrieve one small test artifact through the same client/service. Treat the `mlflow-artifacts` warning as non-actionable when both operations succeed; record sanitized status/trace ID/artifact name only. If either is missing or artifact retrieval fails, preserve that evidence for a separate storage/trace remediation decision rather than changing server self-tracking.

- [ ] **Step 4: Run the controlled architect response validation**

Run the opt-in response test once after Step 3 succeeds or has established a separate trace/artifact failure. Expected: the architect request returns a non-empty assistant message. A 200/empty-choices response fails with sanitized diagnostic evidence and leaves existing endpoint/provider mapping unchanged.

- [ ] **Step 5: Diagnose routing only if the response regression persists**

If and only if Step 3 still fails, open a bounded follow-up diagnosis using the sanitized request correlation plus read-only Gateway endpoint/model-definition state and provider/Gateway logs. Determine whether the failure arises upstream of MLflow, in MLflow Gateway response translation, or from the existing provider mapping. Do not change EnMaaS/Vertex/OpenAI mappings, fallback order, or model names in this task; require a separate reviewed plan amendment with evidence before any routing remediation.

**Acceptance criteria:** A 200 response is accepted only when it contains at least one non-empty assistant choice; controlled HTTP trace/artifact verification distinguishes a non-actionable warning from an actual storage/trace failure without server self-tracking changes; and an empty response produces safe diagnostic evidence rather than an assumed provider change or unnecessary provider calls.

### Task 4: Verify and centralize the MLflow v3.17 Gateway management API contract

**Files:**
- Modify: `.local/bin/mlflow-gateway-sync`
- Create: `.config/dotfiles/tests/test_mlflow_gateway_contract.py`
- Modify: `.config/dotfiles/tests/test_mlflow_gateway.py`

**Interfaces:**
- Consumes: a pinned v3.17.0 MLflow server, the internal control-plane URL, and optional control-plane authentication.
- Produces: a centralized, tested `GatewayApiContract` used by `GatewayClient`, plus a read-only `--verify-contract` gate that succeeds only for the authenticated v3.17 server contract.

- [ ] **Step 1: Run the pre-implementation v3.17 `/api/` integration probe**

Against a disposable MLflow `ghcr.io/mlflow/mlflow:v3.17.0` server, test the approved `/api/3.0/mlflow/gateway/` paths for read-only secret, model-definition, and endpoint listing/get operations, with and without configured control-plane authentication. Verify the expected HTTP verbs, authorization behavior, request field names, and response envelopes needed by create/update/delete. Treat the existing `/ajax-api/` paths as unverified implementation history and do not use or fall back to them. If the pinned server rejects the approved `/api/` route/schema, record the failure and block implementation rollout rather than substituting another prefix.

- [ ] **Step 2: Add executable contract tests before mutation tests**

Create `test_mlflow_gateway_contract.py` as an opt-in v3.17 integration suite and add unit tests in `test_mlflow_gateway.py` for the exact `/api/3.0/mlflow/gateway/` base, rejected `/ajax-api/` fallback, auth header presence only when a token is configured, and required response shapes. The integration suite must use read-only operations and must fail rather than silently falling back or mutating Gateway resources.

- [ ] **Step 3: Centralize only the verified contract**

Refactor `GatewayClient` to obtain all list/get/create/update/delete paths, verbs, and envelope normalization from one `GatewayApiContract` definition whose base is `/api/3.0/mlflow/gateway`. Remove all `/ajax-api/` literals and do not add fallback routing. Retain direct HTTP only while Step 1 verifies the approved `/api/` contract; do not replace it with undocumented/private `MlflowClient` APIs.

- [ ] **Step 4: Gate reconciliation on contract verification**

Add `GatewayClient.verify_contract() -> None` and `mlflow-gateway-sync --verify-contract`. `main()` must run this read-only verification before constructing/running an apply plan; if it fails, return non-zero before any secret/model/endpoint create, update, or delete request. Preserve `--check`/`--dry-run`, redaction, and protected-endpoint preflight.

- [ ] **Step 5: Run contract validation**

Run: `pytest .config/dotfiles/tests/test_mlflow_gateway.py -v` and the opt-in `pytest .config/dotfiles/tests/test_mlflow_gateway_contract.py -v` against the pinned v3.17.0 integration server.

Expected: the accepted contract is documented in code/tests, invalid prefix/schema/auth cases fail read-only, and no mutation is issued before contract validation passes.

**Acceptance criteria:** The plan makes no stability claim for `/ajax-api`; all direct Gateway HTTP paths are centralized under `/api/3.0/mlflow/gateway`, verified against v3.17.0, and every reconcile apply is blocked by a successful read-only contract gate.

### Task 5: Package dynamic Gateway reconciliation as a post-validation Kubernetes Job

**Files:**
- Modify: `.config/mlflow/gateway.yaml`
- Modify: `.local/bin/mlflow-gateway-sync`
- Create: `.config/k8s/gateway-bootstrap/kustomization.yaml`
- Create: `.config/k8s/gateway-bootstrap/mlflow-gateway-bootstrap.yaml`
- Modify: `.config/dotfiles/tests/test_mlflow_gateway.py`
- Modify: `.config/dotfiles/tests/test_mlflow_manifests.py`

**Interfaces:**
- Consumes: successful Task 4 contract verification, runtime MLflow v3.17.0 service, `.config/mlflow/gateway.yaml`, `ai-factory-secrets`, and control-plane URL `http://mlflow.ai-dev.svc.cluster.local:5000`.
- Produces: one fresh Job `mlflow-gateway-bootstrap` per `devcluster up`, converging only the declared MLflow Gateway resources.

- [ ] **Step 1: Preserve desired-state and secret-ordering semantics**

Keep the six managed endpoints, declared secrets/models, `PRIMARY`/`FALLBACK` configurations, `fallback_order`, and `fallback_config: {strategy: SEQUENTIAL}`. Explicitly assert `orchestrator`, `architect`, and `plan` use EnMaaS `gemini-3.8-flash` as PRIMARY and Vertex `gemini-3.8-flash` as sequential FALLBACK. Assert reconciliation order is MLflow-managed secrets first, model definitions second, then endpoints. Require EnMaaS/OpenAI source values; accept `MLFLOW_GATEWAY_API_KEY` only as optional control-plane auth; and require the mounted `itpc-ca-993e2467de-opencode-vertex.json` material for the managed Vertex secret.

- [ ] **Step 2: Verify or pin the reconciler image dependency closure**

Add a build/manifest-level verification that the approved v3.17.0 Job image imports `requests` and `yaml` before rollout. If the official MLflow image lacks either, create a separately pinned, reviewed image reference containing only the reconciler runtime dependencies; do not add runtime `pip install`/`uv` downloads. Record the final image choice in the manifest and docs.

- [ ] **Step 3: Create ConfigMaps and bootstrap Job**

Use Kustomize ConfigMap generators for the desired YAML and reconciler script, with content hashes propagated to the Job template. The Job mounts them read-only, injects required provider values from `ai-factory-secrets`, and injects `MLFLOW_GATEWAY_API_KEY` with an optional `secretKeyRef` only when control-plane auth is enabled. Mount `ai-factory-secrets` key `vertex-credentials.json` read-only at `/var/run/ai-factory/vertex/credentials.json` and set `GOOGLE_APPLICATION_CREDENTIALS` to exactly that in-container path; never inject the host source path. Invoke `--verify-contract` as part of the command path before `--yes`, use the internal Service URL, and set bounded retry/deadline/TTL. It receives no Kubernetes API permissions and never uses the OpenCode external URL.

- [ ] **Step 4: Add manifest and reconciler test coverage**

Assert exactly one Job mounts hashed config/script ConfigMaps and Secret refs, calls no `MlflowClient` Gateway CRUD surface, has no literal provider values, and uses in-cluster Service DNS. Test EnMaaS Gemini → Vertex Gemini fallback mappings, required provider validation, optional token absence/presence, missing/unreadable source credentials rejection, required in-container Vertex file mount/path, contract-gate no-mutation failure, initial convergence, converged repeat no-write, repair/update convergence, API failure, and unrelated/protected endpoint preservation.

- [ ] **Step 5: Run focused validation**

Run: `pytest .config/dotfiles/tests/test_mlflow_gateway.py .config/dotfiles/tests/test_mlflow_manifests.py -v` and `kubectl kustomize ~/.config/k8s/gateway-bootstrap`.

Expected: dynamic Gateway semantics remain intact, secret/model/endpoint ordering is correct, and the Job is a credential-safe, contract-gated HTTP reconciler rather than an invented MLflow-client implementation.

**Acceptance criteria:** A post-validation in-cluster Job, not host code, converges the documented Gateway desired state on every bootstrap while preserving fallback, provider-secret ordering, optional auth, Vertex safety, and protected-resource safety.

### Task 6: Sequence Kubernetes lifecycle in `devcluster up` and provision only Secrets

**Files:**
- Modify: `.local/bin/devcluster:86-131`
- Modify: `.config/dotfiles/tests/test_devcluster.py`
- Modify: `.config/dotfiles/tests/conftest.py` (only for new environment cleanup)

**Interfaces:**
- Consumes: root safe base, migration/runtime/Gateway bootstrap Kustomizations, Job names, writer Deployment names, and the Task 5 `ai-factory-secrets` key/mount contract.
- Produces: a deterministic every-up sequence with no direct host database/API/reconciler execution.

- [ ] **Step 1: Write failing command-order and failure-path tests**

Extend the kubectl stub to capture waits, pod status, and Job logs. Assert this exact high-level order: namespace/Workspace secret → root safe base apply → wait for MLflow and OTel writer Pods to terminate → migration apply/wait/TTL deletion → runtime apply → wait for MLflow and OTel availability → validate/create `ai-factory-secrets` → Gateway bootstrap apply/wait/TTL deletion. Assert DB migration runs with no provider/Gateway secret; missing required provider values block only the Gateway phase; migration failure prevents runtime/Gateway applies; and no command uses local Python, `uv`, `mlflow db`, `mlflow-gateway-sync`, direct management paths, or `kubectl scale`.

- [ ] **Step 2: Provision `ai-factory-secrets` safely**

Preserve Workspace MCP Secret creation at initial namespace setup. Only after runtime MLflow readiness, create/update `ai-factory-secrets` through `kubectl create secret generic --dry-run=client -o yaml | kubectl apply -f -`. Validate required EnMaaS/OpenAI source values and shell-over-`.env` precedence without echoing values. Resolve `GOOGLE_APPLICATION_CREDENTIALS` from its existing bounded configuration value `$HOME/.config/opencode/itpc-ca-993e2467de-opencode-vertex.json`; reject a blank, unreadable, or differently named source, and materialize it only with `--from-file=vertex-credentials.json=<resolved-source>`. Create the optional `MLFLOW_GATEWAY_API_KEY` key only when supplied/enabled. Never pass the host credential path as an environment value or print its contents.

- [ ] **Step 3: Implement apply/wait state machine**

Apply the safe root Kustomization, wait boundedly until no MLflow/OTel writer Pods remain (not merely desired replica count), apply and wait for successful `mlflow-db-migrate`, then wait for its TTL deletion. Apply the runtime overlay; wait for v3.17.0 MLflow and OTel readiness; only then validate/create `ai-factory-secrets`, apply and wait for successful `mlflow-gateway-bootstrap`, then wait for its TTL deletion. On any Job failure, emit bounded Job/pod description and redacted logs and exit non-zero without applying a later phase.

- [ ] **Step 4: Run focused bootstrap tests**

Run: `pytest .config/dotfiles/tests/test_devcluster.py -v`.

Expected: lifecycle ordering, every-up Job recreation, safe failure stop, environment precedence, and absence of host-side migration/Gateway operations pass.

**Acceptance criteria:** Every `devcluster up` safely rechecks/migrates, starts v3.17.0 writers, then creates provider credentials and reconciles Gateway state; a failed phase cannot start a new-version writer or perform Gateway mutation without a verified contract and valid secret inputs.

### Task 7: Align operations, compatibility tests, and live upgrade validation

**Files:**
- Modify: `.config/k8s/README.md`
- Modify: `.config/opencode/README.md`
- Modify: `.config/opencode/opencode.jsonc` (only if an independently verified external routing change is required)
- Modify: `.config/dotfiles/tests/test_mlflow_manifests.py`
- Modify: `.config/dotfiles/tests/test_mlflow_gateway_responses.py`

**Interfaces:**
- Consumes: fixed lifecycle decisions and completed resource interfaces from Tasks 1–6.
- Produces: operationally safe migration/runbook guidance and end-to-end regression coverage.

- [ ] **Step 1: Document upgrade and failure-containment rules**

Document the v3.17.0 phases, downtime expectation, writer stop requirement, SQLite PVC/RWO limitation, direct idempotent migration command, and Job diagnostics. Document that the MLflow server retains the supported SQLite backend plus `--artifacts-destination`/artifact-serving configuration, and that the `mlflow-artifacts` warning alone is non-actionable; operators use the bounded port-forward HTTP-client trace-and-artifact verification before opening a separate remediation. State that the bound devcluster PVC class is `local-path`, must match every manifest render, and must never be deleted/recreated to resolve an immutable storage-class mismatch. State explicitly that data loss is accepted for this initial setup: no backup, restore workflow, automatic schema downgrade, or recovery guarantee is provided. A failed migration leaves writers stopped for operator diagnosis; a successful migration must not be rolled back automatically to an older schema/image.

- [ ] **Step 2: Document Gateway and URL boundaries**

Document that public `MlflowClient` lacks documented Gateway CRUD, that the reconciler uses direct HTTP only through the v3.17 integration-verified `/api/3.0/mlflow/gateway/...` contract, and that `/ajax-api` is not claimed as a documented stable public prefix or fallback. List the internal Service DNS control-plane URL and distinguish it from unchanged OpenCode external base URL. Document database-migration-without-secrets followed by provider Secret creation, optional control-plane authentication, and materialization of the bounded Vertex source file as a mounted in-Job credential (without documenting its contents). Retain the six logical OpenCode models, with EnMaaS Gemini primaries and Vertex Gemini sequential fallbacks for `orchestrator`, `architect`, and `plan`. Warn never to manage `vertex-dprod-opencode-opus-5` through this bootstrap.

- [ ] **Step 3: Add cross-configuration tests**

Assert all runtime/image/docs references use v3.17.0; the MLflow container has no `MLFLOW_TRACKING_URI` override while its SQLite/artifact settings are unchanged; the PVC manifest and all Kustomize renders use `local-path` rather than `standard`; OpenCode agent model names still map to gateway declarations; the Gateway Job internal URL is not substituted into OpenCode configuration; migration resources have no provider/Gateway Secret dependency; the Gateway Job has required provider Secret refs, optional control-plane token behavior, and the exact Vertex file mount/in-container path; and tracking/PVC/MCP/OTel resources remain present after topology changes.

- [ ] **Step 4: Execute staged live validation in an approved disposable devcluster**

Run the focused suite:
```bash
pytest .config/dotfiles/tests/test_devcluster.py .config/dotfiles/tests/test_mlflow_gateway.py .config/dotfiles/tests/test_mlflow_gateway_responses.py .config/dotfiles/tests/test_mlflow_manifests.py -v
```

First run Task 3’s bounded HTTP-client verification through a temporary MLflow port-forward: a unique trace and small artifact must be accepted and retrievable while the server keeps its supported SQLite/artifact configuration; the warning alone does not fail validation. Next run the Task 3 architect response-shape integration test; require a non-empty choice/message and retain the current routing unchanged on failure. Only if it still fails, collect its sanitized evidence and execute the conditional bounded routing diagnosis. Separately run the Task 4 v3.17 integration contract suite against the pinned server. Then validate: (a) safe-base apply succeeds against the existing bound `ai-dev/mlflow-pvc` without an immutable-field error and reports `storageClassName: local-path`; (b) first install initializes the DB without provider/Gateway secrets and starts only v3.17.0 writers after migration; (c) an existing SQLite PVC upgrade stops all writers, runs the direct migration, and starts v3.17.0 only afterward; (d) a deliberate migration failure leaves writers stopped and prevents runtime/Gateway phases; (e) a rejected `/api/` path/auth/schema contract causes no management mutations and never falls back to `/ajax-api`; (f) the exact bounded Vertex source is accepted only when mounted as the expected in-container file, optional control-plane auth is absent/present as configured, and no credential appears in manifests/logs; (g) a second `devcluster up` runs fresh Jobs but is schema/Gateway no-op; (h) `orchestrator`, `architect`, and `plan` retain EnMaaS Gemini primary plus Vertex Gemini sequential fallback, while the protected external endpoint is unchanged; and (i) traces, OTel, MCP, PVC persistence, and an external OpenCode Chat Completions request are healthy.

**Acceptance criteria:** The direct migration is gated by a no-writer state, has no mixed-version write window, controlled HTTP-client trace and artifact checks pass without server self-tracking changes, architect responses have a non-empty assistant choice before any routing change is considered, safe diagnostics gate any conditional routing investigation, Gateway fallback behavior is retained, unverified HTTP management contracts are blocked before mutation, provider/auth/Vertex secret wiring is validated, and no backup, restore, or automatic downgrade guarantee is implied.

## Failure, Rollback, and Compatibility

- **Before migration Job success:** root remains writer-stopped. Correct configuration or migration issues and rerun `devcluster up`; no newer server has written to the database.
- **PVC apply failure:** do not delete, recreate, or resize `ai-dev/mlflow-pvc`. Correct a manifest/overlay that diverges from immutable `storageClassName: local-path`, confirm the bound claim remains intact, then rerun the safe-base apply.
- **Migration failure:** keep writers stopped and retain Job diagnostics for operator investigation. This initial setup has no automated backup, restoration, or data-recovery guarantee.
- **After successful migration:** never automatically downgrade schema. Returning to an older MLflow version is unsupported by this lifecycle and requires a separately approved destructive/manual recovery decision; do not run an automatic Alembic downgrade.
- **Architect 200/empty response:** treat it as an inference regression, not success. Preserve the current provider/model/fallback declaration, collect only the Task 3 sanitized read-only evidence, and do not make additional provider calls or mapping changes until the conditional diagnosis identifies a supported remediation.
- **Gateway contract or Job failure:** MLflow v3.17.0 tracking may remain available, but Gateway desired state is not declared converged; preserve redacted diagnostics, fix only the verified contract/declaration/credentials/connectivity issue, and rerun. A contract failure must occur before management mutation, and neither case may delete or mutate unrelated/protected remote Gateway resources.
- **External compatibility:** OpenCode external routing does not change merely because Jobs use in-cluster Service DNS. Any external URL migration is a separately verified change with its own rollback to the recorded prior URL.

## Self-review

- **Requirement coverage:** Task 1 preserves supported MLflow SQLite/artifact configuration and resolves the immutable `local-path` PVC contract before safe startup; Task 2 implements direct official v3.17.0 DB migration without backup; Task 3 separately verifies real trace/artifact behavior and makes empty architect choices a regression that gates diagnosis; Task 4 verifies the only allowed direct-HTTP Gateway contract; Task 5 packages contract-gated dynamic reconciliation and its secrets; Task 6 makes both Jobs run every up; Task 7 validates traces, artifacts, response shape, migration, PVC compatibility, credentials, repeatability, external routing, and failure containment.
- **Concrete boundaries:** Tasks identify exact artifacts, lifecycle interfaces, test ownership, commands, and observable acceptance criteria. The plan does not conflate database migration with Gateway reconciliation.
- **Resolved design choices:** supported server SQLite/artifact configuration with no self-tracking override, bounded HTTP-client trace/artifact verification before any storage remediation, per-up Job execution, `local-path` preservation for the existing bound PVC, safe-base/runtime overlay, internal Service DNS, direct official-image migration without backups, accepted initial data loss, no automatic downgrade, contract-gated `/api/` HTTP, optional control-plane auth, and the fixed mounted Vertex credential source are fixed. Architect routing changes remain explicitly conditional on sanitized evidence from the non-empty-choice regression. The only other conditional implementation branch is dependency verification for the existing reconciler, with a secure pinned-image fallback already specified.
