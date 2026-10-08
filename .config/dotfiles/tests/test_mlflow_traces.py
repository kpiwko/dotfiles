from __future__ import annotations

import os

import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("mlflow-traces")
SCRIPT = BIN / "mlflow-traces"


def test_script_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_help_lists_commands(clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert "usage: mlflow-traces" in result.stdout
    assert "trace" in result.stdout
    assert "experiment" in result.stdout


def test_requires_a_command(clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, env=clean_env)

    assert result.returncode == 2
    assert "the following arguments are required: COMMAND" in result.stderr


@pytest.mark.parametrize("command", ["trace", "experiment"])
def test_subcommand_help(command: str, clean_env: dict[str, str]) -> None:
    result = run_script(SCRIPT, command, "--help", env=clean_env)

    assert result.returncode == 0, result.stderr
    assert f"usage: mlflow-traces {command}" in result.stdout
