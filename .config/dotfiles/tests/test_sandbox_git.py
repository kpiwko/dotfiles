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


def sandbox_git_at(
    cwd: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BIN / "sandbox-git"), *args],
        cwd=cwd,
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


@pytest.mark.binary("sandbox-git")
def test_start_branch_fetches_base_and_preserves_local_changes(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path, branch="main")
    bare = home / ".dotfiles"
    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]

    subprocess.run(
        [*dotfiles_git, "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
    )
    (home / "tracked.txt").write_text("local change\n")

    result = sandbox_git(home, env, "start-branch", "feat/fresh", "main", "origin")

    assert result.returncode == 0, result.stderr
    branch = subprocess.run(
        [*dotfiles_git, "branch", "--show-current"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert branch.stdout.strip() == "feat/fresh"
    assert (home / "tracked.txt").read_text() == "local change\n"


@pytest.mark.binary("sandbox-git")
def test_start_branch_rejects_protected_destination(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path, branch="main")

    result = sandbox_git(home, env, "start-branch", "main", "main", "origin")

    assert result.returncode == 1
    assert "refusing to create protected/significant branch 'main'" in result.stderr


@pytest.mark.binary("sandbox-git")
def test_start_branch_then_publish_without_upstream_conflict(tmp_path: Path) -> None:
    home, remote, env = init_repo(tmp_path, branch="main")
    bare = home / ".dotfiles"
    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]
    subprocess.run(
        [*dotfiles_git, "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
    )

    started = sandbox_git(home, env, "start-branch", "feat/publish", "main", "origin")
    assert started.returncode == 0, started.stderr
    (home / "feature.txt").write_text("feature\n")
    subprocess.run([*dotfiles_git, "add", "feature.txt"], check=True)
    subprocess.run([*dotfiles_git, "commit", "-m", "feature"], check=True, capture_output=True)

    published = sandbox_git(home, env, "publish")

    assert published.returncode == 0, published.stderr
    assert git("rev-parse", "refs/heads/feat/publish", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_publish_recovers_when_upstream_points_to_base(tmp_path: Path) -> None:
    home, remote, env = init_repo(tmp_path, branch="feat/publish")
    bare = home / ".dotfiles"
    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]
    subprocess.run([*dotfiles_git, "push", "origin", "HEAD:main"], check=True, capture_output=True)
    subprocess.run(
        [*dotfiles_git, "branch", "--set-upstream-to=origin/main"],
        check=True,
        capture_output=True,
    )

    published = sandbox_git(home, env, "publish")

    assert published.returncode == 0, published.stderr
    upstream = subprocess.run(
        [*dotfiles_git, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert upstream.stdout.strip() == "origin/feat/publish"
    assert git("rev-parse", "refs/heads/feat/publish", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_git_base_detects_dotfiles_in_subdirectory_and_dotfiles_dir(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path)
    dotfiles = home / ".dotfiles"
    dotfiles_child = dotfiles / "test-child"
    dotfiles_child.mkdir()
    nested = home / "nested"
    nested.mkdir()
    subrepo = home / "subrepo"
    subprocess.run(["git", "init", str(subrepo)], check=True, capture_output=True)

    for cwd in (dotfiles, dotfiles_child, nested):
        result = sandbox_git_at(cwd, env, "rev-parse", "--git-dir")
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()).resolve() == dotfiles.resolve()

    result = sandbox_git_at(subrepo, env, "rev-parse", "--git-dir")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ".git"


@pytest.mark.binary("sandbox-git")
def test_status_guards_untracked_scan_in_home(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path)
    untracked = home / "deep" / "untracked.txt"
    untracked.parent.mkdir()
    untracked.write_text("not tracked\n")

    result = sandbox_git(home, env, "status", "--untracked-files=all")

    assert result.returncode == 0, result.stderr
    assert "untracked.txt" not in result.stdout


@pytest.mark.binary("sandbox-git")
def test_sync_base_rebases_feature_branch_on_latest_remote_base(tmp_path: Path) -> None:
    home, remote, env = init_repo(tmp_path, branch="main")
    bare = home / ".dotfiles"
    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]

    subprocess.run(
        [*dotfiles_git, "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
    )
    start = sandbox_git(home, env, "start-branch", "feat/work", "main", "origin")
    assert start.returncode == 0, start.stderr

    (home / "feature.txt").write_text("feature\n")
    subprocess.run([*dotfiles_git, "add", "feature.txt"], check=True)
    subprocess.run(
        [*dotfiles_git, "commit", "-m", "feature"],
        check=True,
        capture_output=True,
    )

    updater = tmp_path / "updater"
    subprocess.run(["git", "clone", str(remote), str(updater)], check=True, capture_output=True)
    git("config", "user.email", "test@example.com", cwd=updater)
    git("config", "user.name", "Test", cwd=updater)
    git("switch", "main", cwd=updater)
    (updater / "base.txt").write_text("base\n")
    git("add", "base.txt", cwd=updater)
    git("commit", "-m", "advance base", cwd=updater)
    pushed = git("push", "origin", "main", cwd=updater)
    assert pushed.returncode == 0, pushed.stderr

    result = sandbox_git(home, env, "sync-base", "main", "origin")

    assert result.returncode == 0, result.stderr
    ancestor = subprocess.run(
        [*dotfiles_git, "merge-base", "--is-ancestor", "origin/main", "HEAD"],
        check=False,
    )
    assert ancestor.returncode == 0


@pytest.mark.binary("sandbox-git")
def test_publish_supports_explicit_safe_remote(tmp_path: Path) -> None:
    home, remote, env = init_repo(tmp_path)
    bare = home / ".dotfiles"
    dotfiles_git = ["git", f"--git-dir={bare}", f"--work-tree={home}"]
    subprocess.run(
        [*dotfiles_git, "remote", "add", "upstream", str(remote)],
        check=True,
    )

    result = sandbox_git(home, env, "publish", "upstream")

    assert result.returncode == 0, result.stderr
    remote_branch = git("rev-parse", "refs/heads/feat/test", cwd=remote)
    assert remote_branch.returncode == 0
    upstream = subprocess.run(
        [*dotfiles_git, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert upstream.stdout.strip() == "upstream/feat/test"
