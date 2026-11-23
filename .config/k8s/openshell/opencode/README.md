# OpenCode sandbox (OpenShell stage)

The first workload stage on the pinned OpenShell 0.1.8 gateway: one disposable
sandbox running [OpenCode](https://opencode.ai) with `illusionist` inference
through AgentGateway and OTEL traces into MLflow experiment 23, under a
deny-by-default egress policy.

The gateway stage README in this directory (currently uncommitted) describes the
gateway itself; this file covers only the OpenCode sandbox. This stage exists to
prove transport, policy, and telemetry. It carries no real repositories, no forge
credentials, and no host `$HOME`. Nothing here is applied by the gateway's
deployment script: creating a sandbox is a separate, explicit operator action,
and deleting it is the documented reset.

| Path | Purpose |
| --- | --- |
| `sandbox-policy.yaml` | Deny-by-default egress policy, hard Landlock requirement |
| `opencode.json` | Minimal sandbox OpenCode config (one provider, one OTEL plugin) |
| `create-sandbox.sh` | Precondition checks, create, config upload, binary-path verification |

## Posture

- **deny-by-default.** Traffic is permitted only from `/usr/local/bin/opencode` to
  two internal endpoints, and only for the method/path pairs below. There are no
  wildcard hosts, no blanket private CIDRs, and no extra egress. A denied request
  is evidence the policy works, not a defect to widen away.
- Every endpoint is `protocol: rest` with `enforcement: enforce`, so a request
  outside the allow list is blocked rather than merely logged.
- `landlock.compatibility: hard_requirement`. Every path in `filesystem_policy`
  is a startup requirement: a missing path or an unavailable Landlock ABI aborts
  sandbox startup instead of silently degrading isolation. Never replace this
  with `best_effort` to make a run succeed.
- The main process is `sleep infinity`. OpenCode runs only inside
  `sandbox exec`, so nothing executes and nothing can egress until an operator
  asks for it. `--restart-policy never` keeps a crash visible instead of hiding
  it behind a restart loop.

| Endpoint | Allowed requests |
| --- | --- |
| `agentgateway.ai-dev.svc.cluster.local:4000` | `POST /v1/chat/completions`, `POST /v1/responses`, `GET /v1/models` |
| `otel-collector.ai-dev.svc.cluster.local:4318` | `POST /v1/traces` |

Upstream model credentials stay in AgentGateway; the sandbox holds only the
AgentGateway key, and only by reference (see below).

## Prerequisites

1. The gateway and its API are reachable — the gateway stage README in this
   directory (currently uncommitted) documents that deployment. The host
   registration used here is whatever `openshell` resolves as current.
2. An OpenShell CLI, 0.1.8. `create-sandbox.sh` looks for `openshell` on `PATH`;
   set `OPENSHELL_BIN=/path/to/openshell` to use another binary.
3. `AGENTGATEWAY_API_KEY` in the environment, exported once:

   ```text
   set -a; . ~/.config/k8s/.env; set +a
   ```

## Create

```text
~/.config/k8s/openshell/opencode/create-sandbox.sh
```

The default name is `opencode-dev`; use `--name` for a second sandbox:

```text
~/.config/k8s/openshell/opencode/create-sandbox.sh --name opencode-scratch
```

`create-sandbox.sh [--name NAME]` does the following, in order:

1. **Preconditions, before any cluster contact.** The policy and config files
   exist next to the script, `AGENTGATEWAY_API_KEY` is non-empty, and the CLI was
   found. A missing input fails here, cheaply, instead of mid-create.
2. **Refuses an existing name.** A name already taken is reported with the
   delete command; the script never creates a second sandbox silently and never
   deletes anything. (Whether the CLI's own create rejects duplicates is
   unverified; the wrapper probes with `sandbox get` instead of relying on it.)
3. **Creates** from a digest-pinned image:

   ```text
   ghcr.io/anomalyco/opencode@sha256:be38ebc82f8f0858dc703e76e582c1d32bbdf8534ebfd7d3b4aef55585433965
   ```

   Pinned by digest, never by tag: a retagged image could move the binary path
   the policy matches on, which would turn every request into a denial. Flags are
   `--cpu 1 --memory 1Gi --detach --restart-policy never --policy
   sandbox-policy.yaml`, with `HOME=/sandbox`, `AGENTGATEWAY_BASE_URL`, and
   `OPENCODE_OTLP_ENDPOINT` supplied as non-secret `--env` values, and the main
   process `-- sleep infinity`.
4. **Passes the key by reference.** `--env-from AGENTGATEWAY_API_KEY` copies the
   variable from the operator's environment into the sandbox. The value never
   enters the script's argv, its output, or any file in this repository. Do not
   "helpfully" pass it with `--env`: that would expose the credential to process
   listings and logs.
5. **Uploads `opencode.json`** to `/sandbox/.config/opencode/opencode.json` on
   every run (with `--no-git-ignore`), so an edited config reaches the sandbox on
   the next invocation instead of lingering as a stale copy.
6. **Verifies the binary path.** It resolves `command -v opencode` inside the
   sandbox and fails unless it equals `/usr/local/bin/opencode`, naming the path
   it actually found. Without this check a path mismatch would present as every
   request being denied.
7. Prints the follow-up commands.

## Everyday use

```text
openshell sandbox exec -n opencode-dev -- opencode
openshell sandbox exec -n opencode-dev -- opencode run "reply with the word ready"

openshell sandbox stop opencode-dev     # suspend; identity and workspace are kept
openshell sandbox start opencode-dev

openshell sandbox delete opencode-dev   # reset; the next create starts clean
```

The sandbox's HOME is `/sandbox`, so OpenCode state and session data are expected
under `/sandbox/.local/share/opencode`. That XDG path is expected, not observed:
treat it as unverified until a real run confirms it. Persistence of that state
and the workspace across `sandbox stop` / `sandbox start`, and a real model
response, are live acceptance checks of this stage and remain unverified until
they are actually observed.

Because the wrapper refuses an existing name, changing `opencode.json` means
`sandbox delete` followed by a fresh `create-sandbox.sh`; the upload step then
ships the edited file. The wrapper never reconfigures a sandbox it did not
create in the same run.

## Telemetry

`opencode.json` configures exactly one plugin, `@devtheops/opencode-plugin-otel`,
with `protocol: http/protobuf`, `endpoint: {env:OPENCODE_OTLP_ENDPOINT}`, headers
`x-mlflow-experiment-id=23`, trace propagation for the `agentgateway` provider,
and the cost metrics disabled. The variable carries the collector base URL
(`http://otel-collector.ai-dev.svc.cluster.local:4318`). That the plugin appends
`/v1/traces` to it is an unverified assumption about third-party plugin
behaviour: if the exporter posts to some other path, every trace is denied while
inference keeps working. Confirm the path actually requested on the first run
(see Troubleshooting) and, if it differs, allow exactly that path rather than
widening the endpoint.

## Editing the policy

`sandbox-policy.yaml` is the only place egress is decided. To change it:

1. Edit the endpoint or rule deliberately, with the reason in a comment. Never
   add a wildcard host, a blanket CIDR, or an `access` preset to make a call
   succeed.
2. Keep `binaries[].path` equal to the wrapper's `OPENCODE_BINARY`
   (`/usr/local/bin/opencode`); a test pins that equality.
3. Delete and re-create the sandbox. The policy is passed with `--policy` at
   create time, and this stage documents no in-place policy update.
4. If a real image genuinely lacks a path listed in `filesystem_policy`, delete
   that single path. Do not lower `landlock.compatibility`.

## Verified and unverified

Verified offline, with a stand-in CLI injected through `OPENSHELL_BIN`: the
wrapper's ordering, refuse-on-missing-input behaviour, digest pin, `--env` and
`--env-from` handling, config upload, and binary-path check
(`tests/test_openshell_opencode_sandbox.py`). No cluster was contacted.

Unverified until a real run, and treated as unverified in this document:

- **CLI 0.1.8 flag spellings.** `sandbox create --from --name --cpu --memory
  --detach --restart-policy --policy --env --env-from`,
  `sandbox upload … --no-git-ignore`, and `sandbox exec -n` are written from the
  documented shape of the 0.1.8 CLI, not from an executed invocation.
- **The `-- sleep infinity` argv shape.** That everything after `--` becomes the
  sandbox's main process, passed as a command plus argument rather than one
  shell string, is not proven here.
- **The image's `opencode` binary location.** `/usr/local/bin/opencode` is
  asserted by the wrapper, which fails loudly on a mismatch; the image itself has
  not been inspected.
- **Duplicate-name create behaviour.** Unverified, hence the `sandbox get`
  pre-check.
- **OTLP endpoint shape.** `OPENCODE_OTLP_ENDPOINT` is set to the bare collector
  base URL and the policy allows `POST /v1/traces`, assuming the OTEL plugin
  appends that path itself. Whether it appends `/v1/traces`, or instead expects
  the full `/v1/traces` URL in the variable, is unverified third-party behaviour:
  confirm which path is actually posted on the first run.
- **OpenCode state location.** `/sandbox/.local/share/opencode` follows from
  `HOME=/sandbox` and OpenCode's documented XDG layout; it has not been observed
  in a running sandbox.
- **Landlock support at sandbox startup.** The policy requires it; only a real
  start proves it. Absence is a startup failure, never a downgrade.

## Image fallback (manual, not automatic)

There is no automatic fallback. If the pinned image is unusable — no shell, no
`opencode` binary at the pinned path, or an incompatible Landlock surface — the
wrapper fails closed and prints what it observed. Do not widen the policy to make
a mismatched image work, and do not switch to `best_effort`.

The fallback considered in the design is the NVIDIA community sandbox base image.
Using it is a deliberate edit: change the digest in `create-sandbox.sh`, then
change `binaries[].path` in `sandbox-policy.yaml` to the path the new image
actually provides, re-run the wrapper, and re-check the telemetry and inference
paths. `opencode.json` is carried over unchanged: a replacement image that ships
an incompatible OpenCode release shows up there first — expect to adjust the
config schema, not the policy. That combination is unverified; treat it as a new
image with a new policy, not as a supported mode of this stage.

## Troubleshooting

**Every request is denied.** Check the binary path first. The policy matches
egress on the executable, so a different path denies everything while the sandbox
looks healthy:

```text
openshell sandbox exec -n opencode-dev -- sh -c 'command -v opencode'
```

`command` is a shell builtin, so it only works through a shell; a bare
`-- command -v opencode` would fail to exec. Compare the reported path with
`/usr/local/bin/opencode` and with `binaries[].path`. Fix the policy path or the
image; do not add hosts to compensate.

**Inference works, but no traces appear in MLflow experiment 23.** Check that
`POST /v1/traces` is still allowed on the collector endpoint, then confirm the
path the plugin actually requests. `OPENCODE_OTLP_ENDPOINT` is the bare collector
base URL, which assumes the plugin appends `/v1/traces`; whether it does, or
whether it wants the full `/v1/traces` URL in the variable instead, is unverified.
A policy that omits the path the exporter really uses loses telemetry silently
while inference keeps working, which is the hardest failure to notice.

**The sandbox reports suspended.** Its main process exited. `sleep infinity` is
supposed to outlive the run, and `--restart-policy never` deliberately leaves the
crash visible instead of masking it with a restart loop. Inspect the log, then
delete and re-create.

**Startup aborts naming a Landlock path.** That path is absent from the image.
Delete exactly that one path from `filesystem_policy` and re-create — a
deliberate, reviewable removal. Never change `landlock.compatibility` to
`best_effort`: that converts a visible failure into silent degradation.

**`create-sandbox: error: sandbox 'opencode-dev' already exists`.** Delete it, or
pass `--name`. The wrapper will not adopt or reconfigure a sandbox this run did
not create.

**`create-sandbox: error: AGENTGATEWAY_API_KEY is empty`.** Export the key in the
calling shell (`set -a; . ~/.config/k8s/.env; set +a`). The wrapper cannot read it
from anywhere else, and stops before touching the cluster.

## Not included

This stage deliberately excludes, and its config contains none of:

- repositories: no clone, no mount, no host `$HOME`;
- GitHub or GitLab credentials, deploy keys, or SSH agent;
- a real workspace — `/sandbox` is disposable and carries only OpenCode state;
- MCP servers, agents, and commands (a later stage, after transport is proven);
- Dex/OIDC and provider-profile credential hiding;
- Caddy SSH / interactive `connect` transport.

Live validation of the acceptance checks is a separate operator step; this
directory ships configuration and procedure only.
