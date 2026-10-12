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

- `implement`, `implement-local`, and `implement-maas` use the AgentGateway
  `worker` alias. The legacy names remain for existing workflows.

The primary orchestrator and default root model use `agentgateway/worker`.

## AgentGateway inference boundary

OpenCode calls AgentGateway's OpenAI-compatible endpoint through
`AGENTGATEWAY_BASE_URL` and authenticates with `AGENTGATEWAY_API_KEY`.
`omnipower` routes to Enmaas Claude Opus 5.5, `architect` routes to Enmaas
Terra with direct OpenAI fallback, `worker` and `reviewer` route to Enmaas
Luna with direct OpenAI fallback, `spade` routes to Enmaas GLM 5.3, and
`gemini` explicitly targets Vertex Gemini 3.8 Flash.

AgentGateway keeps its SQLite request database on its own PVC. MLflow remains
the telemetry backend through the existing OpenTelemetry collector and is not
used for inference.

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
