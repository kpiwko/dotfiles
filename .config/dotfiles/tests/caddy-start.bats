#!/usr/bin/env bats

setup() {
  TEST_DIR="$(mktemp -d)"
  export CADDY_ETC_DIR="$TEST_DIR/etc"
  export CADDY_ENV_FILE="$CADDY_ETC_DIR/env/cloudflare.env"
  mkdir -p "$(dirname "$CADDY_ENV_FILE")"
  echo "CF_API_TOKEN=test-token-123" > "$CADDY_ENV_FILE"
  touch "$CADDY_ETC_DIR/Caddyfile"

  FAKE_BIN_DIR="$TEST_DIR/bin"
  mkdir -p "$FAKE_BIN_DIR"
  export CAPTURE_FILE="$TEST_DIR/capture.txt"
  cat > "$FAKE_BIN_DIR/caddy" <<'EOF'
#!/bin/sh
{
  echo "ARGS: $*"
  echo "TOKEN: $CF_API_TOKEN"
} > "$CAPTURE_FILE"
EOF
  chmod +x "$FAKE_BIN_DIR/caddy"
  export CADDY_BIN="$FAKE_BIN_DIR/caddy"

  SCRIPT="$BATS_TEST_DIRNAME/../../caddy/caddy-start"
}

teardown() {
  rm -rf "$TEST_DIR"
}

@test "sources cloudflare.env and execs caddy with the right config path" {
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(grep ARGS "$CAPTURE_FILE")" = "ARGS: run --config $CADDY_ETC_DIR/Caddyfile --adapter caddyfile" ]
  [ "$(grep TOKEN "$CAPTURE_FILE")" = "TOKEN: test-token-123" ]
}

@test "still runs caddy if cloudflare.env is missing" {
  rm "$CADDY_ENV_FILE"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
}
