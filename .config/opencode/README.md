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
export LANGFUSE_BASEURL="https://<langfuse-host>"
export LANGFUSE_ENVIRONMENT="development"
# optional:
export LANGFUSE_USER_ID="$USER"
```

`LANGFUSE_BASEURL` is the Langfuse host itself, not `/api/public/otel`.
Restart OpenCode after installing/configuring the plugin.

### Verify tracing

1. Start a new OpenCode session.
2. Run a small request that produces at least one model generation and tool call.
3. Run a request that delegates to `implement-local` or `implement-maas`.
4. In Langfuse, verify a turn trace with model generations and nested tool spans.
5. For a sufficiently long local session, verify compaction events appear as
   well. Failed steps/retries should also be visible when they occur.

If no trace appears, check that both Langfuse keys are present, the base URL is
correct, `experimental.openTelemetry` is `true`, and the Langfuse plugin is
listed in `opencode.jsonc`.

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

The local implementation model intentionally advertises a smaller context than
the model's theoretical maximum so OpenCode compacts before oMLX reaches its
prefill memory guard. Keep the oMLX guard enabled. If the current 60k budget is
still too aggressive on a specific machine/model, reduce the OpenCode context
budget first; server-side guard tuning is a separate operational choice.
