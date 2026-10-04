# OpenTelemetry Collector Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate an OpenTelemetry Collector into the local Kubernetes AI development stack (`devcluster`, namespace `ai-dev`) to ingest OTLP HTTP traces on NodePort 17903, preserve and inject `x-mlflow-experiment-id` headers, and forward traces reliably to MLflow.

**Architecture:** OpenCode and external clients send OTLP HTTP protobuf/json traces to Caddy (`https://otel.example.internal`) or direct loopback (`http://127.0.0.1:17903`). Caddy proxies traffic to NodePort 17903 on Lima VM `devcluster`. The OpenTelemetry Collector receives HTTP traffic on container port 4318 with `include_metadata: true`, processes it through memory limiter and metadata-aware batching (`x-mlflow-experiment-id`), injects the experiment header via `headers_setter/mlflow`, and exports traces to MLflow (`http://mlflow:5000/v1/traces`). MLflow `--allowed-hosts` is expanded to accept cluster pod requests (`mlflow:*`).

**Tech Stack:** Kubernetes (k3s / Lima `devcluster`, Kind config), Kustomize, OpenTelemetry Collector Contrib/K8s (`otel/opentelemetry-collector-k8s:0.123.0`), MLflow 3.16+, Caddy v2, Python / Pytest.

**Spec:** Subagent task specification in conversation context and existing `.config/k8s/` architecture.

## Global Constraints

- Manifests live in `.config/k8s/base/` and are included in `.config/k8s/kustomization.yaml`.
- NodePort allocation must be in the reserved 17900-17999 range; NodePort 17903 is assigned to OTel HTTP receiver.
- Container image must be pinned explicitly to `otel/opentelemetry-collector-k8s:0.123.0`.
- Collector resource sizing: CPU requests 50m, memory requests 64Mi; CPU limits 500m, memory limits 512Mi.
- Health checks must use extension `health_check` listening on `0.0.0.0:13133` with `/` path for both liveness and readiness.
- Experiment multi-tenancy requires: `include_metadata: true` on OTLP HTTP receiver, `metadata_keys: ["x-mlflow-experiment-id"]` on batch processor, and `headers_setter/mlflow` extension attached as exporter authenticator.
- MLflow host enforcement: `--allowed-hosts` must include `mlflow:*` to permit internal cluster pod calls without breaking external origins.
- Reverse proxy site template lives in `.config/caddy/sites/otel.caddy.example` using `import cloudflare_tls` and upstream `127.0.0.1:17903`.
- All Git operations must run via `sandbox-git` (operating on bare repo `~/.dotfiles` from `$HOME`).

## Review Focus

**Implementation note:** The container image is pinned to `otel/opentelemetry-collector-k8s:0.123.0` because `0.123.1` experienced image pull failures from Docker Hub. The `devcluster-kubectl` wrapper context was also corrected from `kind-kind-ai-dev` to `devcluster` to match `~/.kube/opencode-devcluster`.

1. **Header case sensitivity and missing metadata:** If `x-mlflow-experiment-id` is omitted by the caller, `headers_setter` must not crash or drop spans; traces default to experiment 0 or MLflow default.
2. **Batch processor metadata stripping:** If `metadata_keys` does not include `x-mlflow-experiment-id`, batched spans lose their tenant context in transit; batching must explicitly preserve this key.
3. **MLflow host header rejection:** OpenTelemetry `otlphttp` exporter sends HTTP request headers including `Host: mlflow:5000`; omitting `mlflow:*` from `--allowed-hosts` causes MLflow to reject requests with 403 Forbidden.
4. **Port collision or missing Kind mapping:** Host port 17903 must be registered in both the Service NodePort and `kind-config.yaml` to ensure cluster portability between Lima k3s and Kind.
5. **Memory pressure and pod eviction:** The collector must include a `memory_limiter` processor configured before `batch` in the pipeline to prevent OOMKills under bursty trace volume.

---

### Task 1: Pytest Test Suite for OpenTelemetry Collector Manifests

**Files:**
- Create: `.config/dotfiles/tests/test_otel_collector_manifests.py`

**Interfaces:**
- Consumes: `conftest.ROOT`, `.config/k8s/base/`, `.config/k8s/kind-config.yaml`, `.config/k8s/kustomization.yaml`, `.config/caddy/sites/otel.caddy.example`
- Produces: 13 executable Pytest test cases verifying the complete OTel Collector configuration contract.

 - [x] **Step 1: Write the failing test suite covering all 13 test requirements**

Create `.config/dotfiles/tests/test_otel_collector_manifests.py` with tests:
1. `test_otel_collector_manifest_exists_and_uses_pinned_image`: Deployment exists with image `otel/opentelemetry-collector-k8s:0.123.0`.
2. `test_otel_collector_resource_sizing`: CPU requests `50m`, memory `64Mi`, CPU limits `500m`, memory `512Mi`.
3. `test_otel_collector_health_probes`: Liveness and readiness probes configured on port 13133, path `/`.
4. `test_otel_collector_otlp_http_receiver`: Receiver `otlp.protocols.http` on `0.0.0.0:4318` with `include_metadata: true`.
5. `test_otel_collector_batch_processor_preserves_experiment_id`: Batch processor specifies `metadata_keys` containing `x-mlflow-experiment-id`.
6. `test_otel_collector_memory_limiter_processor`: Memory limiter processor configured with `check_interval`, `limit_percentage`, and `spike_limit_percentage`.
7. `test_otel_collector_health_check_extension`: Health check extension configured on `0.0.0.0:13133`.
8. `test_otel_collector_headers_setter_extension`: `headers_setter/mlflow` extension configured with action `upsert`, key `x-mlflow-experiment-id`, and `from_context: x-mlflow-experiment-id`.
9. `test_otel_collector_otlphttp_exporter_authenticator`: Exporter `otlphttp/mlflow` configured with endpoint `http://mlflow:5000` and `auth.authenticator: headers_setter/mlflow`.
10. `test_otel_collector_traces_pipeline`: Traces pipeline wires receiver `otlp`, processors `[memory_limiter, batch]`, exporter `otlphttp/mlflow`, and service extensions list includes `health_check` and `headers_setter/mlflow`.
11. `test_otel_collector_service_nodeport_mapping`: Service maps `port: 4318` to `nodePort: 17903` as `NodePort`.
12. `test_kustomization_and_kind_config_include_otel_collector`: `kustomization.yaml` includes `base/otel-collector.yaml` and `kind-config.yaml` maps container/host port 17903.
13. `test_mlflow_allowed_hosts_and_caddy_example`: `mlflow.yaml` includes `mlflow:*` in `--allowed-hosts`, and `otel.caddy.example` proxies `otel.example.internal` to `127.0.0.1:17903` with `cloudflare_tls`.

- [x] **Step 2: Run pytest to verify all new tests fail**

Run: `pytest .config/dotfiles/tests/test_otel_collector_manifests.py -v`
Expected: FAIL (files not found / assertions fail).

- [x] **Step 3: Commit initial test suite**

Run:
```bash
sandbox-git add .config/dotfiles/tests/test_otel_collector_manifests.py
sandbox-git commit -m "test(k8s): add manifest tests for otel-collector integration"
```

---

### Task 2: OpenTelemetry Collector Kubernetes Manifest

**Files:**
- Create: `.config/k8s/base/otel-collector.yaml`

**Interfaces:**
- Consumes: ConfigMap and Deployment standards from `.config/k8s/base/`
- Produces: `ConfigMap/otel-collector-config`, `Deployment/otel-collector`, and `Service/otel-collector`

- [x] **Step 1: Create `.config/k8s/base/otel-collector.yaml`**

Define:
1. `ConfigMap` `otel-collector-config`:
   - `receivers.otlp.protocols.http`: `endpoint: 0.0.0.0:4318`, `include_metadata: true`.
   - `processors.memory_limiter`: `check_interval: 1s`, `limit_percentage: 75`, `spike_limit_percentage: 15`.
   - `processors.batch`: `metadata_keys: ["x-mlflow-experiment-id"]`.
   - `extensions.health_check`: `endpoint: 0.0.0.0:13133`.
   - `extensions.headers_setter/mlflow`: `headers: [{action: upsert, key: x-mlflow-experiment-id, from_context: x-mlflow-experiment-id}]`.
   - `exporters.otlphttp/mlflow`: `endpoint: http://mlflow:5000`, `auth: {authenticator: headers_setter/mlflow}`. Include commented `# debug: {verbosity: detailed}` for troubleshooting.
   - `service.extensions`: `[health_check, headers_setter/mlflow]`.
   - `service.pipelines.traces`: `receivers: [otlp]`, `processors: [memory_limiter, batch]`, `exporters: [otlphttp/mlflow]`.
2. `Deployment` `otel-collector`:
   - 1 replica, selector `app: otel-collector`.
   - Pod template with labels `app: otel-collector`, `app.kubernetes.io/name: otel-collector`, `app.kubernetes.io/part-of: ai-infrastructure`.
    - Container image: `otel/opentelemetry-collector-k8s:0.123.0`.
   - Command: `["/otelcol-k8s"]`, Args: `["--config=/etc/otelcol/config.yaml"]`.
   - Container ports: `4318` (name: `otlp-http`), `13133` (name: `healthcheck`).
   - Sizing: requests `cpu: 50m`, `memory: 64Mi`; limits `cpu: 500m`, `memory: 512Mi`.
   - Probes: `livenessProbe` and `readinessProbe` pointing to HTTP port `13133`, path `/`.
   - Volume mount: `name: config`, `mountPath: /etc/otelcol`.
   - Volume: `name: config`, `configMap.name: otel-collector-config`.
3. `Service` `otel-collector`:
   - `type: NodePort`.
   - Selector `app: otel-collector`.
   - Port `4318`, `targetPort: 4318`, `nodePort: 17903`, `name: otlp-http`.
   - Port `13133`, `targetPort: 13133`, `name: healthcheck`.

- [x] **Step 2: Run pytest to check manifest assertions**

Run: `pytest .config/dotfiles/tests/test_otel_collector_manifests.py -k "test_otel_collector" -v`
Expected: Tasks 1-11 pass; tests 12 and 13 fail pending integration.

- [x] **Step 3: Commit manifest**

Run:
```bash
sandbox-git add .config/k8s/base/otel-collector.yaml
sandbox-git commit -m "feat(k8s): add opentelemetry-collector deployment and service manifest"
```

---

### Task 3: Update MLflow Manifest Allowed Hosts

**Files:**
- Modify: `.config/k8s/base/mlflow.yaml:52-54`

**Interfaces:**
- Consumes: MLflow CLI `--allowed-hosts` argument
- Produces: Allowed host configuration permitting cluster internal pod queries (`http://mlflow:5000`)

- [x] **Step 1: Update `--allowed-hosts` in `.config/k8s/base/mlflow.yaml`**

In `.config/k8s/base/mlflow.yaml`, update:
```yaml
            - --allowed-hosts
            - mlflow.example.internal,localhost:*,127.0.0.1:*,mlflow:*
```

- [x] **Step 2: Run existing MLflow manifest tests**

Run: `pytest .config/dotfiles/tests/test_mlflow_manifests.py -v`
Expected: PASS (all tests pass including host pattern check).

- [x] **Step 3: Commit MLflow manifest update**

Run:
```bash
sandbox-git add .config/k8s/base/mlflow.yaml
sandbox-git commit -m "fix(mlflow): allow pod-internal mlflow hostnames in allowed-hosts"
```

---

### Task 4: Cluster Kustomization and Kind Port Mappings

**Files:**
- Modify: `.config/k8s/kustomization.yaml:4-8`
- Modify: `.config/k8s/kind-config.yaml:18-21`

**Interfaces:**
- Consumes: Kustomize resource list, Kind extraPortMappings
- Produces: Automated deployment of `otel-collector.yaml` on `devcluster up` and port 17903 mapping on Kind

- [x] **Step 1: Add `base/otel-collector.yaml` to `.config/k8s/kustomization.yaml`**

Update `resources` in `.config/k8s/kustomization.yaml`:
```yaml
resources:
  - base/namespace.yaml
  - base/mlflow.yaml
  - base/mcp-servers.yaml
  - base/otel-collector.yaml
```

- [x] **Step 2: Add port 17903 mapping to `.config/k8s/kind-config.yaml`**

Under `nodes[0].extraPortMappings` in `.config/k8s/kind-config.yaml`, add:
```yaml
      - containerPort: 17903
        hostPort: 17903
        protocol: TCP
```

- [x] **Step 3: Verify Kustomization build**

Run: `kubectl kustomize .config/k8s/`
Expected: Valid multi-resource YAML containing `Namespace/ai-dev`, `PersistentVolumeClaim/mlflow-pvc`, `Deployment/mlflow`, `Deployment/otel-collector`, `Service/otel-collector`, etc.

- [x] **Step 4: Commit cluster configuration updates**

Run:
```bash
sandbox-git add .config/k8s/kustomization.yaml .config/k8s/kind-config.yaml
sandbox-git commit -m "feat(k8s): register otel-collector in kustomization and kind-config"
```

---

### Task 5: Caddy Ingress Site Configuration

**Files:**
- Create: `.config/caddy/sites/otel.caddy.example`

**Interfaces:**
- Consumes: Caddy reverse proxy on macOS host
- Produces: Reverse proxy template routing `https://otel.example.internal` -> `127.0.0.1:17903`

- [x] **Step 1: Create `.config/caddy/sites/otel.caddy.example`**

```caddy
# OpenTelemetry Collector OTLP HTTP receiver
otel.example.internal {
    import cloudflare_tls
    reverse_proxy 127.0.0.1:17903
}
```

- [x] **Step 2: Run all dotfiles tests**

Run: `pytest .config/dotfiles/tests/ -v`
Expected: 13/13 passed in `test_otel_collector_manifests.py`, all passed across whole suite.

- [x] **Step 3: Commit Caddy site configuration**

Run:
```bash
sandbox-git add .config/caddy/sites/otel.caddy.example
sandbox-git commit -m "feat(caddy): add otel reverse proxy site example"
```

---

### Task 6: Documentation and Runbook Updates

**Files:**
- Modify: `.config/k8s/README.md`
- Modify: `.config/opencode/env.example`

**Interfaces:**
- Consumes: OpenCode telemetry environment variables and stack architecture
- Produces: Comprehensive guide for OpenTelemetry Collector, sizing rationale, port mappings, OpenCode `.envrc` usage, and debugging commands.

- [x] **Step 1: Update `.config/k8s/README.md`**

Update the following sections:
1. **Stack Overview**: Add OpenTelemetry Collector (`otel-collector`) entry describing trace forwarding and header injection into MLflow.
2. **Sizing Rationale**: Add `OpenTelemetry Collector` subsection:
   - Requests: 50m CPU, 64Mi memory
   - Limits: 500m CPU, 512Mi memory
   - NodePort: 17903 (`https://otel.example.internal` through Caddy)
   - Rationale: Lightweight stateless reverse-proxy and batcher buffer; memory limiter prevents container thrashing.
3. **Port Mapping Table**: Add entry `4318` container -> `17903` host for `OTel Collector` (`OTLP HTTP receiver`).
4. **Architecture Diagram**: Add an ASCII or Mermaid diagram illustrating:
   `[OpenCode Client / CLI]` --(OTLP HTTP + x-mlflow-experiment-id)--> `[Caddy / Port 17903]` --> `[OTel Collector Pod (ai-dev)]` --(Batch + headers_setter)--> `[MLflow Pod (port 5000)]` --> `[SQLite / File Store]`.
5. **OpenCode Configuration Guide**: Provide snippet for repository `.envrc` / shell config:
   ```bash
   export OPENCODE_OTLP_ENDPOINT="https://otel.example.internal/v1/traces"
   # or direct loopback:
   # export OPENCODE_OTLP_ENDPOINT="http://127.0.0.1:17903/v1/traces"
   export MLFLOW_EXPERIMENT_ID="<your-experiment-id>"
   ```
6. **Debugging & Operations**: Commands for health checking (`curl http://127.0.0.1:17903/...`), checking collector logs (`kubectl logs -n ai-dev -l app=otel-collector -f`), and toggling `debug` exporter.

- [x] **Step 2: Update `.config/opencode/env.example`**

Add `OPENCODE_OTLP_ENDPOINT` pointing to `https://otel.example.internal/v1/traces` alongside existing `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID`.

- [x] **Step 3: Commit documentation updates**

Run:
```bash
sandbox-git add .config/k8s/README.md .config/opencode/env.example
sandbox-git commit -m "docs(k8s): document otel collector sizing, architecture, and opencode config"
```

---

### Task 7: End-to-End Cluster Validation and Verification

**Files:**
- None (operational execution and verification)

**Interfaces:**
- Consumes: Running Lima `devcluster`, active Caddy instance
- Produces: Verified healthy running collector and validated trace reception in MLflow.

- [x] **Step 1: Deploy to devcluster**

Run:
```bash
devcluster up
```
Verify:
```bash
kubectl get pods -n ai-dev -l app=otel-collector
kubectl get svc -n ai-dev otel-collector
```
Expected: Pod status `Running` (1/1 ready), Service showing NodePort `17903`.

- [x] **Step 2: Check collector health check probe**

From host:
```bash
curl -i http://127.0.0.1:17903/
# Note: Health check runs on internal port 13133; verify via port-forward or pod exec:
kubectl exec -it deployment/otel-collector -n ai-dev -- wget -q -O - http://localhost:13133/
```
Expected: `{"status":"Server available"}` (HTTP 200).

- [x] **Step 3: Send single-project trace test**

Send synthetic OTLP HTTP trace with `x-mlflow-experiment-id: 0`:
```bash
curl -i -X POST http://127.0.0.1:17903/v1/traces \
  -H "Content-Type: application/json" \
  -H "x-mlflow-experiment-id: 0" \
  -d '{"resourceSpans":[]}'
```
Expected: HTTP 200 OK or HTTP 202 Accepted from OTel collector. Check collector logs:
```bash
kubectl logs -n ai-dev -l app=otel-collector --tail=50
```

- [x] **Step 4: Send multi-tenant concurrent trace test**

Send traces with different experiment IDs (`x-mlflow-experiment-id: 1`, `x-mlflow-experiment-id: 2`) concurrently and verify batching/forwarding preserves respective headers to `http://mlflow:5000`:
Check MLflow logs to confirm experiment routing without host errors:
```bash
kubectl logs -n ai-dev -l app=mlflow --tail=50
```

---

## Plan Self-Review Checklist

- [x] **Spec coverage**:
  - NodePort 17903 mapped to container 4318: Task 2, Task 4.
  - Image pinned to `otel/opentelemetry-collector-k8s:0.123.0`: Task 1, Task 2.
  - Receiver OTLP HTTP with `include_metadata: true`: Task 2.
  - Processors: `batch` with `metadata_keys: ["x-mlflow-experiment-id"]` and `memory_limiter`: Task 2.
  - Extensions: `health_check` (13133) and `headers_setter/mlflow` (upsert key `x-mlflow-experiment-id` from context): Task 2.
  - Exporter: `otlphttp/mlflow` targeting `http://mlflow:5000` with authenticator: Task 2.
  - MLflow `--allowed-hosts` updated with `mlflow:*`: Task 3.
  - Caddy template `otel.caddy.example` with `127.0.0.1:17903`: Task 5.
  - Sizing requests 50m/64Mi, limits 500m/512Mi, probes on 13133: Task 2.
  - 13 manifest tests: Task 1.
  - Documentation, sizing rationale, architecture diagram, OpenCode `.envrc` instructions: Task 6.
  - E2E validation: Task 7.
- [x] **Concrete file & symbol references**: Explicit paths (`.config/k8s/base/otel-collector.yaml`, `.config/caddy/sites/otel.caddy.example`, `.config/dotfiles/tests/test_otel_collector_manifests.py`, etc.).
- [x] **Discrete tasks**: Tasks are scoped to distinct deliverables with clear entry/exit criteria and independent test cycles.
- [x] **No unresolved architecture decisions**: Image, ports, components, extensions, and headers are fully specified.
