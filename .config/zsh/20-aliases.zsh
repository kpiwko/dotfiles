alias ll='ls -la -h --color'
alias pass="gopass"
alias maskenv='env | sort | sed -E "/(KEY|TOKEN|PASSWORD|SECRET)/I s/^([^=]+)=([^=]{4,5}).*/\1=\2.../"'
alias vim="nvim"
alias sgit="sandbox-git"

# Zellij aliases
alias zc="zellij --layout claude"
alias zo="zellij --layout opencode"
alias zs="zellij --session"
alias za="zellij attach"

# enable MarkEdit from command line
markedit() {
  open -a MarkEdit "$@"
}





