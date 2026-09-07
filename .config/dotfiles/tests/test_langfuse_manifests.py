from pathlib import Path

import pytest

from conftest import ROOT

pytestmark = pytest.mark.k8s
K8S_BASE = ROOT / ".config" / "k8s" / "base"


def read(name: str) -> str:
    return (K8S_BASE / name).read_text()


def test_langfuse_v4_images_are_exactly_pinned() -> None:
    web = read("langfuse-web.yaml")
    worker = read("langfuse-worker.yaml")

    assert "docker.langfuse.com/langfuse/langfuse:4.30.0" in web
    assert "docker.langfuse.com/langfuse/langfuse-worker:4.30.0" in worker
    assert "langfuse/langfuse:3" not in web
    assert "langfuse/langfuse-worker:3" not in worker


def test_langfuse_worker_waits_for_web_readiness() -> None:
    worker = read("langfuse-worker.yaml")

    assert "initContainers:" in worker
    assert "http://langfuse-web:3000/api/public/health" in worker


def test_clickhouse_meets_langfuse_v4_requirement() -> None:
    clickhouse = read("clickhouse.yaml")

    assert "clickhouse/clickhouse-server:26.4" in clickhouse


def test_minio_api_stays_internal_and_console_has_fixed_nodeport() -> None:
    minio = read("minio.yaml")

    assert "name: minio\n" in minio
    assert "type: ClusterIP" in minio
    assert "name: minio-console" in minio
    assert "nodePort: 17901" in minio
    assert "nodePort: 17982" not in minio
