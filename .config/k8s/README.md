# Kubernetes AI Development Stack

This directory contains Kubernetes manifests for the AI development infrastructure managed by devcluster.
MLflow is pinned to `ghcr.io/mlflow/mlflow:v3.17.0`.

## MLflow Migration-safe Manifests

The root Kustomization is intentionally a maintenance state: `kubectl apply -k
~/.config/k8s` leaves the MLflow and OpenTelemetry Collector writers scaled to
zero. Do not use the root Kustomization to start the stack directly.

The existing `ai-dev/mlflow-pvc` is a 10Gi `ReadWriteOnce` claim with the
immutable `local-path` storage class. Every manifest or Kustomize render that
declares `mlflow-pvc` must retain `storageClassName: local-path`; never change
it to `standard` or delete and recreate the claim to resolve an immutable-field
error. The migration manifest only references the claim, so it does not
declare a storage class.

`devcluster up` is the supported v3.17.0 lifecycle. It starts the Lima
instance if it is stopped (blocking until the instance's k3s service is
active), then applies the safe base, confirms that both writers have terminated, runs
the exclusive `mlflow-db-migrate` Job, waits for it to complete and be cleaned
up, applies `~/.config/k8s/runtime`, and waits for MLflow and OTel readiness.
If the instance does not exist or fails to start, `devcluster up` stops before
any cluster operation. This creates an expected maintenance window. The
migration Job mounts the RWO SQLite PVC by
itself and runs the idempotent command:

```text
mlflow db upgrade sqlite:////mlflow/mlflow.db
```

After the migration, `devcluster up` creates `agentgateway-secrets`, applies
the runtime overlay, and waits for MLflow, OTel, and AgentGateway readiness.
Do not apply the runtime overlay manually unless the preceding migration has
completed successfully.

### Failure containment and upgrade posture

MLflow and OTel are both stopped before migration because they are writers to
the same SQLite database on the `mlflow-pvc` ReadWriteOnce volume. A failed
migration leaves those writers stopped for diagnosis; later runtime and
AgentGateway phases are not applied. Inspect the bounded Job diagnostics with
`devcluster logs <pod>` or `devcluster-kubectl describe job mlflow-db-migrate
-n ai-dev`.

This initial setup explicitly accepts data loss. It provides **no** backup,
restore workflow, automatic schema downgrade, or recovery guarantee. After a
successful v3.17.0 migration, do not automatically roll the schema or image
back to an older MLflow version. Any destructive/manual recovery decision must
be separately approved.

### AgentGateway credentials

AgentGateway is a standalone Deployment with a single SQLite-backed replica.
Its ConfigMap is read-only repository state; provider credentials are loaded
only from `agentgateway-secrets`. The bounded source identity file
`~/.config/opencode/itpc-ca-993e2467de-opencode-vertex.json` must be readable;
its contents are materialized only as the `vertex-credentials.json` Secret key,
mounted read-only in the AgentGateway Pod, and never committed, printed, or
passed as a host path to the Pod.

The model aliases are `omnipower`, `architect`, `worker`, `reviewer`, `spade`,
and `gemini`. Omnipower uses Enmaas Claude Opus 5.5; architect uses Enmaas
GPT-6.1 Sol with OpenAI Terra fallback; worker uses Enmaas GLM 5.3; reviewer
uses Enmaas Claude Sonnet 5.5; and spade uses Enmaas GPT-6 Luna with OpenAI
Luna fallback. Gemini is defined for explicit use through Vertex and is not an
automatic fallback target.

### AgentGateway telemetry and cost attribution

AgentGateway exports resolved provider, upstream model, token usage, and
realized cost through OTLP/gRPC to the in-cluster OpenTelemetry Collector. The
Collector forwards both AgentGateway and OpenCode workflow spans to the fixed
MLflow experiment selected by `MLFLOW_EXPERIMENT_ID`. OpenCode contributes
session, agent, and tool context; AgentGateway is the cost authority because it
knows the actual failover target.

The agreed fixed experiment is **23** for every emitter. OpenCode's telemetry
plugin is configured to send `x-mlflow-experiment-id: 23` itself through the
`otlpHeaders` option in `~/.config/opencode/opencode.jsonc` (effective after
service restart), and the `headers_setter` extension forwards that metadata
unchanged, so OpenCode spans do not depend on this variable. AgentGateway expands the header from the
`MLFLOW_EXPERIMENT_ID` key of the `agentgateway-secrets` Secret, which
`devcluster up` provisions from your shell environment or
`~/.config/k8s/.env`. Neither manifest hardcodes the value. Before running
`devcluster up`, set `MLFLOW_EXPERIMENT_ID=23` in `~/.config/k8s/.env` (or
export it in the shell, which takes precedence) so AgentGateway spans land in
experiment 23 as well; a stale value such as `21` will route only AgentGateway
traffic to the wrong experiment.

The AgentGateway model catalog prices built-in public provider/model pairs. Add
an Enmaas override only after its billing rate and the emitted
provider/model-label pair are verified. Do not substitute an upstream public
price for an Enmaas bill.

## NotebookLM MCP Authentication Guide

NotebookLM uses session-based authentication rather than standard OAuth tokens. To authenticate:

1. Open the noVNC interface in your browser:
   `http://localhost:17982/vnc.html` (click **Connect**)
2. In your host terminal, run:
   ```bash
   KUBECONFIG=~/.kube/opencode-devcluster kubectl exec -it deployment/notebooklm-mcp -n ai-dev -- nlm login
   ```
3. In the Chromium window inside the noVNC browser tab, complete the Google login with your account (`kpiwko@redhat.com`).
4. Once logged in, session tokens are saved to the container volume and the MCP endpoint at `http://localhost:17980/mcp` is live.

## Stack Overview

The stack includes:
- **MLflow** - GenAI tracking and artifact server for OpenCode traces
- **AgentGateway** - the sole inference endpoint, exposing OpenAI-compatible
  and native Gemini APIs
- **MCP Servers** - Model Context Protocol servers (NotebookLM, Workspace)
- **OpenTelemetry Collector** - vendor-neutral telemetry gateway for OpenCode

## Sizing Rationale

### MLflow
- Requests: 200m CPU, 512Mi memory
- Limits: 1000m CPU, 1Gi memory
- PVC: 10Gi (SQLite backend and file artifacts)
- NodePort: 17902 (`https://mlflow.example.internal` through Caddy)
- Reasoning: Single-replica local tracking server; the persistent volume retains experiments and artifacts.

Access MLflow directly at `http://127.0.0.1:17902`. Do not use host port
5000: macOS AirPlay may reserve it. If a Kubernetes port-forward is required
for debugging, use `kubectl port-forward svc/mlflow 15000:5000 -n ai-dev` and
connect to `http://127.0.0.1:15000`.

### AgentGateway
- Image: `cr.agentgateway.dev/agentgateway:v1.6.0`
- NodePort: 17904 (`https://agentgateway.fous.ai/v1` through Caddy)
- PVC: 2Gi SQLite request-log and analytics database
- The external API requires `AGENTGATEWAY_API_KEY`; the UI is deliberately not
  exposed through Caddy.

### MCP Servers
- Requests: 100m CPU, 256Mi memory each
- Limits: 500m CPU, 512Mi memory each
- NodePorts: 17980 (NotebookLM MCP), 17981 (Workspace MCP), 17982 (NotebookLM noVNC)
- Reasoning: Lightweight API servers; minimal resource requirements

### OpenTelemetry Collector
- Requests: 50m CPU, 64Mi memory
- Limits: 500m CPU, 512Mi memory
- NodePort: 17903 (`https://otel.example.internal` through Caddy)
- Reasoning: Stateless telemetry gateway buffering and batching traces; memory limiter prevents pod memory thrashing.

Access the Collector directly at `http://127.0.0.1:17903`.

#### MLflow 3.17.0 span-type compatibility mapping

The Collector's `transform` processor copies `openinference.span.kind` into the
canonical `mlflow.spanType` attribute before ingestion. This is a local workaround
for a measured MLflow 3.17.0 indexing bug: the SQL `spans.type` column is written
only from the inbound canonical `mlflow.spanType`, while `openinference.span.kind`
is translated into stored display attributes only, so OpenInference-only spans get
a NULL SQL type and silently drop out of grouped `span_type` trace metrics even
though the MLflow UI displays their kind. The mapping is copied verbatim from the
upstream MLflow 3.17.0 `OpenInferenceTranslator.SPAN_KIND_TO_MLFLOW_TYPE` allowlist
(TOOL, CHAIN, LLM, RETRIEVER, EMBEDDING, AGENT, RERANKER, UNKNOWN, GUARDRAIL,
EVALUATOR — each mapping to the same-named `SpanType`), fires only when
`mlflow.spanType` is absent, and never overwrites an existing canonical value
(including empty or non-string ones). Missing, unknown or non-string kinds stay
unmapped; no `UNKNOWN` is synthesized. It is gated to removal once an upstream
MLflow release derives the SQL span type from translated attributes. The
opt-in behavioral test in
`.config/dotfiles/tests/test_mlflow_span_type_compatibility.py`
(`OTEL_SPAN_TYPE_BEHAVIORAL=1`) verifies Collector-side behavior only: that the
pinned Collector 0.123.0 exports the expected `mlflow.spanType` attributes
after the manifest transform runs. It does not itself exercise MLflow SQL
ingestion. That ingestion behavior was measured separately in a local MLflow
3.17.0 A/B comparison: spans carrying only `openinference.span.kind` were
stored with a NULL SQL `spans.type` (absent from grouped `span_type` metrics),
while spans that also carried the canonical `mlflow.spanType=TOOL` were stored
with the indexed TOOL type. The default offline suite runs only the module's
static consistency checks.

## Port Mapping

| Container Port | Host Port | Service | Description |
|----------------|-----------|---------|-------------|
| 80 | 17988 | Ingress HTTP | HTTP ingress traffic |
| 443 | 17943 | Ingress HTTPS | HTTPS ingress traffic |
| 5000 | 17902 | MLflow | GenAI tracking, artifacts, and API |
| 4000 | 17904 | AgentGateway | OpenAI-compatible model API |
| 17200 | 17980 | MCP NotebookLM | NotebookLM MCP server |
| 6080 | 17982 | MCP NotebookLM noVNC | NotebookLM noVNC web interface (`/vnc.html`) |
| 8000 | 17981 | MCP Workspace | Google Workspace MCP server |
| 6443 | 17964 | Kubernetes API | API server (127.0.0.1:17964) |
| 4317 | internal only | OTel Collector | AgentGateway OTLP/gRPC receiver |
| 4318 | 17903 | OTel Collector | OTLP HTTP receiver |

## Architecture

```text
OpenCode -- OpenAI-compatible or native Gemini model request --> AgentGateway
   |                                                               |
   | OTLP/HTTP: session, agent, tool, client spans                | OTLP/gRPC: resolved
   |                                                               | provider/model/usage/cost
   +-----------------------------+---------------------------------+
                                 v
                    OTel Collector (fixed MLflow experiment header)
                                 |
                                 v
                              MLflow (k3s)
```

Future telemetry backends (metrics, logs, or alternative trace backends) should
be attached to the Collector rather than directly to OpenCode.

## OpenCode Project Configuration (.envrc)

Projects can configure OpenCode telemetry in their `.envrc`:

```bash
export MLFLOW_EXPERIMENT_ID=23

export OPENCODE_ENABLE_TELEMETRY=1
export OPENCODE_OTLP_ENDPOINT="https://otel.example.internal"
export OPENCODE_OTLP_PROTOCOL="http/protobuf"

export OPENCODE_OTLP_HEADERS="x-mlflow-experiment-id=$MLFLOW_EXPERIMENT_ID"

export OPENCODE_RESOURCE_ATTRIBUTES="service.name=opencode,service.namespace=dotfiles"

# Keep logs/metrics disabled at plugin side until backends are added:
export OPENCODE_DISABLE_LOGS=1
```

The shared service configuration (`~/.config/opencode/opencode.jsonc`) already
sends `x-mlflow-experiment-id: 23` through the plugin's `otlpHeaders` option,
which takes precedence over `OPENCODE_OTLP_HEADERS`; exporting
`OPENCODE_OTLP_HEADERS` from a project `.envrc` therefore does **not** change
the header OpenCode actually sends while that plugin option is set. The
environment variable only becomes effective if the `otlpHeaders` plugin option
is removed or changed in the shared configuration (a supported configuration
change requiring an OpenCode service restart). Experiment 23 is the fixed
target for the shared service; to deviate per project, change the plugin
option explicitly rather than relying on the environment variable to override
it silently.

The shared OpenCode service batches telemetry from concurrent sessions, so a
fixed MLflow experiment is required. Filter traces by OpenCode session/trace
attributes instead of creating one MLflow experiment per session.

## Commands Reference

### Cluster Management

```bash
# Create cluster
devcluster create
# or
make cluster-create

# Deploy manifests
devcluster up
# or
make cluster-up

# Check status
devcluster status
# or
make cluster-status

# View logs
devcluster logs <pod-name> [container]
# or
make cluster-logs

# Stop cluster (preserve state)
devcluster down
# or
make cluster-down

# Delete cluster
devcluster delete
# or
make cluster-delete
```

### Kubectl Commands

```bash
# Apply manifests
kubectl apply -k ~/.config/k8s/

# View resources
kubectl get all -n ai-dev
kubectl get pods -n ai-dev
kubectl get services -n ai-dev

# Port-forward MLflow for debugging
kubectl port-forward svc/mlflow 15000:5000 -n ai-dev

# View MLflow logs
kubectl logs -n ai-dev -l app=mlflow --follow
```

### OpenTelemetry Collector Diagnostics

```bash
devcluster status
devcluster logs <otel-collector-pod>
devcluster-kubectl get pods -n ai-dev -l app=otel-collector
```

For temporary troubleshooting, uncomment the `debug` exporter in
`.config/k8s/base/otel-collector.yaml` (with `verbosity: detailed`) and include
it in `traces.exporters`. Do not leave detailed telemetry logging enabled:
traces may contain prompts or other sensitive information.

### Secret Management & Auto-Provisioning

The Workspace MCP OAuth secret is auto-provisioned by `devcluster up` from the
active shell environment or an optional `~/.config/k8s/.env` fallback.

Manual creation (if needed):
```bash
# Provision workspace-mcp-secrets
kubectl create secret generic workspace-mcp-secrets \
  --namespace ai-dev \
  --from-literal=GOOGLE_OAUTH_CLIENT_ID="${AI_DEV_GOOGLE_OAUTH_CLIENT_ID:-${DEVCLUSTER_GOOGLE_OAUTH_CLIENT_ID:-${GOOGLE_OAUTH_CLIENT_ID:-}}}" \
  --from-literal=GOOGLE_OAUTH_CLIENT_SECRET="${AI_DEV_GOOGLE_OAUTH_CLIENT_SECRET:-${DEVCLUSTER_GOOGLE_OAUTH_CLIENT_SECRET:-${GOOGLE_OAUTH_CLIENT_SECRET:-}}}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Secrets Reference

### `workspace-mcp-secrets` (Google Workspace MCP)

| Secret Key | Env Variable Hierarchy | Purpose | Default Dev Value |
|------------|------------------------|---------|-------------------|
| `GOOGLE_OAUTH_CLIENT_ID` | `AI_DEV_GOOGLE_OAUTH_CLIENT_ID` / `DEVCLUSTER_GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth Client ID | `""` (empty until configured) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `AI_DEV_GOOGLE_OAUTH_CLIENT_SECRET` / `DEVCLUSTER_GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Client Secret | `""` (empty until configured) |

---

## Google Workspace OAuth Setup Guide

The `workspace-mcp` service connects AI tools to Google Workspace (Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Apps Script). Follow this guide to set up credentials in the Google Cloud Console.

### 1. Create a Google Cloud Project & Enable APIs

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `ai-dev-workspace-mcp`) or select an existing project.
3. Navigate to **APIs & Services** > **Library**.
4. Search for and **Enable** each of the following APIs:
   - **Gmail API**
   - **Google Calendar API**
   - **Google Drive API**
   - **Google Docs API**
   - **Google Sheets API**
   - **Google Slides API**
   - **Google Forms API**
   - **Google Apps Script API**

### 2. Configure OAuth Consent Screen & Data Access Scopes

1. Navigate to **APIs & Services** > **OAuth consent screen**.
2. Select User Type:
   - Choose **Internal** if using a Google Workspace organization account.
   - Choose **External** if using a personal `@gmail.com` account (set Publishing status to **Testing** and add your email under **Test users**).
3. Fill in the required application details (App name, User support email, Developer contact email) and click **Save and Continue**.
4. On the **Scopes** (or **Data Access**) screen:
   - Click **Add or Remove Scopes**.
   - Select the required scopes for Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, and Apps Script.
   - Click **Update** and **Save and Continue**.

### 3. Create OAuth 2.0 Credentials

1. Navigate to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Set Application type to **Web application**.
4. Set Name to `workspace-mcp-client` (or any descriptive name).
5. Under **Authorized redirect URIs**, add:
   ```
   http://localhost:17981/oauth2callback
   ```
6. Click **Create**.
7. Copy the generated **Client ID** and **Client Secret**.

### 4. Configure Shell Environment

Export your credentials in your shell startup file (e.g. `~/.config/zsh/10-env.zsh` or `~/.config/zsh/secrets.zsh`):

```zsh
export AI_DEV_GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export AI_DEV_GOOGLE_OAUTH_CLIENT_SECRET="GOCSPX-your-client-secret"
```

### 5. Deploy & Authenticate

1. Apply manifests and secrets:
   ```bash
   devcluster up
   ```
2. `devcluster up` automatically provisions `workspace-mcp-secrets` into the `ai-dev` namespace from your shell environment.
3. Access the Workspace MCP OAuth flow at `http://localhost:17981` to authorize access.

## Troubleshooting

### Pod CrashLoopBackOff
```bash
kubectl logs <pod-name> -n ai-dev
kubectl describe pod <pod-name> -n ai-dev
```

### Service Not Accessible
```bash
kubectl get svc -n ai-dev
kubectl describe service <service-name> -n ai-dev
```

### Connection Refused
```bash
# Check if service is running
kubectl get endpoints <service-name> -n ai-dev

# Test internal connectivity
kubectl run -it --rm debug --image=busybox -n ai-dev -- sh
nslookup <service-name>
```

## Maintenance

### Updates
```bash
# Update image versions in manifests
# Reapply
kubectl apply -k ~/.config/k8s/
```
