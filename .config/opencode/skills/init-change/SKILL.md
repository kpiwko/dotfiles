---
name: init-change
description: Prepare the current repository for an implementation change by synchronizing the intended base and establishing a feature branch through the sandboxed Git interface.
---

# Initialize change

Load this before repository edits unless the parent explicitly says Git setup is
complete.

Use `sandbox-git` for every Git operation. The wrapper automatically uses the
bare `$HOME/.dotfiles` repository with `$HOME` as its work tree when the current
working directory is exactly `$HOME`; elsewhere it uses the current normal Git
repository. Never invoke raw `git` or `dotfiles-git`.

1. Inspect status, current branch, tracking configuration, and remotes.
2. Preserve existing user work. Never discard, reset, clean, stash, or overwrite
   it without explicit approval.
3. Determine the intended base remote and branch from parent instructions or
   strong repository evidence. Never assume `origin/main` only because it exists.
4. Prefer `sandbox-git start-branch <branch> [base] [remote]` when creating a
   fresh branch from a fetched base. It fetches first and lets Git refuse rather
   than overwriting conflicting local or untracked files.
5. Prefer `sandbox-git sync-base [base] [remote]` to rebase an active feature
   branch onto a freshly fetched base.
6. Before reusing a feature branch, verify any associated PR/MR state and check
   whether its commits are already contained in the fetched base.
7. A merged review, or a branch fully contained in the intended base with no new
   work, is stale and must not be reused.
8. If stale and clean, create a fresh descriptive feature branch from the fetched
   base. If stale with uncommitted user work and `start-branch` cannot preserve
   it safely, stop and return the evidence to the orchestrator.
9. If already on a verified active feature branch, keep it and synchronize it
   with `sync-base` when appropriate.
10. Never merge remote changes merely to synchronize a feature branch.
11. Do not push or publish anything.

Return ambiguous base/remote/review state or rebase conflicts to the
orchestrator rather than guessing.
