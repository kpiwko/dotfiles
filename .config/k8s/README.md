# Kubernetes AI Development Stack

This directory contains Kubernetes manifests for the AI development infrastructure managed by devcluster.

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
- **MLflow** - GenAI tracking server for OpenCode traces
- **MCP Servers** - Model Context Protocol servers (NotebookLM, Workspace)

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

### MCP Servers
- Requests: 100m CPU, 256Mi memory each
- Limits: 500m CPU, 512Mi memory each
- NodePorts: 17980 (NotebookLM MCP), 17981 (Workspace MCP), 17982 (NotebookLM noVNC)
- Reasoning: Lightweight API servers; minimal resource requirements

## Port Mapping

| Container Port | Host Port | Service | Description |
|----------------|-----------|---------|-------------|
| 80 | 17988 | Ingress HTTP | HTTP ingress traffic |
| 443 | 17943 | Ingress HTTPS | HTTPS ingress traffic |
| 5000 | 17902 | MLflow | GenAI tracking UI and API |
| 17200 | 17980 | MCP NotebookLM | NotebookLM MCP server |
| 6080 | 17982 | MCP NotebookLM noVNC | NotebookLM noVNC web interface (`/vnc.html`) |
| 8000 | 17981 | MCP Workspace | Google Workspace MCP server |
| 6443 | 17964 | Kubernetes API | API server (127.0.0.1:17964) |

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
