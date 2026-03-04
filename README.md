# Dotfiles configuration

See [The best way to store your dotfiles: A bare Git repository](https://www.ackama.com/articles/the-best-way-to-store-your-dotfiles-a-bare-git-repository-explained/)

# Initialize the repository

```zsh
git init --bare $HOME/.dotfiles
alias config='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
echo "alias config='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'" >> ~/.config/zsh/20-aliases.zsh
config config --local status.showUntrackedFiles no
config remote add origin git@github.com:kpiwko/dotfiles.git
config fetch origin
```

Install the repository on a different machine

```zsh
cd $HOME
echo ".dotfiles" >> .gitignore
git clone --bare git@github.com:kpiwko/dotfiles.git $HOME/.dotfiles
alias config='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
config config --local status.showUntrackedFiles no
config checkout
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
