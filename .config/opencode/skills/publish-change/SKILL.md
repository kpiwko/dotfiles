---
name: publish-change
description: Create logical commits and publish validated feature-branch work through the sandboxed Git interface while keeping push and PR/MR targets independent.
---

# Publish change

Use `sandbox-git` for every Git operation. Never invoke raw `git`,
`dotfiles-git`, or another Git wrapper.

## Commit

1. Inspect status and the diff being committed.
2. Commit independently meaningful coherent portions instead of mechanically
   splitting by file or postponing everything to one final commit.
3. Include this trailer on every created commit:

       Assisted-by: OpenCode

4. Verify the trailer after committing. Do not amend existing commits unless
   explicitly requested and approved.

## Push

Treat the push destination and PR/MR target independently. Before pushing,
fetch the intended target/base and repeat the stale-branch guard: query current
review state and check ancestry against the fetched base.

- Never push a branch whose review is merged.
- Return closed-but-unmerged review state to the orchestrator unless explicitly
  continuing that review.
- Never push completed/stale work as a new change.
- Prefer `sandbox-git publish [remote]` for normal publication. It safely
  pushes the current feature branch to the selected remote (default `origin`),
  establishes tracking when needed, and refuses protected/significant branches
  or inconsistent tracking.
- Bare `sandbox-git push` remains the compatible `origin` publication path.
  Avoid explicit refspecs for normal publication.
- Destructive variants such as force push or branch deletion require explicit
  human approval through agent permissions. Never bypass the permission prompt.

## PR/MR

Determine head repository/branch, target repository/branch, and hosting provider
independently. Use `gh` for GitHub and `glab` for GitLab. Before creating or
modifying a review, query existing reviews for the exact head and target. Reuse
only a currently open matching review.

Prepare the complete title and description, including summary, validation,
relevant ADRs, and important risks/follow-ups. Show the proposed head/target,
title, and description to the user before creating or updating the PR/MR unless
the parent assignment already contains explicit user approval to create or
update that review. Do not request duplicate approval when the parent already
carries it; the configured tool permission boundary still applies. Merges always
require explicit approval.
