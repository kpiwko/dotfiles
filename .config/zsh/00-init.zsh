# ----- History -----
HISTFILE=~/.zsh_history
HISTSIZE=50000
SAVEHIST=50000

setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_FIND_NO_DUPS
setopt HIST_REDUCE_BLANKS
setopt SHARE_HISTORY
setopt EXTENDED_HISTORY
setopt INC_APPEND_HISTORY

# ----- Completion -----
autoload -Uz compinit
compinit

autoload -Uz bashcompinit
bashcompinit

# ----- Word behavior -----
autoload -Uz select-word-style
select-word-style bash

# ----- Keybindings -----
bindkey -e

bindkey "^[f" forward-word
bindkey "^[b" backward-word
bindkey "^[^?" backward-kill-word

bindkey "^[[A" history-search-backward
bindkey "^[[B" history-search-forward

bindkey "^A" beginning-of-line
bindkey "^E" end-of-line
bindkey "^W" backward-kill-word
bindkey "^U" backward-kill-line
bindkey "^K" kill-line
bindkey "^R" history-incremental-search-backward

# ----- Tool init -----
export STARSHIP_CONFIG=~/.config/starship.toml
eval "$(starship init zsh)"

eval "$(uv --generate-shell-completion zsh)"
eval "$(mise activate zsh)"

# Google Cloud SDK
if [ -f "/opt/google-cloud-sdk/path.zsh.inc" ]; then
  . "/opt/google-cloud-sdk/path.zsh.inc"
fi

if [ -f "/opt/google-cloud-sdk/completion.zsh.inc" ]; then
  . "/opt/google-cloud-sdk/completion.zsh.inc"
fi

# Local binaries
[ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
