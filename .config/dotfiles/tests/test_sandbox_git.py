from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import BIN


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def init_repo(tmp_path: Path, branch: str = "feat/test") -> tuple[Path, Path, dict[str, str]]:
    home = tmp_path / "home"
    home.mkdir()
    bare = home / ".dotfiles"
    remote = tmp_path / "origin.git"

    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)

    env = os.environ.copy()
    env["HOME"] = str(home)

    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]
    subprocess.run([*dotfiles_git, "config", "user.email", "test@example.com"], check=True)
    subprocess.run([*dotfiles_git, "config", "user.name", "Test"], check=True)

    (home / "tracked.txt").write_text("one\n")
    subprocess.run([*dotfiles_git, "add", "tracked.txt"], check=True)
    subprocess.run(
        [*dotfiles_git, "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    subprocess.run([*dotfiles_git, "branch", "-M", branch], check=True)
    subprocess.run([*dotfiles_git, "remote", "add", "origin", str(remote)], check=True)

    return home, remote, env


def sandbox_git(home: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BIN / "sandbox-git"), *args],
        cwd=home,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


@pytest.mark.binary("sandbox-git")
def test_dotfiles_push_accepts_remotes_prefixed_upstream(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path)
    bare = home / ".dotfiles"
    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]

    subprocess.run(
        [*dotfiles_git, "push", "-u", "origin", "feat/test"],
        check=True,
        capture_output=True,
    )

    result = sandbox_git(home, env, "push", "origin", "-f", "HEAD:feat/test")

    assert result.returncode == 0, result.stderr


@pytest.mark.binary("sandbox-git")
def test_explicit_push_checks_destination_not_current_branch(tmp_path: Path) -> None:
    home, remote, env = init_repo(tmp_path, branch="main")

    result = sandbox_git(home, env, "push", "origin", "HEAD:aliases")

    assert result.returncode == 0, result.stderr
    remote_branch = git("rev-parse", "refs/heads/aliases", cwd=remote)
    assert remote_branch.returncode == 0


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "refspec",
    [
        "HEAD:main",
        "feat/test:main",
        "HEAD:refs/heads/main",
        "+HEAD:main",
        "HEAD:release/1.0",
        "HEAD:hotfix/urgent",
    ],
)
def test_explicit_push_rejects_protected_destination(tmp_path: Path, refspec: str) -> None:
    home, _, env = init_repo(tmp_path)

    result = sandbox_git(home, env, "push", "origin", refspec)

    assert result.returncode == 1
    assert "refusing to push protected/significant branch" in result.stderr


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "refspec",
    [
        "HEAD:aliases",
        "feat/test:aliases",
        "+HEAD:aliases",
    ],
)
def test_explicit_push_allows_unprotected_destination(tmp_path: Path, refspec: str) -> None:
    home, _, env = init_repo(tmp_path)

    result = sandbox_git(home, env, "push", "origin", refspec)

    assert result.returncode == 0, result.stderr


@pytest.mark.binary("sandbox-git")
def test_bare_push_rejects_protected_current_branch(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path, branch="main")

    result = sandbox_git(home, env, "push")

    assert result.returncode == 1
    assert "refusing to push protected/significant branch 'main'" in result.stderr
