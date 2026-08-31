---
name: init-change
description: Prepare the current repository for an implementation change by selecting the correct Git interface, synchronizing the intended base, and establishing a feature branch.
---

# Initialize change

Load this before repository edits unless the parent explicitly says Git setup is complete.

## Git interface

- If the current working directory is exactly `$HOME`, use `dotfiles-git` for every Git operation.
- Otherwise use `git` and never invoke `dotfiles-git`.
- Work in the current checkout. Never create a worktree.

## Prepare the base

1. Inspect status, current branch, tracking configuration, and remotes.
2. Preserve existing user work. Never discard, reset, clean, stash, or overwrite it without explicit approval.
3. Determine the intended base remote and branch. Prefer an explicit base supplied by the parent, such as `upstream/main`.
4. When no base was supplied, infer it only from strong repository evidence such as current tracking configuration, remote HEAD/default branch, or an established repository convention. Do not assume `origin/main` merely because it exists.
5. Fetch the relevant remote before relying on its base ref.
6. Before reusing a current feature branch, verify that it is still an active change rather than a stale branch from completed work:
   - inspect any PR/MR associated with the branch and verify its current state; never treat a remembered, cached, or previously printed PR/MR URL as evidence that the review is still open;
   - after fetching the intended base, check whether the branch's commits are already contained in that base when the repository history permits a reliable ancestry check;
   - a merged PR/MR, or a feature branch fully contained in the intended base with no new commits for the current task, is stale and must not be reused for a new change;
   - a closed-but-unmerged PR/MR is not automatically reusable: stop and return the evidence unless the parent explicitly says to continue that change.
7. If the current branch is stale and the worktree is clean, synchronize the intended local base with its fetched remote using a fast-forward-only update when applicable, then create and switch to a new short descriptive feature branch from the updated base. Do not push new work onto the stale branch.
8. If the current branch is stale but the worktree already contains uncommitted user work, preserve it and stop. Report that the branch is stale and ask the orchestrator how to relocate the work; do not stash, reset, switch branches, or otherwise move it implicitly.
9. If already on a verified active feature branch, keep it. Rebase it onto the intended fetched base when that is the normal non-destructive synchronization for the task.
10. Otherwise synchronize the intended local base with its fetched remote using a fast-forward-only update when applicable, then create and switch to a short descriptive feature branch from that base.
11. Never merge remote changes into a feature branch merely to synchronize it. Prefer rebase for feature-branch synchronization.
12. Do not push or publish anything.

If the intended base, remote relationship, repository state, review state, or a rebase conflict makes safe preparation ambiguous, stop and return the evidence to the orchestrator rather than guessing or resolving conflicts destructively.
