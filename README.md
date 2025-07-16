See [The best way to store your dotfiles: A bare Git repository](https://www.ackama.com/articles/the-best-way-to-store-your-dotfiles-a-bare-git-repository-explained/)


```
git init --bare $HOME/.dotfiles
alias config='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
echo "alias config='/usr/bin/git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'" >> ~/.config/zsh/20-aliases.zsh
config config --local status.showUntrackedFiles no
config remote add origin git@github.com:kpiwko/dotfiles.git
config fetch origin
```
