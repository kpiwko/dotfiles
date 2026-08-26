---
name: publish-change
description: Finalize validated implementation work with logical commits, push the feature branch, and prepare or publish a PR/MR with human approval.
---

# Publish change

Use this only after implementation and validation are complete.

## Commit

1. Inspect the final diff and status.
2. Split changes into small logical commits when the work contains independently meaningful changes. Do not split mechanically by file.
3. Each commit must leave the repository in a coherent state.
4. Include this Git trailer on every created commit, separated from the body by a blank line:

       Assisted-by: OpenCode

5. Verify the trailer after committing.

Do not amend existing commits unless explicitly requested.

## Push

- Push only the current feature branch to `origin`.
- Use an established safe push wrapper when repository instructions provide one.
- Never bypass a safe-push refusal.
- Force pushes require explicit human approval.

## PR/MR

Detect the hosting provider from `origin` and use its CLI (`gh` for GitHub, `glab` for GitLab). Support identifiable self-hosted instances.

Before creating or modifying a PR/MR:

1. Prepare the complete title and description.
2. Include summary, validation, relevant ADRs, and important risks/follow-ups.
3. Show the proposed title and description to the user.
4. Wait for explicit approval.
5. Only then create or update the PR/MR.

Merges always require explicit approval.
