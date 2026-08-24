#!/usr/bin/env bats

setup() {
  TEST_HOME="$(mktemp -d)"
  export DOTFILES_ROLES_FILE="$TEST_HOME/.config/dotfiles/roles"
  SCRIPT="$BATS_TEST_DIRNAME/../../../.local/bin/dotfiles-role"
}

teardown() {
  rm -rf "$TEST_HOME"
}

@test "list is empty when no roles file exists yet" {
  run "$SCRIPT" list
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "has fails for a role that was never enabled" {
  run "$SCRIPT" has ai-server
  [ "$status" -eq 1 ]
}

@test "enable then has succeeds" {
  "$SCRIPT" enable ai-server
  run "$SCRIPT" has ai-server
  [ "$status" -eq 0 ]
}

@test "enable is idempotent (no duplicate lines)" {
  "$SCRIPT" enable ai-server
  "$SCRIPT" enable ai-server
  run "$SCRIPT" list
  [ "$(echo "$output" | grep -c '^ai-server$')" -eq 1 ]
}

@test "disable removes an enabled role" {
  "$SCRIPT" enable ai-server
  "$SCRIPT" disable ai-server
  run "$SCRIPT" has ai-server
  [ "$status" -eq 1 ]
}

@test "enable rejects an unknown role name" {
  run "$SCRIPT" enable not-a-real-role
  [ "$status" -eq 1 ]
  [[ "$output" == *"unknown role"* ]]
}
