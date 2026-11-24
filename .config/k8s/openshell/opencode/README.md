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
   directory (currently uncommitted) documents that deployment. The wrapper names
   the gateway endpoint on every call; it never relies on whichever registration
   the CLI happens to have current (see below).
2. An OpenShell CLI, 0.1.8. `create-sandbox.sh` looks for `openshell` on `PATH`;
   set `OPENSHELL_BIN=/path/to/openshell` to use another binary.
3. `AGENTGATEWAY_API_KEY` in the environment, exported once:

   ```text
   set -a; . ~/.config/k8s/.env; set +a
   ```

Every `openshell` invocation the wrapper makes — the `sandbox get` existence
probe, `sandbox create`, `sandbox upload`, and the `sandbox exec` binary check —
carries `--gateway-endpoint`, defaulting to `https://127.0.0.1:17910`: the
verified loopback NodePort of the Kubernetes gateway, using the internal-mTLS
registration already in place. The flag is not optional in spirit: left to
itself, `openshell` operates on whatever gateway is *current* for the operator —
on this machine the host gateway on `https://localhost:17670` — which would
create the sandbox in the wrong place. Override per run with `--gateway-endpoint
URL`, or for the whole shell with `OPENSHELL_GATEWAY_ENDPOINT=<url>`; the flag
wins over the variable.

## Create

```text
~/.config/k8s/openshell/opencode/create-sandbox.sh
```

The default name is `opencode-dev`; use `--name` for a second sandbox:

```text
~/.config/k8s/openshell/opencode/create-sandbox.sh --name opencode-scratch
```

`create-sandbox.sh [--name NAME] [--gateway-endpoint URL]` does the following, in order:

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
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox exec -n opencode-dev -- opencode
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox exec -n opencode-dev -- opencode run "reply with the word ready"

# suspend; identity and workspace are kept
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox stop opencode-dev
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox start opencode-dev

# reset; the next create starts clean
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox delete opencode-dev
```

Every command there names the gateway for the same reason the wrapper does: an
endpoint left implicit is resolved from the CLI's *current* registration, which on
this machine is the host gateway, not the Kubernetes one.

The sandbox's HOME is `/sandbox`, so OpenCode state and session data are expected
under `/sandbox/.local/share/opencode`. That XDG path is expected, not observed:
treat it as unverified until a real run confirms it. Persistence of that state
and the workspace across `sandbox stop` / `sandbox start`, and a real model
response, are live acceptance checks of this stage and remain unverified until
they are actually observed.

Because the wrapper refuses an existing name, changing `opencode.json` means
deleting the sandbox on that same gateway, then re-creating it:

```text
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox delete opencode-dev
```

The upload step in the fresh `create-sandbox.sh` run then ships the edited file.
The wrapper never reconfigures a sandbox it did not create in the same run.

## Telemetry

`opencode.json` configures exactly one plugin, `@devtheops/opencode-plugin-otel`
(version `2.1.0`), with `protocol: http/protobuf`,
`endpoint: {env:OPENCODE_OTLP_ENDPOINT}`, headers
`x-mlflow-experiment-id=23`, trace propagation for the `agentgateway` provider,
and the cost metrics disabled. The variable carries the collector base URL
(`http://otel-collector.ai-dev.svc.cluster.local:4318`). A live run confirmed the
plugin appends `/v1/traces` itself: the trace for the prompt that was executed
arrived in experiment 23, which is only possible if the collector accepted the
post at the path the policy allows. If a future plugin release changes that path,
telemetry is denied while inference keeps working — check the policy against the
path actually requested rather than widening the endpoint.

The plugin entry is a **directory**, `/usr/local/share/opencode/plugins/opencode-plugin-otel`,
not an npm package name. Naming the package makes OpenCode run `npm install` at
startup; the policy denies `registry.npmjs.org`, so the plugin fails to load with
only a `WARN` in `opencode.log` and telemetry silently disappears. The image
installs the pinned plugin in a build stage, dependencies included, so loading it
needs no network. `/usr` is `read_only` in the policy, which is what lets the
sandbox read it. The `node:24-slim` stage only exists to run `npm install`; the
runtime's own `node` binary comes from the OpenShell base image and is unrelated
to it.

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
(`tests/test_openshell_opencode_sandbox.py`).

Verified in a live run on 2026-11-23 against the devcluster gateway (sandbox
`opencode-dev`, image pinned in `create-sandbox.sh`):

- **CLI 0.1.8 surface.** `sandbox create --from --name --cpu --memory --detach
  --restart-policy --policy --env --env-from -- sleep infinity`,
  `sandbox upload … --no-git-ignore`, `sandbox exec -n`, and
  `--gateway-endpoint` before the subcommand all worked as written.
- **Main process.** `-- sleep infinity` became the sandbox's main process and it
  stayed `Ready`. This is also why the image clears the base `ENTRYPOINT`: with
  `/bin/bash` inherited, bash read `sleep` as a script path and the process died.
- **Binary location.** `/usr/local/bin/opencode` was observed in the sandbox and
  the wrapper's check passed.
- **Landlock at startup.** Sandbox start succeeded with
  `landlock.compatibility: hard_requirement`, so the ABI and every listed path
  are satisfied by this image.
- **Inference.** `opencode run "reply with the word ready"` answered through
  `agentgateway/illusionist`.
- **OTLP endpoint shape.** A trace for that exact prompt (`request_preview`,
  `os.type=linux`) landed in MLflow experiment 23 with `state=OK`, so the plugin
  does post to `POST /v1/traces` when the variable is the bare collector base
  URL.
- **OpenCode state location.** `/sandbox/.local/share/opencode` exists, with
  `log/`, `opencode.db`, and the plugin's own warnings.
- **Deny-by-default.** A request from the sandbox to `registry.npmjs.org` fails
  at connect, and the OTEL plugin only loads because it is baked into the image.

Still unverified:

- **Duplicate-name create behaviour.** The CLI's own response to an existing
  name has not been exercised; the wrapper's `sandbox get` pre-check is what
  refuses the case.
- **Trace linkage between OpenCode and AgentGateway spans.** One run still
  becomes two traces. The gateway is not the cause: a direct request carrying
  `traceparent: 00-<trace-id>-<span-id>-01` is stored under exactly that trace
  id, so it continues sampled client traces. The plugin option
  `tracePropagationProviders: ["agentgateway"]` is set here and in the host
  config, and the host splits the same way, so the missing injection sits in the
  plugin or in what OpenCode hands it — not in this stage's configuration.

## Image fallback (manual, not automatic)

There is no automatic fallback. If the pinned image is unusable — no shell, no
`opencode` binary at the pinned path, or an incompatible Landlock surface — the
wrapper fails closed and prints what it observed. Do not widen the policy to make
a mismatched image work, and do not switch to `best_effort`.

The image's own repository builds from the NVIDIA community sandbox base, so that
base is not a separate fallback: it is the image's foundation, with OpenCode and
the OTEL plugin added on top. If a base bump breaks something, change the digest
in that repo's `Containerfile`
(https://github.com/kpiwko/opencode-sandbox), let CI rebuild, and re-pin the
resulting digest here. Keep `binaries[].path` in `sandbox-policy.yaml` equal to
the path the new image actually provides; `opencode.json` normally carries over
unchanged, and an incompatible OpenCode release shows up there first — expect to
adjust the config schema, not the policy.

## Troubleshooting

**Every request is denied.** Check the binary path first. The policy matches
egress on the executable, so a different path denies everything while the sandbox
looks healthy:

```text
openshell --gateway-endpoint "${OPENSHELL_GATEWAY_ENDPOINT:-https://127.0.0.1:17910}" sandbox exec -n opencode-dev -- sh -c 'command -v opencode'
```

`command` is a shell builtin, so it only works through a shell; a bare
`-- command -v opencode` would fail to exec. Compare the reported path with
`/usr/local/bin/opencode` and with `binaries[].path`. Fix the policy path or the
image; do not add hosts to compensate.

**Inference works, but no traces appear in MLflow experiment 23.** First check
`opencode.log` for `failed to load plugin`: if the plugin was configured by npm
package name it cannot be installed under the deny-by-default policy, and the
failure is only a `WARN`. Then check that `POST /v1/traces` is still allowed on
the collector endpoint. A live run confirmed the plugin posts to `/v1/traces`
with `OPENCODE_OTLP_ENDPOINT` set to the bare collector base URL, so a wrong path
here means the policy was edited, not that the variable shape is wrong. A policy
that omits the path the exporter really uses loses telemetry silently while
inference keeps working, which is the hardest failure to notice.

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

## Workload image

The sandbox runs `ghcr.io/kpiwko/opencode-sandbox`, built in a separate
repository: https://github.com/kpiwko/opencode-sandbox. That repo owns the
`Containerfile`, the multi-arch build, the CI publish step, and the path contract.
It exists because the published `ghcr.io/anomalyco/opencode` image ships OpenCode
1.x, which discards V2 configuration (`providers`) with a compatibility warning
and then fails to resolve any model — verified in a live sandbox.

| Property | Value |
| --- | --- |
| Image | `ghcr.io/kpiwko/opencode-sandbox@sha256:1f13a548cd5e4d8e467a1328607efdfccd20cc31155356a70340cab96988edd6` |
| Base | Red Hat UBI9 (`registry.access.redhat.com/ubi9/ubi`), pinned by digest |
| OpenCode | `2.4.1`, installed at `/usr/local/bin/opencode` |
| OTEL plugin | `2.1.0`, baked in at `/usr/local/share/opencode/plugins/opencode-plugin-otel` |
| Workdir | `/sandbox`; the image declares `USER sandbox` (uid 998) for native runs |
| Platforms | `linux/amd64`, `linux/arm64` |

One surprise worth knowing when debugging: OpenShell does **not** run the image as
its declared user. In a live sandbox `id -u` is `10001`, not `998`, and OpenCode
still writes under `/sandbox`, so the runtime provides that home rather than the
image's ownership. Do not build a fix on the image's uid.

This stage consumes the image by digest and must not build it: publishing needs
`packages: write`, which the image repo's CI `GITHUB_TOKEN` has and a developer
`gh` login does not. When that repo publishes a new manifest, copy the digest
from its run summary into `create-sandbox.sh` (`IMAGE`); a floating tag would
change the workload under a policy that pins the binary path.

Three of its paths are a contract with this stage — changing them there is a
breaking change here:

- `/usr/local/bin/opencode` must equal `binaries[].path` in `sandbox-policy.yaml`.
- `/usr/local/share/opencode/plugins/opencode-plugin-otel` must equal the
  `plugins[].package` directory in `opencode.json`, and must stay under `/usr`,
  which the filesystem policy allows as read-only.
- The image must clear the base image's bash `ENTRYPOINT`, or the wrapper's
  `-- sleep infinity` is read as a script path.
