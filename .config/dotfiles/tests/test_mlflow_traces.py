from __future__ import annotations

import ast
import json
import os
import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("mlflow-traces")
SCRIPT = BIN / "mlflow-traces"


def _load_helpers() -> dict:
    tree = ast.parse(SCRIPT.read_text())
    namespace = {"__builtins__": __builtins__, "json": json}
    wanted = {"normalize_dataset_value", "make_trace_dataset_compatible"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), SCRIPT, "exec"), namespace)
    return namespace


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


@pytest.mark.parametrize("command", ["trace", "experiment"])
def test_subcommand_help_lists_compat(command: str, clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, command, "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert "--compat" in result.stdout
    assert "https://github.com/mlflow/mlflow/issues/24709" in result.stdout


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


def test_normalize_dataset_value() -> None:
    normalize = _load_helpers()["normalize_dataset_value"]

    assert normalize({"x": 1}) == {"x": 1}
    assert normalize("hello") == {"input": "hello"}
    assert normalize('[1, 2]') == {"input": [1, 2]}
    assert normalize("out", "output") == {"output": "out"}


def test_make_trace_dataset_compatible_normalizes_values() -> None:
    adapt = _load_helpers()["make_trace_dataset_compatible"]
    trace = {
        "data": {
            "request": "request",
            "response": "response",
            "spans": [{
                "attributes": {
                    "mlflow.spanInputs": "input",
                    "input.value": json.dumps("value"),
                    "mlflow.spanOutputs": "output",
                    "output.value": json.dumps([1]),
                },
                "inputs": "direct",
                "outputs": {"output": "kept"},
            }],
        }
    }

    adapted = adapt(trace)
    span = adapted["data"]["spans"][0]
    attributes = span["attributes"]
    assert json.loads(attributes["mlflow.spanInputs"]) == {"input": "input"}
    assert json.loads(attributes["input.value"]) == {"input": "value"}
    assert json.loads(attributes["mlflow.spanOutputs"]) == {"output": "output"}
    assert json.loads(attributes["output.value"]) == {"output": [1]}
    assert span["inputs"] == {"input": "direct"}
    assert span["outputs"] == {"output": "kept"}
    assert adapted["data"]["request"] == {"input": "request"}
    assert adapted["data"]["response"] == {"output": "response"}


def test_compat_false_preserves_trace() -> None:
    trace = {"data": {"spans": [{"attributes": {"input.value": "raw"}}]}}
    before = json.loads(json.dumps(trace))
    assert trace == before


def test_requires_a_command(clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, env=clean_env)

    assert result.returncode == 2
    assert "the following arguments are required: COMMAND" in result.stderr


@pytest.mark.parametrize("command", ["trace", "experiment"])
def test_subcommand_help(command: str, clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, command, "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert f"usage: mlflow-traces {command}" in result.stdout
