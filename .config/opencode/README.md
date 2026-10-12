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

- `worker` uses the AgentGateway `worker` alias.
- `planner` uses the AgentGateway `architect` alias.
- `reviewer` uses the AgentGateway `reviewer` alias.

The primary orchestrator and default root model use
`agentgateway-gemini/gemini`.

## AgentGateway inference boundary

OpenCode uses two providers that target the same AgentGateway deployment and
authenticate with `AGENTGATEWAY_API_KEY`:

- `agentgateway` uses `AGENTGATEWAY_BASE_URL` and OpenAI-compatible requests
  for `omnipower`, `architect`, `worker`, `reviewer`, and `spade`.
- `agentgateway-gemini` uses `AGENTGATEWAY_GEMINI_BASE_URL` and the native
  Gemini API for `gemini`. This avoids OpenAI-format translation during chained
  Gemini function calls while preserving AgentGateway routing and telemetry.

`omnipower` routes to Enmaas Claude Opus 5.5, `architect` routes to Enmaas
Terra with direct OpenAI fallback, `worker` and `reviewer` route to Enmaas
Luna with direct OpenAI fallback, `spade` routes to Enmaas GLM 5.3, and
`gemini` explicitly targets Vertex Gemini 3.8 Flash.

AgentGateway keeps its SQLite request database on its own PVC. MLflow remains
the telemetry backend through the existing OpenTelemetry collector and is not
used for inference. The OpenCode OTel plugin propagates W3C trace context to
both providers and records session/tool workflow spans; AgentGateway records
the resolved upstream model and realized cost. The plugin's alias-based cost
metrics are disabled.

Configuration changes require a new OpenCode session or service restart. An
existing session retains its stored model selection.

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

## Terminal, workspace, and session model

Ghostty is the terminal, Zellij is the workspace/project layer, and OpenCode
holds AI conversations within a project:

```text
Zellij session
│
├── tab: dotfiles
│   ├── pane: OpenCode
│   │   ├── OpenCode session: investigation
│   │   ├── OpenCode session: implementation
│   │   └── OpenCode session: review
│   └── pane: shell/tests
│
├── tab: another project
│   └── ...
```

The main rule is: same checkout and a different AI conversation or task means
an OpenCode session/tab (`Ctrl+n` / `session.new`, switched with `Ctrl+Tab` or
`Ctrl+Shift+Tab`). A different checkout, worktree, or environment means a
Zellij tab/session (`Alt+1/2/3`, `Alt+d`, or `Alt+r`).

Use normal `opencode` by default; it connects to the OpenCode v2 shared
background service. Do not use `--standalone` by default—reserve it for cases
that specifically need process isolation. Zellij keeps `mouse_mode false`, so
Ghostty and OpenCode can handle mouse capture, tab clicks, transcript scrolling,
and text selection. Zellij owns `Alt-*`; applications such as OpenCode own
`Ctrl-*`.
