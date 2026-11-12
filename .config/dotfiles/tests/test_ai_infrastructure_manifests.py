from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


K8S_DIR = ROOT / ".config" / "k8s"
BASE = K8S_DIR / "base"
RUNTIME = K8S_DIR / "runtime"
AGENT_SANDBOX = K8S_DIR / "agent-sandbox"


def render(path: Path) -> str:
    cmd = shutil.which("kubectl") or shutil.which("kustomize") or shutil.which("devcluster-kubectl")
    if not cmd:
        pytest.fail("Neither kubectl, kustomize, nor devcluster-kubectl found in PATH")
    args = [cmd, "build" if Path(cmd).name == "kustomize" else "kustomize", str(path)]
    result = subprocess.run(
        args,
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


def test_agent_sandbox_add_on_is_vendored_with_the_pinned_release() -> None:
    resources = render(AGENT_SANDBOX)
    manifest_digest = hashlib.sha256((AGENT_SANDBOX / "sandbox.yaml").read_bytes()).hexdigest()
    kustomization = (AGENT_SANDBOX / "kustomization.yaml").read_text()

    # The pinned upstream core release is vendored and the digest records what
    # was vendored; the kustomization must not restate or override the image.
    assert "releases/download/v1.0.10/sandbox.yaml" in kustomization
    assert manifest_digest in kustomization
    assert "registry.k8s.io" not in kustomization
    assert "image:" not in kustomization

    assert "name: sandboxes.agents.x-k8s.io" in resources
    assert "image: registry.k8s.io/agent-sandbox/agent-sandbox-controller:v1.0.10" in resources
    assert "name: agent-sandbox-controller" in resources
    assert "namespace: agent-sandbox-system" in resources
    # The controller owns its own namespace and cluster-scoped resources, so no
    # namespace transformer may pull it into the application namespace.
    assert "\nnamespace:" not in kustomization
    assert "namespace: ai-dev" not in resources


def test_application_stages_do_not_install_the_agent_sandbox_add_on() -> None:
    for resources in (render(K8S_DIR), render(RUNTIME)):
        assert "agent-sandbox-system" not in resources
        assert "sandboxes.agents.x-k8s.io" not in resources


def test_operator_docs_pin_the_agent_sandbox_add_on() -> None:
    k8s_readme = (K8S_DIR / "README.md").read_text()
    cluster_readme = (ROOT / ".config" / "dotfiles" / "README.md").read_text()
    kustomization = (AGENT_SANDBOX / "kustomization.yaml").read_text()
    digest = hashlib.sha256((AGENT_SANDBOX / "sandbox.yaml").read_bytes()).hexdigest()

    assert "## Agent Sandbox (pinned v1.0.10)" in k8s_readme
    assert "releases/download/v1.0.10/sandbox.yaml" in k8s_readme
    assert "agent-sandbox-system" in k8s_readme
    assert "sandbox-with-extensions.yaml" in k8s_readme
    assert "devcluster-kubectl get crd sandboxes.agents.x-k8s.io" in k8s_readme
    assert "pinned `v1.0.10`" in cluster_readme
    assert "Agent Sandbox" in cluster_readme
    # Documentation, stage, and vendored bytes record the same artifact.
    assert digest in k8s_readme
    assert digest in kustomization


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
    for model in (
        "enmaas-opus-5-5",
        "enmaas-sonnet-5-5",
        "enmaas-gpt-6-1-sol",
        "openai-gpt-5-6-terra",
        "enmaas-gpt-6-luna",
        "openai-gpt-5-6-luna",
        "enmaas-glm-5-3",
        "enmaas-deepseek-4-1-flash",
        "gemini",
    ):
        assert f"name: {model}" in config, model
    assert config.count("- type: responses") == 2
    completions_blocks = config.split("- name: ")[1:]
    assert len([block for block in completions_blocks if "- type: completions" in block]) == 3
    assert any(
        block.startswith("enmaas-deepseek-4-1-flash")
        and "model: rits/deepseek-ai/DeepSeek-V4.1-Flash-1017" in block
        for block in completions_blocks
    )
    assert "finalTransformation:" not in config
    assert "- model: enmaas-gpt-6-1-sol" in config
    assert "- model: openai-gpt-5-6-terra" in config
    assert config.count("- model: openai-gpt-5-6-luna") == 1
    assert config.count("- model: enmaas-gpt-6-luna") == 1
    assert config.count("- model: enmaas-glm-5-3") == 1
    assert config.count("- model: enmaas-sonnet-5-5") == 1
    assert config.count("- model: enmaas-deepseek-4-1-flash") == 1
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
    for model in ("gpt-5.6-terra", "gpt-6.1-sol", "gpt-5.6-luna", "gpt-6-luna", "claude-opus-5-5", "rits/zai-org/glm-5-3", "claude-sonnet-5-5", "gemini-3.8-flash"):
        assert model in catalog_text
        assert any(model in provider.get("models", {}) for provider in catalog["providers"].values())
    assert "catalog-overlay.json" in kustomization
    assert "agentgateway-config" in kustomization


ILLUSIONIST_UPSTREAM_MODEL = "rits/deepseek-ai/DeepSeek-V4.1-Flash-1017"


def test_agentgateway_catalog_prices_only_illusionist_upstream_as_free() -> None:
    catalog = json.loads((BASE / "catalog-overlay.json").read_text())

    custom_models = catalog["providers"]["custom"]["models"]
    assert custom_models[ILLUSIONIST_UPSTREAM_MODEL]["rates"] == {
        "input": "0",
        "output": "0",
        "cacheRead": "0",
        "cacheWrite": "0",
    }
    assert [name for name in custom_models if "deepseek" in name.lower()] == [
        ILLUSIONIST_UPSTREAM_MODEL
    ]
    # Existing priced routes are unchanged.
    assert custom_models["gpt-6-luna"]["rates"] == {
        "input": "0.10",
        "output": "0.50",
        "cacheRead": "0.01",
        "cacheWrite": "0.125",
    }
    assert catalog["providers"]["anthropic"]["models"]["rits/zai-org/glm-5-3"][
        "rates"
    ] == {"input": "0", "output": "0", "cacheRead": "0", "cacheWrite": "0"}


def test_mlflow_model_catalog_prices_illusionist_alias_as_free() -> None:
    catalog_path = BASE / "mlflow-model-catalog" / "agentgateway.json"
    catalog = json.loads(catalog_path.read_text())

    assert catalog_path.is_file()
    assert catalog["schema_version"] == "1"
    assert list(catalog["models"]) == ["illusionist"]
    illusionist = catalog["models"]["illusionist"]
    assert illusionist["mode"] == "chat"
    assert illusionist["pricing"] == {
        "input_per_million_tokens": 0.0,
        "output_per_million_tokens": 0.0,
        "cache_read_per_million_tokens": 0.0,
        "cache_write_per_million_tokens": 0.0,
    }


def test_mlflow_model_catalog_is_mounted_with_agentgateway_provider_file() -> None:
    kustomization = (BASE / "kustomization.yaml").read_text()
    deployment = (BASE / "mlflow.yaml").read_text()

    assert "name: mlflow-model-catalog" in kustomization
    assert "mlflow-model-catalog/agentgateway.json" in kustomization
    assert "name: MLFLOW_MODEL_CATALOG_URI" in deployment
    assert "value: file:///etc/mlflow/model-catalog" in deployment
    assert "mountPath: /etc/mlflow/model-catalog" in deployment
    assert "readOnly: true" in deployment
    assert "name: mlflow-model-catalog" in deployment
    # Preserve the existing server, database, and storage boundary.
    assert "--backend-store-uri" in deployment
    assert "sqlite:////mlflow/mlflow.db" in deployment
    assert "claimName: mlflow-pvc" in deployment


def test_opencode_agents_reference_only_agentgateway_models() -> None:
    config = json.loads((ROOT / ".config" / "opencode" / "opencode.jsonc").read_text())
    agents = ROOT / ".config" / "opencode" / "agents"

    assert config["model"] == "agentgateway/architect"
    assert config["default_agent"] == "orchestrator"
    assert set(config["providers"]) == {"agentgateway", "agentgateway-gemini"}
    agentgateway = config["providers"]["agentgateway"]
    assert agentgateway["package"] == "@opencode/ai/providers/openai-compatible"
    assert agentgateway["settings"]["baseURL"] == "{env:AGENTGATEWAY_BASE_URL}"
    assert set(agentgateway["models"]) == {
        "omnipower",
        "architect",
        "worker",
        "illusionist",
        "reviewer",
        "spade",
    }
    architect = agentgateway["models"]["architect"]
    assert architect["modelID"] == "architect"
    assert architect["package"] == "@opencode/ai/providers/openai-compatible/responses"
    assert architect["settings"]["reasoningEffort"] == "medium"
    assert {variant["id"] for variant in architect["variants"]} == {
        "low",
        "medium",
        "high",
        "xhigh",
    }
    assert architect["capabilities"]["reasoning"] == {
        "supported": True,
        "effort": ["low", "medium", "high", "xhigh"],
    }
    assert architect["limit"]["context"] == 350000
    illusionist = agentgateway["models"]["illusionist"]
    assert illusionist["modelID"] == "illusionist"
    assert "DeepSeek" in illusionist["name"]
    gemini_provider = config["providers"]["agentgateway-gemini"]
    assert gemini_provider["package"] == "@opencode/ai/providers/google"
    assert gemini_provider["settings"]["baseURL"] == "{env:AGENTGATEWAY_GEMINI_BASE_URL}"
    assert gemini_provider["headers"] == {
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
    ]
    for agent in agents.glob("*.md"):
        frontmatter = agent.read_text().split("---", 2)[1]
        model = next(line.split(":", 1)[1].strip() for line in frontmatter.splitlines() if line.startswith("model:"))
        assert model in {
            "agentgateway/architect",
            "agentgateway/architect#high",
            "agentgateway/illusionist",
            "agentgateway/omnipower",
            "agentgateway/reviewer",
            "agentgateway/worker",
        }

    assert "model: agentgateway/architect" in (agents / "orchestrator.md").read_text()
    assert "model: agentgateway/architect" in (agents / "planner.md").read_text()
    orchestrator = (agents / "orchestrator.md").read_text()
    assert 'resource: "implement-local"' not in orchestrator
    assert 'resource: "implement-maas"' not in orchestrator


def test_telemetry_routes_to_fixed_experiment_23() -> None:
    config = json.loads((ROOT / ".config" / "opencode" / "opencode.jsonc").read_text())
    gateway_config = (BASE / "agentgateway.yaml").read_text()
    gateway_deployment = (BASE / "agentgateway-deployment.yaml").read_text()
    env_example = (K8S_DIR / "env.example").read_text()

    otel_plugin = next(
        plugin
        for plugin in config["plugins"]
        if isinstance(plugin, dict) and plugin.get("package") == "@devtheops/opencode-plugin-otel"
    )
    assert otel_plugin["options"]["otlpHeaders"] == "x-mlflow-experiment-id=23"

    # The gateway header stays secret-sourced: 23 is provisioned into
    # agentgateway-secrets, never hardcoded into the manifest.
    assert 'x-mlflow-experiment-id: "$MLFLOW_EXPERIMENT_ID"' in gateway_config
    assert 'x-mlflow-experiment-id: "23"' not in gateway_config
    assert "x-mlflow-experiment-id: 23" not in gateway_config
    assert "name: MLFLOW_EXPERIMENT_ID" in gateway_deployment
    assert "agentgateway-secrets" in gateway_deployment

    # The provisioning template documents the agreed target and the manual step.
    assert "MLFLOW_EXPERIMENT_ID=23" in env_example


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
