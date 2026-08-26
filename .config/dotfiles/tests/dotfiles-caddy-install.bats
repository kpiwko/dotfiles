#!/usr/bin/env bats

setup() {
  TEST_DIR="$(mktemp -d)"
  export SUDO=""
  export INSTALL_OWNER_FLAGS=""
  export RSYNC_CHOWN_FLAG=""
  export DOTFILES_CADDY_SRC="$TEST_DIR/src"
  export CADDY_ETC_DIR="$TEST_DIR/etc"
  export CADDY_LOG_DIR="$TEST_DIR/log"
  export CADDY_VAR_DIR="$TEST_DIR/var"
  export CADDY_BIN="$TEST_DIR/bin/caddy"
  export CADDY_LIBEXEC_DIR="$TEST_DIR/libexec"
  export LAUNCHD_DIR="$TEST_DIR/launchd"
  export LAUNCHD_LABEL="local.caddy"
  export CADDY_VERSION="v2.9.1"

  mkdir -p "$DOTFILES_CADDY_SRC/sites" "$DOTFILES_CADDY_SRC/snippets" "$DOTFILES_CADDY_SRC/env"
  echo "test-caddyfile" > "$DOTFILES_CADDY_SRC/Caddyfile"
  echo "test-site" > "$DOTFILES_CADDY_SRC/sites/llm.caddy"
  echo "test-snippet" > "$DOTFILES_CADDY_SRC/snippets/cloudflare-tls.caddy"
  echo "CF_API_TOKEN=changeme" > "$DOTFILES_CADDY_SRC/env/cloudflare.env.example"
  echo "test-caddy-start" > "$DOTFILES_CADDY_SRC/caddy-start"
  echo "test-plist" > "$DOTFILES_CADDY_SRC/local.caddy.plist"

  FAKE_BIN_DIR="$TEST_DIR/bin"
  mkdir -p "$FAKE_BIN_DIR" "$TEST_DIR/xcaddy-bin"
  export DOTFILES_ROLE_BIN="$FAKE_BIN_DIR/dotfiles-role"
  export XCADDY_BIN="$TEST_DIR/xcaddy-bin/xcaddy"
  export LAUNCHCTL_BIN="$FAKE_BIN_DIR/launchctl"
  export XCADDY_CALL_LOG="$TEST_DIR/xcaddy-calls.log"
  export LAUNCHCTL_CALL_LOG="$TEST_DIR/launchctl-calls.log"

  SCRIPT="$BATS_TEST_DIRNAME/../../../.local/bin/dotfiles-caddy-install"
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

stub_xcaddy() {
  cat > "$XCADDY_BIN" <<'EOF'
#!/bin/sh
prev=""
out=""
for arg in "$@"; do
  if [ "$prev" = "--output" ]; then
    out="$arg"
  fi
  prev="$arg"
done
cat > "$out" <<'CADDY'
#!/bin/sh
case "$1" in
  version) echo "v2.9.1" ;;
  validate) exit 0 ;;
  *) exit 0 ;;
esac
CADDY
chmod +x "$out"
echo "called" >> "$XCADDY_CALL_LOG"
EOF
  chmod +x "$XCADDY_BIN"
}

# $1: version string `caddy version` should report
# $2: exit code `caddy validate` should return
stub_caddy() {
  mkdir -p "$(dirname "$CADDY_BIN")"
  cat > "$CADDY_BIN" <<EOF
#!/bin/sh
case "\$1" in
  version) echo "$1" ;;
  validate) exit ${2:-0} ;;
  *) exit 0 ;;
esac
EOF
  chmod +x "$CADDY_BIN"
}

# $1: exit code `launchctl list <label>` should return (0 = already loaded)
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

# Convenience: stub every downstream tool to succeed, for tests that only
# care about the earlier directory/sync/secret-bootstrap steps.
stub_all_ok() {
  stub_xcaddy
  stub_caddy "$CADDY_VERSION" 0
  stub_launchctl 1
}

@test "refuses to run when neither dev nor ai-server role is enabled" {
  stub_role_disabled
  run "$SCRIPT"
  [ "$status" -eq 1 ]
  [ ! -d "$CADDY_ETC_DIR" ]
}

@test "succeeds when dev role is enabled" {
  stub_role_enabled dev
  stub_all_ok
  run "$SCRIPT"
  [ "$status" -eq 0 ]
}

@test "succeeds when ai-server role is enabled" {
  stub_role_enabled ai-server
  stub_all_ok
  run "$SCRIPT"
  [ "$status" -eq 0 ]
}

@test "creates required directories when role is enabled" {
  stub_role_enabled
  stub_all_ok
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ -d "$CADDY_ETC_DIR/sites" ]
  [ -d "$CADDY_ETC_DIR/snippets" ]
  [ -d "$CADDY_ETC_DIR/env" ]
  [ -d "$CADDY_LOG_DIR" ]
  [ -d "$CADDY_VAR_DIR" ]
}

@test "syncs Caddyfile, sites, and snippets from the repo source" {
  stub_role_enabled
  stub_all_ok
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(cat "$CADDY_ETC_DIR/Caddyfile")" = "test-caddyfile" ]
  [ "$(cat "$CADDY_ETC_DIR/sites/llm.caddy")" = "test-site" ]
  [ "$(cat "$CADDY_ETC_DIR/snippets/cloudflare-tls.caddy")" = "test-snippet" ]
}

@test "removes stale site files no longer present in the repo source" {
  stub_role_enabled
  stub_all_ok
  "$SCRIPT"
  echo "stale" > "$CADDY_ETC_DIR/sites/stale.caddy"
  "$SCRIPT"
  [ ! -f "$CADDY_ETC_DIR/sites/stale.caddy" ]
}

@test "creates cloudflare.env from the example on first run" {
  stub_role_enabled
  stub_all_ok
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(cat "$CADDY_ETC_DIR/env/cloudflare.env")" = "CF_API_TOKEN=changeme" ]
  [ ! -f "$XCADDY_CALL_LOG" ]
  [ ! -f "$LAUNCHCTL_CALL_LOG" ]
}

@test "never overwrites an existing cloudflare.env" {
  stub_role_enabled
  stub_all_ok
  mkdir -p "$CADDY_ETC_DIR/env"
  echo "CF_API_TOKEN=real-secret-value" > "$CADDY_ETC_DIR/env/cloudflare.env"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(cat "$CADDY_ETC_DIR/env/cloudflare.env")" = "CF_API_TOKEN=real-secret-value" ]
}

@test "performs cloudflare.env existence check via run_privileged" {
  stub_role_enabled
  stub_all_ok
  SUDO_LOG="$TEST_DIR/sudo.log"
  mkdir -p "$(dirname "$SUDO_LOG")"

  STUB_SUDO="$FAKE_BIN_DIR/sudo"
  cat > "$STUB_SUDO" <<'INNEREOF'
#!/bin/sh
echo "$@" >> "$SUDO_LOG"
exec "$@"
INNEREOF
  chmod +x "$STUB_SUDO"

  export SUDO="$STUB_SUDO"
  export SUDO_LOG

  run "$SCRIPT"
  [ "$status" -eq 0 ]

  # Proves the existence check went through run_privileged, not a raw [ -f ]
  grep -q "test -f.*cloudflare.env" "$SUDO_LOG"
}

@test "builds caddy via xcaddy when the binary is missing" {
  stub_role_enabled
  stub_xcaddy
  stub_launchctl 1
  mkdir -p "$CADDY_ETC_DIR/env"
  echo "CF_API_TOKEN=real-secret" > "$CADDY_ETC_DIR/env/cloudflare.env"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ -f "$XCADDY_CALL_LOG" ]
  [ "$("$CADDY_BIN" version)" = "v2.9.1" ]
}

@test "skips the rebuild when the pinned version is already installed" {
  stub_role_enabled
  stub_all_ok
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ ! -f "$XCADDY_CALL_LOG" ]
}

@test "aborts before touching launchctl when caddy validate fails" {
  stub_role_enabled
  stub_xcaddy
  stub_caddy "$CADDY_VERSION" 1
  stub_launchctl 1
  mkdir -p "$CADDY_ETC_DIR/env"
  echo "CF_API_TOKEN=real-secret" > "$CADDY_ETC_DIR/env/cloudflare.env"
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [ ! -f "$LAUNCHCTL_CALL_LOG" ]
}

@test "bootstraps the daemon when it is not already loaded" {
  stub_role_enabled
  stub_all_ok
  mkdir -p "$CADDY_ETC_DIR/env"
  echo "CF_API_TOKEN=real-secret" > "$CADDY_ETC_DIR/env/cloudflare.env"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "launchctl bootstrap system $LAUNCHD_DIR/$LAUNCHD_LABEL.plist" "$LAUNCHCTL_CALL_LOG"
}

@test "kickstarts the daemon when it is already loaded" {
  stub_role_enabled
  stub_xcaddy
  stub_caddy "$CADDY_VERSION" 0
  stub_launchctl 0
  mkdir -p "$CADDY_ETC_DIR/env"
  echo "CF_API_TOKEN=real-secret" > "$CADDY_ETC_DIR/env/cloudflare.env"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  grep -q "launchctl kickstart -k system/$LAUNCHD_LABEL" "$LAUNCHCTL_CALL_LOG"
}

@test "deploys caddy-start and the plist into place" {
  stub_role_enabled
  stub_all_ok
  mkdir -p "$CADDY_ETC_DIR/env"
  echo "CF_API_TOKEN=real-secret" > "$CADDY_ETC_DIR/env/cloudflare.env"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [ "$(cat "$CADDY_LIBEXEC_DIR/caddy-start")" = "test-caddy-start" ]
  [ "$(cat "$LAUNCHD_DIR/$LAUNCHD_LABEL.plist")" = "test-plist" ]
}
