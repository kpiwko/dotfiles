# OpenShell OpenCode sandbox — design

Date: 2026-11-23
Status: draft for review

## Purpose

Run OpenCode inside a disposable OpenShell sandbox on the existing Lima/k3s
devcluster, and prove that it can reach AgentGateway for inference and the OTEL
collector for telemetry through OpenShell's supervised network path.

This is the first OpenCode stage. It validates transport, policy, and
telemetry. It does not carry real repositories or credentials.

## Inherited context

Already implemented and verified in earlier stages:

- Agent Sandbox core v1.0.10 in `agent-sandbox-system`.
- OpenShell 0.1.8 gateway, namespace `openshell`, sandbox namespace
  `openshell-sandboxes`, single SQLite replica on `local-path`.
- CA-only projection (`openshell-client-tls` with exactly `ca.crt`) into the
  sandbox namespace; supervisors never receive a client private key.
- Public path `openshell.fous.ai` via Caddy: ACME certificate, HTTP/2,
  mandatory caller client certificates, verified upstream TLS.
- One disposable sandbox created, reached Ready, executed commands as
  unprivileged UID, and preserved a workspace file across stop/start.

## Constraints

- ARM64 only; all images must publish `linux/arm64`.
- Cluster can only pull registry images (no local image loading).
- Upstream model credentials stay in AgentGateway; the sandbox receives only
  the AgentGateway API key.
- No host `$HOME`, existing PVCs, runtime sockets, or repository credentials.
- No relaxation of isolation: no `allow_unauthenticated_users`, no
  `tls_insecure_skip_verify`, no `best_effort` Landlock, no privileged pods.
- Deny-by-default egress; only named internal endpoints.

## Landlock position

OpenShell installs a mandatory Landlock baseline before agent code runs and
fails startup when it cannot be enforced. The earlier smoke sandbox reached
Ready, which indicates this kernel satisfies the ABI requirement; the first
validation step confirms it from the sandbox log. The policy
therefore sets `landlock.compatibility: hard_requirement` rather than accepting
silent degradation. Any Landlock regression becomes a startup failure, not a
security downgrade.

## Components

All new files live in `.config/k8s/openshell/opencode/`.

### `sandbox-policy.yaml`

Deny-by-default egress with two supervised endpoints, both `protocol: rest`,
`enforcement: enforce`, scoped to the OpenCode binary.

| Endpoint | Allowed requests |
|---|---|
| `agentgateway.ai-dev.svc.cluster.local:4000` | `POST /v1/chat/completions`, `POST /v1/responses`, `GET /v1/models` |
| `otel-collector.ai-dev.svc.cluster.local:4318` | `POST /v1/traces` |

Filesystem policy uses the documented baseline plus a writable workspace
(`include_workdir: true`), with `landlock.compatibility: hard_requirement`.

No wildcard hosts, no blanket private CIDRs, no additional egress. A denied
request is evidence of correct behaviour, not a defect to work around by
widening the policy.

### `opencode.json`

Minimal sandbox configuration:

- `agentgateway` provider pointing at
  `http://agentgateway.ai-dev.svc.cluster.local:4000/v1`, default model
  `illusionist`.
- OTEL plugin configured for `http/protobuf` to
  `http://otel-collector.ai-dev.svc.cluster.local:4318` with
  `x-mlflow-experiment-id=23` and trace propagation for the `agentgateway`
  provider.

Deliberately excluded: all MCP servers, the `superpowers` and notifier plugins,
`AGENTS.md` instructions, agents, and commands. They are added in a later stage
once the transport is proven.

The endpoint values come from environment variables so the same file works if
the collector or gateway moves.

### `create-sandbox.sh`

Idempotent-by-refusal wrapper that:

1. Requires the reviewed policy file and an `AGENTGATEWAY_API_KEY` in the
   environment; fails before contacting the cluster when either is missing.
2. Creates one sandbox from the pinned image digest
   (`ghcr.io/anomalyco/opencode@sha256:be38ebc82f8f0858dc703e76e582c1d32bbdf8534ebfd7d3b4aef55585433965`),
   `--cpu 1 --memory 1Gi`,
   `--detach`, `--restart-policy never`, with `HOME=/sandbox` and the
   non-secret endpoint variables set via `--env`.
3. Passes the API key via `--env-from` so it never appears in argv, logs, or the
   repository.
4. Uses an idle long-lived main process (`sleep infinity`) so the sandbox does
   not suspend like the smoke sandbox did.
5. Uploads `opencode.json` to `/sandbox/.config/opencode/opencode.json` and
   verifies it parses.
6. Refuses to reuse an existing sandbox name; prints the exact `exec`, `stop`,
   `start`, and `delete` commands.

The script never creates a second sandbox silently, never deletes pre-existing
resources, and never prints credential values.

## Data flow

```text
openshell sandbox exec … opencode run
        │
        ├── egress policy → agentgateway.ai-dev.svc.cluster.local:4000
        │        └── AgentGateway → upstream providers (keys stay here)
        │
        └── egress policy → otel-collector.ai-dev.svc.cluster.local:4318
                 └── MLflow experiment 23
```

All requests traverse the OpenShell supervisor. The workload never receives
direct network permission, and the Kubernetes NetworkPolicy fence remains in
place.

## Credential handling

- The sandbox receives the AgentGateway API key as an environment variable. The
  agent can read it; that is accepted for this stage because the key only grants
  model access through AgentGateway.
- Follow-up (not this stage): attach the key through an OpenShell provider
  profile so egress injection hides it from the workload.
- No upstream provider key, GitHub, GitLab, SSH, or model-provider credential
  enters the sandbox.

## Validation

Executable acceptance checks, in order:

1. Sandbox reaches Ready; supervisor log shows a Landlock ruleset built.
2. `opencode run` returns a model response using `illusionist`.
3. A trace appears in MLflow experiment 23 with the expected model call.
4. A request to an unlisted destination is denied, demonstrating `enforce`.
5. Stop/start preserves the workspace and session state.

Checks 1–5 must be recorded with observed output. A readiness check alone is not
acceptance.

## Non-goals

Repository cloning, GitHub/GitLab permissions, real workspaces, MCP servers,
Dex/OIDC, Caddy SSH transport, provider-profile credential hiding, and
multi-sandbox orchestration.

## Risks

| Risk | Mitigation |
|---|---|
| `anomalyco/opencode` image lacks a shell or git | Non-fatal for validation; fall back to the NVIDIA community sandbox base |
| Image runs as root | `HOME=/sandbox` and unprivileged runtime identity; verify with `id` |
| `latest` tag drift | Digest pin in the wrapper and docs |
| Wrong path in policy silently blocks calls | Denied requests are surfaced and policy updated deliberately |
| Debug exporter in the collector | Pre-existing; review telemetry sensitivity before real workloads |

## Follow-up stages

1. Repository access with narrowly scoped forge credentials.
2. Provider-profile credential injection.
3. MCP servers and the full agent/tool configuration.
4. Caddy SSH / interactive `connect` transport.
