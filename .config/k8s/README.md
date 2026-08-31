# Kubernetes AI Development Stack

This directory contains Kubernetes manifests for the AI development infrastructure managed by dotfiles-cluster.

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
- NodePorts: 17980 (NotebookLM), 17981 (Workspace)
- Reasoning: Lightweight API servers; minimal resource requirements

## Port Mapping

| Container Port | Host Port | Service | Description |
|----------------|-----------|---------|-------------|
| 80 | 17988 | Ingress HTTP | HTTP ingress traffic |
| 443 | 17943 | Ingress HTTPS | HTTPS ingress traffic |
| 3000 | 17900 | Langfuse Web | Web UI access |
| 9001 | 17901 | MinIO Console | Storage console |
| 17200 | 17980 | MCP NotebookLM | NotebookLM MCP server |
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
dotfiles-cluster create
# or
make cluster-create

# Deploy manifests
dotfiles-cluster up
# or
make cluster-up

# Check status
dotfiles-cluster status
# or
make cluster-status

# View logs
dotfiles-cluster logs <pod-name> [container]
# or
make cluster-logs

# Stop cluster (preserve state)
dotfiles-cluster down
# or
make cluster-down

# Delete cluster
dotfiles-cluster delete
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

### Secret Management

1. Copy environment template:
   ```bash
   cp ~/.config/k8s/env.example ~/.config/k8s/.env
   ```

2. Fill in secrets:
   ```bash
   # Generate secure passwords
   openssl rand -base64 32
   ```

3. Create secrets:
   ```bash
   kubectl create secret generic langfuse-secrets \
     --from-env-file=~/.config/k8s/.env \
     -n ai-dev
   ```

4. Update environment:
   ```bash
   kubectl create configmap langfuse-config \
     --from-env-file=~/.config/k8s/.env \
     -n ai-dev
   ```

## Secrets Reference

| Secret Key | Purpose |
|------------|---------|
| `LANGFUSE_SECRET_KEY` | NextAuth secret for Langfuse |
| `POSTGRES_USER` | PostgreSQL username |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `CLICKHOUSE_USER` | ClickHouse username |
| `CLICKHOUSE_PASSWORD` | ClickHouse password |
| `REDIS_PASSWORD` | Redis authentication |
| `MINIO_ROOT_USER` | MinIO access key |
| `MINIO_ROOT_PASSWORD` | MinIO secret key |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID for Workspace MCP |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret for Workspace MCP |

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
                                    │  NodePorts 17980  │
                                    │  NodePorts 17981  │
                                    └───────────────────┘
```
