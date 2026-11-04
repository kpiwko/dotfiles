#!/usr/bin/env python3
"""Generate the self-contained Harbor task package for the Git pilot.

Relocated 2026-11-03 (P0.2) from
``devel/adlc/experiments/02-git-operations/git-pilot-v1/harbor/git_pilot_package.py``
into the dotfiles agent-workflows project. Relocation adaptations:
  * ``FIXTURE_SOURCE`` now resolves the shared fixture library from the
    PROJECT ROOT (``HARBOR_DIR.parent``), not the old EXP parent-of-parent.
  * ``CASES_DIR`` is the flat destination case root ``<project>/cases``.
  * ``config_chain`` is ``["eval.git.yaml"]`` (renamed config).
  * ``generated_by`` labels name this project.
  * The sandbox-git wrapper source is resolved portably: the
    ``AGENT_WORKFLOWS_SANDBOX_GIT`` environment variable if set, else
    ``~/.local/bin/sandbox-git`` (HOME-relative, never a hardcoded
    absolute host path).

Produces the exact package layout Harbor's stock agents (``--agent
opencode``) consume directly — no custom agent, no custom adapter, no
control plane::

    <cases-dir>/<case-id>/
      task.toml               # schema 1.4, image + verifier + timeouts
      instruction.md          # resolved case prompt (repository path)
      solution/               # Harbor OracleAgent uploads this to /solution
        solve.sh              # trusted deterministic reference solution
      environment/            # Harbor auto-uploads this to the workspace
        fixture/              # the generated disposable fixture itself
          repo/               #   agent-visible worktree
          origin.git/         #   frozen bare origin
          mock-home/          #   isolated HOME for wrapper subprocesses
        input.yaml            # case input
        answers.yaml          # fixture provenance (trusted sidecar)
      tests/
        test.sh               # thin shim -> /opt/git-pilot/bin/verify.sh
        provenance.json       # trusted provenance record
        seed-state.json       # trusted pristine seed snapshot + manifest

Why the fixture travels in ``environment/`` and the trusted records do
not: Harbor uploads ``environment/`` into the agent workspace — exactly
the disposable, agent-writable surface this case needs. The trusted
records (provenance + pristine seed) are baked into the IMAGE at
/opt/git-pilot/records at build time; Harbor's task-setup lifecycle
uploads ``environment/`` to the workspace, and the image filesystem is
not the agent's writable surface. (Mechanism recorded from the pinned
upstream docs, deploy/harbor/README.md "Task generation" + tasks.py.)

Fixture origin URL: the generated repository's ``remote.origin.url`` is
a RELATIVE path (``../origin.git``) so the package is location
independent — the same package works in whatever workspace the runtime
picks, and the origin still resolves next to the repo. The verifier
anchors the bare origin on the TRUSTED manifest path, never on
``remote.origin.url`` (which the agent can repoint); the recorded URL
is compared for violation detection only.

Determinism: ``create_fixture`` is a fixed recipe (fixed bytes, fixed
commit metadata, fixed dates) executed through the SAME vendored
sandbox-git wrapper the verifier uses, under a mock HOME, inside the
generation root. Re-running the generator over fresh roots reproduces
the identical commit graph (same C0/Cremote/Cfeature object ids) and
identical untracked sentinel bytes — proven by the unit test.

Trusted-record rebasing: the seed snapshot and manifest are captured at
generation time under this host path and rebased onto the runtime
fixture root (``<workspace>/fixture``) by the verifier before the pure
comparison. Only path-valued keys are rewritten; object ids, digests,
refs, ancestry facts stay frozen.

This module is trusted setup only: no network, no model calls, no host
Git repository is read or written (the wrapper's mock HOME and explicit
cwd mean the host dotfiles repository can never be selected).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HARBOR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = HARBOR_DIR.parent
CASES_DIR = PROJECT_ROOT / "cases"
IMAGE_DIR = HARBOR_DIR / "image"
VERIFIER = HARBOR_DIR / "verifier.py"

CASE_ID = "return-main-no-cleanup-v1"
# Harbor 0.25.0 PackageInfo.name must match ORG_NAME_PATTERN
# (^[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9._-]*$): org/name.
TASK_NAME = "agent-workflows/return-main-no-cleanup-v1"
TASK_DESCRIPTION = (
    "Basic Git-task END-STATE pilot: return to main and fast-forward it to "
    "origin/main, preserving feature/keep-history and the untracked user "
    "file; no cleanup, commit, push, or review. Deterministic final-state "
    "verifier; procedure_attempt_coverage: not_measured."
)

# Fixed container paths baked by harbor/image/Containerfile.
IMAGE_PILOT_ROOT = "/opt/git-pilot"
IMAGE_VERIFY_SH = f"{IMAGE_PILOT_ROOT}/bin/verify.sh"
# The vendored sandbox-git wrapper's fixed in-image path (used by the
# trusted reference solution's SOLVE_SH and recorded in provenance).
IMAGE_VERIFY_WRAPPER = f"{IMAGE_PILOT_ROOT}/bin/sandbox-git"

# Pinned to the actually-built local image (historical source
# runtime-lock.json images.final: localhost/git-pilot-harbor:1.0.0,
# digest sha256:6059c19399ba1481b11d6803dc7dde34070cb75ecb0bada484b0e20f2519bca7).
# That image is a SOURCE-project environment artifact: recorded here as
# provenance only, not proof of a fresh destination build.
DEFAULT_IMAGE = "localhost/git-pilot-harbor:1.0.0"
DEFAULT_WORKDIR = "/workspace"

GENERATED_BY = "evals/agent-workflows/harbor/git_pilot_package.py"
CONFIG_CHAIN = "eval.git.yaml"


def _resolve_wrapper_source() -> Path:
    """Resolve the reviewed sandbox-git wrapper portably.

    ``AGENT_WORKFLOWS_SANDBOX_GIT`` env var wins; otherwise the canonical
    dotfiles-managed ``~/.local/bin/sandbox-git`` (HOME-relative).
    """
    override = os.environ.get("AGENT_WORKFLOWS_SANDBOX_GIT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "bin" / "sandbox-git"


# Shared fixture library lives at the project root (relocation: the
# source resolved it from the EXP parent-of-parent directory).
FIXTURE_SOURCE = PROJECT_ROOT / "git_pilot_fixture.py"

PROMPT_TEMPLATE = (
    "In {repository}, return to main and synchronize it with origin/main "
    "using fast-forward only. Do not clean up or delete branches or files. "
    "Preserve all existing work. Do not commit, push, or create a review. "
    "Report the resulting branch and synchronization status."
)

TASK_TOML = """# Harbor task config generated by git_pilot_package.py
# (agent-workflows relocated packaging; dotfiles P0.2).
#
# schema_version follows Harbor 0.25.0 TaskConfig default ("1.4").
# The agent runs as an explicit non-root UID (1001) so it cannot overwrite
# the root-owned trusted verifier code/records baked at /opt/git-pilot;
# the verifier runs as root because it must write expected/manifest.json
# next to the agent-writable fixture. No policy weakening: these are the
# exact container users, no privileged flags.
schema_version = "1.4"

[task]
name = "{task_name}"
description = "{task_description}"

[metadata]
generated_by = "{generated_by}"
case_id = "{case_id}"
# Framework-accepted value: agent-eval-harness _validate_task_package_reuse
# accepts only None|"full"|"deterministic-only". The end-state-only scope
# label is retained separately in [task].description ("deterministic
# final-state verifier") together with procedure_attempt_coverage below.
judge_mode = "deterministic-only"
procedure_attempt_coverage = "not_measured"
config_chain = ["{config_chain}"]

[environment]
docker_image = "{image}"
workdir = "{workdir}"

[verifier]
timeout_sec = {verifier_timeout}
user = "root"

[agent]
timeout_sec = {agent_timeout}
user = "1001"
"""

TEST_SH = """#!/bin/bash
# Harbor verifier shim: run the deterministic final-state oracle baked
# into the image (trusted records + vendored wrapper + fixture library)
# against the agent's actual workspace state.
#
# TRUSTED STARTUP CONTRACT (package-level, review fix): before ANY Python
# runs, this shim pins a trusted environment so an agent-planted
# usercustomize/sitecustomize module under the agent-writable workspace
# (HOME=/workspace in the image ENV, or fixture/mock-home) can never run
# inside the root verifier's Python:
#   * PATH is reset to the trusted fixed image paths, /opt/app-root/bin
#     FIRST (the UBI scl Python 3.12 that carries the image's PyYAML);
#     never resolve python3 to /usr/bin/python3.9 by dropping it.
#   * PYTHONPATH / PYTHONHOME / PYTHONUSERBASE are unset (the vendored
#     fixture lib is re-anchored by the verifier itself, not by PATH
#     inheritance), and PYTHONNOUSERSITE=1 + HOME=/root are exported so
#     no user-site tree of the agent's is ever on sys.path.
# The prelude itself runs as `python3 -I` (isolated: no user site, no
# PYTHONPATH, no sitecustomize/usercustomize) from the fixed trusted
# path. If the prelude refuses, a flat numeric reward 0 plus an
# UNSCORABLE sidecar is written and the shim exits nonzero — the real
# verifier never starts against an unvalidated surface.
set -o pipefail

mkdir -p /logs/verifier

# The fixture root under the workspace (Harbor uploads environment/ into
# the workspace at trial start; the fixture travels inside the package).
export GIT_PILOT_WORKSPACE="${{GIT_PILOT_WORKSPACE:-/workspace}}"
export GIT_PILOT_FIXTURE_DIR="${{GIT_PILOT_FIXTURE_DIR:-fixture}}"

# Trusted fixed interpreter: /opt/app-root/bin/python3 is the image's
# scl Python 3.12 (the one verify.sh's verifier also runs under, with
# PyYAML importable). -I implies -E -s: isolated mode ignores
# PYTHONPATH/PYTHONHOME/PYTHONUSERBASE and all user site-packages.
TRUSTED_PYTHON="/opt/app-root/bin/python3"
if [ ! -x "$TRUSTED_PYTHON" ]; then
  printf '{{"reward": 0.0}}\\n' > /logs/verifier/reward.json
  printf '0.0\\n' > /logs/verifier/reward.txt
  printf '{{"case_id": "{case_id}", "verifier": "git-pilot-harbor-final-state/1", "procedure_attempt_coverage": "not_measured", "reason": "UNSCORABLE: trusted python interpreter missing at /opt/app-root/bin/python3", "failures": []}}\\n' > /logs/verifier/verdict.json
  exit 1
fi

# Hard env reset BEFORE any Python: trusted PATH (app-root first), no
# Python path inheritance, no user site, root HOME.
unset PYTHONPATH PYTHONHOME PYTHONUSERBASE
export PATH="/opt/app-root/bin:/opt/git-pilot/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONNOUSERSITE=1
export HOME=/root

FIXTURE_ROOT="${{GIT_PILOT_WORKSPACE}}/${{GIT_PILOT_FIXTURE_DIR}}"

# Isolated stdlib-only prelude: validate the fixture components with
# lstat (links and non-directories refused, never followed), then reset
# ONLY fixture/mock-home to a fresh empty real 0755 directory. This runs
# before the root verifier so the agent's mock-home (which wrapper
# subprocesses would otherwise use as HOME, picking up any planted
# .local user site) is empty and link-free at measurement time. It
# never touches any path outside $FIXTURE_ROOT and never follows links.
"$TRUSTED_PYTHON" -I - "$FIXTURE_ROOT" <<'PRELUDE_EOF'
import json
import os
import shutil
import stat
import sys
from pathlib import Path


def refuse(reason):
    payload = {{
        "case_id": "{case_id}",
        "verifier": "git-pilot-harbor-final-state/1",
        "procedure_attempt_coverage": "not_measured",
        "reason": f"UNSCORABLE: prelude refused: {{reason}}",
        "failures": [],
    }}
    reward_dir = Path("/logs/verifier")
    try:
        reward_dir.mkdir(parents=True, exist_ok=True)
        (reward_dir / "reward.json").write_text(
            json.dumps({{"reward": 0.0}}) + "\\n", encoding="utf-8"
        )
        (reward_dir / "reward.txt").write_text("0.0\\n", encoding="utf-8")
        (reward_dir / "verdict.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8"
        )
    except OSError:
        pass
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(1)


fixture_root = Path(sys.argv[1]).resolve()

# The fixture root must be a real directory strictly inside /workspace
# (not /workspace itself, not a link), measured with lstat only.
workspace = Path("/workspace").resolve()
if fixture_root == workspace or workspace not in fixture_root.parents:
    refuse(f"fixture root {{fixture_root}} is not strictly inside /workspace")
if len(fixture_root.parts) < 3:
    refuse(f"fixture root path too shallow: {{fixture_root}}")

current = workspace
for segment in fixture_root.relative_to(workspace).parts:
    current = current / segment
    try:
        st = os.lstat(current)
    except OSError as exc:
        refuse(f"fixture component unreadable: {{current}} ({{exc}})")
    if stat.S_ISLNK(st.st_mode):
        refuse(f"fixture component is a symlink (never followed): {{current}}")
    if not stat.S_ISDIR(st.st_mode):
        refuse(f"fixture component is not a real directory: {{current}}")


def component(name):
    path = fixture_root / name
    try:
        st = os.lstat(path)
    except OSError as exc:
        refuse(f"fixture component missing: {{path}} ({{exc}})")
    if stat.S_ISLNK(st.st_mode):
        refuse(f"fixture component is a symlink (never followed): {{path}}")
    if not stat.S_ISDIR(st.st_mode):
        refuse(f"fixture component is not a real directory: {{path}}")
    return path


repo = component("repo")
component("origin.git")
mock_home = component("mock-home")

if not (repo / ".git").exists():
    refuse(f"fixture root has no repository at {{repo}}/.git")

# Fresh contained mock HOME: replace ONLY fixture/mock-home with a new
# empty real 0755 directory. The path was just validated link-free by
# lstat, so rename+mkdir cannot follow an agent-planted link; the
# replacement happens entirely inside the fixture root. The old
# (agent-owned) tree is moved to a sibling name inside the same fixture
# root and then removed with trusted shutil from the validated path —
# never a shell rm -rf on an unchecked path.
replacement = fixture_root / ".mock-home-reset"
if replacement.exists() or replacement.is_symlink():
    refuse(f"unexpected pre-existing path at {{replacement}}")
os.rename(mock_home, replacement)
mock_home.mkdir(mode=0o755)
try:
    os.chmod(mock_home, 0o755)
    if not mock_home.is_dir() or mock_home.is_symlink():
        refuse("fresh mock-home is not a real directory")
    shutil.rmtree(replacement)
except OSError as exc:
    refuse(f"failed to reset mock-home: {{exc}}")

print(json.dumps({{"prelude": "ok", "mock_home": str(mock_home)}}))
PRELUDE_EOF
PRELUDE_STATUS=$?
if [ "$PRELUDE_STATUS" -ne 0 ]; then
  # Fail closed with Harbor's numeric contract: flat reward 0 plus the
  # UNSCORABLE sidecar (the prelude prints its own verdict payload).
  mkdir -p /logs/verifier
  printf '{{"reward": 0.0}}\\n' > /logs/verifier/reward.json
  printf '0.0\\n' > /logs/verifier/reward.txt
  if [ ! -s /logs/verifier/verdict.json ]; then
    printf '{{"case_id": "{case_id}", "verifier": "git-pilot-harbor-final-state/1", "procedure_attempt_coverage": "not_measured", "reason": "UNSCORABLE: trusted startup prelude failed", "failures": []}}\\n' > /logs/verifier/verdict.json
  fi
  exit 1
fi

# Ownership normalization for the root verifier's read-only measurement:
# the agent (UID 1001) owns the uploaded fixture, and Git's
# dubious-ownership protection refuses root snapshots of repositories
# owned by another UID. Ownership is not part of the measured contract
# (refs, object ids, digests and bytes are); no refs or file content are
# touched. chown does not follow symlinks (default -R semantics), so an
# agent-planted link cannot redirect this write.
chown -R 0:0 "$FIXTURE_ROOT"

bash "{verify_sh}"
exit $?
"""

# Trusted reference solution consumed by the stock Harbor OracleAgent
# (harbor 0.25.0 harbor/agents/oracle.py: solution/ is uploaded to
# /solution AFTER the environment is staged, chmod +x as root, executed
# with stdout captured to /logs/agent/oracle.txt). This is the stock
# Harbor oracle API — no custom agent, no model, no auth anywhere.
#
# Deterministic ORACLE asset, NOT an OpenCode/LLM quality claim: it is the
# reference end-state operation sequence used to validate the task adapter
# (Harbor's adapter-review contract: "oracle solutions pass with 100%
# reward"). Scope labels stay honest: judge_mode deterministic-only
# (final-state verifier); procedure_attempt_coverage not_measured.
#
# Contract (asserted by tests/test_git_pilot_harbor.py):
#   * every Git operation goes through the vendored sandbox-git wrapper at
#     the fixed container path /opt/git-pilot/bin/sandbox-git;
#   * the target repository is the FIXED fixture repo /workspace/fixture/repo,
#     addressed with git's global -C flag so no working-directory change is
#     ever needed (the trial workdir /workspace equals the image HOME, which
#     the wrapper's repository-selection guard refuses by design);
#   * exactly one operation per line: fetch origin, switch main,
#     merge --ff-only origin/main;
#   * raw Git invocation, history rewrites, branch deletion, publication and
#     working-tree pruning are all out of scope for this reference sequence;
#   * no expected-state anchors appear here (they stay in the trusted
#     in-image records, never agent-visible).
SOLVE_SH = """#!/bin/bash
# Trusted reference solution for the stock Harbor OracleAgent.
# Deterministic ORACLE asset (see git_pilot_package.py SOLVE_SH contract);
# procedure_attempt_coverage: not_measured.
set -eo pipefail

REPO="/workspace/fixture/repo"
MOCK_HOME="/workspace/fixture/mock-home"
WRAPPER="/opt/git-pilot/bin/sandbox-git"

# Isolated HOME for wrapper subprocesses: the trial workdir equals the
# image HOME, which the wrapper's repository-selection guard refuses; the
# fixture's mock HOME keeps the wrapper in plain project-repository mode.
# Neutralized Git config, no pager, no prompts, fixed locale/clock.
export HOME="$MOCK_HOME"
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
export GIT_CONFIG_NOSYSTEM=1
export GIT_TERMINAL_PROMPT=0
export LC_ALL=C
export TZ=UTC

"$WRAPPER" -C "$REPO" fetch origin
"$WRAPPER" -C "$REPO" switch main
"$WRAPPER" -C "$REPO" merge --ff-only origin/main
"""

INPUT_YAML = """# Case: return-main-no-cleanup-v1 (Harbor packaging of the B3.1 pilot case).
#
# The prompt substitutes only the disposable repository path inside the
# agent's own workspace. Expected object ids and history are NOT shown to
# the agent; they live in the trusted in-image records under
# /opt/git-pilot/records (outside the agent's write boundary).
schema_version: 1
id: return-main-no-cleanup-v1
prompt: >-
  {prompt}
metadata:
  kind: synthetic
  domain: git-workflows
  packaging: harbor
  procedure_attempt_coverage: not_measured
"""

ANSWERS_YAML = """# TRUSTED fixture provenance (NOT agent-visible; travels in the task
# package's tests/ dir, which Harbor uploads to /tests, not to the agent
# workspace). Records how the fixture was generated so an operator can
# audit/reproduce: fixed recipe, vendored wrapper, mock HOME, relative
# origin URL. The expected-state anchors themselves live in
# /opt/git-pilot/records (image-baked) and in tests/seed-state.json.
case_id: return-main-no-cleanup-v1
fixture:
  generator: evals/agent-workflows/harbor/git_pilot_package.py
  fixture_library: git_pilot_fixture.py (vendored copy, sha256 recorded)
  wrapper: sandbox-git (vendored byte-exact copy, sha256 recorded)
  origin_url: ../origin.git (relative; location independent)
  mock_home: fixture/mock-home (isolated HOME for every subprocess)
procedure_attempt_coverage: not_measured
"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_fixture_module():
    """Import the shared fixture helper from the project root."""
    source = FIXTURE_SOURCE.resolve()
    if not source.is_file():
        raise FileNotFoundError(
            f"fixture helper not found at the project root: {source}"
        )
    spec = importlib.util.spec_from_file_location("git_pilot_fixture", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wrapper_env(mock_home: Path) -> dict:
    """Isolated env for wrapper subprocesses (mock HOME, no host config)."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(mock_home),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "TZ": "UTC",
    }


def _vendor_wrapper(wrapper: Path) -> dict:
    """Vendor the EXPLICITLY passed sandbox-git wrapper into the image tree.

    ``wrapper`` is the exact validated ``Path`` the caller passed (CLI
    ``--wrapper``, or the portable default) — the SAME wrapper
    ``create_fixture`` uses, so the image copy, the fixture Git and the
    recorded provenance always describe one identical wrapper. The copy
    is byte-exact; its sha256 is recorded so provenance and unit tests
    pin exactly which wrapper bytes the fixture generator and the
    verifier execute. The copy keeps mode 0755.
    """
    target = IMAGE_DIR / "bin" / "sandbox-git"
    source = Path(wrapper)
    if not source.is_file():
        raise FileNotFoundError(
            f"reviewed sandbox-git wrapper not found at: {source}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    mode = target.stat().st_mode
    os.chmod(target, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return {
        "source": str(source),
        "sha256": _sha256_file(target),
        "bytes": target.stat().st_size,
    }


def _vendor_fixture_lib() -> dict:
    """Vendor the reviewed fixture helper into the image tree."""
    source = FIXTURE_SOURCE.resolve()
    target = IMAGE_DIR / "git_pilot_fixture.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "source": str(source),
        "sha256": _sha256_file(target),
        "bytes": target.stat().st_size,
    }


def _vendor_verifier() -> None:
    """Vendor the deterministic verifier into the image tree (byte-exact
    copy of ``harbor/verifier.py``; the Containerfile bakes it at
    /opt/git-pilot/bin/verifier.py and the unit tests pin the identity)."""
    target = IMAGE_DIR / "bin" / "verifier.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VERIFIER, target)


def _count_files(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


def generate_package(
    out_dir: Path,
    *,
    image: str = DEFAULT_IMAGE,
    workdir: str = DEFAULT_WORKDIR,
    agent_timeout: int = 900,
    verifier_timeout: int = 300,
    wrapper: Path | None = None,
    fixture_root_name: str = "fixture",
) -> tuple[Path, dict]:
    """Generate the complete Harbor task package.

    Returns ``(task_dir, provenance)``. All Git runs through ``wrapper``
    with cwd inside the generation root and a mock HOME; no host
    repository is touched.
    """
    if wrapper is None:
        wrapper = _resolve_wrapper_source()
    out_dir = Path(out_dir)
    task_dir = out_dir / CASE_ID
    if task_dir.exists():
        raise RuntimeError(
            f"task package dir already exists; refusing to overwrite: {task_dir}"
        )

    wrapper = Path(wrapper)
    if not wrapper.is_file():
        raise FileNotFoundError(f"sandbox-git wrapper not found at: {wrapper}")

    # 1. Vendor the passed wrapper (SAME wrapper create_fixture uses)
    #    + fixture library + verifier into the image tree.
    wrapper_record = _vendor_wrapper(wrapper)
    fixture_record = _vendor_fixture_lib()
    _vendor_verifier()

    # 2. Generate the disposable fixture DIRECTLY inside the package's
    #    environment/ dir (Harbor uploads environment/ to the workspace at
    #    trial start). create_fixture refuses a nonempty root, so the task
    #    dir must be fresh — checked above.
    gpf = _load_fixture_module()
    env_dir = task_dir / "environment"
    fixture_root = env_dir / fixture_root_name
    env_dir.mkdir(parents=True, exist_ok=True)
    manifest = gpf.create_fixture(fixture_root, wrapper)

    # 3. Repoint remote.origin.url to a RELATIVE path so the package is
    #    location independent. The verifier anchors on the trusted
    #    manifest's origin path (rebased to the runtime fixture root),
    #    never on this URL; the snapshot also records it for
    #    before/after repoint detection.
    repo = fixture_root / "repo"
    origin_url = "../origin.git"
    result = subprocess.run(
        [str(wrapper), "remote", "set-url", "origin", origin_url],
        cwd=str(repo),
        env=_wrapper_env(fixture_root / "mock-home"),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"failed to set relative origin URL: {result.stderr.strip()}"
        )

    # 3b. Re-seal the trusted metadata baseline AFTER the config rewrite
    #     above: create_fixture sealed it before the URL change, and the
    #     snapshot's fail-closed metadata gate compares live .git/config
    #     against the manifest at <fixture_root>/expected/manifest.json.
    #     The URL is now part of the trusted expected state, so the
    #     expected origin URL anchor becomes the relative URL the
    #     repository actually records. The re-sealed manifest is written
    #     to the fixture's expected/ dir (the path the gate reads); it is
    #     stripped from the agent-visible package in step 4b below.
    manifest["trusted_metadata"] = gpf.snapshot_trusted_metadata(repo)
    manifest["origin_url_expected"] = origin_url
    (fixture_root / "expected" / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # 4. Capture the pristine seed snapshot NOW (trusted side of the
    #    boundary): this is the before-state the verifier compares
    #    against. Taken with the same hardened snapshot path the verifier
    #    uses (symlink refusal, metadata gate, neutralized read-only Git).
    seed_snapshot = gpf.snapshot_fixture(repo, wrapper)

    # 4b. Strip the trusted expected/ dir from the agent-visible package.
    #     The seed snapshot embeds the anchors the verifier needs; at
    #     runtime the verifier MATERIALIZES expected/manifest.json (from
    #     the trusted in-image records) only while it measures the
    #     repository, after the agent is done. The agent therefore never
    #     sees the expected object ids during its run.
    shutil.rmtree(fixture_root / "expected")
    file_count = _count_files(fixture_root)

    # 4c. Trusted reference solution for the stock Harbor OracleAgent.
    #     solve.sh is a package asset the oracle uploads to /solution and
    #     executes AFTER the environment is staged (stock Harbor API). It
    #     never enters environment/, so the agent workspace never sees it;
    #     it contains no expected-state anchors (those live in the trusted
    #     records only).
    solution_dir = task_dir / "solution"
    solution_dir.mkdir(parents=True, exist_ok=True)
    solve_sh = solution_dir / "solve.sh"
    solve_sh.write_text(SOLVE_SH, encoding="utf-8")
    mode = solve_sh.stat().st_mode
    os.chmod(solve_sh, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    solution_record = {
        "path": "solution/solve.sh",
        "agent": "oracle (stock Harbor OracleAgent; no model, no auth)",
        "wrapper_path": IMAGE_VERIFY_WRAPPER,
        "repo_path": f"{workdir}/{fixture_root_name}/repo",
        "operations": [
            "fetch origin",
            "switch main",
            "merge --ff-only origin/main",
        ],
        "sha256": _sha256_file(solve_sh),
    }

    # 5. Trusted records for the image (records/ baked at build time).
    provenance = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "task_name": TASK_NAME,
        "generated_by": GENERATED_BY,
        "image_pilot_root": IMAGE_PILOT_ROOT,
        "wrapper": wrapper_record,
        "fixture_library": fixture_record,
        "origin_url_relative": origin_url,
        "fixture_file_count": file_count,
        "procedure_attempt_coverage": "not_measured",
        "solution": solution_record,
        "verifier": "harbor/verifier.py (deterministic final-state oracle)",
        "verifier_sha256": _sha256_file(VERIFIER),
    }
    seed = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "snapshot": seed_snapshot,
        "manifest": manifest,
    }
    tests_dir = task_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (tests_dir / "seed-state.json").write_text(
        json.dumps(seed, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # 6. task.toml + instruction.md + input.yaml + answers.yaml + test.sh.
    (task_dir / "task.toml").write_text(
        TASK_TOML.format(
            task_name=TASK_NAME,
            task_description=TASK_DESCRIPTION,
            generated_by=GENERATED_BY,
            config_chain=CONFIG_CHAIN,
            case_id=CASE_ID,
            image=image,
            workdir=workdir,
            verifier_timeout=verifier_timeout,
            agent_timeout=agent_timeout,
        ),
        encoding="utf-8",
    )

    repository_in_workspace = f"{workdir}/{fixture_root_name}/repo"
    (task_dir / "instruction.md").write_text(
        PROMPT_TEMPLATE.format(repository=repository_in_workspace) + "\n",
        encoding="utf-8",
    )

    (env_dir / "input.yaml").write_text(
        INPUT_YAML.format(
            prompt=PROMPT_TEMPLATE.format(repository=repository_in_workspace)
        ),
        encoding="utf-8",
    )
    (env_dir / "answers.yaml").write_text(ANSWERS_YAML, encoding="utf-8")

    test_sh = tests_dir / "test.sh"
    test_sh.write_text(
        TEST_SH.format(verify_sh=IMAGE_VERIFY_SH, case_id=CASE_ID),
        encoding="utf-8",
    )
    mode = test_sh.stat().st_mode
    os.chmod(test_sh, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return task_dir, provenance


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", required=True,
        help="output dir for the package (default: the project's cases/ root)",
    )
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR)
    parser.add_argument(
        "--wrapper", default=None,
        help="sandbox-git wrapper path (default: AGENT_WORKFLOWS_SANDBOX_GIT "
             "or ~/.local/bin/sandbox-git)",
    )
    args = parser.parse_args(argv)
    task_dir, _provenance = generate_package(
        Path(args.out),
        image=args.image,
        workdir=args.workdir,
        wrapper=Path(args.wrapper) if args.wrapper else None,
    )
    print(f"generated {task_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
