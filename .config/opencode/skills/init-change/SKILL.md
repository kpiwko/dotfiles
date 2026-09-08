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
4. Fetch the relevant remote before relying on its base ref.
5. Before reusing a feature branch, verify any associated PR/MR state and check
   whether its commits are already contained in the fetched base.
6. A merged review, or a branch fully contained in the intended base with no new
   work, is stale and must not be reused.
7. If stale and clean, fast-forward the local base when applicable and create a
   fresh descriptive feature branch. If stale with uncommitted user work, stop
   and return the evidence to the orchestrator.
8. If already on a verified active feature branch, keep it and rebase onto the
   intended fetched base when appropriate.
9. Never merge remote changes merely to synchronize a feature branch.
10. Do not push or publish anything.

Return ambiguous base/remote/review state or rebase conflicts to the
orchestrator rather than guessing.
