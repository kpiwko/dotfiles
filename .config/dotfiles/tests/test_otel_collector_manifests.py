from conftest import ROOT


K8S_DIR = ROOT / ".config" / "k8s"
K8S_BASE = K8S_DIR / "base"
OTEL_MANIFEST = K8S_BASE / "otel-collector.yaml"


def test_otel_collector_manifest_exists_and_uses_pinned_image() -> None:
    assert OTEL_MANIFEST.is_file()
    manifest = OTEL_MANIFEST.read_text()

    assert "kind: Deployment" in manifest
    assert "image: otel/opentelemetry-collector-k8s:0.123.1" in manifest


def test_otel_collector_resource_sizing() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "cpu: 50m" in manifest or 'cpu: "50m"' in manifest
    assert "memory: 64Mi" in manifest or 'memory: "64Mi"' in manifest
    assert "cpu: 500m" in manifest or 'cpu: "500m"' in manifest
    assert "memory: 512Mi" in manifest or 'memory: "512Mi"' in manifest


def test_otel_collector_health_probes() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "livenessProbe:" in manifest
    assert "readinessProbe:" in manifest
    assert manifest.count("path: /") >= 2
    assert manifest.count("port: 13133") >= 2


def test_otel_collector_otlp_http_receiver() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "receivers:" in manifest
    assert "otlp:" in manifest
    assert "http:" in manifest
    assert "endpoint: 0.0.0.0:4318" in manifest
    assert "include_metadata: true" in manifest


def test_otel_collector_batch_processor_preserves_experiment_id() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "batch:" in manifest
    assert "metadata_keys:" in manifest
    assert "x-mlflow-experiment-id" in manifest


def test_otel_collector_memory_limiter_processor() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "memory_limiter:" in manifest
    assert "check_interval: 1s" in manifest
    assert "limit_percentage: 75" in manifest
    assert "spike_limit_percentage: 15" in manifest


def test_otel_collector_health_check_extension() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "health_check:" in manifest
    assert "endpoint: 0.0.0.0:13133" in manifest


def test_otel_collector_headers_setter_extension() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "headers_setter/mlflow:" in manifest
    assert "action: upsert" in manifest
    assert "key: x-mlflow-experiment-id" in manifest
    assert "from_context: x-mlflow-experiment-id" in manifest


def test_otel_collector_otlphttp_exporter_authenticator() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "otlphttp/mlflow:" in manifest
    assert "endpoint: http://mlflow:5000" in manifest
    assert "authenticator: headers_setter/mlflow" in manifest


def test_otel_collector_traces_pipeline() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "pipelines:" in manifest
    assert "traces:" in manifest
    assert "receivers: [otlp]" in manifest
    assert "processors: [memory_limiter, batch]" in manifest
    assert "exporters: [otlphttp/mlflow]" in manifest
    assert "extensions: [health_check, headers_setter/mlflow]" in manifest


def test_otel_collector_service_nodeport_mapping() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "kind: Service" in manifest
    assert "type: NodePort" in manifest
    assert "port: 4318" in manifest
    assert "targetPort: 4318" in manifest
    assert "nodePort: 17903" in manifest


def test_kustomization_and_kind_config_include_otel_collector() -> None:
    kustomization = (K8S_DIR / "kustomization.yaml").read_text()
    kind_config = (K8S_DIR / "kind-config.yaml").read_text()

    assert "base/otel-collector.yaml" in kustomization
    assert "containerPort: 17903" in kind_config
    assert "hostPort: 17903" in kind_config


def test_mlflow_allowed_hosts_and_caddy_example() -> None:
    mlflow_manifest = (K8S_BASE / "mlflow.yaml").read_text()
    caddy_example = (ROOT / ".config" / "caddy" / "sites" / "otel.caddy.example").read_text()

    assert "--allowed-hosts" in mlflow_manifest
    assert "mlflow:*" in mlflow_manifest
    assert "otel.example.internal" in caddy_example
    assert "import cloudflare_tls" in caddy_example
    assert "reverse_proxy 127.0.0.1:17903" in caddy_example
