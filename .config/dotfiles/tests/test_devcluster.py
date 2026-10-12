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
    home = tmp_path / "home"
    credentials = home / ".config/opencode/itpc-ca-993e2467de-opencode-vertex.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"type":"service_account"}\n')
    kubectl_log = tmp_path / "kubectl.log"

    make_executable(
        stubs / "dotfiles-role",
        f'[ "$1" = has ] && [ "$2" = cluster ] && grep -qx cluster "{roles}" 2>/dev/null\n',
    )
    make_executable(
        stubs / "limactl",
        'echo "limactl $*"\n'
        'if [ "$1" = shell ]; then printf "apiVersion: v1\\ncurrent-context: default\\ncontexts:\\n- name: default\\n"; fi\n',
    )
    make_executable(
        stubs / "devcluster-kubectl",
        'printf "%s\\n" "$*" >> "$KUBECTL_LOG"\n'
        'if [ -n "${KUBECTL_FAIL_WAIT_JOB:-}" ]; then case " $* " in *" $KUBECTL_FAIL_WAIT_JOB "*) exit 1;; esac; fi\n'
        'if [ "$1" = get ] && [ "$2" = job ]; then\n'
        '  [ "${KUBECTL_EXISTING_JOB:-}" = "$3" ] || exit 1\n'
        '  case "$*" in *.status.active*) [ "${KUBECTL_JOB_STATUS:-}" = active ] && printf 1;; *.status.succeeded*) [ "${KUBECTL_JOB_STATUS:-}" = succeeded ] && printf 1;; *.status.failed*) [ "${KUBECTL_JOB_STATUS:-}" = failed ] && printf 1;; esac\n'
        '  exit 0\n'
        'fi\n'
        'if [ "$1" = logs ]; then printf "%s\\n" "${KUBECTL_JOB_LOG:-}"; fi\n'
        'if [ "$1" = create ]; then echo "kind: Secret"; fi\n'
        'if [ "$1" = apply ] && [ "$2" = -f ]; then cat; fi\n',
    )
    env = clean_env | {
        "HOME": str(home),
        "K8S_DIR": str(k8s),
        "DOTFILES_ROLES_FILE": str(roles),
        "DEVCLUSTER_KUBECONFIG": str(kubeconfig),
        "LIMA_CONFIG": str(tmp_path / "devcluster.yaml"),
        "GOOGLE_APPLICATION_CREDENTIALS": str(credentials),
        "KUBECTL_LOG": str(kubectl_log),
        "PATH": f"{stubs}:{clean_env['PATH']}",
    }
    kubeconfig.write_text("apiVersion: v1\n")
    return env, tmp_path


def ai_factory_inputs() -> dict[str, str]:
    return {
        "ENMAAS_KEY": "enmaas-secret",
        "ENMAAS_URL": "https://enmaas.example/v1",
        "OPENAI_API_KEY": "openai-secret",
        "VERTEX_PROJECT": "project",
        "VERTEX_LOCATION": "global",
        "AGENTGATEWAY_API_KEY": "agentgateway-secret",
        "MLFLOW_EXPERIMENT_ID": "42",
    }


def kubectl_commands(env: dict[str, str]) -> list[str]:
    return Path(env["KUBECTL_LOG"]).read_text().splitlines()


def command_index(commands: list[str], needle: str) -> int:
    return next(index for index, command in enumerate(commands) if needle in command)


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


def test_create_uses_lima_config(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    Path(env["DOTFILES_ROLES_FILE"]).write_text("cluster\n")
    config = Path(env["LIMA_CONFIG"])
    config.write_text("vmType: vz\n")
    result = run_script(SCRIPT, "create", env=env)
    assert result.returncode == 0, result.stderr
    assert f"start --name devcluster {config}" in result.stdout


def test_up_sequences_safe_lifecycle_and_secrets_after_runtime(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    result = run_script(SCRIPT, "up", env=env | ai_factory_inputs())
    assert result.returncode == 0, result.stderr
    commands = kubectl_commands(env)

    namespace = command_index(commands, "create namespace ai-dev")
    workspace_secret = command_index(commands, "create secret generic workspace-mcp-secrets")
    safe_base = command_index(commands, f"apply -k {env['K8S_DIR']}")
    writer_check = command_index(commands, "wait --for=delete pod -n ai-dev -l app=mlflow")
    migration_apply = command_index(commands, f"apply -k {env['K8S_DIR']}/migration")
    migration_complete = command_index(commands, "wait --for=condition=complete job/mlflow-db-migrate")
    migration_delete = command_index(commands, "wait --for=delete job/mlflow-db-migrate")
    runtime_apply = command_index(commands, f"apply -k {env['K8S_DIR']}/runtime")
    mlflow_ready = command_index(commands, "rollout status deployment/mlflow")
    otel_ready = command_index(commands, "rollout status deployment/otel-collector")
    agentgateway_secret = command_index(commands, "create secret generic agentgateway-secrets")
    agentgateway_ready = command_index(commands, "rollout status deployment/agentgateway")
    assert namespace < workspace_secret < safe_base < writer_check < migration_apply
    assert migration_apply < migration_complete < migration_delete < runtime_apply
    assert migration_apply < migration_complete < migration_delete < agentgateway_secret < runtime_apply
    assert runtime_apply < mlflow_ready < otel_ready < agentgateway_ready
    assert "--from-file=vertex-credentials.json=" in commands[agentgateway_secret]
    assert "AGENTGATEWAY_API_KEY=agentgateway-secret" in commands[agentgateway_secret]
    assert "MLFLOW_EXPERIMENT_ID=42" in commands[agentgateway_secret]
    assert "enmaas-secret" not in result.stdout + result.stderr
    assert str(Path(env["GOOGLE_APPLICATION_CREDENTIALS"])) not in result.stdout + result.stderr


def test_migration_failure_stops_runtime_and_gateway(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    env = env | ai_factory_inputs() | {"KUBECTL_FAIL_WAIT_JOB": "job/mlflow-db-migrate"}
    result = run_script(SCRIPT, "up", env=env)
    assert result.returncode != 0
    commands = kubectl_commands(env)
    assert any("describe job mlflow-db-migrate" in command for command in commands)
    assert not any(f"apply -k {env['K8S_DIR']}/runtime" in command for command in commands)
    assert not any("agentgateway-secrets" in command for command in commands)


def test_terminal_migration_job_is_removed_before_a_fresh_retry(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    result = run_script(
        SCRIPT,
        "up",
        env=env | ai_factory_inputs() | {"KUBECTL_EXISTING_JOB": "mlflow-db-migrate", "KUBECTL_JOB_STATUS": "succeeded"},
    )
    assert result.returncode == 0, result.stderr
    commands = kubectl_commands(env)
    delete = command_index(commands, "delete job mlflow-db-migrate")
    fresh_apply = command_index(commands, f"apply -k {env['K8S_DIR']}/migration")
    assert delete < fresh_apply


def test_active_job_is_not_replaced(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    result = run_script(
        SCRIPT,
        "up",
        env=env | ai_factory_inputs() | {"KUBECTL_EXISTING_JOB": "mlflow-db-migrate", "KUBECTL_JOB_STATUS": "active"},
    )
    assert result.returncode != 0
    assert "is active; refusing to replace it" in result.stderr
    commands = kubectl_commands(env)
    assert not any("delete job mlflow-db-migrate" in command for command in commands)
    assert not any(f"apply -k {env['K8S_DIR']}/migration" in command for command in commands)


def test_failed_job_diagnostics_redact_shell_yaml_and_vertex_json(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    sensitive_log = "\n".join(
        [
            "export ENMAAS_KEY=enmaas-secret",
            '"api_key": "openai-secret"',
                "AGENTGATEWAY_API_KEY: 'gateway-token'",
            '{"type":"service_account","private_key":"vertex-private","private_key_id":"vertex-id","client_email":"svc@example.test"}',
        ]
    )
    result = run_script(
        SCRIPT,
        "up",
        env=env
        | ai_factory_inputs()
        | {
            "KUBECTL_EXISTING_JOB": "mlflow-db-migrate",
            "KUBECTL_JOB_STATUS": "failed",
            "KUBECTL_JOB_LOG": sensitive_log,
        },
    )
    assert result.returncode == 0, result.stderr
    for value in ("enmaas-secret", "openai-secret", "gateway-token", "vertex-private", "vertex-id", "svc@example.test"):
        assert value not in result.stderr
    assert result.stderr.count("[REDACTED]") >= 6


def test_missing_provider_input_blocks_only_gateway_phase(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    inputs = ai_factory_inputs()
    inputs.pop("OPENAI_API_KEY")
    result = run_script(SCRIPT, "up", env=env | inputs)
    assert result.returncode != 0
    commands = kubectl_commands(env)
    assert any("job/mlflow-db-migrate" in command for command in commands)
    assert not any(f"apply -k {env['K8S_DIR']}/runtime" in command for command in commands)
    assert not any("create secret generic agentgateway-secrets" in command for command in commands)


def test_vertex_source_must_be_the_configured_exact_filename(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, tmp_path = devcluster_env
    wrong_source = tmp_path / "other.json"
    wrong_source.write_text("{}")
    result = run_script(
        SCRIPT,
        "up",
        env=env | ai_factory_inputs() | {"GOOGLE_APPLICATION_CREDENTIALS": str(wrong_source)},
    )
    assert result.returncode != 0
    assert "configured Vertex credentials source is invalid" in result.stderr
    assert str(wrong_source) not in result.stderr
    commands = kubectl_commands(env)
    assert not any("ai-factory-secrets" in command for command in commands)


def test_dotenv_is_fallback_and_shell_value_wins(devcluster_env: tuple[dict[str, str], Path]) -> None:
    env, _ = devcluster_env
    (Path(env["K8S_DIR"]) / ".env").write_text(
        "ENMAAS_KEY=from-file\nENMAAS_URL=https://file.example\nOPENAI_API_KEY=file-openai\nAGENTGATEWAY_API_KEY=file-gateway\n"
        "VERTEX_PROJECT=file-project\nVERTEX_LOCATION=file-location\nAI_DEV_GOOGLE_OAUTH_CLIENT_ID=from-file\n"
    )
    result = run_script(SCRIPT, "up", env=env | ai_factory_inputs() | {"ENMAAS_KEY": "from-shell"})
    assert result.returncode == 0, result.stderr
    commands = kubectl_commands(env)
    workspace = next(command for command in commands if "workspace-mcp-secrets" in command)
    secret = next(command for command in commands if "agentgateway-secrets" in command)
    assert "GOOGLE_OAUTH_CLIENT_ID=from-file" in workspace
    assert "ENMAAS_KEY=from-shell" in secret


def test_agentgateway_key_is_created_from_the_required_input(
    devcluster_env: tuple[dict[str, str], Path],
) -> None:
    env, _ = devcluster_env
    result = run_script(SCRIPT, "up", env=env | ai_factory_inputs() | {"AGENTGATEWAY_API_KEY": "token"})
    assert result.returncode == 0, result.stderr
    secret = next(command for command in kubectl_commands(env) if "agentgateway-secrets" in command)
    assert "AGENTGATEWAY_API_KEY=token" in secret


def test_up_uses_only_cluster_native_lifecycle_operations() -> None:
    script = SCRIPT.read_text()
    assert "devcluster-kubectl" in script
    assert " kubectl" not in script
    assert " scale " not in script
    assert "mlflow-gateway-sync" not in script
    assert "mlflow db" not in script
    assert "uv " not in script
