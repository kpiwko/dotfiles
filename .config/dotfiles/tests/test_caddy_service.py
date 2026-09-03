from pathlib import Path

import pytest

from conftest import BIN, ROOT, run_script


def make_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.mark.caddy
def test_caddy_start_loads_env_and_execs_caddy(tmp_path: Path, clean_env: dict[str, str]) -> None:
    caddy = tmp_path / "caddy"
    output = tmp_path / "args"
    make_executable(caddy, f'echo "TOKEN=$CF_API_TOKEN ARGS=$*" > "{output}"\n')
    etc = tmp_path / "etc"
    (etc / "env").mkdir(parents=True)
    (etc / "Caddyfile").write_text("test\n")
    env_file = etc / "env/cloudflare.env"
    env_file.write_text("CF_API_TOKEN=secret\n")
    env = clean_env | {
        "CADDY_ETC_DIR": str(etc),
        "CADDY_BIN": str(caddy),
        "CADDY_ENV_FILE": str(env_file),
    }
    result = run_script(ROOT / ".config/caddy/caddy-start", env=env)
    assert result.returncode == 0
    assert output.read_text().strip() == f"TOKEN=secret ARGS=run --config {etc}/Caddyfile --adapter caddyfile"


@pytest.mark.binary("dotfiles-caddy-uninstall")
def test_caddy_uninstall_removes_installed_files(tmp_path: Path, clean_env: dict[str, str]) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    role = fake / "dotfiles-role"
    make_executable(role, '[ "$1" = has ] && [ "$2" = dev ]\n')
    launchctl = fake / "launchctl"
    make_executable(launchctl, '[ "$1" = list ] && exit 1\nexit 0\n')
    caddy = fake / "caddy"
    caddy.write_text("x")
    libexec = tmp_path / "libexec"
    launchd = tmp_path / "launchd"
    libexec.mkdir(); launchd.mkdir()
    (libexec / "caddy-start").write_text("x")
    (launchd / "local.caddy.plist").write_text("x")
    env = clean_env | {
        "SUDO": "",
        "DOTFILES_ROLE_BIN": str(role),
        "LAUNCHCTL_BIN": str(launchctl),
        "CADDY_BIN": str(caddy),
        "CADDY_LIBEXEC_DIR": str(libexec),
        "LAUNCHD_DIR": str(launchd),
    }
    result = run_script(BIN / "dotfiles-caddy-uninstall", env=env)
    assert result.returncode == 0
    assert not caddy.exists()
    assert not (libexec / "caddy-start").exists()
    assert not (launchd / "local.caddy.plist").exists()
