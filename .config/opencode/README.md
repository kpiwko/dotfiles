# OpenCode setup

This directory contains the global OpenCode configuration, agents, skills, and
plugin configuration used by the dotfiles setup.

## Required environment

Set provider credentials in your shell rather than committing them here:

```zsh
export OPENAI_API_KEY="sk-..."
export OMLX_BASE_URL="https://<omlx-host>/v1"
export OMLX_API_KEY="..."
export LITEMAAS_BASE_URL="https://<litemaas-host>/v1"
export LITEMAAS_API_KEY="..."
```

`LITEMAAS_BASE_URL` already includes `/v1`. The configured MaaS implementation
model is `Qwen3.8-27B-NT`.

## Langfuse tracing

OpenCode tracing uses the official Langfuse OpenCode observability plugin. The
old generic `OTEL_EXPORTER_OTLP_*` setup is not needed for this integration.

The tracked `opencode.jsonc` enables `experimental.openTelemetry` and contains:

```json
"plugin": [
  "superpowers@git+https://github.com/obra/superpowers.git",
  "@langfuse/opencode-observability-plugin@latest"
]
```

OpenCode installs configured npm package plugins when it loads them. To install
or repair the Langfuse plugin explicitly with the OpenCode CLI, run:

```zsh
opencode plugin @langfuse/opencode-observability-plugin@latest --global
```

Then configure Langfuse credentials:

```zsh
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_BASE_URL="https://<langfuse-host>"
export LANGFUSE_ENVIRONMENT="development"
# optional:
export LANGFUSE_USER_ID="$USER"
```

`LANGFUSE_BASE_URL` is the Langfuse host itself, not `/api/public/otel`.
The plugin also accepts the legacy `LANGFUSE_BASEURL` name, but the canonical
`LANGFUSE_BASE_URL` form is preferred. Restart OpenCode after changing plugin
configuration or credentials.

`LANGFUSE_INIT_*` variables belong to the Langfuse server and are used to
bootstrap the organization, project, user, and project API keys. They are not
read by the OpenCode plugin. OpenCode must receive the resulting project key
pair separately through `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (or
`opencode-langfuse.json`).

### Verify tracing

1. Start a new OpenCode session.
2. Run a small request that produces at least one model generation and tool call.
3. Run a request that delegates to `implement-local` or `implement-maas`.
4. In Langfuse, verify a turn trace with model generations and nested tool spans.
5. For a sufficiently long local session, verify compaction events appear as
   well. Failed steps/retries should also be visible when they occur.

### Debug tracing

First verify the OpenCode process sees the expected environment without printing
secret values:

```zsh
for v in LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_BASE_URL; do
  if [[ -n "${(P)v:-}" ]]; then
    echo "$v=set"
  else
    echo "$v=MISSING"
  fi
done
```

Then start OpenCode with its logs visible:

```zsh
opencode --print-logs --log-level DEBUG
```

The Langfuse plugin logs through OpenCode with service name `langfuse`. On a
successful startup, look for:

```text
OTEL tracing initialized → https://<langfuse-host>
```

If credentials are not visible to the OpenCode process, look for:

```text
[Tracing disabled] Missing langfuse credentials
```

OpenCode also writes logs under `~/.local/share/opencode/log/`. To inspect the
latest Langfuse-related messages after reproducing the issue:

```zsh
grep -i langfuse ~/.local/share/opencode/log/* | tail -100
```

Before debugging ingestion, verify the Langfuse endpoint itself is reachable:

```zsh
curl -fsS "$LANGFUSE_BASE_URL/api/public/health"
```

If plugin initialization succeeds but no traces arrive, next inspect the
Langfuse web logs while generating one small OpenCode turn:

```zsh
devcluster-kubectl logs -n ai-dev deployment/langfuse-web --tail=200 -f
```

Authentication or ingestion errors there distinguish a bad project key pair
from a plugin-loading problem.

For a freshly initialized self-hosted Langfuse instance, the project created by
`LANGFUSE_INIT_PROJECT_*` should have the initialized API key pair associated
with it. If the project exists but Project Settings shows no API keys, verify the
actual `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` and `LANGFUSE_INIT_PROJECT_SECRET_KEY`
environment values inside the `langfuse-web` pod and inspect its startup logs;
that indicates bootstrap did not create the key resource as expected rather
than an OpenCode tracing issue.

## Implementation agents

- `implement-local`: default implementation agent using local oMLX.
- `implement-maas`: explicitly selected LiteMaaS implementation agent.
- Both intentionally use the same workflow, skills, Git policy, and roughly the
  same advertised context budget so their behavior can be compared.
- `implement-maas` is only used when explicitly requested; there is no automatic
  remote fallback.

## Git safety

Agents use only `sandbox-git` for Git operations. It selects
`git --git-dir="$HOME/.dotfiles" --work-tree="$HOME"` when invoked from exactly
`$HOME`, and ordinary Git in other repositories. Raw `git`, `dotfiles-git`, and
the former `sandbox-git-push` path are not part of the implementation workflow.
Destructive `sandbox-git` forms remain approval-gated by agent permissions.

## Local context and oMLX

The local implementation model advertises a 90k context with an 8k compaction
reserve. This intentionally gives `implement-local` more working room than the
previous 60k/16k setup while keeping automatic compaction and pruning enabled.
Keep the oMLX memory guard enabled. If the server still rejects large prefills,
reduce the advertised OpenCode context before weakening the server-side guard.
