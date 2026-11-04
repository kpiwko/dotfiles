#!/usr/bin/env python3
"""P0.3 offline migration proof for evals/agent-workflows (read-only).

Loads eval.git.yaml through the pinned harness EvalConfig.from_yaml, runs
the harness package-reuse validator and the native Harbor Task loader
against the destination-generated flat case, and exercises the
destination case's verifier positive/negative contract on disposable
copies. NO harness run lifecycle, no agent, no container, no network.

Run with the pinned external interpreter (AGENT_WORKFLOWS_TEST_PYTHON),
cwd = the agent-workflows project root.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
CASES = PROJECT / "cases"
CASE = CASES / "return-main-no-cleanup-v1"
WRAPPER = Path(
    os.environ.get("AGENT_WORKFLOWS_SANDBOX_GIT")
    or Path.home() / ".local" / "bin" / "sandbox-git"
)
# F3: portable temp base — env override, then the approved dir if it
# exists on this machine, else the platform default (never an absolute
# local path without fallback).
_TMP_ENV = os.environ.get("AGENT_WORKFLOWS_TEST_TMP")
_TMP_APPROVED = Path(
    "/private/var/folders/9m/5dhpkvg51750wz6ypg9nz25m0000gn/T/opencode"
)
if _TMP_ENV:
    TMP_BASE = Path(_TMP_ENV)
elif _TMP_APPROVED.is_dir():
    TMP_BASE = _TMP_APPROVED
else:
    import tempfile as _tf

    TMP_BASE = Path(_tf.gettempdir())


def _prereq(condition: bool, message: str) -> None:
    """Fail early with a clear prerequisite error, not a raw traceback."""
    if not condition:
        print(f"PREREQUISITE MISSING: {message}", file=sys.stderr)
        sys.exit(2)

results: list[tuple[str, bool, str]] = []

# Prerequisites (F3: clear early errors, not raw tracebacks):
_prereq(
    (CASE / "task.toml").is_file(),
    "generated case package not found at cases/return-main-no-cleanup-v1 — "
    "run the generator first: python3 harbor/git_pilot_package.py --out cases "
    "(see README 'Fresh-clone bootstrap')",
)
_prereq(
    WRAPPER.is_file(),
    f"sandbox-git wrapper not found at {WRAPPER} — set "
    "AGENT_WORKFLOWS_SANDBOX_GIT or install the wrapper at "
    "~/.local/bin/sandbox-git",
)
_prereq(
    (PROJECT / "harbor" / "image" / "bin" / "sandbox-git").is_file()
    and (PROJECT / "harbor" / "image" / "git_pilot_fixture.py").is_file(),
    "generated image vendored wrapper/fixture lib not found under "
    "harbor/image/ — they are produced by the generator "
    "(python3 harbor/git_pilot_package.py --out cases)",
)


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


# 1. Pinned harness typed config load (relative dataset path from cwd).
from agent_eval.config import EvalConfig  # noqa: E402

config = EvalConfig.from_yaml(PROJECT / "eval.git.yaml")
check(
    "EvalConfig.from_yaml loads eval.git.yaml",
    config is not None,
    f"dataset.path={config.dataset.path!r}",
)
check(
    "dataset.path is the flat destination case",
    str(config.dataset.path).endswith("cases/return-main-no-cleanup-v1"),
)

# 2. Harness package-reuse validator (the exact gate a future run uses).
from agent_eval.harbor.run import _validate_task_package_reuse  # noqa: E402

try:
    _validate_task_package_reuse(CASES, config, no_llm_judges=True)
    check("_validate_task_package_reuse accepts destination package", True,
          "no_llm_judges=True, deterministic-only package")
except ValueError as exc:
    check("_validate_task_package_reuse accepts destination package", False, str(exc))

# Negative control: the validator must reject a config-chain mismatch.
import tomllib  # noqa: E402

tmp = Path(tempfile.mkdtemp(
    prefix="agent-workflows-p03-neg-", dir=str(TMP_BASE)
))
neg_cases = tmp / "cases"
shutil.copytree(CASE, neg_cases / "return-main-no-cleanup-v1")
tt = neg_cases / "return-main-no-cleanup-v1" / "task.toml"
doc = tomllib.loads(tt.read_text())
doc["metadata"]["config_chain"] = ["eval.harbor.yaml"]
tt.write_text(tt.read_text().replace(
    'config_chain = ["eval.git.yaml"]',
    'config_chain = ["eval.harbor.yaml"]',
))
try:
    _validate_task_package_reuse(neg_cases, config, no_llm_judges=True)
    check("validator rejects stale config_chain", False, "accepted wrongly")
except ValueError as exc:
    check("validator rejects stale config_chain", True, str(exc)[:90])

# 3. Native Harbor Task loader on the destination package.
from harbor.models.task.task import Task  # noqa: E402

task = Task(CASE)
check("Harbor Task loads destination package", task.name ==
      "agent-workflows/return-main-no-cleanup-v1", f"name={task.name}")
check("Task paths resolve (config/tests/instruction/environment)",
      task.paths.config_path.is_file() and task.paths.tests_dir.is_dir()
      and task.paths.instruction_path.is_file()
      and task.paths.environment_dir.is_dir())
check("instruction carries case contract", "return to main" in task.instruction)
meta = tomllib.loads((CASE / "task.toml").read_text())["metadata"]
check("config_chain is [eval.git.yaml]", meta["config_chain"] == ["eval.git.yaml"],
      repr(meta["config_chain"]))
check("judge_mode deterministic-only", meta["judge_mode"] == "deterministic-only")
check("generated_by names relocated packager",
      meta["generated_by"].endswith("agent-workflows/harbor/git_pilot_package.py"),
      meta["generated_by"])

# 4. Verifier positive/negative on DISPOSABLE copies of the destination case.
sys.path.insert(0, str(PROJECT / "harbor"))
import verifier as gpv  # noqa: E402
from unittest import mock  # noqa: E402


def fresh_ws(name: str) -> Path:
    ws = tmp / name
    shutil.copytree(CASE / "environment" / "fixture", ws / "fixture",
                    symlinks=False)
    return ws


def run_verifier(ws: Path, records: Path | None = None) -> dict:
    reward_dir = tmp / f"reward-{ws.name}"
    with mock.patch.object(gpv, "REWARD_DIR", reward_dir):
        code = gpv.run_verification(
            records or (CASE / "tests"), ws, "fixture",
            PROJECT / "harbor" / "image" / "git_pilot_fixture.py",
            PROJECT / "harbor" / "image" / "bin" / "sandbox-git",
        )
    return {
        "reward": json.loads((reward_dir / "reward.json").read_text())["reward"],
        "verdict": json.loads((reward_dir / "verdict.json").read_text()),
        "code": code,
    }


def wrapper_env(mock_home: Path) -> dict:
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


def in_repo(ws: Path, *groups) -> None:
    repo = ws / "fixture" / "repo"
    for args in groups:
        r = subprocess.run([str(WRAPPER), *args], cwd=str(repo),
                           env=wrapper_env(ws / "fixture" / "mock-home"),
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


# Negative: pristine (pre-oracle) state must score 0 (main not fast-forwarded).
neg = run_verifier(fresh_ws("ws-negative"))
check("verifier: pristine state scores 0", neg["reward"] == 0.0,
      neg["verdict"]["reason"][:70])

# Positive: oracle end-state (fetch + switch main + ff-only) scores 1.
ws = fresh_ws("ws-positive")
in_repo(ws, ["checkout", "main"], ["fetch", "origin"],
        ["merge", "--ff-only", "origin/main"])
pos = run_verifier(ws)
check("verifier: oracle end-state scores 1", pos["reward"] == 1.0,
      pos["verdict"]["reason"][:70])

# Negative: empty/foreign trusted records fail closed (safe protocol).
empty = tmp / "empty-records"
empty.mkdir()
neg2 = run_verifier(fresh_ws("ws-empty-records"), records=empty)
check("verifier: empty trusted records UNSCORABLE 0",
      neg2["reward"] == 0.0 and "UNSCORABLE" in neg2["verdict"]["reason"])

shutil.rmtree(tmp, ignore_errors=True)

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} checks passed")
sys.exit(1 if fails else 0)
