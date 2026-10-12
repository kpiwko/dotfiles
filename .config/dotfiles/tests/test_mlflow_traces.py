from __future__ import annotations

import ast
import os
import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("mlflow-traces")
SCRIPT = BIN / "mlflow-traces"


def _build_time_filter(session_id: str | None) -> str | None:
    tree = ast.parse(SCRIPT.read_text())
    namespace = {"__builtins__": __builtins__}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            alias.name == "mlflow" for alias in getattr(node, "names", [])
        ):
            continue
        if isinstance(node, ast.FunctionDef) and node.name == "build_time_filter":
            exec(compile(ast.Module(body=[node], type_ignores=[]), SCRIPT, "exec"), namespace)
            break
    return namespace["build_time_filter"](None, None, session_id)


def test_script_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_inline_mlflow_dependency_requires_v317() -> None:
    script = SCRIPT.read_text()

    assert '"mlflow>=3.17.0,<4",' in script
    assert "mlflow>=3.16" not in script


def test_help_lists_commands(clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert "usage: mlflow-traces" in result.stdout
    assert "trace" in result.stdout
    assert "experiment" in result.stdout


def test_experiment_help_lists_session_filter(clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, "experiment", "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert "--session" in result.stdout
    assert "--session-id" in result.stdout


def test_build_time_filter_includes_session() -> None:
    result = _build_time_filter("ses_ed02670c1ffefeAJhhWV1KVRZZ")

    assert result == (
        "metadata.`mlflow.trace.session` = "
        "'ses_ed02670c1ffefeAJhhWV1KVRZZ'"
    )


def test_build_time_filter_escapes_session_quote() -> None:
    result = _build_time_filter("ses_'quoted")

    assert result == "metadata.`mlflow.trace.session` = 'ses_\\'quoted'"


def test_requires_a_command(clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, env=clean_env)

    assert result.returncode == 2
    assert "the following arguments are required: COMMAND" in result.stderr


@pytest.mark.parametrize("command", ["trace", "experiment"])
def test_subcommand_help(command: str, clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, command, "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert f"usage: mlflow-traces {command}" in result.stdout
