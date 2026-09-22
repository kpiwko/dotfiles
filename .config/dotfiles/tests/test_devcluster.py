from __future__ import annotations

import stat
import shutil
import sys
from pathlib import Path

import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("devcluster")
SCRIPT = BIN / "devcluster"


def make_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\nset -eu\n" + body)
    path.chmod(0o755)


@pytest.fixture
def devcluster_env(tmp_path: Path, clean_env: dict[str, str]) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    home.mkdir()
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    lima_config = tmp_path / "devcluster.yaml"
    lima_config.write_text("cpus: 4\n")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    roles = tmp_path / "roles"
    state = tmp_path / "lima-state"
    log = tmp_path / "commands.log"

    make_executable(
        stubs / "dotfiles-role",
        f'[ "$1" = has ] && [ "$2" = cluster ] && grep -qx cluster "{roles}" 2>/dev/null\n',
    )
    make_executable(
        stubs / "limactl",
        "state=${LIMA_STATE:?}\n"
        "log=${LIMA_LOG:?}\n"
        "case \"$1\" in\n"
        "  list)\n"
        "    if [ \"${2:-}\" = --format ]; then\n"
        "      [ -f \"$state\" ] || exit 0\n"
        "      case \"$3\" in '{{.Name}}') printf '%s\\n' devcluster ;; '{{.Status}}') cat \"$state\" ;; esac\n"
        "    elif [ \"${3:-}\" = --format ]; then\n"
        "      [ -f \"$state\" ] || exit 0\n"
        "      case \"$4\" in '{{.Name}}') printf '%s\\n' devcluster ;; '{{.Status}}') cat \"$state\" ;; esac\n"
        "    elif [ -f \"$state\" ]; then printf 'devcluster %s\\n' \"$(cat \"$state\")\"; fi\n"
        "    ;;\n"
        "  start)\n"
        "    printf 'limactl %s\\n' \"$*\" >>\"$log\"\n"
        "    printf '%s\\n' Running >\"$state\"\n"
        "    ;;\n"
        "  shell)\n"
        "    printf 'limactl %s\\n' \"$*\" >>\"$log\"\n"
        "    case \"$*\" in\n"
        "      *'cat /etc/rancher/k3s/k3s.yaml'*)\n"
        "        [ \"${K3S_KUBECONFIG_READY:-1}\" = 1 ] || exit 1\n"
        "        printf '%s\\n' 'apiVersion: v1' 'clusters:' '  - cluster:' \"      server: ${K3S_SERVER_URL:-https://127.0.0.1:6443}\" 'contexts:' '  - name: default' 'current-context: default'\n"
        "        ;;\n"
        "      *) [ -f \"$state\" ] && [ \"$(cat \"$state\")\" = Running ] ;;\n"
        "    esac\n"
        "    ;;\n"
        "  stop) printf 'limactl %s\\n' \"$*\" >>\"$log\"; printf '%s\\n' Stopped >\"$state\" ;;\n"
        "  delete) printf 'limactl %s\\n' \"$*\" >>\"$log\"; rm -f \"$state\" ;;\n"
        "esac\n",
    )
    make_executable(
        stubs / "kubectl",
        'printf "kubectl %s\\n" "$*" >>"$LIMA_LOG"\n',
    )
    make_executable(
        stubs / "devcluster-kubectl",
        'printf "devcluster-kubectl %s\\n" "$*" >>"$LIMA_LOG"\n'
        'if [ "${1:-}" = create ]; then printf "%s\\n" "kind: Secret"; fi\n'
        'if [ "${1:-}" = apply ] && [ "${2:-}" = -f ]; then cat; fi\n',
    )
    env = clean_env | {
        "HOME": str(home),
        "K8S_DIR": str(k8s),
        "DEVCLUSTER_LIMA_CONFIG": str(lima_config),
        "DOTFILES_ROLES_FILE": str(roles),
        "LIMA_STATE": str(state),
        "LIMA_LOG": str(log),
        "PATH": f"{stubs}:{clean_env['PATH']}",
    }
    return env, tmp_path


def command_log(root: Path) -> str:
    log = root / "commands.log"
    return log.read_text() if log.exists() else ""


def kubeconfig_path(env: dict[str, str]) -> Path:
    return Path(env["HOME"]) / ".kube" / "opencode-devcluster"


def enable_cluster(env: dict[str, str]) -> None:
    Path(env["DOTFILES_ROLES_FILE"]).write_text("cluster\n")


def test_usage_without_command(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    result = run_script(SCRIPT, env=env)
    assert result.returncode == 1
    assert "Commands:" in result.stderr


def test_create_requires_cluster_role(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 1
    assert "cluster role not enabled" in result.stderr


def test_create_requires_limactl(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    stubs = root / "stubs"
    (stubs / "limactl").unlink()
    make_executable(stubs / "python3", f'exec "{sys.executable}" "$@"\n')
    grep = shutil.which("grep")
    assert grep is not None
    make_executable(stubs / "grep", f'exec "{grep}" "$@"\n')
    env["PATH"] = str(stubs)
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 1
    assert "limactl not found" in result.stderr
    assert "brew install lima" in result.stderr


def test_create_creates_vm_waits_for_k3s_and_exports_kubeconfig(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 0, result.stderr
    log = command_log(root)
    assert "limactl start --name devcluster --cpus 4 --memory 8 --disk 100" in log
    assert "limactl shell devcluster sudo systemctl is-active --quiet k3s" in log
    assert "limactl shell devcluster sudo cat /etc/rancher/k3s/k3s.yaml" in log
    assert "config rename-context default devcluster" in log
    assert "config use-context devcluster" in log
    assert "127.0.0.1:17964" in kubeconfig_path(env).read_text()
    assert stat.S_IMODE(kubeconfig_path(env).stat().st_mode) == 0o600
    assert "context: devcluster" in result.stdout


def test_create_uses_first_creation_sizing_overrides(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    env |= {
        "DEVCLUSTER_CPUS": "10",
        "DEVCLUSTER_MEMORY_GIB": "24",
        "DEVCLUSTER_DISK_GIB": "150",
    }
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 0, result.stderr
    assert "limactl start --name devcluster --cpus 10 --memory 24 --disk 150" in command_log(root)


@pytest.mark.parametrize("server_url", ["https://0.0.0.0:6443", "https://localhost:6443", "https://192.168.5.15:6443"])
def test_create_rewrites_any_k3s_api_endpoint(
    devcluster_env: tuple[dict[str, str], Path], server_url: str
) -> None:
    env, _ = devcluster_env
    enable_cluster(env)
    env["K3S_SERVER_URL"] = server_url
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 0, result.stderr
    assert "server: https://127.0.0.1:17964" in kubeconfig_path(env).read_text()


def test_create_waits_for_kubeconfig_server_entry(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    enable_cluster(env)
    env["K3S_KUBECONFIG_READY"] = "0"
    env["DEVCLUSTER_K3S_WAIT_SECONDS"] = "0"
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 1
    assert "k3s kubeconfig did not become ready within 0s" in result.stderr


def test_create_is_idempotent_for_running_vm(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    Path(env["LIMA_STATE"]).write_text("Running\n")
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 0, result.stderr
    assert "limactl start" not in command_log(root)


def test_create_requires_lima_configuration(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    Path(env["DEVCLUSTER_LIMA_CONFIG"]).unlink()
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 1
    assert "Lima config not found" in result.stderr
    assert not (root / "lima-state").exists()


def test_up_starts_stopped_vm_and_provisions_workspace_secret(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    Path(env["LIMA_STATE"]).write_text("Stopped\n")
    result = run_script(SCRIPT, "up", env=env)
    assert result.returncode == 0, result.stderr
    log = command_log(root)
    assert "limactl start devcluster" in log
    assert "workspace-mcp-secrets" in log
    assert "apply -k" in log
    assert "ai-dev-secrets" not in log


def test_dotenv_is_fallback_for_workspace_oauth(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    (Path(env["K8S_DIR"]) / ".env").write_text("AI_DEV_GOOGLE_OAUTH_CLIENT_ID=from-file\n")
    result = run_script(SCRIPT, "up", env=env)
    assert result.returncode == 0, result.stderr
    assert "GOOGLE_OAUTH_CLIENT_ID=from-file" in command_log(root)


def test_status_reports_lima_k3s_nodes_and_pods(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    Path(env["LIMA_STATE"]).write_text("Running\n")
    kubeconfig_path(env).parent.mkdir()
    kubeconfig_path(env).write_text("apiVersion: v1\n")
    result = run_script(SCRIPT, "status", env=env)
    assert result.returncode == 0, result.stderr
    assert "=== Lima VM ===" in result.stdout
    assert "=== k3s service ===" in result.stdout
    assert "=== Cluster Nodes ===" in result.stdout
    assert "=== Pods (ai-dev namespace) ===" in result.stdout


def test_logs_delegates_pod_and_container(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    result = run_script(SCRIPT, "logs", "notebooklm-mcp-123", "notebooklm-mcp", env=env)
    assert result.returncode == 0, result.stderr
    assert "logs -n ai-dev notebooklm-mcp-123 -c notebooklm-mcp --tail=100 --follow" in command_log(root)


def test_logs_requires_a_pod_name(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    result = run_script(SCRIPT, "logs", env=env)
    assert result.returncode == 1
    assert "Usage: devcluster logs <pod> [container]" in result.stderr


def test_down_stops_vm_without_destroying_state(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    Path(env["LIMA_STATE"]).write_text("Running\n")
    result = run_script(SCRIPT, "down", env=env)
    assert result.returncode == 0, result.stderr
    assert Path(env["LIMA_STATE"]).read_text() == "Stopped\n"
    assert "limactl stop devcluster" in command_log(root)


def test_delete_deletes_vm_and_kubeconfig(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, root = devcluster_env
    enable_cluster(env)
    Path(env["LIMA_STATE"]).write_text("Running\n")
    kubeconfig_path(env).parent.mkdir()
    kubeconfig_path(env).write_text("apiVersion: v1\n")
    result = run_script(SCRIPT, "delete", env=env)
    assert result.returncode == 0, result.stderr
    assert not Path(env["LIMA_STATE"]).exists()
    assert not kubeconfig_path(env).exists()
    assert "limactl delete --force devcluster" in command_log(root)
