# Dotfiles configuration

See [The best way to store your dotfiles: A bare Git repository](https://www.ackama.com/articles/the-best-way-to-store-your-dotfiles-a-bare-git-repository-explained/)

# NotebookLM MCP Authentication Guide

NotebookLM uses session-based authentication rather than standard OAuth tokens. To authenticate:

1. Open the noVNC interface in your browser:
   `http://localhost:17982/vnc.html` (click **Connect**)
2. In your host terminal, run:
   ```bash
   devcluster-kubectl exec -it deployment/notebooklm-mcp -n ai-dev -- nlm login
   ```
3. In the Chromium window inside the noVNC browser tab, complete the Google login with your account.
4. Once logged in, session tokens are saved to the container volume and the MCP endpoint at `http://localhost:17980/mcp` is live.

# Initialize the repository

```zsh
git init --bare "$HOME/.dotfiles"
git --git-dir="$HOME/.dotfiles" --work-tree="$HOME" remote add origin git@github.com:kpiwko/dotfiles.git
git --git-dir="$HOME/.dotfiles" --work-tree="$HOME" fetch origin
git --git-dir="$HOME/.dotfiles" --work-tree="$HOME" branch --set-upstream-to=origin/main main
git --git-dir="$HOME/.dotfiles" --work-tree="$HOME" config --local status.showUntrackedFiles no
```

Install the repository on a different machine:

```zsh
cd $HOME
echo ".dotfiles" >> .gitignore
git clone --bare git@github.com:kpiwko/dotfiles.git "$HOME/.dotfiles"
git --git-dir="$HOME/.dotfiles" --work-tree="$HOME" config --local status.showUntrackedFiles no
git --git-dir="$HOME/.dotfiles" --work-tree="$HOME" checkout
```

After checkout, `sandbox-git` is the normal Git entry point for agents. From exactly `$HOME` it automatically uses `git --git-dir="$HOME/.dotfiles" --work-tree="$HOME"`; from other repositories it uses normal Git.

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
extra software and services. Available roles include:
- `dev`: Local development workstation (enables local Caddy reverse proxy, local TLS, developer tools).
- `ai-server`: Dedicated AI server (Caddy reverse proxy with Cloudflare DNS-01 TLS, local LLM/tracing backends).
- `cluster`: Local Kubernetes development environment (Lima, CentOS Stream 10,
  k3s, MLflow, and MCP servers).

Manage roles with the `dotfiles-role` helper (installed to `~/.local/bin`,
already on `PATH` once this repo is checked out):

```zsh
dotfiles-role enable dev          # enable local dev workstation role
dotfiles-role enable cluster      # enable Kubernetes cluster role
dotfiles-role enable ai-server    # enable AI server role
dotfiles-role disable ai-server   # turn a role off
dotfiles-role list                # show roles enabled on this machine
dotfiles-role has dev             # exit 0/1, check if role is enabled
dotfiles-role has ai-server       # exit 0/1, used by install scripts
dotfiles-role has cluster         # check if cluster role is enabled
```

Role state lives in `~/.config/dotfiles/roles`, an untracked, per-machine
file (never committed — see [Local secrets](#local-secrets)).

# OpenCode & AI Agent Configuration

OpenCode configuration is stored under `~/.config/opencode/`. See `~/.config/opencode/README.md` for provider, LiteMaaS, context-budget, and verification instructions.

- **Configuration:** `~/.config/opencode/opencode.jsonc`
- **Markdown Agents:** `~/.config/opencode/agents/`
  - `orchestrator.md`: user-facing primary agent and task router.
  - `implement-local.md`: default local oMLX implementation specialist.
  - `implement-maas.md`: explicitly selected LiteMaaS implementation specialist with matching capabilities.
  - `plan.md`: planning specialist for complex sequencing/multi-component tasks.
  - `architect.md`: architecture specialist that persists durable decisions in ADR directories under `docs/`.
  - `review.md`: read-only reviewer leveraging Qodo.
  - `zweistein.md`: explicitly selected premium autonomous engineering path.
- **Implementation skills:** `~/.config/opencode/skills/`
  - `init-change`: synchronizes the intended base and establishes a feature branch through `sandbox-git`.
  - `publish-change`: creates logical commits and publishes validated work through `sandbox-git` while treating push and PR/MR target remotes independently.
- **Sandbox commands:** `sandbox-find` and `sandbox-git` reduce the operations available to implementation agents. `sandbox-git` selects the bare `$HOME/.dotfiles` repository only when working from exactly `$HOME`; raw Git is denied to implementation agents and destructive Git forms require approval.
- **Architecture Decision Records (ADRs):** Template at `~/.config/opencode/ADR-TEMPLATE.md`.

# Reverse Proxy: Caddy

The `dev`, `cluster`, and `ai-server` roles support [Caddy](https://caddyserver.com) as a reverse
proxy for local services and development, built with `xcaddy` to include the
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
- Reusable snippets are provided in `snippets/`:
  - `snippets/local-tls.caddy` (`(local_tls)`): Internal TLS using Caddy's built-in root CA for local development (`tls internal`).
  - `snippets/cloudflare-tls.caddy` (`(cloudflare_tls)`): Cloudflare DNS-01 ACME challenge for public/internal domain resolution.
- Host-specific local site configs matching `*.local.caddy` (such as `sites/my-app.local.caddy`) are ignored in Git, allowing per-host site configuration without dirtying repository state.
- Fronting `devcluster` services: Caddy can reverse proxy local cluster services exposed via NodePort / HostPort, such as MLflow (`127.0.0.1:17902`), Workspace MCP (`127.0.0.1:17981`), NotebookLM MCP (`127.0.0.1:17980`), and NotebookLM noVNC (`127.0.0.1:17982`). See `sites/mlflow.caddy.example`, `sites/mcp.caddy.example`, and `sites/app.local.caddy`.
- **ACME Email Configuration**: Let's Encrypt notifications use the first defined in this hierarchy: `DNS_ACME_EMAIL` > `ACME_EMAIL` > `git config --get user.email`. Set `DNS_ACME_EMAIL` (or `ACME_EMAIL`) in your shell environment (e.g. `~/.config/zsh/10-env.zsh`). The `dotfiles-caddy-install` script warns if no email is configured.
- The Cloudflare API token is never in the plist. `caddy-start` sources it
  from `/usr/local/etc/caddy/env/cloudflare.env` into its own process
  environment right before `exec`ing `caddy run`.

## Installation

```zsh
dotfiles-role enable dev        # or: dotfiles-role enable cluster / dotfiles-role enable ai-server
dotfiles-caddy-install
```

This is idempotent — rerunning it is the normal way to pick up config
changes (see Upgrades below). It requires any of the `dev`, `cluster`, or `ai-server` roles
to be enabled.

On first run against a machine that doesn't already have Caddy configured,
it creates `/usr/local/etc/caddy/env/cloudflare.env` from
`env/cloudflare.env.example` and stops — edit that file with a real
`CF_API_TOKEN` (a Cloudflare API token scoped to `Zone:DNS:Edit` for the
zone(s) your sites use), then rerun `dotfiles-caddy-install`. If the file
already exists (e.g. this machine already had Caddy running before this
repo managed it), it's left untouched.

## Bootstrap

On a brand-new machine: clone this repo per the top-level install instructions, run `brew bundle --file=~/.config/Brewfile`, then follow Installation above.

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
- `sudo launchctl bootout system/local.caddy && sudo launchctl bootstrap system /Library/LaunchDaemons/local.caddy.plist` — force a clean restart (reloads plist if changed).

## Certificates

Certificates can be obtained via ACME DNS-01 challenges against Cloudflare (using `import cloudflare_tls`) or via internal TLS for local domains (using `import local_tls`). Caddy's certificate/state storage lives under `/var/lib/caddy` (the `XDG_DATA_HOME` set in the plist) — `dotfiles-caddy-uninstall` never touches this directory, so disabling and re-enabling the role doesn't force reissuance.

## Local secrets

Two flavors of "never commit this" exist in this repo:

- `~/.gitconfig.local` and `~/.config/dotfiles/roles` — untracked files under `$HOME`, protected by a `.gitignore` in their directory as a safety net against accidental `git add`.
- `/usr/local/etc/caddy/env/cloudflare.env` — lives entirely outside `$HOME` (and therefore outside this repo's work-tree), so it can never be tracked by construction. Only `env/cloudflare.env.example` is committed.

## Adding another Caddy site

1. Add a new file under `.config/caddy/sites/`, e.g. `sites/notes.caddy` or `sites/app.local.caddy`. See `sites/app.local.caddy` for a working example or rename one of the `.example` templates.
2. Templates ending in `.example` are not imported by the `import sites/*.caddy` directive — rename them to remove the `.example` suffix to enable.
3. Commit tracked site definitions as usual.
4. Rerun `dotfiles-caddy-install` — it syncs `sites/` with `rsync --delete`, validates, and reloads.

# Kubernetes (Lima + k3s) Cluster Role

The `cluster` role runs a dedicated, single-node Kubernetes VM rather than a
Kind cluster. The host architecture is:

```text
macOS -> Lima VM (devcluster) -> CentOS Stream 10 -> k3s -> embedded containerd
```

The repository-owned template is
`~/.config/lima/devcluster.yaml`. It extends Lima's official CentOS Stream 10
template, uses the native aarch64 image on Apple Silicon, and intentionally
disables Lima-managed containerd. Do not install Podman or another container
runtime in this VM: k3s manages its supported embedded containerd itself.

## Architecture

- Source of truth lives in this repo under `.config/k8s/` (Kustomize manifests
  for all services), and `.config/lima/devcluster.yaml` (the VM and k3s
  provisioning).
- `devcluster` manages VM and workload lifecycle: `create`, `up`, `status`,
  `logs`, `down`, and `delete`.
- k3s keeps CoreDNS and its `local-path` provisioner, and disables Traefik and
  ServiceLB because host Caddy reaches explicitly forwarded NodePorts.
- The host kubeconfig is always `~/.kube/opencode-devcluster` with context
  `devcluster`. Use `devcluster-kubectl` when you want a wrapper that refuses
  caller-selected kubeconfigs and contexts.

## Services

The cluster includes:
- **MLflow** - GenAI tracking server for OpenCode traces
- **MCP Servers** - Model Context Protocol (NotebookLM, Workspace)

## Secret Management & Google Workspace OAuth

- **Auto-Provisioning**: Running `devcluster up` provisions the `workspace-mcp-secrets` Kubernetes secret from the active shell environment.
- **Google Workspace OAuth**: To connect the `workspace-mcp` server:
  1. Create a GCP Project and enable APIs (Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Apps Script).
  2. Configure OAuth Consent Screen & Data Access scopes (Add or Remove Scopes).
  3. Create an OAuth 2.0 Web Application client with Authorized redirect URI: `http://localhost:17981/oauth2callback`.
  4. Export credentials in your shell (e.g. in `~/.config/zsh/10-env.zsh` or `secrets.zsh`):
     ```zsh
     export AI_DEV_GOOGLE_OAUTH_CLIENT_ID="<client-id>"
     export AI_DEV_GOOGLE_OAUTH_CLIENT_SECRET="<client-secret>"
     ```
  5. Run `devcluster up` to deploy and sync secrets.
  6. See `~/.config/k8s/README.md` for the full setup guide.

## Installation

```zsh
dotfiles-role enable cluster
devcluster create          # Create/start the Lima VM and export kubeconfig
devcluster up              # Deploy kustomize manifests
devcluster status          # Check cluster status
```

Or use Make:
```zsh
make cluster-create
make cluster-up
make cluster-status
```

## Port Mapping

Lima forwards the k3s API from guest `6443` to host `127.0.0.1:17964`, and
forwards the complete k3s NodePort range `17900-17999` one-to-one on host
loopback. Caddy examples already proxy to the stable host ports below; no VM IP
lookup or `kubectl port-forward` is needed for normal use.

| k3s Service Port | NodePort / Host Port | Service |
|------------------|----------------------|---------|
| 5000 | 17902 | MLflow |
| 17200 | 17980 | MCP NotebookLM |
| 6080 | 17982 | MCP NotebookLM noVNC |
| 8000 | 17981 | MCP Workspace |
| 6443 | 17964 | Kubernetes API |

Ports `17900`, `17901`, and the rest of `17900-17999` are reserved and
forwarded for additional local NodePort services. All forwards bind only to
`127.0.0.1`.

## Sizing and lifecycle

The template defaults to 8 CPUs, 16 GiB RAM, and 100 GiB disk—sized for the
Langfuse-style stateful stack (PostgreSQL, ClickHouse, Redis, MinIO) as well as
the current MLflow and MCP workloads. On the first `devcluster create`, these
can be overridden with `DEVCLUSTER_CPUS`, `DEVCLUSTER_MEMORY_GIB`, and
`DEVCLUSTER_DISK_GIB`. Lima stores CPU and memory choices with the VM, so use
`devcluster delete` and recreate to change them later (or manage an existing
VM with `limactl` deliberately).

- `devcluster create` is idempotent: it creates or starts the VM, waits for
  systemd-managed k3s, and rewrites the guest-only API endpoint to
  `127.0.0.1:17964` in the host kubeconfig.
- `devcluster up` performs the same readiness work, reconciles OAuth secrets,
  and applies Kustomize manifests.
- `devcluster down` stops the VM and preserves disks, k3s state, and PVCs.
- `devcluster delete` force-deletes the VM and removes only the generated host
  kubeconfig.

## Troubleshooting

```zsh
# VM state and k3s journal
limactl list devcluster
limactl shell devcluster sudo systemctl status k3s
limactl shell devcluster sudo journalctl -u k3s -b --no-pager

# Confirm SELinux stays enforcing, firewall rules, nodes, storage, and services
limactl shell devcluster getenforce
limactl shell devcluster sudo firewall-cmd --list-ports
devcluster-kubectl get nodes
devcluster-kubectl get storageclass
devcluster-kubectl get services -n ai-dev
```

## Documentation

See the full Kubernetes stack documentation at:
`~/.config/k8s/README.md`
