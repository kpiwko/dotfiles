from conftest import ROOT


K8S_DIR = ROOT / ".config" / "k8s"
K8S_BASE = K8S_DIR / "base"
LIMA_CONFIG = ROOT / ".config" / "lima" / "devcluster.yaml"


def test_lima_template_uses_centos_k3s_without_a_second_runtime() -> None:
    template = LIMA_CONFIG.read_text()

    assert "templates/_images/centos-stream-9.yaml" in template
    assert "arch: aarch64" in template
    assert "legacyBIOS: true" in template
    assert 'memory: "16GiB"' in template
    assert 'disk: "100GiB"' in template
    assert "system: false" in template
    assert "user: false" in template
    assert "k3s-selinux" in template
    assert "k3s-selinux-1.6-1.el9.noarch.rpm" in template
    assert "iptables iptables-nft" in template
    assert "systemctl enable --now firewalld" in template
    assert "- traefik" in template
    assert "- servicelb" in template


def test_mlflow_manifest_provides_persistent_tracking_service() -> None:
    manifest = (K8S_BASE / "mlflow.yaml").read_text()

    assert "name: mlflow-pvc" in manifest
    assert "storageClassName: local-path" in manifest
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
    lima_config = LIMA_CONFIG.read_text()
    caddy_example = (ROOT / ".config" / "caddy" / "sites" / "mlflow.caddy.example").read_text()
    readme = (K8S_DIR / "README.md").read_text()

    assert "nodePort: 17902" in manifest
    assert "guestPortRange: [17900, 17999]" in lima_config
    assert "hostPortRange: [17900, 17999]" in lima_config
    assert "reverse_proxy 127.0.0.1:17902" in caddy_example
    assert "http://127.0.0.1:17902" in readme
    assert "devcluster-kubectl port-forward svc/mlflow 15000:5000 -n ai-dev" in readme


def test_mcp_nodeports_are_forwarded_to_caddy() -> None:
    manifest = (K8S_BASE / "mcp-servers.yaml").read_text()
    lima_config = LIMA_CONFIG.read_text()
    caddy_example = (ROOT / ".config" / "caddy" / "sites" / "mcp.caddy.example").read_text()

    assert "nodePort: 17980" in manifest
    assert "nodePort: 17981" in manifest
    assert "nodePort: 17982" in manifest
    assert "guestPortRange: [17900, 17999]" in lima_config
    assert "reverse_proxy 127.0.0.1:17980" in caddy_example
    assert "reverse_proxy 127.0.0.1:17981" in caddy_example
    assert "reverse_proxy 127.0.0.1:17982" in caddy_example


def test_kustomization_contains_only_mlflow_and_mcp_workloads() -> None:
    kustomization = (K8S_DIR / "kustomization.yaml").read_text()

    assert "base/mlflow.yaml" in kustomization
    assert "base/mcp-servers.yaml" in kustomization
    assert "postgres" not in kustomization
    assert "clickhouse" not in kustomization
    assert "redis" not in kustomization
    assert "minio" not in kustomization
