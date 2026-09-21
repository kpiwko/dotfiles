from conftest import ROOT


K8S_DIR = ROOT / ".config" / "k8s"
K8S_BASE = K8S_DIR / "base"


def test_mlflow_manifest_provides_persistent_tracking_service() -> None:
    manifest = (K8S_BASE / "mlflow.yaml").read_text()

    assert "name: mlflow-pvc" in manifest
    assert "storageClassName: standard" in manifest
    assert "storage: 10Gi" in manifest
    assert "mountPath: /mlflow" in manifest
    assert "image: ghcr.io/mlflow/mlflow:v3.16.1" in manifest
    assert "sqlite:////mlflow/mlflow.db" in manifest
    assert "/mlflow/artifacts" in manifest
    assert '- --workers\n            - "1"' in manifest
    assert 'memory: "2Gi"' in manifest


def test_mlflow_accepts_exported_and_local_hosts() -> None:
    manifest = (K8S_BASE / "mlflow.yaml").read_text()

    assert "--allowed-hosts" in manifest
    assert "mlflow.example.internal,localhost:*,127.0.0.1:*" in manifest
    assert "path: /health" in manifest
    assert "value: localhost:5000" in manifest


def test_mlflow_accepts_caddy_mapped_origin() -> None:
    manifest = (K8S_BASE / "mlflow.yaml").read_text()
    caddy_example = (ROOT / ".config" / "caddy" / "sites" / "mlflow.caddy.example").read_text()

    assert '- --cors-allowed-origins\n            - https://mlflow.example.internal' in manifest
    assert "header_up Host mlflow.example.internal" in caddy_example
    assert "header_up Origin https://mlflow.example.internal" in caddy_example


def test_mlflow_nodeport_is_mapped_and_exported() -> None:
    manifest = (K8S_BASE / "mlflow.yaml").read_text()
    kind_config = (K8S_DIR / "kind-config.yaml").read_text()
    caddy_example = (ROOT / ".config" / "caddy" / "sites" / "mlflow.caddy.example").read_text()
    readme = (K8S_DIR / "README.md").read_text()

    assert "nodePort: 17902" in manifest
    assert "containerPort: 17902" in kind_config
    assert "hostPort: 17902" in kind_config
    assert "reverse_proxy 127.0.0.1:17902" in caddy_example
    assert "http://127.0.0.1:17902" in readme
    assert "kubectl port-forward svc/mlflow 15000:5000 -n ai-dev" in readme
