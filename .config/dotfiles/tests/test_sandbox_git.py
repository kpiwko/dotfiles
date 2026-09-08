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


@pytest.mark.binary("sandbox-git")
def test_dotfiles_push_accepts_remotes_prefixed_upstream(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    bare = home / ".dotfiles"
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)

    env = os.environ.copy()
    env["HOME"] = str(home)

    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "config", "user.name", "Test"],
        check=True,
    )
    (home / "tracked.txt").write_text("one\n")
    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "add", "tracked.txt"],
        check=True,
    )
    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "branch", "-M", "feat/test"],
        check=True,
    )
    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "remote", "add", "origin", str(remote)],
        check=True,
    )
    subprocess.run(
        ["git", f"--git-dir={bare}", f"--work-tree={home}", "push", "-u", "origin", "feat/test"],
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        [str(BIN / "sandbox-git"), "push", "origin", "-f", "HEAD:feat/test"],
        cwd=home,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
