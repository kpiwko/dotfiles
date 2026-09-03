from pathlib import Path

import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("dotfiles-role")
SCRIPT = BIN / "dotfiles-role"


def test_enable_list_has_disable(tmp_path: Path, clean_env: dict[str, str]) -> None:
    roles = tmp_path / "roles"
    env = clean_env | {"DOTFILES_ROLES_FILE": str(roles)}

    assert run_script(SCRIPT, "enable", "dev", env=env).returncode == 0
    assert run_script(SCRIPT, "enable", "dev", env=env).returncode == 0
    assert run_script(SCRIPT, "has", "dev", env=env).returncode == 0
    assert run_script(SCRIPT, "list", env=env).stdout.splitlines() == ["dev"]
    assert run_script(SCRIPT, "disable", "dev", env=env).returncode == 0
    assert run_script(SCRIPT, "has", "dev", env=env).returncode != 0


def test_rejects_unknown_role(tmp_path: Path, clean_env: dict[str, str]) -> None:
    env = clean_env | {"DOTFILES_ROLES_FILE": str(tmp_path / "roles")}
    result = run_script(SCRIPT, "enable", "nope", env=env)
    assert result.returncode == 1
    assert "unknown role" in result.stderr
