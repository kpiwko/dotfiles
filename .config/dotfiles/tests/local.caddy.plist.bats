#!/usr/bin/env bats

setup() {
  PLIST="$BATS_TEST_DIRNAME/../../caddy/local.caddy.plist"
}

@test "plist is valid property list syntax" {
  run plutil -lint "$PLIST"
  [ "$status" -eq 0 ]
}

@test "label matches local.caddy" {
  run plutil -extract Label raw -o - "$PLIST"
  [ "$status" -eq 0 ]
  [ "$output" = "local.caddy" ]
}

@test "ProgramArguments invokes the caddy-start wrapper, not caddy directly" {
  run plutil -extract ProgramArguments.0 raw -o - "$PLIST"
  [ "$status" -eq 0 ]
  [ "$output" = "/usr/local/libexec/caddy-start" ]
}

@test "RunAtLoad and KeepAlive are both true" {
  run plutil -extract RunAtLoad raw -o - "$PLIST"
  [ "$output" = "true" ]
  run plutil -extract KeepAlive raw -o - "$PLIST"
  [ "$output" = "true" ]
}

@test "EnvironmentVariables carry HOME/XDG paths and no secrets" {
  run plutil -extract EnvironmentVariables.HOME raw -o - "$PLIST"
  [ "$output" = "/var/lib/caddy" ]
  run plutil -extract EnvironmentVariables.XDG_DATA_HOME raw -o - "$PLIST"
  [ "$output" = "/var/lib/caddy" ]
  run plutil -extract EnvironmentVariables.XDG_CONFIG_HOME raw -o - "$PLIST"
  [ "$output" = "/usr/local/etc/caddy" ]
  run bash -c "! grep -qi cloudflare '$PLIST'"
  [ "$status" -eq 0 ]
}

@test "logs go under /var/log/caddy" {
  run plutil -extract StandardOutPath raw -o - "$PLIST"
  [[ "$output" == /var/log/caddy/* ]]
  run plutil -extract StandardErrorPath raw -o - "$PLIST"
  [[ "$output" == /var/log/caddy/* ]]
}
