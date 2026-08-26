#!/usr/bin/env bats

setup() {
  CADDY_DIR="$BATS_TEST_DIRNAME/../../caddy"
}

@test "local_tls snippet exists and defines internal TLS" {
  [ -f "$CADDY_DIR/snippets/local-tls.caddy" ]
  grep -q "(local_tls)" "$CADDY_DIR/snippets/local-tls.caddy"
  grep -q "tls internal" "$CADDY_DIR/snippets/local-tls.caddy"
}

@test "cloudflare_tls snippet exists and configures Cloudflare DNS challenge" {
  [ -f "$CADDY_DIR/snippets/cloudflare-tls.caddy" ]
  grep -q "(cloudflare_tls)" "$CADDY_DIR/snippets/cloudflare-tls.caddy"
  grep -q "dns cloudflare" "$CADDY_DIR/snippets/cloudflare-tls.caddy"
}

@test "local-dev site example exists and imports local_tls" {
  [ -f "$CADDY_DIR/sites/local-dev.caddy.example" ]
  grep -q "import local_tls" "$CADDY_DIR/sites/local-dev.caddy.example"
  grep -q "reverse_proxy" "$CADDY_DIR/sites/local-dev.caddy.example"
}

@test "caddy .gitignore exists and ignores local site overrides" {
  [ -f "$CADDY_DIR/.gitignore" ]
  grep -q "\*\.local\.caddy" "$CADDY_DIR/.gitignore"
}
