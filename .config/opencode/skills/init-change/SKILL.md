---
name: init-change
description: Prepare the current repository for an implementation change by inspecting Git state and creating a feature branch when needed.
---

# Initialize change

Prepare Git before editing.

1. Inspect repository status, current branch, and remotes.
2. Preserve existing user work. Never discard, reset, clean, stash, or overwrite it without explicit approval.
3. Work in the current checkout. Never create a worktree.
4. If already on a suitable feature branch, keep it.
5. Otherwise create and switch to a short descriptive feature branch from the current intended base.
6. Do not push or publish anything.

Use repository-specific Git wrappers when established by local instructions. For the dotfiles bare repository, use `dotfiles-git` rather than `git`.

If the repository state makes safe branch creation ambiguous, stop and report the blocker rather than guessing.
