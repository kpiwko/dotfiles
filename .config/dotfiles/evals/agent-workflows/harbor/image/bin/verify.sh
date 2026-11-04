#!/bin/bash
# Deterministic final-state verifier entrypoint baked into the image at
# /opt/git-pilot/bin/verify.sh (harbor/image/Containerfile).
#
# Runs AFTER the agent, inside the Harbor trial container. Wraps the actual
# post-run repository state through the vendored sandbox-git wrapper with
# neutralized, read-only Git, compares against the trusted in-image records,
# and writes Harbor's reward contract (/logs/verifier/reward.json).
#
# Explicit scope: basic Git-task END-STATE pilot.
# procedure_attempt_coverage: not_measured — no attempt observation, no
# denied-destructive-attempt coverage, no holdout/golden-history claims.
set -o pipefail

mkdir -p /logs/verifier

export GIT_PILOT_WORKSPACE="${GIT_PILOT_WORKSPACE:-/workspace}"
export GIT_PILOT_FIXTURE_DIR="${GIT_PILOT_FIXTURE_DIR:-fixture}"

# /tests is where Harbor uploads the task package's tests/ dir; the trusted
# records also travel there (the image bakes an identical copy under
# /opt/git-pilot/records). Prefer the in-image copy — the agent cannot have
# written it.
RECORDS_DIR="/opt/git-pilot/records"
if [ ! -f "$RECORDS_DIR/provenance.json" ]; then
  RECORDS_DIR="/tests"
fi

# The verifier module lives in the image; records dir is resolved by the
# verifier from the image path, but allow an explicit override for local
# (non-container) unit runs of this same script.
PYTHONPATH="/opt/git-pilot/lib" python3 /opt/git-pilot/bin/verifier.py \
  --records "$RECORDS_DIR" \
  --workspace "$GIT_PILOT_WORKSPACE" \
  --fixture-dir "$GIT_PILOT_FIXTURE_DIR"
exit $?
