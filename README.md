# Dotfiles configuration

See [The best way to store your dotfiles: A bare Git repository](https://www.ackama.com/articles/the-best-way-to-store-your-dotfiles-a-bare-git-repository-explained/)

# Initialize the repository

```zsh
git init --bare "$HOME/.dotfiles"
alias config='/usr/bin/git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
config remote add origin git@github.com:kpiwko/dotfiles.git
config fetch origin
config branch --set-upstream-to=origin/main main
config config --local status.showUntrackedFiles no
```

Install the repository on a different machine

```zsh
cd $HOME
echo ".dotfiles" >> .gitignore
git clone --bare git@github.com:kpiwko/dotfiles.git "$HOME/.dotfiles"
alias config='/usr/bin/git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
config config --local status.showUntrackedFiles no
config checkout
```

# Machine-specific git config

Machine-specific settings (e.g. CodeRabbit machineId) go in `~/.gitconfig.local`,
which is included via `[include] path = ~/.gitconfig.local` but not tracked in this repo.

Create it on each machine as needed:

```zsh
cat > ~/.gitconfig.local << 'EOF'
[coderabbit]
	machineId = cli/<your-machine-id>
EOF
```

# Working with Brew

You can create a snapshot of currently installed Brew dependiencies by:

```zsh
brew bundle dump --force --file=~/.config/Brewfile
```

You can restore on a different machine:

```zsh
brew bundle --file=~/.config/Brewfile
```
