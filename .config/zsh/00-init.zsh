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
setopt HIST_FCNTL_LOCK
setopt EXTENDED_HISTORY


# The next line updates PATH for the Google Cloud SDK.
if [ -f '/opt/google-cloud-sdk/path.zsh.inc' ]; then . '/opt/google-cloud-sdk/path.zsh.inc'; fi

# The next line enables shell command completion for gcloud.
if [ -f '/opt/google-cloud-sdk/completion.zsh.inc' ]; then . '/opt/google-cloud-sdk/completion.zsh.inc'; fi

# prepend local binaries if needed
. "$HOME/.local/bin/env"
