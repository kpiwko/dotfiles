from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import BIN, run_script

pytestmark = pytest.mark.binary("dotfiles-caddy-install")
SCRIPT = BIN / "dotfiles-caddy-install"


def make_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.fixture
def caddy_env(tmp_path: Path, clean_env: dict[str, str]) -> tuple[dict[str, str], Path]:
    src = tmp_path / "src"
    (src / "sites").mkdir(parents=True)
    (src / "snippets").mkdir()
    (src / "env").mkdir()
    (src / "Caddyfile").write_text("test-caddyfile\n")
    (src / "sites/llm.caddy").write_text("test-site\n")
    (src / "sites/example.caddy.example").write_text("skip\n")
    (src / "snippets/cloudflare-tls.caddy").write_text("test-snippet\n")
    (src / "env/cloudflare.env.example").write_text("CF_API_TOKEN=changeme\nACME_EMAIL=you@example.com\n")
    (src / "caddy-start").write_text("#!/bin/sh\n")
    (src / "local.caddy.plist").write_text("plist\n")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    role = fake_bin / "dotfiles-role"
    make_executable(role, '[ "$1" = has ] && [ "$2" = ai-server ] && exit 0\nexit 1\n')
    launchctl = fake_bin / "launchctl"
    make_executable(launchctl, f'echo "$*" >> "{tmp_path / "launchctl.log"}"\n[ "$1" = list ] && exit 1\nexit 0\n')
    xcaddy = fake_bin / "xcaddy"
    make_executable(
        xcaddy,
        'while [ "$#" -gt 0 ]; do if [ "$1" = --output ]; then shift; out="$1"; fi; shift; done\n'
        'cat > "$out" <<\'EOF\'\n#!/bin/sh\n[ "$1" = version ] && echo v2.9.1\nexit 0\nEOF\nchmod +x "$out"\n',
    )

    env = clean_env.copy()
    env.update({
        "SUDO": "",
        "INSTALL_OWNER_FLAGS": "",
        "DOTFILES_CADDY_SRC": str(src),
        "CADDY_ETC_DIR": str(tmp_path / "etc"),
        "CADDY_LOG_DIR": str(tmp_path / "log"),
        "CADDY_VAR_DIR": str(tmp_path / "var"),
        "CADDY_BIN": str(fake_bin / "caddy"),
        "CADDY_LIBEXEC_DIR": str(tmp_path / "libexec"),
        "LAUNCHD_DIR": str(tmp_path / "launchd"),
        "DOTFILES_ROLE_BIN": str(role),
        "LAUNCHCTL_BIN": str(launchctl),
        "XCADDY_BIN": str(xcaddy),
        "DNS_ACME_EMAIL": "test@example.net",
    })
    return env, tmp_path


def test_refuses_without_supported_role(caddy_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = caddy_env
    make_executable(Path(env["DOTFILES_ROLE_BIN"]), "exit 1\n")
    result = run_script(SCRIPT, env=env)
    assert result.returncode == 1
    assert not (tmp / "etc").exists()


def test_first_run_bootstraps_example_and_stops_before_build(caddy_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = caddy_env
    result = run_script(SCRIPT, env=env)
    assert result.returncode == 0
    assert "created" in result.stderr
    assert (tmp / "etc/env/cloudflare.env").read_text().startswith("CF_API_TOKEN=changeme")
    assert not Path(env["CADDY_BIN"]).exists()


def test_syncs_config_and_removes_stale_files(caddy_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = caddy_env
    env["CF_API_TOKEN"] = "real-secret"
    result = run_script(SCRIPT, env=env)
    assert result.returncode == 0, result.stderr
    assert (tmp / "etc/Caddyfile").read_text() == "test-caddyfile\n"
    assert (tmp / "etc/sites/llm.caddy").read_text() == "test-site\n"
    assert not (tmp / "etc/sites/example.caddy.example").exists()
    stale = tmp / "etc/sites/stale.caddy"
    stale.write_text("stale")
    assert run_script(SCRIPT, env=env).returncode == 0
    assert not stale.exists()


def test_existing_secret_is_preserved(caddy_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = caddy_env
    secret = tmp / "etc/env/cloudflare.env"
    secret.parent.mkdir(parents=True)
    secret.write_text("CF_API_TOKEN=keep-me\nACME_EMAIL=real@example.net\n")
    assert run_script(SCRIPT, env=env).returncode == 0
    assert secret.read_text() == "CF_API_TOKEN=keep-me\nACME_EMAIL=real@example.net\n"


def test_builds_validates_and_bootstraps_launchd(caddy_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = caddy_env
    env["CF_API_TOKEN"] = "real-secret"
    result = run_script(SCRIPT, env=env)
    assert result.returncode == 0, result.stderr
    assert Path(env["CADDY_BIN"]).exists()
    assert (tmp / "libexec/caddy-start").exists()
    assert (tmp / "launchd/local.caddy.plist").exists()
    assert "bootstrap system" in (tmp / "launchctl.log").read_text()


def test_clean_is_supported(caddy_env: tuple[dict[str, str], Path]) -> None:
    env, tmp = caddy_env
    env["CF_API_TOKEN"] = "real-secret"
    assert run_script(SCRIPT, "--clean", env=env).returncode == 0
    assert (tmp / "etc/sites/llm.caddy").exists()
