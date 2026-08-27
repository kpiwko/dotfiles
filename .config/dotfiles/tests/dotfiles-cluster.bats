#!/usr/bin/env bats

setup() {
  TEST_HOME="$(mktemp -d)"
  export K8S_DIR="$TEST_HOME/k8s"
  export DOTFILES_ROLES_FILE="$TEST_HOME/.config/dotfiles/roles"
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
exit 0
EOF
  chmod +x "$STUB_DIR/kind"
  
  # Stub devcluster-kubectl (takes precedence over kubectl)
  cat > "$STUB_DIR/devcluster-kubectl" << 'EOF'
#!/bin/sh
echo "devcluster-kubectl (stub) $*"
exit 0
EOF
  chmod +x "$STUB_DIR/devcluster-kubectl"
  
  # Stub kubectl
  cat > "$STUB_DIR/kubectl" << 'EOF'
#!/bin/sh
echo "kubectl (stub) $*"
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
}

@test "up command requires kubectl" {
  run "$SCRIPT" up
  [ "$status" -eq 0 ]
  [[ "$output" == *"Deploying kustomize manifests"* ]]
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
  run "$SCRIPT" delete
  [ "$status" -eq 0 ]
  [[ "$output" == *"Deleting cluster"* ]]
}
