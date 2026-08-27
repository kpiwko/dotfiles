# Dotfiles configuration

See [The best way to store your dotfiles: A bare Git repository](https://www.ackama.com/articles/the-best-way-to-store-your-dotfiles-a-bare-git-repository-explained/)

# Initialize the repository

```zsh
git init --bare "$HOME/.dotfiles"
alias dotfiles-git='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
dotfiles-git remote add origin git@github.com:kpiwko/dotfiles.git
dotfiles-git fetch origin
dotfiles-git branch --set-upstream-to=origin/main main
dotfiles-git config --local status.showUntrackedFiles no
```

Install the repository on a different machine:

```zsh
cd $HOME
echo ".dotfiles" >> .gitignore
git clone --bare git@github.com:kpiwko/dotfiles.git "$HOME/.dotfiles"
alias dotfiles-git='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
dotfiles-git config --local status.showUntrackedFiles no
dotfiles-git checkout
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

You can create a snapshot of currently installed Brew dependencies by:

```zsh
brew bundle dump --force --file=~/.config/Brewfile
```

You can restore on a different machine:

```zsh
brew bundle --file=~/.config/Brewfile
```

# Host roles

Every machine gets the same base configuration checked out above — there is
no per-machine variant of the shell/git/editor config. On top of that base,
a machine can opt into additional, non-exclusive **roles** that install
extra software and services. Today there are two roles: `ai-server` and `cluster`.

Manage roles with the `dotfiles-role` helper (installed to `~/.local/bin`,
already on `PATH` once this repo is checked out):

```zsh
dotfiles-role enable cluster      # enable Kubernetes cluster role
dotfiles-role enable ai-server    # turn a role on for this machine
dotfiles-role disable ai-server   # turn it back off
dotfiles-role list                # show roles enabled on this machine
dotfiles-role has ai-server       # exit 0/1, used by install scripts
dotfiles-role has cluster         # check if cluster role is enabled
```

Role state lives in `~/.config/dotfiles/roles`, an untracked, per-machine
file (never committed — see [Local secrets](#local-secrets)).

# OpenCode & AI Agent Configuration

OpenCode configuration is stored under `~/.config/opencode/`.

- **Configuration:** `~/.config/opencode/opencode.jsonc`
- **Markdown Agents:** `~/.config/opencode/agents/`
  - `orchestrator.md`: User-facing primary agent (Gemini Flash), orchestrating task delegation.
  - `implement.md`: Default implementation specialist (Qwen3 Coder Next, thinking disabled).
  - `implement-deep.md`: Stronger local implementation fallback (Qwen3.8 27B, thinking disabled).
  - `plan.md`: Planning specialist for complex sequencing/multi-component tasks.
  - `architect.md`: Architecture specialist that persists durable decisions in ADR directories under `docs/`.
  - `review.md`: Read-only reviewer leveraging Qodo.
- **Implementation skills:** `~/.config/opencode/skills/`
  - `init-change`: selects normal vs dotfiles Git, synchronizes the intended base, and establishes a feature branch.
  - `publish-change`: creates logical commits and publishes validated work while treating push and PR/MR target remotes independently.
- **Sandbox commands:** constrained wrappers such as `sandbox-find` and `sandbox-git-push` reduce the operations available to implementation agents. `sandbox-git-push` permits ordinary feature-branch pushes to `origin` while refusing significant branches, detached HEAD, mismatched tracking, and force-push behavior.
- **Architecture Decision Records (ADRs):** Template at `~/.config/opencode/ADR-TEMPLATE.md`.

# AI server: Caddy

The `ai-server` role installs [Caddy](https://caddyserver.com) as a reverse
proxy in front of local AI services, built with `xcaddy` to include the
[Cloudflare DNS](https://github.com/caddy-dns/cloudflare) module for DNS-01
ACME challenges.

## Architecture

- Source of truth lives in this repo under `.config/caddy/` (`Caddyfile`,
  `sites/`, `snippets/`, `env/cloudflare.env.example`, the `caddy-start`
  wrapper, and the `local.caddy.plist` LaunchDaemon template).
- `dotfiles-caddy-install` deploys **copies** of these into system paths
  (`/usr/local/etc/caddy`, `/usr/local/libexec`, `/Library/LaunchDaemons`) —
  deliberately not symlinks, since those paths are read/executed by a
  `root` LaunchDaemon. A symlink back into your user-writable checkout would
  let your regular user account rewrite what root runs, without `sudo`.
- The root `Caddyfile` only holds global options and `import`s — actual
  site definitions live one-per-file under `sites/`.
- The Cloudflare API token is never in the plist. `caddy-start` sources it
  from `/usr/local/etc/caddy/env/cloudflare.env` into its own process
  environment right before `exec`ing `caddy run`.

## Installation

```zsh
dotfiles-role enable ai-server
dotfiles-caddy-install
```

This is idempotent — rerunning it is the normal way to pick up config
changes (see Upgrades below). It refuses to run if the `ai-server` role
isn't enabled.

On first run against a machine that doesn't already have Caddy configured,
it creates `/usr/local/etc/caddy/env/cloudflare.env` from
`env/cloudflare.env.example` and stops — edit that file with a real
`CF_API_TOKEN` (a Cloudflare API token scoped to `Zone:DNS:Edit` for the
zone(s) your sites use), then rerun `dotfiles-caddy-install`. If the file
already exists (e.g. this machine already had Caddy running before this
repo managed it), it's left untouched.

## Bootstrap

On a brand-new AI server: clone this repo per the top-level install instructions, run `brew bundle --file=~/.config/Brewfile`, then follow Installation above.

## Upgrades

Edit `.config/caddy/Caddyfile`, `sites/*.caddy`, or `snippets/*.caddy` in
this repo, commit as usual, then rerun `dotfiles-caddy-install`. It
validates the new config with `caddy validate` before reloading the running
daemon, so a bad edit won't take down the running service.

To change the pinned Caddy version or add another `xcaddy` module, edit the
`CADDY_VERSION` default (and the `--with` flags) at the top of
`.local/bin/dotfiles-caddy-install`, then rerun it.

## Logs

`/var/log/caddy/caddy.log` (stdout) and `/var/log/caddy/caddy-error.log`
(stderr). Tail it with `tail -f /var/log/caddy/caddy.log`.

## Troubleshooting

- `caddy validate --config /usr/local/etc/caddy/Caddyfile --adapter caddyfile`
  — check the deployed config directly.
- `sudo launchctl print system/local.caddy` — confirm the daemon is loaded and see its last exit status.
- `sudo launchctl kickstart -k system/local.caddy` — force a clean restart.

## Certificates

Certificates are obtained automatically via ACME DNS-01 challenges against Cloudflare, so ports 80/443 don't need to be reachable from the internet for issuance. Caddy's certificate/state storage lives under `/var/lib/caddy` (the `XDG_DATA_HOME` set in the plist) — `dotfiles-caddy-uninstall` never touches this directory, so disabling and re-enabling the role doesn't force reissuance.

## Local secrets

Two flavors of "never commit this" exist in this repo:

- `~/.gitconfig.local` and `~/.config/dotfiles/roles` — untracked files under `$HOME`, protected by a `.gitignore` in their directory as a safety net against accidental `git add`.
- `/usr/local/etc/caddy/env/cloudflare.env` — lives entirely outside `$HOME` (and therefore outside this repo's work-tree), so it can never be tracked by construction. Only `env/cloudflare.env.example` is committed.

## Adding another Caddy site

1. Add a new file under `.config/caddy/sites/`, e.g. `sites/notes.caddy`.
2. Commit it like any other dotfiles change.
3. Rerun `dotfiles-caddy-install` on the AI server — it syncs `sites/` with `rsync --delete`, validates, and reloads.

# Kubernetes (Kind) Cluster Role

The `cluster` role sets up a local Kubernetes development environment using
[Kind](https://kind.sigs.k8s.io/) (Kubernetes in Docker) with Podman as the
container runtime.

## Architecture

- Source of truth lives in this repo under `.config/k8s/` (Kustomize manifests for all services).
- `dotfiles-cluster` CLI manages the cluster lifecycle: create, up, status, logs, down, delete.

## Services

The cluster includes:
- **Langfuse** - Observation & analytics (Web UI + Worker)
- **PostgreSQL** - Primary database (v16)
- **ClickHouse** - Analytics database (v24.3)
- **Redis** - Caching layer (v7)
- **MinIO** - Object storage
- **MCP Servers** - Model Context Protocol (Context7, Atlassian)

## Installation

```zsh
dotfiles-role enable cluster
dotfiles-cluster create          # Create Kind cluster
dotfiles-cluster up              # Deploy kustomize manifests
dotfiles-cluster status          # Check cluster status
```

Or use Make:
```zsh
make cluster-create
make cluster-up
make cluster-status
```

## Port Mapping

| Container Port | Host Port | Service |
|----------------|-----------|---------|
| 80 | 17988 | Ingress HTTP |
| 443 | 17943 | Ingress HTTPS |
| 3000 | 17900 | Langfuse Web |
| 9001 | 17901 | MinIO Console |
| 8080 | 17980 | MCP Context7 |
| 8081 | 17981 | MCP Atlassian |
| 6443 | 17964 | Kubernetes API |

## Documentation

See the full Kubernetes stack documentation at:
`~/.config/k8s/README.md`
