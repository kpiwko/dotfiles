#!/usr/bin/env bats

setup() {
  TEST_HOME="$(mktemp -d)"
  export K8S_DIR="$TEST_HOME/k8s"
  export DOTFILES_ROLES_FILE="$TEST_HOME/.config/dotfiles/roles"
  export DEVCLUSTER_KUBECONFIG="$TEST_HOME/.kube/opencode-devcluster"
  mkdir -p "$K8S_DIR"
  mkdir -p "$(dirname "$DOTFILES_ROLES_FILE")"
  
  # Create stub scripts
  STUB_DIR="$TEST_HOME/stubs"
  mkdir -p "$STUB_DIR"
  
  # Stub dotfiles-role
  cat > "$STUB_DIR/dotfiles-role" << 'EOF'
#!/bin/sh
case "$1" in
  has)
    if [ "$2" = "cluster" ]; then
      if [ -f "$DOTFILES_ROLES_FILE" ] && grep -qx cluster "$DOTFILES_ROLES_FILE"; then
        exit 0
      else
        exit 1
      fi
    fi
    exit 1
    ;;
  enable)
    mkdir -p "$(dirname "$DOTFILES_ROLES_FILE")"
    if ! grep -qx "$2" "$DOTFILES_ROLES_FILE"; then
      echo "$2" >> "$DOTFILES_ROLES_FILE"
    fi
    ;;
  list)
    if [ -f "$DOTFILES_ROLES_FILE" ]; then
      cat "$DOTFILES_ROLES_FILE"
    fi
    ;;
  *)
    exit 1
    ;;
esac
EOF
  chmod +x "$STUB_DIR/dotfiles-role"
  
  # Stub kind
  cat > "$STUB_DIR/kind" << 'EOF'
#!/bin/sh
echo "kind (stub) $*"
if [ "$1" = "export" ] && [ "$2" = "kubeconfig" ]; then
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "--kubeconfig" ]; then
      mkdir -p "$(dirname "$arg")"
      touch "$arg"
    fi
    prev="$arg"
  done
fi
exit 0
EOF
  chmod +x "$STUB_DIR/kind"
  
  # Stub devcluster-kubectl (takes precedence over kubectl)
  cat > "$STUB_DIR/devcluster-kubectl" << 'EOF'
#!/bin/sh
echo "devcluster-kubectl (stub) $*"
if [ "$1" = "apply" ] && [ "$2" = "-f" ] && [ "$3" = "-" ]; then
  cat -
fi
exit 0
EOF
  chmod +x "$STUB_DIR/devcluster-kubectl"
  
  # Stub kubectl
  cat > "$STUB_DIR/kubectl" << 'EOF'
#!/bin/sh
echo "kubectl (stub) $*"
if [ "$1" = "apply" ] && [ "$2" = "-f" ] && [ "$3" = "-" ]; then
  cat -
fi
exit 0
EOF
  chmod +x "$STUB_DIR/kubectl"
  
  # Add stubs to PATH
  export PATH="$STUB_DIR:$PATH"
  
  SCRIPT="$BATS_TEST_DIRNAME/../../../.local/bin/dotfiles-cluster"
}

teardown() {
  rm -rf "$TEST_HOME"
}

@test "show usage without arguments" {
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Commands:"* ]]
}

@test "show usage for unknown command" {
  run "$SCRIPT" unknown
  [ "$status" -eq 1 ]
}

@test "create command requires cluster role" {
  # Role not enabled
  run "$SCRIPT" create
  [ "$status" -eq 1 ]
  [[ "$output" == *"cluster role not enabled"* ]]
}

@test "create command creates cluster with config" {
  # Enable cluster role
  dotfiles-role enable cluster
  
  # Create kind config
  cat > "$K8S_DIR/kind-config.yaml" << 'EOF'
apiVersion: kind.x-k8s.io/v1alpha4
kind: Cluster
name: kind-ai-dev
nodes:
  - role: control-plane
EOF
  
  run "$SCRIPT" create
  [ "$status" -eq 0 ]
  [[ "$output" == *"Creating Kind cluster"* ]]
  [[ "$output" == *"kind (stub) create cluster --name kind-ai-dev --config $K8S_DIR/kind-config.yaml --kubeconfig $DEVCLUSTER_KUBECONFIG"* ]]
  [[ "$output" == *"kind (stub) export kubeconfig --name kind-ai-dev --kubeconfig $DEVCLUSTER_KUBECONFIG"* ]]
  [ -f "$DEVCLUSTER_KUBECONFIG" ]
}

@test "up command exports kubeconfig when missing" {
  [ ! -f "$DEVCLUSTER_KUBECONFIG" ]
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"Exporting kubeconfig to $DEVCLUSTER_KUBECONFIG"* ]]
  [[ "$output" == *"kind (stub) export kubeconfig --name kind-ai-dev --kubeconfig $DEVCLUSTER_KUBECONFIG"* ]]
  [ -f "$DEVCLUSTER_KUBECONFIG" ]
}

@test "up command requires kubectl" {
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"Provisioning secrets for namespace ai-dev"* ]]
  [[ "$output" == *"Deploying kustomize manifests"* ]]
}

@test "up command auto-provisions secrets with default values" {
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"create secret generic ai-dev-secrets"* ]]
  [[ "$output" == *"POSTGRES_USER=langfuse"* ]]
  [[ "$output" == *"POSTGRES_PASSWORD=postgresdevpass123"* ]]
  [[ "$output" == *"CLICKHOUSE_USER=langfuse"* ]]
  [[ "$output" == *"CLICKHOUSE_PASSWORD=clickhousedevpass123"* ]]
  [[ "$output" == *"MINIO_ROOT_USER=langfuse"* ]]
  [[ "$output" == *"MINIO_ROOT_PASSWORD=miniodevpass123"* ]]
  [[ "$output" == *"REDIS_PASSWORD=redisdevpass123"* ]]
  [[ "$output" == *"LANGFUSE_SECRET_KEY=devsecretkey_0123456789abcdef0123456789abcdef"* ]]
  [[ "$output" == *"LANGFUSE_INIT_USER_EMAIL=kpiwko@localhost"* ]]
  [[ "$output" == *"LANGFUSE_INIT_USER_NAME=Karel Piwko"* ]]
  [[ "$output" == *"LANGFUSE_INIT_USER_PASSWORD=langfusedevpass123"* ]]
  [[ "$output" == *"LANGFUSE_INIT_ORG_ID=local-dev"* ]]
  [[ "$output" == *"LANGFUSE_INIT_ORG_NAME=Local Dev"* ]]
  [[ "$output" == *"LANGFUSE_INIT_PROJECT_ID=local-project"* ]]
  [[ "$output" == *"LANGFUSE_INIT_PROJECT_NAME=Local Project"* ]]
  [[ "$output" == *"LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-0123456789abcdef0123456789abcdef"* ]]
  [[ "$output" == *"LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-0123456789abcdef0123456789abcdef"* ]]
  [[ "$output" == *"create secret generic workspace-mcp-secrets"* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_ID="* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_SECRET="* ]]
}

@test "up command auto-provisions secrets with legacy shell environment variables" {
  export POSTGRES_PASSWORD="custompostgrespass"
  export LANGFUSE_SECRET_KEY="customsecretkey"
  export LANGFUSE_INIT_USER_EMAIL="admin@example.com"
  export LANGFUSE_INIT_PROJECT_ID="custom-project"
  export GOOGLE_OAUTH_CLIENT_ID="custom-client-id.apps.googleusercontent.com"
  export GOOGLE_OAUTH_CLIENT_SECRET="custom-client-secret"
  
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"POSTGRES_PASSWORD=custompostgrespass"* ]]
  [[ "$output" == *"LANGFUSE_SECRET_KEY=customsecretkey"* ]]
  [[ "$output" == *"LANGFUSE_INIT_USER_EMAIL=admin@example.com"* ]]
  [[ "$output" == *"LANGFUSE_INIT_PROJECT_ID=custom-project"* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_ID=custom-client-id.apps.googleusercontent.com"* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_SECRET=custom-client-secret"* ]]
}

@test "up command prioritizes DEVCLUSTER_ variables over legacy variables" {
  export POSTGRES_PASSWORD="legacypassword"
  export LANGFUSE_SECRET_KEY="legacykey"
  export LANGFUSE_INIT_USER_EMAIL="legacy@example.com"
  export GOOGLE_OAUTH_CLIENT_ID="legacy-id"
  
  export DEVCLUSTER_POSTGRES_PASSWORD="devclusterpostgrespass"
  export DEVCLUSTER_LANGFUSE_ENCRYPTION_KEY="devclusterencryptionkey"
  export DEVCLUSTER_LANGFUSE_INIT_USER_EMAIL="devcluster@example.com"
  export DEVCLUSTER_GOOGLE_OAUTH_CLIENT_ID="devcluster-client-id"
  
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"POSTGRES_PASSWORD=devclusterpostgrespass"* ]]
  [[ "$output" == *"LANGFUSE_SECRET_KEY=devclusterencryptionkey"* ]]
  [[ "$output" == *"LANGFUSE_INIT_USER_EMAIL=devcluster@example.com"* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_ID=devcluster-client-id"* ]]
}

@test "up command prioritizes AI_DEV_ variables over DEVCLUSTER_ and legacy variables" {
  export POSTGRES_PASSWORD="legacypassword"
  export DEVCLUSTER_POSTGRES_PASSWORD="devclusterpostgrespass"
  export AI_DEV_POSTGRES_PASSWORD="aidevpostgrespass"

  export LANGFUSE_SECRET_KEY="legacykey"
  export DEVCLUSTER_LANGFUSE_ENCRYPTION_KEY="devclusterencryptionkey"
  export AI_DEV_LANGFUSE_ENCRYPTION_KEY="aidevencryptionkey"

  export LANGFUSE_INIT_USER_EMAIL="legacy@example.com"
  export DEVCLUSTER_LANGFUSE_INIT_USER_EMAIL="devcluster@example.com"
  export AI_DEV_LANGFUSE_INIT_USER_EMAIL="aidev@example.com"

  export GOOGLE_OAUTH_CLIENT_ID="legacy-id"
  export DEVCLUSTER_GOOGLE_OAUTH_CLIENT_ID="devcluster-client-id"
  export AI_DEV_GOOGLE_OAUTH_CLIENT_ID="aidev-client-id"
  
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"POSTGRES_PASSWORD=aidevpostgrespass"* ]]
  [[ "$output" == *"LANGFUSE_SECRET_KEY=aidevencryptionkey"* ]]
  [[ "$output" == *"LANGFUSE_INIT_USER_EMAIL=aidev@example.com"* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_ID=aidev-client-id"* ]]
}

@test "up command falls back to .env file when env variables are not exported" {
  cat > "$K8S_DIR/.env" << 'EOF'
AI_DEV_POSTGRES_PASSWORD=envfilepostgrespass
AI_DEV_LANGFUSE_ENCRYPTION_KEY=envfileencryptionkey
AI_DEV_GOOGLE_OAUTH_CLIENT_ID=env-client-id
EOF

  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"POSTGRES_PASSWORD=envfilepostgrespass"* ]]
  [[ "$output" == *"LANGFUSE_SECRET_KEY=envfileencryptionkey"* ]]
  [[ "$output" == *"GOOGLE_OAUTH_CLIENT_ID=env-client-id"* ]]
}

@test "status command shows cluster info" {
  run "$SCRIPT" status
  [ "$status" -eq 0 ]
  [[ "$output" == *"=== Cluster Nodes ==="* ]]
  [[ "$output" == *"=== Pods"* ]]
}

@test "logs command requires pod name" {
  run "$SCRIPT" logs
  [ "$status" -eq 1 ]
  [[ "$output" == *"Usage:"* ]]
}

@test "logs command with pod name works" {
  run "$SCRIPT" logs test-pod
  [ "$status" -eq 0 ]
  [[ "$output" == *"kubectl (stub)"* ]]
}

@test "down command works" {
  run "$SCRIPT" down
  [ "$status" -eq 0 ]
  [[ "$output" == *"Stopping cluster"* ]]
}

@test "delete command works" {
  mkdir -p "$(dirname "$DEVCLUSTER_KUBECONFIG")"
  touch "$DEVCLUSTER_KUBECONFIG"
  [ -f "$DEVCLUSTER_KUBECONFIG" ]

  run "$SCRIPT" delete
  [ "$status" -eq 0 ]
  [[ "$output" == *"Deleting cluster"* ]]
  [[ "$output" == *"kind (stub) delete cluster --name kind-ai-dev --kubeconfig $DEVCLUSTER_KUBECONFIG"* ]]
  [ ! -f "$DEVCLUSTER_KUBECONFIG" ]
}
