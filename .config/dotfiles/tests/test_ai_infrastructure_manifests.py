from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from conftest import ROOT


K8S_DIR = ROOT / ".config" / "k8s"
BASE = K8S_DIR / "base"
RUNTIME = K8S_DIR / "runtime"


def render(path: Path) -> str:
    result = subprocess.run(
        ["devcluster-kubectl", "kustomize", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def has_deployment_replicas(resources: str, name: str, replicas: int) -> bool:
    return bool(
        re.search(
            rf"kind: Deployment.*?\n  name: {name}\n.*?\n  replicas: {replicas}\n",
            resources,
            re.DOTALL,
        )
    )


def test_safe_base_includes_agentgateway_but_leaves_writers_stopped() -> None:
    resources = render(K8S_DIR)
    assert has_deployment_replicas(resources, "agentgateway", 0)
    assert has_deployment_replicas(resources, "mlflow", 0)
    assert has_deployment_replicas(resources, "otel-collector", 0)
    assert "nodePort: 17904" in resources
    assert "name: agentgateway-pvc" in resources
    assert "storageClassName: local-path" in resources


def test_runtime_starts_agentgateway_and_existing_telemetry_writers() -> None:
    resources = render(RUNTIME)

    for name in ("agentgateway", "mlflow", "otel-collector"):
        assert has_deployment_replicas(resources, name, 1)


def test_agentgateway_config_uses_expected_models_and_secret_boundary() -> None:
    config = (BASE / "agentgateway.yaml").read_text()
    deployment_manifest = (BASE / "agentgateway-deployment.yaml").read_text()

    assert "url: sqlite:///data/agentgateway.db" in config
    assert "mode: strict" in config
    for model in ("enmaas-opus-5-5", "enmaas-gpt-5-6-terra", "openai-gpt-5-6-terra", "enmaas-gpt-5-6-luna", "openai-gpt-5-6-luna", "spade", "gemini"):
        assert f"name: {model}" in config
    assert config.count('max_completion_tokens: "llmRequest.max_tokens"') == 2
    assert config.count("max_tokens: 'fail(\"remove\")'") == 2
    assert config.count("reasoning_effort: '\"none\"'") == 2
    assert "- model: openai-gpt-5-6-terra" in config
    assert config.count("- model: openai-gpt-5-6-luna") == 2
    assert "frontendPolicies:" in config
    assert "host: otel-collector.ai-dev.svc.cluster.local:4317" in config
    assert "protocol: grpc" in config
    assert 'x-mlflow-experiment-id: "$MLFLOW_EXPERIMENT_ID"' in config
    assert "agentgateway-secrets" in deployment_manifest
    assert "ai-factory-secrets" not in deployment_manifest
    assert "vertex-credentials.json" in deployment_manifest
    assert "name: MLFLOW_EXPERIMENT_ID" in deployment_manifest
    assert "modelCatalog:" in config
    assert "- file: /etc/agentgateway/catalog-overlay.json" in config


def test_agentgateway_catalog_overlay_and_kustomization() -> None:
    catalog_path = BASE / "catalog-overlay.json"
    catalog = json.loads(catalog_path.read_text())
    catalog_text = catalog_path.read_text()
    kustomization = (BASE / "kustomization.yaml").read_text()

    assert catalog_path.is_file()
    for model in ("gpt-5.6-terra", "gpt-5.6-luna", "claude-opus-5-5", "gemini-3.8-flash"):
        assert model in catalog_text
        assert any(model in provider.get("models", {}) for provider in catalog["providers"].values())
    assert "catalog-overlay.json" in kustomization
    assert "agentgateway-config" in kustomization


def test_opencode_agents_reference_only_agentgateway_models() -> None:
    config = json.loads((ROOT / ".config" / "opencode" / "opencode.jsonc").read_text())
    agents = ROOT / ".config" / "opencode" / "agents"

    assert config["model"] == "agentgateway-gemini/gemini"
    assert config["default_agent"] == "orchestrator"
    assert set(config["provider"]) == {"agentgateway", "agentgateway-gemini"}
    gemini_provider = config["provider"]["agentgateway-gemini"]
    assert gemini_provider["npm"] == "@ai-sdk/google"
    assert gemini_provider["options"]["baseURL"] == "{env:AGENTGATEWAY_GEMINI_BASE_URL}"
    assert gemini_provider["options"]["headers"] == {
        "Authorization": "Bearer {env:AGENTGATEWAY_API_KEY}"
    }
    assert gemini_provider["models"]["gemini"]["modelID"] == "gemini"
    otel_plugin = next(
        plugin
        for plugin in config["plugins"]
        if isinstance(plugin, dict) and plugin.get("package") == "@devtheops/opencode-plugin-otel"
    )
    assert otel_plugin["options"]["tracePropagationProviders"] == [
        "agentgateway",
        "agentgateway-gemini",
    ]
    assert otel_plugin["options"]["disabledMetrics"] == [
        "cost.usage",
        "session.cost.total",
        "model.usage",
    ]
    for agent in agents.glob("*.md"):
        frontmatter = agent.read_text().split("---", 2)[1]
        model = next(line.split(":", 1)[1].strip() for line in frontmatter.splitlines() if line.startswith("model:"))
        assert model in {
            "agentgateway/architect",
            "agentgateway/omnipower",
            "agentgateway/reviewer",
            "agentgateway/worker",
            "agentgateway-gemini/gemini",
        }

    assert "model: agentgateway-gemini/gemini" in (agents / "orchestrator.md").read_text()
    assert "model: agentgateway/architect" in (agents / "planner.md").read_text()
    orchestrator = (agents / "orchestrator.md").read_text()
    assert 'resource: "implement-local"' not in orchestrator
    assert 'resource: "implement-maas"' not in orchestrator


def test_mlflow_gateway_artifacts_are_removed() -> None:
    assert not (ROOT / ".config" / "mlflow" / "gateway.yaml").exists()
    assert not (K8S_DIR / "gateway-bootstrap").exists()
    assert not (ROOT / ".local" / "bin" / "mlflow-gateway-sync").exists()


def test_operator_docs_explain_agentgateway_telemetry_contract() -> None:
    k8s_readme = (K8S_DIR / "README.md").read_text()
    opencode_readme = (ROOT / ".config" / "opencode" / "README.md").read_text()
    env_example = (ROOT / ".config" / "opencode" / "env.example").read_text()

    assert "AgentGateway exports resolved provider, upstream model" in k8s_readme
    assert "realized cost" in k8s_readme
    assert "fixed MLflow experiment" in k8s_readme
    assert "agentgateway-gemini" in opencode_readme
    assert "Gemini API for `gemini`" in opencode_readme
    assert "new OpenCode session or service restart" in opencode_readme
    assert "AGENTGATEWAY_GEMINI_BASE_URL" in env_example
