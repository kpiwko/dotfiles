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

## Implementation agents

- `implement-local`: default implementation agent using local oMLX.
- `implement-cloud`: explicit OpenAI Luna implementation agent.
- `implement-maas`: explicit LiteMaaS implementation agent.
- The implementation agents intentionally use the same workflow, skills, and
  Git policy so provider/model behavior can be compared.
- `implement-cloud` and `implement-maas` are only used when explicitly
  requested; there is no automatic remote fallback.

The primary orchestrator and default root model use
`vertex_ai/gemini-3.8-flash`.

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
