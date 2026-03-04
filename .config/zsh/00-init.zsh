# Additional instructions for zsh and keyboard navigation
# ----- Better word behavior -----
autoload -U select-word-style
select-word-style bash

# Option + Arrow = move by word
bindkey "^[f" forward-word
bindkey "^[b" backward-word

# Option + Backspace = delete word
bindkey "^[^?" backward-kill-word

# ----- Arrow key fixes (Shift + arrows etc.) -----
bindkey "^[[1;2C" forward-char
bindkey "^[[1;2D" backward-char
bindkey "^[[1;2A" up-line-or-history
bindkey "^[[1;2B" down-line-or-history

# ----- Better history search -----
bindkey "^[[A" history-search-backward
bindkey "^[[B" history-search-forward

# ----- Useful editing shortcuts -----
bindkey "^A" beginning-of-line
bindkey "^E" end-of-line
bindkey "^W" backward-kill-word
bindkey "^U" backward-kill-line
bindkey "^K" kill-line

# Additional instructions needed for uv
autoload -U +X compinit && compinit
autoload -U +X bashcompinit && bashcompinit 


# Starship configuration
eval "$(starship init zsh)"
export STARSHIP_CONFIG=~/.config/starship.toml

# UV Configuration
eval "$(uv --generate-shell-completion zsh)"

# FNM configuration
eval "$(fnm env --use-on-cd --shell zsh)"

# history setup
# -------- History configuration --------
HISTSIZE=50000
SAVEHIST=50000
HISTFILE=~/.zsh_history

setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_FIND_NO_DUPS
setopt HIST_REDUCE_BLANKS
setopt SHARE_HISTORY
setopt EXTENDED_HISTORY


# The next line updates PATH for the Google Cloud SDK.
if [ -f '/opt/google-cloud-sdk/path.zsh.inc' ]; then . '/opt/google-cloud-sdk/path.zsh.inc'; fi

# The next line enables shell command completion for gcloud.
if [ -f '/opt/google-cloud-sdk/completion.zsh.inc' ]; then . '/opt/google-cloud-sdk/completion.zsh.inc'; fi

# prepend local binaries if needed
. "$HOME/.local/bin/env"
