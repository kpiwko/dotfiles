# Workspace Instructions

## `$HOME` and dotfiles

The workspace is `$HOME` (`/Users/kpiwko`). Its version control is the bare
Git repository `~/.dotfiles`, with `$HOME` as the work tree. Use `sandbox-git`
for every Git operation in `$HOME`; do not use raw `git` or inspect the bare
repository directly.

Do not search all of `$HOME` for repositories or `.git` directories. Avoid
broad `glob` or recursive `grep` searches rooted at `$HOME`; inspect only named,
bounded paths required by the task.
