#!/usr/bin/env bash
# Build and push the multi-arch OpenCode sandbox image.
#
# The cluster pulls what is in the registry, so a local-only build is useless:
# this always publishes a multi-arch manifest (linux/amd64 + linux/arm64) to
# $IMAGE.
#
# Prerequisites: `podman login ghcr.io` for the target repository, and network
# access from the build to opencode.ai (installer) and the base image registry.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-ghcr.io/kpiwko/opencode-sandbox}"
TAG="${TAG:-2.4.1}"
OPENCODE_VERSION="${OPENCODE_VERSION:-2.4.1}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

command -v podman >/dev/null 2>&1 || { echo "build: podman not found" >&2; exit 1; }

MANIFEST="$IMAGE:$TAG"

echo "build: $MANIFEST for $PLATFORMS (opencode $OPENCODE_VERSION)"
# A previous partial run leaves a manifest under the same name; podman refuses to
# create over it, so drop it explicitly instead of failing on a stale build.
podman manifest rm "$MANIFEST" >/dev/null 2>&1 || true
podman rmi "$MANIFEST" >/dev/null 2>&1 || true
podman manifest create "$MANIFEST"

IFS=',' read -r -a platform_list <<< "$PLATFORMS"
native_arch="$(podman info --format '{{.Host.Arch}}' 2>/dev/null || uname -m)"
case "$native_arch" in
    x86_64) native_arch="amd64" ;;
    aarch64) native_arch="arm64" ;;
esac

for platform in "${platform_list[@]}"; do
    arch="${platform##*/}"
    if [ "$arch" = "$native_arch" ]; then
        verify=1
    else
        verify=0
    fi
    echo "build: $platform (verify binary: $verify)"
    podman build \
        --platform "$platform" \
        --build-arg "OPENCODE_VERSION=$OPENCODE_VERSION" \
        --build-arg "VERIFY_BINARY=$verify" \
        --manifest "$MANIFEST" \
        -f "$HERE/Containerfile" \
        "$HERE"
done

echo "build: pushing $MANIFEST"
podman manifest push --all "$MANIFEST" "docker://$MANIFEST"

echo "build: done. Pin the pushed manifest digest in create-sandbox.sh:"
podman manifest inspect "$MANIFEST" >/dev/null
echo "  podman manifest inspect $MANIFEST | grep -m1 '\"digest\"'"
