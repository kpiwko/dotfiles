from __future__ import annotations

from pathlib import Path

import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("devcluster")
SCRIPT = BIN / "devcluster"


def make_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.fixture
def devcluster_env(tmp_path: Path, clean_env: dict[str, str]) -> tuple[dict[str, str], Path]:
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    roles = tmp_path / "roles"
    kubeconfig = tmp_path / "kubeconfig"

    make_executable(
        stubs / "dotfiles-role",
        f'[ "$1" = has ] && [ "$2" = cluster ] && grep -qx cluster "{roles}" 2>/dev/null\n',
    )
    make_executable(
        stubs / "kind",
        'echo "kind $*"\n'
        'if [ "$1" = export ]; then while [ "$#" -gt 0 ]; do if [ "$1" = --kubeconfig ]; then shift; mkdir -p "$(dirname "$1")"; touch "$1"; fi; shift; done; fi\n',
    )
    make_executable(
        stubs / "devcluster-kubectl",
        'echo "kubectl $*"\nif [ "$1" = create ]; then echo "kind: Secret"; fi\nif [ "$1" = apply ] && [ "$2" = -f ]; then cat >/dev/null; fi\n',
    )
    env = clean_env | {
        "K8S_DIR": str(k8s),
        "DOTFILES_ROLES_FILE": str(roles),
        "DEVCLUSTER_KUBECONFIG": str(kubeconfig),
        "PATH": f"{stubs}:{clean_env['PATH']}",
    }
    return env, tmp_path


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


def test_create_uses_kind_config(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = devcluster_env
    Path(env["DOTFILES_ROLES_FILE"]).write_text("cluster\n")
    config = Path(env["K8S_DIR"]) / "kind-config.yaml"
    config.write_text("kind: Cluster\n")
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 0, result.stderr
    assert f"create cluster --name kind-ai-dev --config {config}" in result.stdout
    assert Path(env["DEVCLUSTER_KUBECONFIG"]).exists()


def test_ai_dev_environment_has_highest_precedence(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    env.update({
        "POSTGRES_PASSWORD": "legacy",
        "DEVCLUSTER_POSTGRES_PASSWORD": "devcluster",
        "AI_DEV_POSTGRES_PASSWORD": "aidev",
    })
    result = run_script(SCRIPT, "up", env=env)
    assert result.returncode == 0, result.stderr
    assert "POSTGRES_PASSWORD=aidev" in result.stdout
    assert "DATABASE_URL=postgresql://langfuse:aidev@postgres:5432/langfuse" in result.stdout


def test_dotenv_is_fallback(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    (Path(env["K8S_DIR"]) / ".env").write_text("AI_DEV_POSTGRES_PASSWORD=from-file\n")
    result = run_script(SCRIPT, "up", env=env)
    assert result.returncode == 0, result.stderr
    assert "POSTGRES_PASSWORD=from-file" in result.stdout
