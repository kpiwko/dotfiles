#!/usr/bin/env bash
# Create the disposable OpenCode sandbox on the pinned OpenShell stage.
#
# One sandbox, one idle main process (`sleep infinity`): OpenCode is invoked
# later with `sandbox exec`, so nothing runs (and nothing can egress) until an
# operator asks for it. `--restart-policy never` keeps a crash visible instead
# of hiding it behind a silent restart loop.
#
# Egress is governed entirely by sandbox-policy.yaml: deny by default, with only
# the two internal endpoints the policy names. A denied request is evidence the
# policy works, not a defect to widen away.
#
# The AgentGateway key is handed over by *reference* (`--env-from`), so its value
# never enters this script's argv, its output, or any file in this repository.
#
# Steps, in order: preconditions (no cluster contact), refuse an existing name,
# create, upload the OpenCode config (every run, so edits are never stale),
# verify the OpenCode binary sits at the path the policy pins.
#
# Usage: create-sandbox.sh [--name NAME] [--gateway-endpoint URL]
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
POLICY="$SCRIPT_DIR/sandbox-policy.yaml"
CONFIG="$SCRIPT_DIR/opencode.json"

OPENSHELL_BIN="${OPENSHELL_BIN:-openshell}"

# The gateway is named explicitly on every call. Without it the CLI uses whatever
# registration is current for the operator — on this machine the *host* gateway —
# and the sandbox would be created in the wrong place.
#
# Two flags, not one, because they answer different questions. `-g NAME` selects
# the stored registration, which is where the CLI looks up the mTLS material; a
# bare `--gateway-endpoint` connects directly and looks for certificates under a
# registration derived from the endpoint itself, which does not exist here
# ("failed to read TLS CA from ... mtls/ca.crt"). `--gateway-endpoint` then points
# that registration at the live loopback NodePort of the Kubernetes gateway,
# overriding the stale endpoint recorded in its metadata. TLS stays verified: the
# registration's own CA, client cert, and key are used.
GATEWAY_NAME_DEFAULT="devcluster-k8s"
GATEWAY_NAME="${OPENSHELL_GATEWAY_NAME:-$GATEWAY_NAME_DEFAULT}"
GATEWAY_ENDPOINT_DEFAULT="https://127.0.0.1:17910"
GATEWAY_ENDPOINT="${OPENSHELL_GATEWAY_ENDPOINT:-$GATEWAY_ENDPOINT_DEFAULT}"

# Digest-pinned: a moving tag would silently swap the binary path the policy
# matches on, which turns every request into a denial.
#
# Built by .github/workflows/opencode-sandbox-image.yml from image/Containerfile
# (OpenShell community base + OpenCode 2.4.1). The published `anomalyco/opencode`
# image ships OpenCode 1.x, which drops the V2 `providers` block and cannot
# resolve a model. To move to a new build, take the digest printed in the
# workflow's job summary.
IMAGE="ghcr.io/kpiwko/opencode-sandbox@sha256:fd336ffe461ffc5e339ae4b2c0ab849809500e78f621273e23fbc3da627e73b5"
# Must equal network_policies.*.binaries[].path in sandbox-policy.yaml.
OPENCODE_BINARY="/usr/local/bin/opencode"

SANDBOX_HOME="/sandbox"
REMOTE_CONFIG="$SANDBOX_HOME/.config/opencode/opencode.json"
BASE_URL="http://agentgateway.ai-dev.svc.cluster.local:4000/v1"
OTLP_ENDPOINT="http://otel-collector.ai-dev.svc.cluster.local:4318"

NAME_DEFAULT="opencode-dev"
NAME="$NAME_DEFAULT"

usage() {
    cat >&2 <<EOF
usage: create-sandbox.sh [--name NAME] [--gateway-endpoint URL]

  --name NAME             sandbox name (default: $NAME_DEFAULT)
  --gateway-endpoint URL  OpenShell gateway endpoint to operate on (default:
                          $GATEWAY_ENDPOINT_DEFAULT). Override for the whole
                          shell with OPENSHELL_GATEWAY_ENDPOINT=<url>; the flag
                          wins over that variable.

  The registration named by OPENSHELL_GATEWAY_NAME (default: $GATEWAY_NAME_DEFAULT)
  supplies the mTLS material; both flags are sent on every call.
EOF
}

die() {
    echo "create-sandbox: error: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)
            [[ $# -ge 2 && -n "$2" ]] || { usage; exit 2; }
            NAME="$2"
            shift 2
            ;;
        --gateway-endpoint)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { usage; exit 2; }
            GATEWAY_ENDPOINT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

# Preconditions. All of them run before the first openshell invocation so a
# missing input fails here, cheaply, instead of mid-create.
if [[ ! -f "$POLICY" ]]; then
    die "sandbox policy not found at $POLICY"
fi

if [[ ! -f "$CONFIG" ]]; then
    die "OpenCode config not found at $CONFIG"
fi

if [[ -z "${AGENTGATEWAY_API_KEY:-}" ]]; then
    die "AGENTGATEWAY_API_KEY is empty; export it (e.g. 'set -a; . ~/.config/k8s/.env; set +a') before creating the sandbox. It is passed to the sandbox with --env-from and never on the command line."
fi

if ! command -v "$OPENSHELL_BIN" >/dev/null 2>&1; then
    die "openshell CLI not found: $OPENSHELL_BIN (set OPENSHELL_BIN to its path)"
fi

# A name that is already taken must not be re-created: the upload and the binary
# check would then silently target a sandbox this run did not configure. A failed
# probe is read as "absent", so an unreachable cluster surfaces as the create
# error itself rather than as a guessed parse of the probe's output.
if "$OPENSHELL_BIN" -g "$GATEWAY_NAME" --gateway-endpoint "$GATEWAY_ENDPOINT" sandbox get "$NAME" >/dev/null 2>&1; then
    die "sandbox '$NAME' already exists; use --name to create another, or delete it first: $OPENSHELL_BIN -g $GATEWAY_NAME --gateway-endpoint $GATEWAY_ENDPOINT sandbox delete $NAME"
fi

echo "create-sandbox: creating '$NAME' on $GATEWAY_ENDPOINT from $IMAGE"

"$OPENSHELL_BIN" -g "$GATEWAY_NAME" --gateway-endpoint "$GATEWAY_ENDPOINT" sandbox create \
    --from "$IMAGE" \
    --name "$NAME" \
    --cpu 1 \
    --memory 1Gi \
    --detach \
    --restart-policy never \
    --policy "$POLICY" \
    --env "HOME=$SANDBOX_HOME" \
    --env "AGENTGATEWAY_BASE_URL=$BASE_URL" \
    --env "OPENCODE_OTLP_ENDPOINT=$OTLP_ENDPOINT" \
    --env-from AGENTGATEWAY_API_KEY \
    -- sleep infinity

# Uploaded on every run: an edited opencode.json must reach the sandbox on the
# next invocation rather than lingering as a stale copy from the first one.
echo "create-sandbox: uploading $CONFIG"
"$OPENSHELL_BIN" -g "$GATEWAY_NAME" --gateway-endpoint "$GATEWAY_ENDPOINT" sandbox upload "$NAME" "$CONFIG" "$REMOTE_CONFIG" --no-git-ignore

# The policy matches egress on the binary path. If the image puts OpenCode
# somewhere else, every request is denied and the sandbox merely looks broken;
# fail here instead, naming the path that was actually found.
if ! observed=$("$OPENSHELL_BIN" -g "$GATEWAY_NAME" --gateway-endpoint "$GATEWAY_ENDPOINT" sandbox exec -n "$NAME" -- sh -c 'command -v opencode'); then
    die "could not resolve the OpenCode binary inside '$NAME'; expected $OPENCODE_BINARY"
fi
observed=$(printf '%s' "$observed" | tr -d '[:space:]')

if [[ "$observed" != "$OPENCODE_BINARY" ]]; then
    die "OpenCode binary in '$NAME' resolves to '$observed', but sandbox-policy.yaml pins '$OPENCODE_BINARY'. Every request would be denied. Fix the policy path or the image, then: $OPENSHELL_BIN -g $GATEWAY_NAME --gateway-endpoint $GATEWAY_ENDPOINT sandbox delete $NAME"
fi

echo "create-sandbox: '$NAME' is ready (opencode at $OPENCODE_BINARY)"
echo
# The follow-ups carry the same registration and endpoint, or they would reach a
# different gateway than the one this sandbox was created on.
echo "  exec:   $OPENSHELL_BIN -g $GATEWAY_NAME --gateway-endpoint $GATEWAY_ENDPOINT sandbox exec -n $NAME -- opencode"
echo "  stop:   $OPENSHELL_BIN -g $GATEWAY_NAME --gateway-endpoint $GATEWAY_ENDPOINT sandbox stop $NAME"
echo "  start:  $OPENSHELL_BIN -g $GATEWAY_NAME --gateway-endpoint $GATEWAY_ENDPOINT sandbox start $NAME"
echo "  delete: $OPENSHELL_BIN -g $GATEWAY_NAME --gateway-endpoint $GATEWAY_ENDPOINT sandbox delete $NAME"
