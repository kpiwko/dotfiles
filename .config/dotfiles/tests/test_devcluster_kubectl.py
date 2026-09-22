from __future__ import annotations

from pathlib import Path

import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("devcluster-kubectl")
SCRIPT = BIN / "devcluster-kubectl"


def make_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\nset -eu\n" + body)
    path.chmod(0o755)


@pytest.fixture
def kubectl_env(tmp_path: Path, clean_env: dict[str, str]) -> tuple[dict[str, str], Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    log = tmp_path / "kubectl.log"
    make_executable(stubs / "kubectl", 'printf "kubectl %s\\n" "$*" >>"$KUBECTL_LOG"\n')
    env = clean_env | {
        "HOME": str(home),
        "KUBECTL_LOG": str(log),
        "PATH": f"{stubs}:{clean_env['PATH']}",
    }
    return env, home / ".kube" / "opencode-devcluster", log


@pytest.mark.parametrize(
    "argument",
    ["--kubeconfig", "--kubeconfig=/tmp/other-kubeconfig", "--context", "--context=other"],
)
def test_rejects_kubeconfig_and_context_overrides(
    kubectl_env: tuple[dict[str, str], Path, Path], argument: str
) -> None:
    env, kubeconfig, _ = kubectl_env
    kubeconfig.parent.mkdir()
    kubeconfig.write_text("apiVersion: v1\n")

    result = run_script(SCRIPT, argument, env=env)

    assert result.returncode == 1
    assert "overriding kubeconfig or context is not allowed" in result.stderr


def test_fails_when_kubeconfig_does_not_exist(
    kubectl_env: tuple[dict[str, str], Path, Path],
) -> None:
    env, kubeconfig, _ = kubectl_env

    result = run_script(SCRIPT, "get", "nodes", env=env)

    assert result.returncode == 1
    assert f"kubeconfig not found: {kubeconfig}" in result.stderr


def test_executes_kubectl_with_devcluster_configuration(
    kubectl_env: tuple[dict[str, str], Path, Path],
) -> None:
    env, kubeconfig, log = kubectl_env
    kubeconfig.parent.mkdir()
    kubeconfig.write_text("apiVersion: v1\n")

    result = run_script(SCRIPT, "get", "pods", "-n", "ai-dev", env=env)

    assert result.returncode == 0, result.stderr
    assert log.read_text() == (
        f"kubectl --kubeconfig={kubeconfig} --context=devcluster get pods -n ai-dev\n"
    )
