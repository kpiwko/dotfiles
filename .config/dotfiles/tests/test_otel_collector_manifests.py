from conftest import ROOT


K8S_DIR = ROOT / ".config" / "k8s"
K8S_BASE = K8S_DIR / "base"
OTEL_MANIFEST = K8S_BASE / "otel-collector.yaml"


def test_otel_collector_manifest_exists_and_uses_pinned_image() -> None:
    assert OTEL_MANIFEST.is_file()
    manifest = OTEL_MANIFEST.read_text()

    assert "kind: Deployment" in manifest
    assert "image: otel/opentelemetry-collector-k8s:0.123.0" in manifest


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


def test_otel_collector_accepts_in_cluster_otlp_grpc() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "grpc:" in manifest
    assert "endpoint: 0.0.0.0:4317" in manifest
    assert "name: otlp-grpc" in manifest
    assert "port: 4317" in manifest
    assert "targetPort: 4317" in manifest
    assert "nodePort: 4317" not in manifest


def test_otel_collector_batch_processor_preserves_experiment_id() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "batch:" in manifest
    assert "metadata_keys:" in manifest
    assert "x-mlflow-experiment-id" in manifest


def test_otel_collector_experiment_header_has_no_fallback_default() -> None:
    manifest = OTEL_MANIFEST.read_text()

    # Batching must keep per-request experiment metadata so mixed-header
    # batches never lose the routing key, and the headers_setter must not gain
    # a default_value fallback that would silently reroute missing-header
    # traffic into an unintended experiment.
    assert 'metadata_keys: ["x-mlflow-experiment-id"]' in manifest
    assert "default_value" not in manifest


def test_otel_collector_maps_agentgateway_realized_costs() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert 'attributes["agw.ai.usage.cost.total"]' in manifest
    assert 'attributes["agw.ai.usage.cost.total"] == nil' in manifest
    assert 'set(attributes["agw.ai.usage.cost.total"], attributes["gen_ai.usage.cost"])' in manifest
    assert 'attributes["agw.ai.usage.cost.input"]' in manifest
    assert 'attributes["agw.ai.usage.cost.output"]' in manifest
    assert 'attributes["mlflow.llm.cost"]' in manifest


def test_otel_collector_guards_zero_cost_transformations() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert 'attributes["cost_usd"] != 0' in manifest
    assert 'attributes["session.total_cost_usd"] != 0' in manifest


# Exact MLflow 3.17.0 OpenInferenceTranslator.SPAN_KIND_TO_MLFLOW_TYPE allowlist
# (mlflow/tracing/otel/translation/open_inference.py in the pinned v3.17.0 image).
# Each kind maps to the same-named mlflow.entities.SpanType value. Do not add or
# invent kinds: unsupported kinds must stay unmapped (no UNKNOWN synthesis).
OPENINFERENCE_SPAN_KIND_ALLOWLIST = frozenset(
    {
        "TOOL",
        "CHAIN",
        "LLM",
        "RETRIEVER",
        "EMBEDDING",
        "AGENT",
        "RERANKER",
        "UNKNOWN",
        "GUARDRAIL",
        "EVALUATOR",
    }
)


def test_otel_collector_maps_openinference_span_types_without_overwrite() -> None:
    manifest = OTEL_MANIFEST.read_text()

    # MLflow 3.17.0 SQL span-type workaround: the SQL spans.type column is written
    # only from the inbound canonical mlflow.spanType, while openinference.span.kind
    # is translated into stored display attributes only, so OpenInference-only spans
    # get a NULL SQL type and disappear from grouped span_type metrics. The Collector
    # copies the canonical attribute before ingestion using the exact upstream
    # allowlist, only when the canonical attribute is absent.
    for kind in sorted(OPENINFERENCE_SPAN_KIND_ALLOWLIST):
        statement = (
            f'set(attributes["mlflow.spanType"], "{kind}") '
            f'where attributes["mlflow.spanType"] == nil '
            f'and attributes["openinference.span.kind"] == "{kind}"'
        )
        assert statement in manifest, f"missing guarded span-type mapping for {kind}"

    # Every canonical write must be nil-guarded: no overwrite of an existing
    # canonical value (including empty or non-string ones).
    for line in manifest.splitlines():
        if 'set(attributes["mlflow.spanType"]' in line:
            assert 'attributes["mlflow.spanType"] == nil' in line, (
                f"unguarded mlflow.spanType write: {line.strip()}"
            )

    # Exactly the allowlist kinds are mapped; nothing else invents a span type.
    mapped = {
        line.split('"')[-2]
        for line in manifest.splitlines()
        if 'set(attributes["mlflow.spanType"]' in line
    }
    assert mapped == OPENINFERENCE_SPAN_KIND_ALLOWLIST


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
    assert "processors: [memory_limiter, transform, batch]" in manifest
    assert "exporters: [otlphttp/mlflow, debug]" in manifest
    assert "extensions: [health_check, headers_setter/mlflow]" in manifest


def test_otel_collector_service_nodeport_mapping() -> None:
    manifest = OTEL_MANIFEST.read_text()

    assert "kind: Service" in manifest
    assert "type: NodePort" in manifest
    assert "port: 4318" in manifest
    assert "targetPort: 4318" in manifest
    assert "nodePort: 17903" in manifest


def test_kustomization_and_lima_config_expose_otel_collector() -> None:
    kustomization = (K8S_DIR / "kustomization.yaml").read_text()
    base_kustomization = (K8S_BASE / "kustomization.yaml").read_text()
    lima_config = (ROOT / ".config" / "lima" / "devcluster.yaml").read_text()

    assert "- base" in kustomization
    assert "otel-collector.yaml" in base_kustomization
    assert "guestPortRange: [17900, 17999]" in lima_config
    assert "hostPortRange: [17900, 17999]" in lima_config


def test_mlflow_allowed_hosts_and_caddy_example() -> None:
    mlflow_manifest = (K8S_BASE / "mlflow.yaml").read_text()
    caddy_example = (ROOT / ".config" / "caddy" / "sites" / "otel.caddy.example").read_text()

    assert "--allowed-hosts" in mlflow_manifest
    assert '- "*"' in mlflow_manifest
    assert "otel.example.internal" in caddy_example
    assert "import cloudflare_tls" in caddy_example
    assert "reverse_proxy 127.0.0.1:17903" in caddy_example
