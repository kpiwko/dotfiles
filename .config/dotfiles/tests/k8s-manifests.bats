#!/usr/bin/env bats

setup() {
  K8S_DIR="/Users/kpiwko/.config/k8s"
}

@test "k8s directory structure exists" {
  [ -d "$K8S_DIR" ]
  [ -d "$K8S_DIR/base" ]
}

@test "k8s .gitignore exists" {
  [ -f "$K8S_DIR/.gitignore" ]
}

@test "k8s env.example exists" {
  [ -f "$K8S_DIR/env.example" ]
}

@test "k8s kind-config.yaml exists" {
  [ -f "$K8S_DIR/kind-config.yaml" ]
  grep -q "apiServerAddress: \"127.0.0.1\"" "$K8S_DIR/kind-config.yaml"
  grep -q "apiServerPort: 17964" "$K8S_DIR/kind-config.yaml"
  grep -q "17988" "$K8S_DIR/kind-config.yaml"
  grep -q "17943" "$K8S_DIR/kind-config.yaml"
  grep -q "17900" "$K8S_DIR/kind-config.yaml"
  grep -q "17901" "$K8S_DIR/kind-config.yaml"
  grep -q "17980" "$K8S_DIR/kind-config.yaml"
  grep -q "17981" "$K8S_DIR/kind-config.yaml"
  grep -q "service-node-port-range: 17900-17999" "$K8S_DIR/kind-config.yaml"
}

@test "k8s base/namespace.yaml exists and is valid YAML" {
  [ -f "$K8S_DIR/base/namespace.yaml" ]
  # Basic YAML syntax check
  grep -q "apiVersion:" "$K8S_DIR/base/namespace.yaml"
  grep -q "kind: Namespace" "$K8S_DIR/base/namespace.yaml"
  grep -q "name: ai-dev" "$K8S_DIR/base/namespace.yaml"
}

@test "k8s base/configmap.yaml exists and is valid YAML" {
  [ -f "$K8S_DIR/base/configmap.yaml" ]
  grep -q "apiVersion:" "$K8S_DIR/base/configmap.yaml"
  grep -q "kind: ConfigMap" "$K8S_DIR/base/configmap.yaml"
  grep -q "name: langfuse-config" "$K8S_DIR/base/configmap.yaml"
  grep -q "DATABASE_URL: \"postgresql://langfuse:postgresdevpass123@postgres:5432/langfuse\"" "$K8S_DIR/base/configmap.yaml"
  grep -q "CLICKHOUSE_PASSWORD: \"clickhousedevpass123\"" "$K8S_DIR/base/configmap.yaml"
  grep -q "REDIS_PASSWORD: \"redisdevpass123\"" "$K8S_DIR/base/configmap.yaml"
  grep -q "MINIO_SECRET_KEY: \"miniodevpass123\"" "$K8S_DIR/base/configmap.yaml"
}

@test "k8s base/postgres.yaml exists and has required resources" {
  [ -f "$K8S_DIR/base/postgres.yaml" ]
  grep -q "apiVersion:" "$K8S_DIR/base/postgres.yaml"
  grep -q "kind: PersistentVolumeClaim" "$K8S_DIR/base/postgres.yaml"
  grep -q "kind: Deployment" "$K8S_DIR/base/postgres.yaml"
  grep -q "image: postgres:16" "$K8S_DIR/base/postgres.yaml"
  grep -q "name: ai-dev-secrets" "$K8S_DIR/base/postgres.yaml"
  grep -q "requests:" "$K8S_DIR/base/postgres.yaml"
  grep -q "limits:" "$K8S_DIR/base/postgres.yaml"
}

@test "k8s base/clickhouse.yaml exists and has required resources" {
  [ -f "$K8S_DIR/base/clickhouse.yaml" ]
  grep -q "apiVersion:" "$K8S_DIR/base/clickhouse.yaml"
  grep -q "image: clickhouse/clickhouse-server:24.3" "$K8S_DIR/base/clickhouse.yaml"
  grep -q "name: ai-dev-secrets" "$K8S_DIR/base/clickhouse.yaml"
  grep -q "requests:" "$K8S_DIR/base/clickhouse.yaml"
  grep -q "limits:" "$K8S_DIR/base/clickhouse.yaml"
  # Check for dual PVC
  grep -q "clickhouse-pvc" "$K8S_DIR/base/clickhouse.yaml"
  grep -q "clickhouse-log-pvc" "$K8S_DIR/base/clickhouse.yaml"
}

@test "k8s base/redis.yaml exists and has noeviction policy" {
  [ -f "$K8S_DIR/base/redis.yaml" ]
  grep -q "image: redis:7" "$K8S_DIR/base/redis.yaml"
  grep -q "noeviction" "$K8S_DIR/base/redis.yaml"
  grep -q "name: ai-dev-secrets" "$K8S_DIR/base/redis.yaml"
  grep -q "requests:" "$K8S_DIR/base/redis.yaml"
  grep -q "limits:" "$K8S_DIR/base/redis.yaml"
}

@test "k8s base/minio.yaml exists and has NodePort 17901" {
  [ -f "$K8S_DIR/base/minio.yaml" ]
  grep -q "image: minio/minio" "$K8S_DIR/base/minio.yaml"
  grep -q "type: NodePort" "$K8S_DIR/base/minio.yaml"
  grep -q "name: ai-dev-secrets" "$K8S_DIR/base/minio.yaml"
  # Check port 17901 is defined in service
  grep -q "17901" "$K8S_DIR/base/minio.yaml"
}

@test "k8s base/langfuse-web.yaml exists and has NodePort 17900" {
  [ -f "$K8S_DIR/base/langfuse-web.yaml" ]
  grep -q "image: langfuse/langfuse:3" "$K8S_DIR/base/langfuse-web.yaml"
  grep -q "17900" "$K8S_DIR/base/langfuse-web.yaml"
  grep -q "type: NodePort" "$K8S_DIR/base/langfuse-web.yaml"
  grep -q "requests:" "$K8S_DIR/base/langfuse-web.yaml"
  grep -q "limits:" "$K8S_DIR/base/langfuse-web.yaml"
}

@test "k8s base/langfuse-worker.yaml exists" {
  [ -f "$K8S_DIR/base/langfuse-worker.yaml" ]
  grep -q "image: langfuse/langfuse:3" "$K8S_DIR/base/langfuse-worker.yaml"
  grep -q "worker" "$K8S_DIR/base/langfuse-worker.yaml"
  grep -q "requests:" "$K8S_DIR/base/langfuse-worker.yaml"
  grep -q "limits:" "$K8S_DIR/base/langfuse-worker.yaml"
}

@test "k8s base/mcp-servers.yaml exists and has both MCP servers" {
  [ -f "$K8S_DIR/base/mcp-servers.yaml" ]
  grep -q "notebooklm-mcp" "$K8S_DIR/base/mcp-servers.yaml"
  grep -q "workspace-mcp" "$K8S_DIR/base/mcp-servers.yaml"
  grep -q "name: workspace-mcp-secrets" "$K8S_DIR/base/mcp-servers.yaml"
  grep -q "17980" "$K8S_DIR/base/mcp-servers.yaml"
  grep -q "17981" "$K8S_DIR/base/mcp-servers.yaml"
  grep -q "type: NodePort" "$K8S_DIR/base/mcp-servers.yaml"
}

@test "k8s kustomization.yaml exists" {
  [ -f "$K8S_DIR/kustomization.yaml" ]
  grep -q "apiVersion: kustomize.config.k8s.io/v1beta1" "$K8S_DIR/kustomization.yaml"
  grep -q "kind: Kustomization" "$K8S_DIR/kustomization.yaml"
  grep -q "namespace: ai-dev" "$K8S_DIR/kustomization.yaml"
  grep -q "resources:" "$K8S_DIR/kustomization.yaml"
}

@test "k8s README.md exists and has documentation" {
  [ -f "$K8S_DIR/README.md" ]
  grep -q "Stack Overview" "$K8S_DIR/README.md"
  grep -q "Port Mapping" "$K8S_DIR/README.md"
  grep -q "Commands Reference" "$K8S_DIR/README.md"
  grep -q "Google Workspace OAuth Setup Guide" "$K8S_DIR/README.md"
  grep -q "ai-dev-secrets" "$K8S_DIR/README.md"
  grep -q "workspace-mcp-secrets" "$K8S_DIR/README.md"
}
