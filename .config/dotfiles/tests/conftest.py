from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BIN = ROOT / ".local" / "bin"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--binary",
        action="append",
        default=[],
        help="run only tests owned by the named .local/bin executable; repeatable",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    selected = set(config.getoption("--binary"))
    if not selected:
        return
    keep: list[pytest.Item] = []
    drop: list[pytest.Item] = []
    for item in items:
        marker = item.get_closest_marker("binary")
        if marker and marker.args and marker.args[0] in selected:
            keep.append(item)
        else:
            drop.append(item)
    items[:] = keep
    config.hook.pytest_deselected(items=drop)


@pytest.fixture
def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("AI_DEV_", "DEVCLUSTER_", "LANGFUSE_", "CF_", "CLOUDFLARE_")):
            env.pop(key, None)
    return env


def run_script(path: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(path), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
