# Kubernetes AI Development Stack

This directory contains Kubernetes manifests for the AI development infrastructure managed by devcluster.

## Stack Overview

The stack includes:
- **Langfuse** - Observation & analytics platform (Web UI + Worker)
- **PostgreSQL** - Primary database (v16)
- **ClickHouse** - Analytics database (v24.3)
- **Redis** - Caching layer (v7)
- **MinIO** - Object storage (v2024)
- **MCP Servers** - Model Context Protocol servers (NotebookLM, Workspace)

## Sizing Rationale

### PostgreSQL
- Requests: 100m CPU, 256Mi memory
- Limits: 500m CPU, 1Gi memory
- PVC: 10Gi
- Reasoning: Supports Langfuse's primary database with room for growth

### ClickHouse
- Requests: 200m CPU, 512Mi memory
- Limits: 1000m CPU, 2Gi memory
- PVC: 20Gi (data) + 10Gi (logs)
- Reasoning: Analytics queries require more memory; dual PVC for separation

### Redis
- Requests: 50m CPU, 64Mi memory
- Limits: 200m CPU, 256Mi memory
- PVC: 5Gi (noeviction policy)
- Reasoning: Caching layer with minimal resources; persistence for failover

### MinIO
- Requests: 100m CPU, 128Mi memory
- Limits: 500m CPU, 512Mi memory
- PVC: 50Gi
- Reasoning: Object storage for Langfuse assets with substantial capacity

### Langfuse Web
- Requests: 200m CPU, 512Mi memory
- Limits: 1000m CPU, 1.5Gi memory
- NodePort: 17900
- Reasoning: Web server handling user requests; scales with traffic

### Langfuse Worker
- Requests: 200m CPU, 512Mi memory
- Limits: 1000m CPU, 1.5Gi memory
- Reasoning: Background job processing; same sizing as web server

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
| 3000 | 17900 | Langfuse Web | Web UI access |
| 9001 | 17901 | MinIO Console | Storage console |
| 17200 | 17980 | MCP NotebookLM | NotebookLM MCP server |
| 6080 | 17982 | MCP NotebookLM noVNC | NotebookLM noVNC web interface (`/vnc.html`) |
| 8000 | 17981 | MCP Workspace | Google Workspace MCP server |
| 6443 | 17964 | Kubernetes API | API server (127.0.0.1:17964) |
| 5432 | - | PostgreSQL | Internal (ClusterIP) |
| 8123 | - | ClickHouse | HTTP API (internal) |
| 6379 | - | Redis | Internal (ClusterIP) |
| 9000 | - | MinIO API | Internal (ClusterIP) |

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

# Port-forward for debugging
kubectl port-forward svc/langfuse-web 3000:3000 -n ai-dev

# View logs
kubectl logs -n ai-dev -l app=langfuse-web --follow
kubectl logs -n ai-dev -l app=postgres --follow
```

### Secret Management & Auto-Provisioning

Secrets are managed via separated Kubernetes secrets and auto-provisioned automatically by `devcluster up`.

- **Zero-Config Dev Defaults**: For local development, all database and Langfuse secrets (including headless organization, project, and user provisioning) have built-in defaults. You do not need to configure any environment variables to run Langfuse, PostgreSQL, ClickHouse, MinIO, or Redis locally.
- **Headless Auto-Initialization**: Langfuse automatically seeds an initial admin user, organization, and project with deterministic API keys on first boot using `LANGFUSE_INIT_*` environment variables passed via `ai-dev-secrets`.
- **Environment Variable Hierarchy & Prefixes**: To avoid variable collisions in global shell environments (`~/.config/zsh/`), environment variables support `AI_DEV_*` (highest priority) and `DEVCLUSTER_*` prefixes, falling back to legacy unprefixed names:
  - `POSTGRES_PASSWORD`: `${AI_DEV_POSTGRES_PASSWORD:-${DEVCLUSTER_POSTGRES_PASSWORD:-${POSTGRES_PASSWORD:-postgresdevpass123}}}`
  - `CLICKHOUSE_PASSWORD`: `${AI_DEV_CLICKHOUSE_PASSWORD:-${DEVCLUSTER_CLICKHOUSE_PASSWORD:-${CLICKHOUSE_PASSWORD:-clickhousedevpass123}}}`
  - `MINIO_ROOT_PASSWORD`: `${AI_DEV_MINIO_ROOT_PASSWORD:-${DEVCLUSTER_MINIO_ROOT_PASSWORD:-${MINIO_ROOT_PASSWORD:-miniodevpass123}}}`
  - `REDIS_PASSWORD`: `${AI_DEV_REDIS_PASSWORD:-${DEVCLUSTER_REDIS_PASSWORD:-${REDIS_PASSWORD:-redisdevpass123}}}`
  - `LANGFUSE_SECRET_KEY` (encryption/session key): `${AI_DEV_LANGFUSE_ENCRYPTION_KEY:-${DEVCLUSTER_LANGFUSE_ENCRYPTION_KEY:-${LANGFUSE_SECRET_KEY:-devsecretkey_0123456789abcdef0123456789abcdef}}}`
  - Headless Init: `${AI_DEV_LANGFUSE_INIT_*:-${DEVCLUSTER_LANGFUSE_INIT_*:-${LANGFUSE_INIT_*:-...}}}`
- **Shell Environment Variables (Primary)**: Customize credentials by setting variables in your shell configuration (e.g. `~/.config/zsh/10-env.zsh` or `~/.config/zsh/secrets.zsh`). When `devcluster up` runs, it reads these variables from your active shell environment.
- **Fallback `.env`**: Alternatively, you can copy `~/.config/k8s/env.example` to `~/.config/k8s/.env` as a fallback. Shell environment variables always take precedence.

When `devcluster up` executes, it automatically generates and applies two separated secrets:
1. `ai-dev-secrets`: Infrastructure & Langfuse secrets (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `REDIS_PASSWORD`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_INIT_*`).
2. `workspace-mcp-secrets`: Google Workspace OAuth secrets (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`).

Manual creation (if needed):
```bash
# Provision ai-dev-secrets
kubectl create secret generic ai-dev-secrets \
  --namespace ai-dev \
  --from-literal=POSTGRES_USER="${AI_DEV_POSTGRES_USER:-${DEVCLUSTER_POSTGRES_USER:-${POSTGRES_USER:-langfuse}}}" \
  --from-literal=POSTGRES_PASSWORD="${AI_DEV_POSTGRES_PASSWORD:-${DEVCLUSTER_POSTGRES_PASSWORD:-${POSTGRES_PASSWORD:-postgresdevpass123}}}" \
  --from-literal=CLICKHOUSE_USER="${AI_DEV_CLICKHOUSE_USER:-${DEVCLUSTER_CLICKHOUSE_USER:-${CLICKHOUSE_USER:-langfuse}}}" \
  --from-literal=CLICKHOUSE_PASSWORD="${AI_DEV_CLICKHOUSE_PASSWORD:-${DEVCLUSTER_CLICKHOUSE_PASSWORD:-${CLICKHOUSE_PASSWORD:-clickhousedevpass123}}}" \
  --from-literal=MINIO_ROOT_USER="${AI_DEV_MINIO_ROOT_USER:-${DEVCLUSTER_MINIO_ROOT_USER:-${MINIO_ROOT_USER:-langfuse}}}" \
  --from-literal=MINIO_ROOT_PASSWORD="${AI_DEV_MINIO_ROOT_PASSWORD:-${DEVCLUSTER_MINIO_ROOT_PASSWORD:-${MINIO_ROOT_PASSWORD:-miniodevpass123}}}" \
  --from-literal=REDIS_PASSWORD="${AI_DEV_REDIS_PASSWORD:-${DEVCLUSTER_REDIS_PASSWORD:-${REDIS_PASSWORD:-redisdevpass123}}}" \
  --from-literal=LANGFUSE_SECRET_KEY="${AI_DEV_LANGFUSE_ENCRYPTION_KEY:-${DEVCLUSTER_LANGFUSE_ENCRYPTION_KEY:-${LANGFUSE_SECRET_KEY:-devsecretkey_0123456789abcdef0123456789abcdef}}}" \
  --from-literal=LANGFUSE_INIT_USER_EMAIL="${AI_DEV_LANGFUSE_INIT_USER_EMAIL:-${DEVCLUSTER_LANGFUSE_INIT_USER_EMAIL:-${LANGFUSE_INIT_USER_EMAIL:-kpiwko@localhost}}}" \
  --from-literal=LANGFUSE_INIT_USER_NAME="${AI_DEV_LANGFUSE_INIT_USER_NAME:-${DEVCLUSTER_LANGFUSE_INIT_USER_NAME:-${LANGFUSE_INIT_USER_NAME:-Karel Piwko}}}" \
  --from-literal=LANGFUSE_INIT_USER_PASSWORD="${AI_DEV_LANGFUSE_INIT_USER_PASSWORD:-${DEVCLUSTER_LANGFUSE_INIT_USER_PASSWORD:-${LANGFUSE_INIT_USER_PASSWORD:-langfusedevpass123}}}" \
  --from-literal=LANGFUSE_INIT_ORG_ID="${AI_DEV_LANGFUSE_INIT_ORG_ID:-${DEVCLUSTER_LANGFUSE_INIT_ORG_ID:-${LANGFUSE_INIT_ORG_ID:-local-dev}}}" \
  --from-literal=LANGFUSE_INIT_ORG_NAME="${AI_DEV_LANGFUSE_INIT_ORG_NAME:-${DEVCLUSTER_LANGFUSE_INIT_ORG_NAME:-${LANGFUSE_INIT_ORG_NAME:-Local Dev}}}" \
  --from-literal=LANGFUSE_INIT_PROJECT_ID="${AI_DEV_LANGFUSE_INIT_PROJECT_ID:-${DEVCLUSTER_LANGFUSE_INIT_PROJECT_ID:-${LANGFUSE_INIT_PROJECT_ID:-local-project}}}" \
  --from-literal=LANGFUSE_INIT_PROJECT_NAME="${AI_DEV_LANGFUSE_INIT_PROJECT_NAME:-${DEVCLUSTER_LANGFUSE_INIT_PROJECT_NAME:-${LANGFUSE_INIT_PROJECT_NAME:-Local Project}}}" \
  --from-literal=LANGFUSE_INIT_PROJECT_PUBLIC_KEY="${AI_DEV_LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-${DEVCLUSTER_LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-${LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-pk-lf-0123456789abcdef0123456789abcdef}}}" \
  --from-literal=LANGFUSE_INIT_PROJECT_SECRET_KEY="${AI_DEV_LANGFUSE_INIT_PROJECT_SECRET_KEY:-${DEVCLUSTER_LANGFUSE_INIT_PROJECT_SECRET_KEY:-${LANGFUSE_INIT_PROJECT_SECRET_KEY:-sk-lf-0123456789abcdef0123456789abcdef}}}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Provision workspace-mcp-secrets
kubectl create secret generic workspace-mcp-secrets \
  --namespace ai-dev \
  --from-literal=GOOGLE_OAUTH_CLIENT_ID="${AI_DEV_GOOGLE_OAUTH_CLIENT_ID:-${DEVCLUSTER_GOOGLE_OAUTH_CLIENT_ID:-${GOOGLE_OAUTH_CLIENT_ID:-}}}" \
  --from-literal=GOOGLE_OAUTH_CLIENT_SECRET="${AI_DEV_GOOGLE_OAUTH_CLIENT_SECRET:-${DEVCLUSTER_GOOGLE_OAUTH_CLIENT_SECRET:-${GOOGLE_OAUTH_CLIENT_SECRET:-}}}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Secrets Reference

### `ai-dev-secrets` (Langfuse & Databases)

| Secret Key | Env Variable Hierarchy | Purpose | Default Dev Value |
|------------|------------------------|---------|-------------------|
| `POSTGRES_USER` | `AI_DEV_POSTGRES_USER` / `DEVCLUSTER_POSTGRES_USER` / `POSTGRES_USER` | PostgreSQL username | `langfuse` |
| `POSTGRES_PASSWORD` | `AI_DEV_POSTGRES_PASSWORD` / `DEVCLUSTER_POSTGRES_PASSWORD` / `POSTGRES_PASSWORD` | PostgreSQL password | `postgresdevpass123` |
| `CLICKHOUSE_USER` | `AI_DEV_CLICKHOUSE_USER` / `DEVCLUSTER_CLICKHOUSE_USER` / `CLICKHOUSE_USER` | ClickHouse username | `langfuse` |
| `CLICKHOUSE_PASSWORD` | `AI_DEV_CLICKHOUSE_PASSWORD` / `DEVCLUSTER_CLICKHOUSE_PASSWORD` / `CLICKHOUSE_PASSWORD` | ClickHouse password | `clickhousedevpass123` |
| `MINIO_ROOT_USER` | `AI_DEV_MINIO_ROOT_USER` / `DEVCLUSTER_MINIO_ROOT_USER` / `MINIO_ROOT_USER` | MinIO access key | `langfuse` |
| `MINIO_ROOT_PASSWORD` | `AI_DEV_MINIO_ROOT_PASSWORD` / `DEVCLUSTER_MINIO_ROOT_PASSWORD` / `MINIO_ROOT_PASSWORD` | MinIO secret key | `miniodevpass123` |
| `REDIS_PASSWORD` | `AI_DEV_REDIS_PASSWORD` / `DEVCLUSTER_REDIS_PASSWORD` / `REDIS_PASSWORD` | Redis password | `redisdevpass123` |
| `LANGFUSE_SECRET_KEY` | `AI_DEV_LANGFUSE_ENCRYPTION_KEY` / `DEVCLUSTER_LANGFUSE_ENCRYPTION_KEY` / `LANGFUSE_SECRET_KEY` | NextAuth secret key | `devsecretkey_0123456789abcdef0123456789abcdef` |
| `LANGFUSE_INIT_USER_EMAIL` | `AI_DEV_LANGFUSE_INIT_USER_EMAIL` / `DEVCLUSTER_LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_EMAIL` | Headless seed admin user email | `kpiwko@localhost` |
| `LANGFUSE_INIT_USER_NAME` | `AI_DEV_LANGFUSE_INIT_USER_NAME` / `DEVCLUSTER_LANGFUSE_INIT_USER_NAME` / `LANGFUSE_INIT_USER_NAME` | Headless seed admin user name | `Karel Piwko` |
| `LANGFUSE_INIT_USER_PASSWORD` | `AI_DEV_LANGFUSE_INIT_USER_PASSWORD` / `DEVCLUSTER_LANGFUSE_INIT_USER_PASSWORD` / `LANGFUSE_INIT_USER_PASSWORD` | Headless seed admin user password | `langfusedevpass123` |
| `LANGFUSE_INIT_ORG_ID` | `AI_DEV_LANGFUSE_INIT_ORG_ID` / `DEVCLUSTER_LANGFUSE_INIT_ORG_ID` / `LANGFUSE_INIT_ORG_ID` | Headless seed organization ID | `local-dev` |
| `LANGFUSE_INIT_ORG_NAME` | `AI_DEV_LANGFUSE_INIT_ORG_NAME` / `DEVCLUSTER_LANGFUSE_INIT_ORG_NAME` / `LANGFUSE_INIT_ORG_NAME` | Headless seed organization name | `Local Dev` |
| `LANGFUSE_INIT_PROJECT_ID` | `AI_DEV_LANGFUSE_INIT_PROJECT_ID` / `DEVCLUSTER_LANGFUSE_INIT_PROJECT_ID` / `LANGFUSE_INIT_PROJECT_ID` | Headless seed project ID | `local-project` |
| `LANGFUSE_INIT_PROJECT_NAME` | `AI_DEV_LANGFUSE_INIT_PROJECT_NAME` / `DEVCLUSTER_LANGFUSE_INIT_PROJECT_NAME` / `LANGFUSE_INIT_PROJECT_NAME` | Headless seed project name | `Local Project` |
| `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` | `AI_DEV_LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `DEVCLUSTER_LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` | Headless seed project public API key | `pk-lf-0123456789abcdef0123456789abcdef` |
| `LANGFUSE_INIT_PROJECT_SECRET_KEY` | `AI_DEV_LANGFUSE_INIT_PROJECT_SECRET_KEY` / `DEVCLUSTER_LANGFUSE_INIT_PROJECT_SECRET_KEY` / `LANGFUSE_INIT_PROJECT_SECRET_KEY` | Headless seed project secret API key | `sk-lf-0123456789abcdef0123456789abcdef` |

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

### Backups
```bash
# PostgreSQL backup
kubectl exec -n ai-dev -t postgres -- pg_dump -U langfuse langfuse > backup.sql

# ClickHouse backup
kubectl exec -n ai-dev -t clickhouse -- clickhouse-client --query "BACKUP DATABASE langfuse TO Disk('data', 'backup.tar')"
```

### Updates
```bash
# Update image versions in manifests
# Reapply
kubectl apply -k ~/.config/k8s/
```

## Architecture Diagram

```
                    ┌─────────────────┐
                    │   NodePort      │
                    │   17900         │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Langfuse Web   │
                    │   (Port 3000)   │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐      ┌─────▼─────┐      ┌────▼────┐
    │ PostgreSQL│      │  ClickHouse│     │  Redis  │
    │   (5432)  │      │  (8123/9000)│    │  (6379) │
    └───────────┘      └───────────┘      └─────────┘
          │                  │                  │
          │                  │                  │
    ┌─────▼─────┐      ┌─────▼─────┐      ┌────▼────┐
    │ Langfuse  │      │   MinIO    │      │  MCP    │
    │  Worker   │      │ (9000/9001)│      │ Servers │
    └───────────┘      └───────────┘      └─────────┘
                                              │
                                    ┌─────────┴─────────┐
                                    │  NodePort 17980   │
                                    │  NodePort 17981   │
                                    │  NodePort 17982   │
                                    └───────────────────┘
```
