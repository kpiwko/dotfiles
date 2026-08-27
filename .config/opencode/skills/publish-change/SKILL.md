---
name: publish-change
description: Create logical commits and publish validated feature-branch work, keeping the push destination separate from the PR/MR target repository and base.
---

# Publish change

Load this before the first commit when the assignment includes committing, pushing, or PR/MR publication. It may be used during implementation for logical checkpoint commits; pushing and PR/MR publication happen only after relevant validation.

## Commit

1. Inspect status and the diff being committed.
2. Create a logical commit whenever the completed portion is independently meaningful and leaves the repository coherent. Do not split mechanically by file and do not postpone all commits merely to make one final commit.
3. Include this Git trailer on every created commit, separated from the body by a blank line:

       Assisted-by: OpenCode

4. Verify the trailer after committing.

Do not amend existing commits unless explicitly requested.

## Push

Treat the push destination and PR/MR target as independent concepts.

Before pushing, fetch the intended target/base remote and perform a stale-branch guard even if `init-change` was previously run or the parent says Git setup is complete:

1. Identify any PR/MR associated with the current feature branch and query its current state from the hosting provider. Never reuse a remembered, cached, or previously printed PR/MR URL without verifying it.
2. Check whether the current branch's commits are already contained in the freshly fetched intended base when the repository history permits a reliable ancestry check.
3. If the associated PR/MR is merged, do not push. The branch represents completed work; return to the orchestrator so the new change can start from the updated base on a new feature branch.
4. If the PR/MR is closed but unmerged, do not silently push or create another review from the same branch. Return the review state and branch evidence to the orchestrator unless the parent explicitly requested continuation of that closed change.
5. If the branch is fully contained in the intended base and has no new commits beyond it, do not push and do not report the old PR/MR as the result. Treat it as completed/stale work and return to the orchestrator for a fresh branch.

After the stale-branch guard passes:

1. Determine the feature branch's writable push remote from tracking configuration and repository evidence. `origin` is the normal default only when the evidence supports it.
2. The pushed remote branch should normally have the same name as the local feature branch.
3. For the ordinary `origin` feature-branch case, use `sandbox-git-push`.
4. If the correct writable push remote is not supported by the sandbox wrapper, do not silently fall back to raw `git push`; request approval for the exact push command.
5. Never bypass a sandbox refusal. Force pushes always require explicit human approval.

## PR/MR

Determine these independently from the push destination:

- head repository and feature branch
- target/base repository, which may be a different remote such as `upstream`
- target/base branch
- hosting provider and instance

Use repository configuration, remotes, tracking information, task context, and explicit parent instructions. Do not infer that the PR/MR target is `origin` just because the feature branch was pushed there. If multiple plausible targets remain, return the evidence to the orchestrator instead of guessing.

Use `gh` for GitHub and `glab` for GitLab, including identifiable self-hosted instances.

Before creating or modifying a PR/MR:

1. Query the hosting provider for reviews associated with the exact head repository and branch. Reuse a review only when it is currently open and its head and target match the intended publication.
2. A merged or closed review is historical evidence, not the publication target for new work. Never return its URL as if publication succeeded.
3. Prepare the complete title and description.
4. Include summary, validation, relevant ADRs, and important risks/follow-ups.
5. Show the proposed head and target repositories/branches, title, and description to the user.
6. Wait for explicit approval.
7. Only then create or update the PR/MR.

Merges always require explicit approval.
