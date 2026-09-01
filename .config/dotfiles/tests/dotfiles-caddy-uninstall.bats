#!/usr/bin/env bats

setup() {
  TEST_DIR="$(mktemp -d)"
  export SUDO=""
  export CADDY_BIN="$TEST_DIR/bin/caddy"
  export CADDY_LIBEXEC_DIR="$TEST_DIR/libexec"
  export LAUNCHD_DIR="$TEST_DIR/launchd"
  export LAUNCHD_LABEL="local.caddy"
  export CADDY_ETC_DIR="$TEST_DIR/etc"
  export CADDY_VAR_DIR="$TEST_DIR/var"

  mkdir -p "$(dirname "$CADDY_BIN")" "$CADDY_LIBEXEC_DIR" "$LAUNCHD_DIR" "$CADDY_ETC_DIR" "$CADDY_VAR_DIR"
  echo "caddy-binary" > "$CADDY_BIN"
  echo "wrapper" > "$CADDY_LIBEXEC_DIR/caddy-start"
  echo "plist" > "$LAUNCHD_DIR/$LAUNCHD_LABEL.plist"
  echo "caddyfile-should-survive" > "$CADDY_ETC_DIR/Caddyfile"
  echo "cert-state-should-survive" > "$CADDY_VAR_DIR/state.bin"

  FAKE_BIN_DIR="$TEST_DIR/fakebin"
  mkdir -p "$FAKE_BIN_DIR"
  export DOTFILES_ROLE_BIN="$FAKE_BIN_DIR/dotfiles-role"
  export LAUNCHCTL_BIN="$FAKE_BIN_DIR/launchctl"
  export LAUNCHCTL_CALL_LOG="$TEST_DIR/launchctl-calls.log"

  SCRIPT="$BATS_TEST_DIRNAME/../../../.local/bin/dotfiles-caddy-uninstall"
}

teardown() {
  rm -rf "$TEST_DIR"
}

stub_role_enabled() {
  role="${1:-ai-server}"
  cat > "$DOTFILES_ROLE_BIN" <<EOF
#!/bin/sh
[ "\$1" = "has" ] && [ "\$2" = "$role" ] && exit 0
exit 1
EOF
  chmod +x "$DOTFILES_ROLE_BIN"
}

stub_role_disabled() {
  cat > "$DOTFILES_ROLE_BIN" <<'EOF'
#!/bin/sh
exit 1
EOF
  chmod +x "$DOTFILES_ROLE_BIN"
}

# $1: exit code `launchctl list <label>` should return (0 = loaded)
stub_launchctl() {
  cat > "$LAUNCHCTL_BIN" <<EOF
#!/bin/sh
echo "launchctl \$*" >> "$LAUNCHCTL_CALL_LOG"
case "\$1" in
  list) exit ${1:-1} ;;
  *) exit 0 ;;
esac
EOF
  chmod +x "$LAUNCHCTL_BIN"
}

@test "refuses to run when none of ai-server, cluster, or dev role is enabled" {
  stub_role_disabled
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [ -f "$CADDY_BIN" ]
}

@test "succeeds when dev role is enabled" {
  stub_role_enabled dev
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ ! -f "$LAUNCHD_DIR/$LAUNCHD_LABEL.plist" ]
  [ ! -f "$CADDY_LIBEXEC_DIR/caddy-start" ]
  [ ! -f "$CADDY_BIN" ]
}

@test "succeeds when cluster role is enabled" {
  stub_role_enabled cluster
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ ! -f "$LAUNCHD_DIR/$LAUNCHD_LABEL.plist" ]
  [ ! -f "$CADDY_LIBEXEC_DIR/caddy-start" ]
  [ ! -f "$CADDY_BIN" ]
}

@test "succeeds when ai-server role is enabled" {
  stub_role_enabled ai-server
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ ! -f "$LAUNCHD_DIR/$LAUNCHD_LABEL.plist" ]
  [ ! -f "$CADDY_LIBEXEC_DIR/caddy-start" ]
  [ ! -f "$CADDY_BIN" ]
}

@test "removes the plist, wrapper, and binary" {
  stub_role_enabled
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ ! -f "$LAUNCHD_DIR/$LAUNCHD_LABEL.plist" ]
  [ ! -f "$CADDY_LIBEXEC_DIR/caddy-start" ]
  [ ! -f "$CADDY_BIN" ]
}

@test "bootouts the daemon only if it is currently loaded" {
  stub_role_enabled
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "launchctl bootout system/$LAUNCHD_LABEL" "$LAUNCHCTL_CALL_LOG"
}

@test "skips bootout if the daemon is not loaded" {
  stub_role_enabled
  stub_launchctl 1
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  ! grep -q "bootout" "$LAUNCHCTL_CALL_LOG" 2>/dev/null
}

@test "leaves Caddyfile and var data untouched" {
  stub_role_enabled
  stub_launchctl 0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(cat "$CADDY_ETC_DIR/Caddyfile")" = "caddyfile-should-survive" ]
  [ "$(cat "$CADDY_VAR_DIR/state.bin")" = "cert-state-should-survive" ]
}
