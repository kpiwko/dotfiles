# Workspace Instructions

## `$HOME` and dotfiles

The workspace is `$HOME` (`/Users/kpiwko`). Its version control is the bare
Git repository `~/.dotfiles`, with `$HOME` as the work tree. Use `sandbox-git`
for every Git operation in `$HOME`; do not use raw `git` or inspect the bare
repository directly.

Do not search all of `$HOME` for repositories or `.git` directories. Avoid
broad `glob` or recursive `grep` searches rooted at `$HOME`; inspect only named,
bounded paths required by the task.

## Plans and Specs Location

- When working in `$HOME` (the dotfiles bare repository), do not create a `docs/` directory directly under `$HOME`. All implementation plans and Superpowers specs/plans must be placed in `.config/dotfiles/docs/plans/` and `.config/dotfiles/docs/superpowers/`.
- In individual project repositories (e.g. under `devel/*`), keep plans within that repository's own `docs/plans/` or `docs/superpowers/` directory.
