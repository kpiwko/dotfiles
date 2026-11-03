from __future__ import annotations

import os
import shutil
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


def make_failing_git(sentinel: Path) -> Path:
    """Write a fake git executable that records any invocation and fails."""
    script = sentinel.parent / "fake-bin" / "git"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{sentinel}"\n'
        "exit 99\n"
    )
    script.chmod(0o755)
    return script.parent


def make_recording_git(sentinel: Path, real_git: str, drift: bool = False) -> Path:
    """Write a git shim that records every invocation, then forwards to real git.

    With drift=True, the shim renames the current branch to 'feat/drift'
    when it first sees the guard phase's `rev-parse --is-inside-work-tree`
    call (used only by ensure_repo inside validate_publish/validate_push),
    which runs between the gate's two comparisons.
    """
    import shutil

    resolved = real_git or shutil.which("git")
    assert resolved, "real git not found on PATH"
    script = sentinel.parent / "record-bin" / "git"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys\n"
        f"REAL = {resolved!r}\n"
        f"SENTINEL = {str(sentinel)!r}\n"
        "args = sys.argv[1:]\n"
        "with open(SENTINEL, 'a') as fh:\n"
        "    fh.write('\\0'.join(args) + '\\n')\n"
        f"DRIFT = {drift!r}\n"
        "prefix = args[:2] if args and args[0].startswith('--git-dir=') else []\n"
        "rest = args[len(prefix):]\n"
        "if DRIFT and rest[:1] == ['rev-parse'] and '--is-inside-work-tree' in rest:\n"
        "    subprocess.run([REAL, *prefix, 'branch', '-m', 'feat/drift'],\n"
        "                   check=False, capture_output=True)\n"
        "os.execv(REAL, [REAL, *args])\n"
    )
    script.chmod(0o755)
    return script.parent


def read_sentinel(sentinel: Path) -> list[list[str]]:
    if not sentinel.exists():
        return []
    text = sentinel.read_text()
    return [line.split("\0") for line in text.splitlines() if line]


def env_with_git_shim(env: dict[str, str], shim_bin: Path) -> dict[str, str]:
    patched = env.copy()
    patched["PATH"] = f"{shim_bin}{os.pathsep}{patched.get('PATH', '')}"
    return patched


def observe_fixture(home: Path) -> dict[str, str]:
    """Observe the fixture's actual state for building matching expectations."""
    bare = home / ".dotfiles"
    dg = ["git", f"--git-dir={bare}", f"--work-tree={home}"]

    def out(*args: str) -> str:
        return subprocess.run(
            [*dg, *args], text=True, capture_output=True, check=True
        ).stdout.strip()

    return {
        "head": out("rev-parse", "HEAD"),
        "branch": out("symbolic-ref", "--quiet", "--short", "HEAD"),
        "url": out("config", "--get-all", "remote.origin.url"),
    }


def guarded_prefix(
    root: str,
    head: str,
    branch: str,
    upstream: str,
    destination: str,
    push_url: str,
    check_only: bool = False,
) -> list[str]:
    args = [
        "--expect-root", root,
        "--expect-head", head,
        "--expect-branch", branch,
        "--expect-upstream", upstream,
        "--expect-destination", destination,
        "--expect-push-url", push_url,
    ]
    if check_only:
        args.append("--check-only")
    return args


def env_with_failing_git(env: dict[str, str], fake_bin: Path) -> dict[str, str]:
    patched = env.copy()
    patched["PATH"] = f"{fake_bin}{os.pathsep}{patched.get('PATH', '')}"
    return patched


@pytest.mark.binary("sandbox-git")
def test_help_in_home_exits_zero_without_invoking_git(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    fake_bin = make_failing_git(sentinel)

    result = sandbox_git_at(
        home, env_with_failing_git(env, fake_bin), "--help"
    )

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


@pytest.mark.binary("sandbox-git")
def test_help_outside_git_repository_exits_zero_without_invoking_git(
    tmp_path: Path,
) -> None:
    home, _, env = init_repo(tmp_path)
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    sentinel = tmp_path / "git-calls.log"
    fake_bin = make_failing_git(sentinel)

    result = sandbox_git_at(
        outside, env_with_failing_git(env, fake_bin), "--help"
    )

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()


@pytest.mark.binary("sandbox-git")
def test_help_documents_wrapper_usage_and_guards(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    fake_bin = make_failing_git(sentinel)

    result = sandbox_git_at(
        home, env_with_failing_git(env, fake_bin), "--help"
    )

    assert result.returncode == 0, result.stderr
    assert not sentinel.exists()
    for expected in (
        "local shell executable",
        "HOME bare dotfiles",
        "project repository",
        "start-branch",
        "sync-base",
        "publish",
        "approval",
        "wrapper",
    ):
        assert expected in result.stdout, f"help output missing {expected!r}"


@pytest.mark.binary("sandbox-git")
def test_git_subcommand_still_passes_through_after_help(tmp_path: Path) -> None:
    home, _, env = init_repo(tmp_path, branch="main")

    passing = sandbox_git(home, env, "rev-parse", "--git-dir")
    assert passing.returncode == 0, passing.stderr


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


# --- Task 3A: opt-in publication expectation gate ---------------------------
#
# All tests below use disposable offline fixtures (init_repo) and PATH git
# shims; no real HOME Git operation, network push or fetch occurs.


def guarded_fixture(tmp_path: Path, branch: str = "feat/test") -> tuple[Path, Path, dict[str, str], dict[str, str]]:
    """Fixture plus its observed head/branch/url for matching expectations."""
    home, remote, env = init_repo(tmp_path, branch=branch)
    observed = observe_fixture(home)
    return home, remote, env, observed


def expect_args(
    observed: dict[str, str],
    home: Path,
    upstream: str = "none",
    destination: str | None = None,
    push_url: str | None = None,
) -> list[str]:
    return guarded_prefix(
        root=str(home),
        head=observed["head"],
        branch=observed["branch"],
        upstream=upstream,
        destination=destination or f"origin:refs/heads/{observed['branch']}",
        push_url=push_url or observed["url"],
    )


OPT_ORDER = [
    "--expect-root",
    "--expect-head",
    "--expect-branch",
    "--expect-upstream",
    "--expect-destination",
    "--expect-push-url",
]


def t3a_opts(home: Path, observed: dict[str, str], **overrides: str) -> dict[str, str]:
    opts = {
        "--expect-root": str(home),
        "--expect-head": observed["head"],
        "--expect-branch": observed["branch"],
        "--expect-upstream": "none",
        "--expect-destination": f"origin:refs/heads/{observed['branch']}",
        "--expect-push-url": observed["url"],
    }
    opts.update(overrides)
    return opts


def t3a_render(opts: dict[str, str], check_only: bool = False) -> list[str]:
    args: list[str] = []
    for name in OPT_ORDER:
        if name in opts:
            args.extend([name, opts[name]])
    if check_only:
        args.append("--check-only")
    return args


def t3a_parse_failure_argv(case: str, opts: dict[str, str]) -> list[str]:
    rendered = t3a_render(opts)
    if case.startswith("missing-"):
        reduced = {k: v for k, v in opts.items() if k != case.removeprefix("missing-")}
        return [*t3a_render(reduced), "publish"]
    if case == "check-only-alone":
        return ["--check-only", "publish"]
    if case == "unknown-option":
        return [*rendered, "--expect-foo", "x", "publish"]
    if case == "duplicate-option":
        return [*rendered, "--expect-root", "/tmp", "publish"]
    if case == "value-missing":
        reduced = {k: v for k, v in opts.items() if k != "--expect-upstream"}
        return [*t3a_render(reduced), "--expect-upstream"]
    if case == "after-subcommand":
        return [*rendered, "publish", "--check-only"]
    if case == "after-subcommand-push":
        return [*rendered, "push", "--expect-root", "/tmp"]
    if case == "publish-force-option":
        return [*rendered, "publish", "--force"]
    if case == "publish-receive-pack":
        return [*rendered, "publish", "--receive-pack=x"]
    if case == "nonpublication-status":
        return [*rendered, "status"]
    if case == "nonpublication-sync-base":
        return [*rendered, "sync-base", "main"]
    if case == "nonpublication-start-branch":
        return [*rendered, "start-branch", "feat/x"]
    if case == "nonpublication-rev-parse":
        return [*rendered, "rev-parse", "HEAD"]
    if case == "push-force-option":
        return [*rendered, "push", "--force", "origin"]
    if case == "push-force-refspec":
        return [*rendered, "push", "origin", "+HEAD:refs/heads/x"]
    if case == "push-delete-refspec":
        return [*rendered, "push", "origin", ":refs/heads/x"]
    if case == "push-tag-destination":
        return [*rendered, "push", "origin", "HEAD:refs/tags/v1"]
    if case == "push-branch-source-refspec":
        return [*rendered, "push", "origin", "refs/heads/feat/test:refs/heads/x"]
    if case == "push-bare-destination":
        return [*rendered, "push", "origin", "HEAD:aliases"]
    if case == "push-source-only":
        return [*rendered, "push", "origin", "HEAD"]
    if case == "push-too-many":
        return [*rendered, "push", "origin", "HEAD:refs/heads/a", "HEAD:refs/heads/b"]
    if case == "push-refspec-without-remote":
        return [*rendered, "push", "HEAD:refs/heads/x"]
    if case == "bad-head":
        return [*t3a_render(dict(opts, **{"--expect-head": "abc123"})), "publish"]
    if case == "bad-branch":
        return [*t3a_render(dict(opts, **{"--expect-branch": "refs/heads/x"})), "publish"]
    if case == "bad-upstream":
        return [*t3a_render(dict(opts, **{"--expect-upstream": "origin:main"})), "publish"]
    if case == "bad-destination":
        return [*t3a_render(dict(opts, **{"--expect-destination": "origin"})), "push", "origin"]
    if case == "relative-root":
        return [*t3a_render(dict(opts, **{"--expect-root": "relative/path"})), "publish"]
    if case == "empty-url":
        return [*t3a_render(dict(opts, **{"--expect-push-url": ""})), "publish"]
    if case == "conflict-destination-remote":
        mutated = dict(opts, **{"--expect-destination": "other:refs/heads/feat/test"})
        return [*t3a_render(mutated), "push", "origin"]
    if case == "conflict-publish-branch":
        mutated = dict(opts, **{"--expect-destination": "origin:refs/heads/other"})
        return [*t3a_render(mutated), "publish"]
    raise AssertionError(f"unknown parse-failure case '{case}'")


PARSE_FAILURE_FRAGMENTS = {
    "missing---expect-root": "all six options are required together",
    "missing---expect-head": "all six options are required together",
    "missing---expect-branch": "all six options are required together",
    "missing---expect-upstream": "all six options are required together",
    "missing---expect-destination": "all six options are required together",
    "missing---expect-push-url": "all six options are required together",
    "check-only-alone": "all six options are required together",
    "unknown-option": "unknown option",
    "duplicate-option": "duplicate option",
    "value-missing": "requires a value",
    "after-subcommand": "must be a prefix",
    "after-subcommand-push": "must be a prefix",
    "publish-force-option": "invalid remote name '--force'",
    "publish-receive-pack": "invalid remote name '--receive-pack=x'",
    "nonpublication-status": "not a supported guarded operation",
    "nonpublication-sync-base": "not a supported guarded operation",
    "nonpublication-start-branch": "not a supported guarded operation",
    "nonpublication-rev-parse": "not a supported guarded operation",
    "push-force-option": "unsupported guarded push option",
    "push-force-refspec": "unsupported guarded push refspec",
    "push-delete-refspec": "unsupported guarded push refspec",
    "push-tag-destination": "unsupported guarded push refspec",
    "push-branch-source-refspec": "unsupported guarded push refspec",
    "push-bare-destination": "unsupported guarded push refspec",
    "push-source-only": "unsupported guarded push refspec",
    "push-too-many": "too many arguments",
    "push-refspec-without-remote": "invalid remote name",
    "bad-head": "--expect-head must be a full",
    "bad-branch": "--expect-branch must be a short branch name",
    "bad-upstream": "expected a refs/heads/NAME ref",
    "bad-destination": "expected REMOTE:refs/heads/NAME form",
    "relative-root": "must be an absolute path",
    "empty-url": "--expect-push-url must be a non-empty URL",
    "conflict-destination-remote": "conflicting expectations",
    "conflict-publish-branch": "conflicting expectations",
}


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize("case", sorted(PARSE_FAILURE_FRAGMENTS))
def test_guarded_parse_failures_are_closed_before_any_git(
    tmp_path: Path, case: str
) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    fake_bin = make_failing_git(sentinel)

    args = t3a_parse_failure_argv(case, t3a_opts(home, observed))
    result = sandbox_git_at(home, env_with_failing_git(env, fake_bin), *args)

    assert result.returncode == 1
    fragment = PARSE_FAILURE_FRAGMENTS[case]
    assert fragment in result.stderr, f"{case}: {result.stderr}"
    assert not sentinel.exists(), f"{case}: no Git invocation may run for invalid options"


@pytest.mark.binary("sandbox-git")
def test_guarded_wrong_cwd_runs_zero_git_calls(tmp_path: Path) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    sentinel = tmp_path / "git-calls.log"
    fake_bin = make_failing_git(sentinel)

    args = [*expect_args(observed, home), "publish"]
    result = sandbox_git_at(elsewhere, env_with_failing_git(env, fake_bin), *args)

    assert result.returncode == 1
    assert "wrong working directory" in result.stderr, result.stderr
    assert not sentinel.exists(), "wrong root must not run any Git call"


@pytest.mark.binary("sandbox-git")
def test_guarded_root_mismatch_inside_repo_fails_before_guards(tmp_path: Path) -> None:
    """A nested non-repo dir falls back to the HOME bare repo: rejected.

    The expectation names the nested dir, so the HOME-bare fallback (which
    would push dotfiles) is refused: worktree root != assigned root.
    """
    home, _, env, observed = guarded_fixture(tmp_path)
    nested = home / "nested"
    nested.mkdir()
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *expect_args(
            observed,
            home,
            push_url=observed["url"],
        ),
        "publish",
    ]
    # Point the root expectation at the nested dir (not a repo of its own).
    args = [
        *guarded_prefix(
            root=str(nested),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "publish",
    ]
    result = sandbox_git_at(nested, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "expectation mismatch (before guards)" in result.stderr, result.stderr
    assert "root" in result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:2] for c in calls), calls


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "field,override",
    [
        ("head", None),
        ("branch", "feat/other"),
        ("upstream", "origin:refs/heads/feat/test"),
        ("destination", "origin:refs/heads/feat/other"),
        ("push_url", "file:///nonexistent/other.git"),
    ],
)
def test_guarded_mismatch_stops_before_guards_and_network(
    tmp_path: Path, field: str, override: str | None
) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    if field == "head":
        mutated = dict(t3a_opts(home, observed), **{"--expect-head": "0" * 40})
        args = [*t3a_render(mutated), "publish"]
    elif field == "branch":
        # Use the push form: branch may legitimately differ from destination,
        # so a wrong branch expectation must surface as a comparison mismatch
        # rather than a parse-time conflict.
        mutated = dict(t3a_opts(home, observed), **{"--expect-branch": "feat/other"})
        args = [*t3a_render(mutated), "push", "origin"]
    elif field == "destination":
        mutated = dict(t3a_opts(home, observed), **{"--expect-destination": "origin:refs/heads/feat/other"})
        args = [*t3a_render(mutated), "push", "origin"]
    else:
        key = f"--expect-{field.replace('_', '-')}"
        mutated = dict(t3a_opts(home, observed), **{key: override or ""})
        args = [*t3a_render(mutated), "publish"]

    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "expectation mismatch (before guards)" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:2] for c in calls), f"push ran: {calls}"
    assert not any("remote" in c[:2] and "get-url" not in c for c in calls), (
        f"networked guard ran: {calls}"
    )


@pytest.mark.binary("sandbox-git")
def test_guarded_upstream_absence_expectation_matches(tmp_path: Path) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "push", "-u", "origin", observed["branch"]], check=True, capture_output=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "publish",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)
    assert result.returncode == 0, result.stderr
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode == 0

    # Same state, but the expectation wrongly says 'none': mismatch.
    sentinel2 = tmp_path / "git-calls-2.log"
    recording2 = make_recording_git(sentinel2, shutil.which("git") or "git")
    args_none = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "publish",
    ]
    result2 = sandbox_git_at(home, env_with_git_shim(env, recording2), *args_none)
    assert result2.returncode == 1
    assert "expectation mismatch (before guards)" in result2.stderr
    assert "upstream" in result2.stderr


@pytest.mark.binary("sandbox-git")
def test_guarded_check_only_reports_json_without_side_effects(tmp_path: Path) -> None:
    import json as json_mod

    home, remote, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    head_before = subprocess.run(
        ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}", "rev-parse", "HEAD"],
        text=True, capture_output=True, check=True,
    ).stdout.strip()

    args = [*expect_args(observed, home), "--check-only", "publish"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 0, result.stderr
    payload = json_mod.loads(result.stdout)
    assert payload["check_only"] is True
    assert payload["authorization_claimed"] is False
    assert payload["all_match"] is True
    assert all(payload["matches"].values())
    assert payload["observed"]["head"] == observed["head"]
    assert payload["observed"]["branch"] == observed["branch"]
    assert payload["observed"]["upstream"] == "none"
    assert payload["observed"]["destination"] == f"origin:refs/heads/{observed['branch']}"
    assert payload["observed"]["push_url"] == observed["url"]
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:2] for c in calls), calls
    assert not any("remote" in c[:2] and "get-url" not in c for c in calls), calls
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode != 0
    head_after = subprocess.run(
        ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}", "rev-parse", "HEAD"],
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    assert head_after == head_before


@pytest.mark.binary("sandbox-git")
def test_guarded_check_only_mismatch_reports_json_and_exits_nonzero(tmp_path: Path) -> None:
    import json as json_mod

    home, _, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    mutated = dict(t3a_opts(home, observed), **{"--expect-branch": "feat/other"})
    args = [*t3a_render(mutated), "--check-only", "push", "origin"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    payload = json_mod.loads(result.stdout)
    assert payload["all_match"] is False
    assert payload["matches"]["branch"] is False
    assert payload["observed"]["branch"] == observed["branch"]
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:2] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_matching_publish_executes_expected_normal_argv(tmp_path: Path) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "push", "-u", "origin", observed["branch"]], check=True, capture_output=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "publish",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 0, result.stderr
    calls = read_sentinel(sentinel)
    push_calls = [c for c in calls if c[:1] == ["push"] or "push" in c[:3]]
    assert push_calls, calls
    final = push_calls[-1]
    assert f"HEAD:refs/heads/{observed['branch']}" in final, final
    assert "--set-upstream" not in final, final
    assert "--force" not in final and "-f" not in final, final
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_guarded_matching_publish_without_upstream_sets_upstream(tmp_path: Path) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [*expect_args(observed, home), "publish"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 0, result.stderr
    calls = read_sentinel(sentinel)
    push_calls = [c for c in calls if "push" in c[:3]]
    final = push_calls[-1]
    assert "--set-upstream" in final, final
    assert f"HEAD:refs/heads/{observed['branch']}" in final, final
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_guarded_matching_push_forms_execute_expected_argv(tmp_path: Path) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "push", "-u", "origin", observed["branch"]], check=True, capture_output=True)
    shim_git = shutil.which("git") or "git"

    # Bare guarded push: wrapper constructs origin HEAD:refs/heads/<branch>.
    sentinel = tmp_path / "s1.log"
    recording = make_recording_git(sentinel, shim_git)
    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "push",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)
    assert result.returncode == 0, result.stderr
    final = [c for c in read_sentinel(sentinel) if "push" in c[:3]][-1]
    assert f"HEAD:refs/heads/{observed['branch']}" in final, final
    assert "--force" not in final, final

    # push REMOTE (no refspec): passes REMOTE through to git.
    sentinel2 = tmp_path / "s2.log"
    recording2 = make_recording_git(sentinel2, shim_git)
    args2 = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "push",
        "origin",
    ]
    result2 = sandbox_git_at(home, env_with_git_shim(env, recording2), *args2)
    assert result2.returncode == 0, result2.stderr
    final2 = [c for c in read_sentinel(sentinel2) if "push" in c[:3]][-1]
    assert final2[-2:] == ["push", "origin"] or final2[:1] == ["push"], final2
    assert "--force" not in final2, final2

    # push REMOTE with the single HEAD refspec: passthrough argv.
    sentinel3 = tmp_path / "s3.log"
    recording3 = make_recording_git(sentinel3, shim_git)
    args3 = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination="origin:refs/heads/feat/target",
            push_url=observed["url"],
        ),
        "push",
        "origin",
        f"HEAD:refs/heads/feat/target",
    ]
    result3 = sandbox_git_at(home, env_with_git_shim(env, recording3), *args3)
    assert result3.returncode == 0, result3.stderr
    final3 = [c for c in read_sentinel(sentinel3) if "push" in c[:3]][-1]
    assert "HEAD:refs/heads/feat/target" in final3, final3
    assert git("rev-parse", "refs/heads/feat/target", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_guarded_publish_still_rejects_protected_branch(tmp_path: Path) -> None:
    home, _, env, observed = guarded_fixture(tmp_path, branch="main")
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [*expect_args(observed, home), "publish"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "refusing to push protected/significant branch 'main'" in result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_push_refspec_still_rejects_protected_destination(tmp_path: Path) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination="origin:refs/heads/main",
            push_url=observed["url"],
        ),
        "push",
        "origin",
        "HEAD:refs/heads/main",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "refusing to push protected/significant branch 'main'" in result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_publish_still_rejects_cross_remote_upstream(tmp_path: Path) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "remote", "add", "other", str(remote)], check=True, capture_output=True)
    subprocess.run([*dg, "push", "other", f"HEAD:refs/heads/{observed['branch']}"], check=True, capture_output=True)
    subprocess.run([*dg, "branch", "--set-upstream-to=other/" + observed["branch"]], check=True, capture_output=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"other:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "publish",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "is not on requested remote 'origin'" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_publish_state_drift_between_checks_rejects(tmp_path: Path) -> None:
    """State change between the initial and final comparison must reject.

    The drift shim renames the current branch during the guard phase (its
    first `rev-parse --is-inside-work-tree`, used only by ensure_repo inside
    validate_publish/validate_push, which runs between the two comparisons).
    """
    home, remote, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    drifting = make_recording_git(sentinel, shutil.which("git") or "git", drift=True)

    args = [*expect_args(observed, home), "publish"]
    result = sandbox_git_at(home, env_with_git_shim(env, drifting), *args)

    assert result.returncode == 1
    assert "expectation mismatch (before exec)" in result.stderr, result.stderr
    assert "branch" in result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), f"push ran: {calls}"
    # The push never happened: neither the old nor the drifted branch name.
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode != 0
    assert git("rev-parse", "refs/heads/feat/drift", cwd=remote).returncode != 0


@pytest.mark.binary("sandbox-git")
def test_guarded_push_state_drift_between_checks_rejects(tmp_path: Path) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    drifting = make_recording_git(sentinel, shutil.which("git") or "git", drift=True)

    args = [
        *expect_args(observed, home),
        "push",
        "origin",
        f"HEAD:refs/heads/{observed['branch']}",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, drifting), *args)

    assert result.returncode == 1
    assert "expectation mismatch (before exec)" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), f"push ran: {calls}"
    assert git("rev-parse", "refs/heads/feat/drift", cwd=remote).returncode != 0


@pytest.mark.binary("sandbox-git")
def test_guarded_nonzero_exec_status_propagates(tmp_path: Path) -> None:
    """A wrapped push that itself fails must propagate its nonzero status."""
    home, _, env, observed = guarded_fixture(tmp_path)
    # Push to an unreachable URL: git itself fails after the gate passes.
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run(
        [*dg, "remote", "set-url", "origin", str(tmp_path / "nonexistent-remote.git")],
        check=True,
    )
    url = subprocess.run(
        [*dg, "config", "--get-all", "remote.origin.url"],
        text=True, capture_output=True, check=True,
    ).stdout.strip()

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=url,
        ),
        "publish",
    ]
    result = sandbox_git(home, env, *args)

    assert result.returncode != 0
    assert result.returncode != 1 or "does not appear to be a git repository" in result.stderr, (
        result.stderr
    )


@pytest.mark.binary("sandbox-git")
def test_guarded_push_remote_no_refspec_resolves_via_push_default_upstream(
    tmp_path: Path,
) -> None:
    """push REMOTE without refspec: destination from push.default, not echo.

    Resolution is proven via --check-only JSON (no guards run). Execution
    then preserves the existing legacy upstream-branch guard, which rejects
    a differently-named upstream before any push runs.
    """
    import json as json_mod

    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "push", "origin", "HEAD:refs/heads/base"], check=True, capture_output=True)
    subprocess.run([*dg, "branch", "--set-upstream-to=origin/base"], check=True, capture_output=True)
    subprocess.run([*dg, "config", "push.default", "upstream"], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    expectations = guarded_prefix(
        root=str(home),
        head=observed["head"],
        branch=observed["branch"],
        upstream="origin:refs/heads/base",
        destination="origin:refs/heads/base",
        push_url=observed["url"],
    )

    check = sandbox_git_at(
        home,
        env_with_git_shim(env, recording),
        *expectations,
        "--check-only",
        "push",
        "origin",
    )
    assert check.returncode == 0, check.stderr
    payload = json_mod.loads(check.stdout)
    assert payload["observed"]["destination"] == "origin:refs/heads/base"
    assert payload["all_match"] is True

    execute = sandbox_git_at(
        home,
        env_with_git_shim(env, recording),
        *expectations,
        "push",
        "origin",
    )
    assert execute.returncode == 1
    assert "upstream branch 'base' differs from 'feat/test'" in execute.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls



@pytest.mark.binary("sandbox-git")
def test_guarded_push_remote_no_refspec_rejects_unsupported_push_default(
    tmp_path: Path,
) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "config", "push.default", "matching"], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [*expect_args(observed, home), "push", "origin"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "unsupported push.default 'matching'" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_push_remote_no_refspec_rejects_multiple_push_refspecs(
    tmp_path: Path,
) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "config", "remote.origin.push", "HEAD:refs/heads/a"], check=True)
    subprocess.run([*dg, "config", "--add", "remote.origin.push", "HEAD:refs/heads/b"], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [*expect_args(observed, home), "push", "origin"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "multiple remote.origin.push refspecs" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_multiple_effective_push_urls_rejected(tmp_path: Path) -> None:
    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "config", "--add", "remote.origin.url", str(tmp_path / "second.git")], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [*expect_args(observed, home), "publish"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "multiple effective push URLs" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
def test_guarded_push_remote_no_refspec_resolves_remote_push_refspec(
    tmp_path: Path,
) -> None:
    """A single remote.origin.push refspec determines the actual destination."""
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "config", "remote.origin.push", f"HEAD:refs/heads/{observed['branch']}"], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [*expect_args(observed, home), "push", "origin"]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 0, result.stderr
    final = [c for c in read_sentinel(sentinel) if "push" in c[:3]][-1]
    assert "--force" not in final, final
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_guarded_legacy_push_remains_unguarded_and_unmodified(tmp_path: Path) -> None:
    """Without expectation options the legacy paths are byte-for-byte legacy."""
    home, remote, env, observed = guarded_fixture(tmp_path)

    # Legacy explicit-refspec push with a short destination name still works.
    result = sandbox_git(home, env, "push", "origin", "HEAD:aliases")
    assert result.returncode == 0, result.stderr
    assert git("rev-parse", "refs/heads/aliases", cwd=remote).returncode == 0

    # Legacy refs/heads/SOURCE refspec still passes through unchanged.
    result2 = sandbox_git(home, env, "push", "origin", f"{observed['branch']}:refs/heads/short-src")
    assert result2.returncode == 0, result2.stderr
    assert git("rev-parse", "refs/heads/short-src", cwd=remote).returncode == 0


# --- Focused security-closure tests (B1, B2, I1, I3) ------------------------


@pytest.mark.binary("sandbox-git")
def test_guarded_push_remote_config_resolved_protected_destination_rejects(
    tmp_path: Path,
) -> None:
    """B1: remote.origin.push resolving to main must reject even when all
    six expectations match, using the ACTUAL push remote's default branch."""
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "config", "remote.origin.push", "HEAD:refs/heads/main"], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination="origin:refs/heads/main",
            push_url=observed["url"],
        ),
        "push",
        "origin",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "refusing to push protected/significant branch 'main'" in result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls
    assert git("rev-parse", "refs/heads/main", cwd=remote).returncode != 0


@pytest.mark.binary("sandbox-git")
def test_guarded_push_explicit_refspec_protected_destination_uses_actual_remote(
    tmp_path: Path,
) -> None:
    """B1: explicit refspec to the push remote's own default branch rejects."""
    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "push", "origin", "HEAD:refs/heads/trunk"], check=True, capture_output=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination="origin:refs/heads/trunk",
            push_url=observed["url"],
        ),
        "push",
        "origin",
        "HEAD:refs/heads/trunk",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)

    assert result.returncode == 1
    assert "refusing to push protected/significant branch 'trunk'" in result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "config_args",
    [
        ["config", "remote.origin.mirror", "true"],
        ["config", "push.followTags", "true"],
        ["config", "push.pushOption", "bypass"],
        ["config", "remote.origin.pushOption", "x"],
        ["config", "push.recurseSubmodules", "on"],
        ["config", "push.recurseSubmodules", "check"],
        ["config", "push.gpgSign", "true"],
        ["config", "push.gpgSign", "if-asked"],
        ["config", "remote.origin.mirror", "maybe"],
    ],
)
def test_guarded_push_widening_config_rejects(
    tmp_path: Path, config_args: list[str]
) -> None:
    """B2: push-widening effective config rejects guarded execution AND check-only."""
    import json as json_mod

    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, *config_args], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")
    fragment = "guarded push refuses"

    exec_result = sandbox_git_at(
        home, env_with_git_shim(env, recording), *expect_args(observed, home), "push", "origin"
    )
    assert exec_result.returncode == 1
    assert (
        "guarded push refuses" in exec_result.stderr
        or "malformed boolean" in exec_result.stderr
    ), exec_result.stderr

    sentinel2 = tmp_path / "check-only.log"
    recording2 = make_recording_git(sentinel2, shutil.which("git") or "git")
    check_result = sandbox_git_at(
        home,
        env_with_git_shim(env, recording2),
        *expect_args(observed, home),
        "--check-only",
        "push",
        "origin",
    )
    assert check_result.returncode == 1
    assert (
        fragment in check_result.stderr
        or "malformed boolean" in check_result.stderr
        or (
            check_result.stdout and json_mod.loads(check_result.stdout)["all_match"] is False
        )
    ), check_result.stderr + check_result.stdout

    calls = read_sentinel(sentinel)
    assert not any("push" in c[:3] for c in calls), calls


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "config_args",
    [
        ["config", "push.followTags", "false"],
        ["config", "push.recurseSubmodules", "no"],
        ["config", "push.gpgSign", "false"],
        ["config", "remote.origin.mirror", "false"],
    ],
)
def test_guarded_push_safe_widening_config_values_still_allowed(
    tmp_path: Path, config_args: list[str]
) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, *config_args], check=True)
    # Give the branch an upstream so plain `git push origin` succeeds.
    subprocess.run([*dg, "push", "-u", "origin", observed["branch"]], check=True, capture_output=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    result = sandbox_git_at(
        home,
        env_with_git_shim(env, recording),
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "push",
        "origin",
    )
    assert result.returncode == 0, result.stderr
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
def test_unguarded_legacy_tokens_after_subcommand_forward_unchanged(
    tmp_path: Path,
) -> None:
    """I1: unguarded calls may carry --expect-*/--check-only as literal data.

    The sentinel records the argv; the push itself must not run (no real
    commit/push happens — the failing git exits 99 before any effect).
    """
    home, _, env, observed = guarded_fixture(tmp_path)
    sentinel = tmp_path / "git-calls.log"
    fake_bin = make_failing_git(sentinel)

    result = sandbox_git_at(
        home,
        env_with_failing_git(env, fake_bin),
        "log",
        "--check-only",
        "--expect-root",
        "/tmp",
    )

    assert result.returncode == 99  # forwarded to git, which failed by design
    assert sentinel.exists(), "git must have been invoked"
    # make_failing_git logs space-joined argv: assert the literal tokens
    # forwarded unchanged after the wrapper's --git-dir/--work-tree prefix.
    logged = sentinel.read_text().strip().splitlines()[-1]
    tail = logged.split(" ", 2)[2] if logged.startswith("--git-dir=") else logged
    assert tail == "log --check-only --expect-root /tmp", logged


@pytest.mark.binary("sandbox-git")
def test_guarded_url_credentials_redacted_from_all_output(tmp_path: Path) -> None:
    """I3: userinfo never appears in stdout or stderr, on match or mismatch."""
    import json as json_mod

    secret = "user:supersecret@github.com"
    home, _, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "remote", "set-url", "origin", f"https://{secret}/kpiwko/dotfiles.git"], check=True)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    # Mismatch: wrong expected URL containing a DIFFERENT secret.
    args_mismatch = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url="https://other:wrongpass@github.com/kpiwko/dotfiles.git",
        ),
        "publish",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args_mismatch)
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "supersecret" not in combined
    assert "wrongpass" not in combined
    assert "expectation mismatch (before guards): push_url" in result.stderr

    # Check-only JSON reports the redacted observed URL.
    args_check = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream="none",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=f"https://{secret}/kpiwko/dotfiles.git",
        ),
        "--check-only",
        "publish",
    ]
    sentinel2 = tmp_path / "check-only.log"
    recording2 = make_recording_git(sentinel2, shutil.which("git") or "git")
    result2 = sandbox_git_at(home, env_with_git_shim(env, recording2), *args_check)
    assert result2.returncode == 0, result2.stderr
    assert "supersecret" not in result2.stdout + result2.stderr
    payload = json_mod.loads(result2.stdout)
    assert payload["all_match"] is True
    # `git remote get-url` itself strips userinfo, so the observed URL is
    # already credential-free; the wrapper's redaction additionally guards
    # the expected/mismatch reporting paths (asserted above).
    assert payload["observed"]["push_url"] == "https://github.com/kpiwko/dotfiles.git"
    assert "supersecret" not in result2.stdout


# --- Focused N1/N2 review fixes ---------------------------------------------


def append_repo_config(home: Path, fragment: str) -> None:
    """Append a raw config fragment to the fixture repo's config file.

    Used to create valueless (bare) keys that `git config <key> <value>`
    cannot write; never touches the real HOME config.
    """
    config = home / ".dotfiles" / "config"
    with open(config, "a", encoding="utf-8") as fh:
        fh.write(fragment)


def strip_git_prefix(call: list[str]) -> list[str]:
    return call[2:] if call and call[0].startswith("--git-dir=") else call


@pytest.mark.binary("sandbox-git")
def test_guarded_publish_network_guards_run_before_final_observation(
    tmp_path: Path,
) -> None:
    """N1: network-capable guards (remote show fallback) run BEFORE the last
    identity observation; after the final comparison only the push execs."""
    home, remote, env, observed = guarded_fixture(tmp_path)
    # No refs/remotes/origin/HEAD in this fixture: default_branch must use
    # the network-capable `remote show` fallback during the guard phase.
    assert not (home / ".dotfiles" / "refs" / "remotes" / "origin" / "HEAD").exists()
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    result = sandbox_git_at(
        home, env_with_git_shim(env, recording), *expect_args(observed, home), "publish"
    )
    assert result.returncode == 0, result.stderr
    stripped = [strip_git_prefix(c) for c in read_sentinel(sentinel)]
    head_reads = [i for i, c in enumerate(stripped) if "rev-parse" in c and c[-1] == "HEAD"]
    remote_shows = [i for i, c in enumerate(stripped) if "remote" in c and "show" in c]
    pushes = [i for i, c in enumerate(stripped) if "push" in c]
    assert head_reads and remote_shows and pushes, stripped
    last_head = head_reads[-1]
    assert max(remote_shows) < last_head, f"network guard after final observation: {stripped}"
    assert min(pushes) > last_head, stripped


@pytest.mark.binary("sandbox-git")
def test_guarded_push_origin_network_guards_run_before_final_observation(
    tmp_path: Path,
) -> None:
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    subprocess.run([*dg, "push", "-u", "origin", observed["branch"]], check=True, capture_output=True)
    assert not (home / ".dotfiles" / "refs" / "remotes" / "origin" / "HEAD").exists()
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    args = [
        *guarded_prefix(
            root=str(home),
            head=observed["head"],
            branch=observed["branch"],
            upstream=f"origin:refs/heads/{observed['branch']}",
            destination=f"origin:refs/heads/{observed['branch']}",
            push_url=observed["url"],
        ),
        "push",
        "origin",
    ]
    result = sandbox_git_at(home, env_with_git_shim(env, recording), *args)
    assert result.returncode == 0, result.stderr
    stripped = [strip_git_prefix(c) for c in read_sentinel(sentinel)]
    head_reads = [i for i, c in enumerate(stripped) if "rev-parse" in c and c[-1] == "HEAD"]
    remote_shows = [i for i, c in enumerate(stripped) if "remote" in c and "show" in c]
    pushes = [i for i, c in enumerate(stripped) if "push" in c]
    assert head_reads and remote_shows and pushes, stripped
    last_head = head_reads[-1]
    assert max(remote_shows) < last_head, f"network guard after final observation: {stripped}"
    assert min(pushes) > last_head, stripped


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "fragment",
    [
        '[remote "origin"]\n\tmirror\n',
        "[push]\n\tfollowTags\n",
        "[push]\n\tgpgSign\n",
        "[push]\n\trecurseSubmodules\n",
        "[push]\n\tpushOption\n",
    ],
)
def test_guarded_bare_valueless_widening_key_rejects(
    tmp_path: Path, fragment: str
) -> None:
    """N2: a valueless (bare) config key is git TRUE, not false — rejected."""
    home, _, env, observed = guarded_fixture(tmp_path)
    append_repo_config(home, fragment)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    result = sandbox_git_at(
        home, env_with_git_shim(env, recording), *expect_args(observed, home), "publish"
    )
    assert result.returncode == 1
    assert "guarded push refuses" in result.stderr, result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c for c in calls), calls


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "fragment",
    [
        '[remote "origin"]\n\tmirror =\n',
        "[push]\n\tfollowTags =\n",
        "[push]\n\tgpgSign =\n",
        "[push]\n\trecurseSubmodules =\n",
        "[push]\n\tpushOption =\n",
    ],
)
def test_guarded_explicit_empty_widening_keys_still_allowed(
    tmp_path: Path, fragment: str
) -> None:
    """N2: an explicitly empty value is git false/reset semantics — allowed."""
    home, remote, env, observed = guarded_fixture(tmp_path)
    append_repo_config(home, fragment)
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    result = sandbox_git_at(
        home, env_with_git_shim(env, recording), *expect_args(observed, home), "publish"
    )
    assert result.returncode == 0, result.stderr
    assert git("rev-parse", f"refs/heads/{observed['branch']}", cwd=remote).returncode == 0


@pytest.mark.binary("sandbox-git")
@pytest.mark.parametrize(
    "key,value",
    [("pushOption", "x"), ("mirror", "true")],
)
def test_guarded_case_sensitive_remote_subsection_widening_rejects(
    tmp_path: Path, key: str, value: str
) -> None:
    """N3: remote SUBSECTION names are case-sensitive — a widening setting on
    remote 'My Fork' (not 'origin') must still reject with the actual unsafe
    mirror/pushOption message, not a malformed/lookup artifact."""
    home, remote, env, observed = guarded_fixture(tmp_path)
    dg = ["git", f"--git-dir={home / '.dotfiles'}", f"--work-tree={home}"]
    # Case-sensitive subsection 'MyFork' (not 'origin'): proves the exact
    # emitted key is preserved for every per-key config lookup.
    subprocess.run([*dg, "remote", "add", "MyFork", str(remote)], check=True, capture_output=True)
    # Write the widening setting directly into the repo config so the
    # subsection case is exactly as emitted by --get-regexp.
    append_repo_config(home, f'[remote "MyFork"]\n\t{key} = {value}\n')
    sentinel = tmp_path / "git-calls.log"
    recording = make_recording_git(sentinel, shutil.which("git") or "git")

    exec_result = sandbox_git_at(
        home, env_with_git_shim(env, recording), *expect_args(observed, home), "publish"
    )
    assert exec_result.returncode == 1
    if key == "mirror":
        assert "guarded push refuses remote.MyFork.mirror (mirror)" in exec_result.stderr
    else:
        # --get-regexp lowercases the variable name: pushoption.
        assert "guarded push refuses remote.MyFork.pushoption (pushOption)" in exec_result.stderr
    assert "malformed" not in exec_result.stderr, exec_result.stderr
    assert "disappeared" not in exec_result.stderr, exec_result.stderr
    calls = read_sentinel(sentinel)
    assert not any("push" in c for c in calls), calls

    # Check-only must reject the same widening config without publication.
    sentinel2 = tmp_path / "check-only.log"
    recording2 = make_recording_git(sentinel2, shutil.which("git") or "git")
    check_result = sandbox_git_at(
        home,
        env_with_git_shim(env, recording2),
        *expect_args(observed, home),
        "--check-only",
        "publish",
    )
    assert check_result.returncode == 1
    assert "guarded push refuses remote.MyFork" in check_result.stderr
    calls2 = read_sentinel(sentinel2)
    assert not any("push" in c for c in calls2), calls2
