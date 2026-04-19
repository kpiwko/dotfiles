alias ll='ls -la -h --color'
alias pass="gopass"
alias config='/usr/bin/git --git-dir=/Users/kpiwko/.dotfiles/ --work-tree=/Users/kpiwko'
alias maskenv='env | sort | sed -E "/(KEY|TOKEN|PASSWORD)/I s/^([^=]+)=([^=]{4,5}).*/\1=\2.../"'


claude-ccr() {
  (
    pgrep -f claude-code-router >/dev/null || ccr start >/dev/null 2>&1

    unset GOOGLE_API_KEY GEMINI_API_KEY GOOGLE_APPLICATION_CREDENTIALS
    unset GOOGLE_CLOUD_PROJECT VERTEXAI_PROJECT VERTEXAI_LOCATION
    unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY

    eval "$(ccr activate)"

    claude "$@"
  )
}
